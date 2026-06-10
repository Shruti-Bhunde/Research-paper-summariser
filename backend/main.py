import io
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from ai_summarizer import summarize_pdf
from db import (
    create_paper,
    ensure_schema,
    get_paper_for_user,
    get_user_by_sub,
    list_papers_for_user,
    update_paper_conversation,
    upsert_user,
)
from pdf_generator import generate_summary_pdf
from pdf_processor import build_pdf_chunks, extract_pdf_text, process_pdf, retrieve_relevant_chunks

app = FastAPI(
    title="Research Paper Summarizer AI API",
    description="Backend API for uploading research papers, extracting summaries using Gemini, and exporting report PDFs.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GoogleAuthRequest(BaseModel):
    credential: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    sources: List[Dict[str, Any]] = Field(default_factory=list)


class ChatRequest(BaseModel):
    summary_id: str
    message: str
    history: List[ChatMessage] = Field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_google_user_from_token(credential: str) -> Dict[str, str]:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_ID is missing. Add it to backend/.env before using Google login.",
        )

    try:
        payload = google_id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            client_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Google login verification failed: {exc}") from exc

    return {
        "sub": payload["sub"],
        "email": payload.get("email", ""),
        "name": payload.get("name") or payload.get("email") or "Google User",
        "picture": payload.get("picture", ""),
    }


def _get_user_from_authorization(authorization: Optional[str]) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Google login token.")

    credential = authorization.split(" ", 1)[1].strip()
    user = upsert_user(_load_google_user_from_token(credential))
    return {
        "id": user["id"],
        "sub": user["google_sub"],
        "email": user["email"],
        "name": user["name"],
        "picture": user.get("picture", ""),
    }


def _normalize_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    for turn in history:
        normalized.append(
            {
                "role": turn.get("role", "user"),
                "content": turn.get("content", ""),
                "sources": turn.get("sources", []),
            }
        )
    return normalized


def _conversation_to_text(conversation_history: List[Dict[str, Any]], limit: int = 14) -> str:
    recent_turns = conversation_history[-limit:]
    if not recent_turns:
        return "No prior conversation."

    return "\n".join(
        f"{'User' if turn.get('role') == 'user' else 'Assistant'}: {turn.get('content', '')}"
        for turn in recent_turns
    )


def _paper_list_item(record: Dict[str, Any]) -> Dict[str, Any]:
    summary = record.get("summary_data", {})
    return {
        "summary_id": record["summary_id"],
        "title": summary.get("title") or record.get("title") or "Untitled Paper",
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "author": record.get("author", "Unknown"),
        "page_count": record.get("page_count", 0),
        "original_filename": record.get("original_filename", ""),
        "chat_turns": len(record.get("conversation_history") or []),
        "summary_pdf_url": f"/api/papers/{record['summary_id']}/pdf?kind=summary",
        "original_pdf_url": f"/api/papers/{record['summary_id']}/pdf?kind=original",
    }


def _paper_detail(record: Dict[str, Any]) -> Dict[str, Any]:
    payload = _paper_list_item(record)
    payload.update(
        {
            "summary": record.get("summary_data", {}),
            "metadata": {
                "title": record.get("title", ""),
                "author": record.get("author", "Unknown"),
                "page_count": record.get("page_count", 0),
            },
            "conversation_history": record.get("conversation_history") or [],
            "conversation_memory": record.get("conversation_memory") or "",
        }
    )
    return payload


def _blob_response(pdf_bytes: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.on_event("startup")
def _startup() -> None:
    ensure_schema()


@app.post("/api/auth/google")
async def auth_google(payload: GoogleAuthRequest):
    user = upsert_user(_load_google_user_from_token(payload.credential))
    papers = [_paper_list_item(record) for record in list_papers_for_user(user["id"])]
    return {
        "user": {
            "sub": user["google_sub"],
            "email": user["email"],
            "name": user["name"],
            "picture": user.get("picture", ""),
        },
        "papers": papers,
    }


@app.get("/api/me")
async def get_me(authorization: Optional[str] = Header(default=None)):
    user = _get_user_from_authorization(authorization)
    papers = [_paper_list_item(record) for record in list_papers_for_user(user["id"])]
    return {"user": user, "papers": papers}


@app.get("/api/papers")
async def list_papers(authorization: Optional[str] = Header(default=None)):
    user = _get_user_from_authorization(authorization)
    return {"papers": [_paper_list_item(record) for record in list_papers_for_user(user["id"])]}


@app.get("/api/papers/{summary_id}")
async def get_paper(summary_id: str, authorization: Optional[str] = Header(default=None)):
    user = _get_user_from_authorization(authorization)
    record = get_paper_for_user(user["id"], summary_id)
    if not record:
        raise HTTPException(status_code=404, detail="Paper not found for this account.")
    return {"paper": _paper_detail(record)}


@app.get("/api/papers/{summary_id}/pdf")
async def get_paper_pdf(
    summary_id: str,
    kind: Literal["original", "summary"] = "summary",
    authorization: Optional[str] = Header(default=None),
):
    user = _get_user_from_authorization(authorization)
    record = get_paper_for_user(user["id"], summary_id)
    if not record:
        raise HTTPException(status_code=404, detail="Paper not found for this account.")

    pdf_bytes = record["summary_pdf"] if kind == "summary" else record["original_pdf"]
    clean_title = (record.get("title") or record.get("original_filename") or "paper").replace(" ", "_")
    filename = f"{clean_title}_{kind}.pdf"
    return _blob_response(pdf_bytes, filename)


@app.post("/api/summarize")
async def summarize_endpoint(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_user_from_authorization(authorization)

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    uploaded_pdf_bytes = await file.read()
    if len(uploaded_pdf_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="PDF file exceeds the 20 MB size limit.")

    summary_id = str(uuid.uuid4())

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
        temp_pdf.write(uploaded_pdf_bytes)
        temp_pdf_path = temp_pdf.name

    try:
        pdf_info = process_pdf(temp_pdf_path)
        if not pdf_info["is_valid"]:
            raise HTTPException(status_code=400, detail=pdf_info["error"])

        document_text = extract_pdf_text(temp_pdf_path)
        document_chunks = build_pdf_chunks(temp_pdf_path)
        ai_summary = summarize_pdf(temp_pdf_path)
        if "error" in ai_summary:
            raise HTTPException(status_code=500, detail=ai_summary["error"])

        if not ai_summary.get("title"):
            ai_summary["title"] = pdf_info["title"]

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as summary_pdf_temp:
            summary_pdf_path = summary_pdf_temp.name

        try:
            generate_summary_pdf(ai_summary, file.filename, summary_pdf_path)
            with open(summary_pdf_path, "rb") as summary_pdf_handle:
                summary_pdf_bytes = summary_pdf_handle.read()
        finally:
            if os.path.exists(summary_pdf_path):
                os.remove(summary_pdf_path)

        create_paper(
            user_id=user["id"],
            summary_id=summary_id,
            original_filename=file.filename,
            title=pdf_info["title"],
            author=pdf_info["author"],
            page_count=pdf_info["page_count"],
            original_pdf=uploaded_pdf_bytes,
            summary_pdf=summary_pdf_bytes,
            summary_data=ai_summary,
            document_text=document_text,
            document_chunks=document_chunks,
            conversation_history=[],
            conversation_memory="",
        )

        record = get_paper_for_user(user["id"], summary_id)
        return {"paper": _paper_detail(record)}
    finally:
        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)


@app.post("/api/chat")
async def chat_endpoint(
    payload: ChatRequest,
    authorization: Optional[str] = Header(default=None),
):
    user = _get_user_from_authorization(authorization)
    record = get_paper_for_user(user["id"], payload.summary_id)
    if not record:
        raise HTTPException(status_code=404, detail="Paper not found for this account.")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        raise HTTPException(status_code=500, detail="Gemini API Key is missing. Please add GEMINI_API_KEY to your backend/.env file.")

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-2.5-flash")

    conversation_history = record.get("conversation_history") or []
    if not conversation_history and payload.history:
      conversation_history = _normalize_history([item.model_dump() for item in payload.history])

    conversation_history.append({"role": "user", "content": payload.message, "sources": []})

    document_chunks = record.get("document_chunks") or []
    relevant_chunks = retrieve_relevant_chunks(payload.message, document_chunks, top_k=4)
    retrieved_context_lines = [
        f"[Chunk {chunk['chunk_id']} | Page {chunk['page']} | Score {chunk['score']:.3f}] {chunk['text']}"
        for chunk in relevant_chunks
    ]

    prompt = f"""
You are a warm, helpful research-paper chatbot.
Use the retrieved paper chunks, the paper summary, and the remembered conversation.
Answer in simple language that is easy to scan.
Prefer this structure when it fits:
Direct answer:
- ...
Key points:
- ...
Evidence from the paper:
- ...
If the user asks a follow-up, keep the thread connected to what was said before.
If the evidence is weak or missing, say that clearly instead of guessing.
When relevant, cite sources inline like [Chunk 2].

Paper title: {record.get("title", "Unknown")}
Paper author: {record.get("author", "Unknown")}
Page count: {record.get("page_count", 0)}

Paper summary:
{record.get("summary_data", {})}

Top retrieved chunks:
{chr(10).join(retrieved_context_lines) if retrieved_context_lines else "No highly relevant chunks were found."}

Conversation memory:
{_conversation_to_text(conversation_history)}

User question:
{payload.message}
""".strip()

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.25,
                "max_output_tokens": 900,
            },
        )
        assistant_reply = response.text.strip()
        sources = [
            {
                "chunk_id": chunk["chunk_id"],
                "page": chunk["page"],
                "score": round(chunk["score"], 3),
                "snippet": chunk["text"][:260],
            }
            for chunk in relevant_chunks
        ]

        conversation_history.append(
            {
                "role": "assistant",
                "content": assistant_reply,
                "sources": sources,
            }
        )
        conversation_memory = _conversation_to_text(conversation_history, limit=16)
        update_paper_conversation(user["id"], payload.summary_id, conversation_history, conversation_memory)

        record = get_paper_for_user(user["id"], payload.summary_id)
        return {
            "reply": assistant_reply,
            "sources": sources,
            "conversation_history": record.get("conversation_history", []),
            "conversation_memory": record.get("conversation_memory", ""),
            "paper": _paper_detail(record),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat generation failed: {exc}") from exc
