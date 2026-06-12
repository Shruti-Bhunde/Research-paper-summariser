import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from ai_summarizer import summarize_pdf
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

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


class GoogleAuthRequest(BaseModel):
    credential: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    summary_id: str
    message: str
    history: List[ChatMessage] = Field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_user_dir(user_id: str) -> Path:
    return STORAGE_DIR / user_id


def _safe_paper_dir(user_id: str, summary_id: str) -> Path:
    return _safe_user_dir(user_id) / summary_id


def _paper_record_path(user_id: str, summary_id: str) -> Path:
    return _safe_paper_dir(user_id, summary_id) / "record.json"


def _paper_file_path(user_id: str, summary_id: str, kind: Literal["original", "summary"]) -> Path:
    filename = "original.pdf" if kind == "original" else "summary.pdf"
    return _safe_paper_dir(user_id, summary_id) / filename


def _paper_pdf_url(summary_id: str, kind: Literal["original", "summary"]) -> str:
    return f"/papers/{summary_id}/pdf?kind={kind}"


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


def _get_user_from_authorization(authorization: Optional[str]) -> Dict[str, str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Google login token.")

    credential = authorization.split(" ", 1)[1].strip()
    return _load_google_user_from_token(credential)


def _read_record_file(record_path: Path) -> Optional[Dict[str, Any]]:
    if not record_path.exists():
        return None
    try:
        with record_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _save_record_file(record: Dict[str, Any]) -> None:
    record_path = Path(record["record_path"])
    record_path.parent.mkdir(parents=True, exist_ok=True)
    with record_path.open("w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, ensure_ascii=False)


def _load_paper_record(user_id: str, summary_id: str) -> Dict[str, Any]:
    record = _read_record_file(_paper_record_path(user_id, summary_id))
    if not record:
        raise HTTPException(status_code=404, detail="Paper not found for this account.")
    return record


def _list_user_records(user_id: str) -> List[Dict[str, Any]]:
    user_dir = _safe_user_dir(user_id)
    if not user_dir.exists():
        return []

    records: List[Dict[str, Any]] = []
    for paper_dir in user_dir.iterdir():
        if not paper_dir.is_dir():
            continue
        record = _read_record_file(paper_dir / "record.json")
        if record:
            records.append(record)

    records.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    return records


def _conversation_to_text(conversation_history: List[Dict[str, Any]], limit: int = 14) -> str:
    recent_turns = conversation_history[-limit:]
    if not recent_turns:
        return "No prior conversation."

    return "\n".join(
        f"{'User' if turn.get('role') == 'user' else 'Assistant'}: {turn.get('content', '')}"
        for turn in recent_turns
    )


def _store_paper_record(record: Dict[str, Any]) -> None:
    record["updated_at"] = _utc_now()
    _save_record_file(record)


def _serialize_paper_list_item(record: Dict[str, Any]) -> Dict[str, Any]:
    summary = record.get("summary", {})
    metadata = record.get("metadata", {})
    conversation_history = record.get("conversation_history", [])
    return {
        "summary_id": record["summary_id"],
        "title": summary.get("title") or metadata.get("title") or "Untitled Paper",
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "author": metadata.get("author", "Unknown"),
        "page_count": metadata.get("page_count", 0),
        "original_filename": record.get("original_filename", ""),
        "chat_turns": len(conversation_history),
        "summary_pdf_url": _paper_pdf_url(record["summary_id"], "summary"),
        "original_pdf_url": _paper_pdf_url(record["summary_id"], "original"),
    }


def _serialize_paper_detail(record: Dict[str, Any]) -> Dict[str, Any]:
    payload = _serialize_paper_list_item(record)
    payload.update(
        {
            "summary": record.get("summary", {}),
            "metadata": record.get("metadata", {}),
            "conversation_history": record.get("conversation_history", []),
            "conversation_memory": record.get("conversation_memory", ""),
        }
    )
    return payload


@app.post("/api/auth/google")
async def auth_google(payload: GoogleAuthRequest):
    user = _load_google_user_from_token(payload.credential)
    papers = [_serialize_paper_list_item(record) for record in _list_user_records(user["sub"])]
    return {"user": user, "papers": papers}


@app.get("/api/me")
async def get_me(authorization: Optional[str] = Header(default=None)):
    user = _get_user_from_authorization(authorization)
    papers = [_serialize_paper_list_item(record) for record in _list_user_records(user["sub"])]
    return {"user": user, "papers": papers}


@app.get("/api/papers")
async def list_papers(authorization: Optional[str] = Header(default=None)):
    user = _get_user_from_authorization(authorization)
    return {"papers": [_serialize_paper_list_item(record) for record in _list_user_records(user["sub"])]}


@app.get("/api/papers/{summary_id}")
async def get_paper(summary_id: str, authorization: Optional[str] = Header(default=None)):
    user = _get_user_from_authorization(authorization)
    record = _load_paper_record(user["sub"], summary_id)
    return {"paper": _serialize_paper_detail(record)}


@app.get("/api/papers/{summary_id}/pdf")
async def get_paper_pdf(
    summary_id: str,
    kind: Literal["original", "summary"] = "summary",
    authorization: Optional[str] = Header(default=None),
):
    user = _get_user_from_authorization(authorization)
    record = _load_paper_record(user["sub"], summary_id)
    pdf_path = _paper_file_path(user["sub"], summary_id, kind)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Requested PDF was not found.")

    clean_title = record.get("metadata", {}).get("title") or record.get("original_filename", "paper")
    clean_title = clean_title.replace(" ", "_").replace("/", "_")
    filename = f"{clean_title}_{kind}.pdf"

    return FileResponse(path=str(pdf_path), media_type="application/pdf", filename=filename)


@app.post("/api/summarize")
async def summarize_endpoint(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(default=None),
):
    user = _get_user_from_authorization(authorization)

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    summary_id = str(uuid.uuid4())
    paper_dir = _safe_paper_dir(user["sub"], summary_id)
    paper_dir.mkdir(parents=True, exist_ok=True)

    original_pdf_path = _paper_file_path(user["sub"], summary_id, "original")
    summary_pdf_path = _paper_file_path(user["sub"], summary_id, "summary")
    record_path = _paper_record_path(user["sub"], summary_id)

    try:
        with original_pdf_path.open("wb") as buffer:
            total_size = 0
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > 20 * 1024 * 1024:
                    raise HTTPException(status_code=400, detail="PDF file exceeds the 20 MB size limit.")
                buffer.write(chunk)
    except HTTPException:
        if paper_dir.exists():
            for child in paper_dir.iterdir():
                try:
                    if child.is_file():
                        child.unlink()
                except Exception:
                    pass
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {exc}") from exc

    pdf_info = process_pdf(str(original_pdf_path))
    if not pdf_info["is_valid"]:
        raise HTTPException(status_code=400, detail=pdf_info["error"])

    document_text = extract_pdf_text(str(original_pdf_path))
    document_chunks = build_pdf_chunks(str(original_pdf_path))

    ai_summary = summarize_pdf(str(original_pdf_path))
    if "error" in ai_summary:
        raise HTTPException(status_code=500, detail=ai_summary["error"])

    if "title" not in ai_summary or not ai_summary["title"]:
        ai_summary["title"] = pdf_info["title"]

    try:
        generate_summary_pdf(ai_summary, file.filename, str(summary_pdf_path))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate summary PDF: {exc}") from exc

    paper_record = {
        "summary_id": summary_id,
        "user_id": user["sub"],
        "user_name": user.get("name", ""),
        "user_email": user.get("email", ""),
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "original_filename": file.filename,
        "original_pdf_path": str(original_pdf_path),
        "summary_pdf_path": str(summary_pdf_path),
        "record_path": str(record_path),
        "metadata": {
            "title": pdf_info["title"],
            "author": pdf_info["author"],
            "page_count": pdf_info["page_count"],
        },
        "summary": ai_summary,
        "document_text": document_text,
        "document_chunks": document_chunks,
        "conversation_history": [],
        "conversation_memory": "",
    }
    _store_paper_record(paper_record)

    return {
        "paper": _serialize_paper_detail(paper_record),
    }


@app.post("/api/chat")
async def chat_endpoint(
    payload: ChatRequest,
    authorization: Optional[str] = Header(default=None),
):
    user = _get_user_from_authorization(authorization)
    record = _load_paper_record(user["sub"], payload.summary_id)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        raise HTTPException(status_code=500, detail="Gemini API Key is missing. Please add GEMINI_API_KEY to your backend/.env file.")

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name="gemini-2.5-flash")

    conversation_history = record.get("conversation_history", [])
    if payload.history and not conversation_history:
        conversation_history = [
            {"role": item.role, "content": item.content}
            for item in payload.history
        ]

    conversation_history.append({"role": "user", "content": payload.message})

    relevant_chunks = retrieve_relevant_chunks(payload.message, record.get("document_chunks", []), top_k=4)
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

Paper title: {record.get("metadata", {}).get("title", "Unknown")}
Paper author: {record.get("metadata", {}).get("author", "Unknown")}
Page count: {record.get("metadata", {}).get("page_count", 0)}

Paper summary:
{record.get("summary", {})}

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
        record["conversation_history"] = conversation_history
        record["conversation_memory"] = _conversation_to_text(conversation_history, limit=16)
        _store_paper_record(record)

        return {
            "reply": assistant_reply,
            "sources": sources,
            "conversation_history": conversation_history,
            "conversation_memory": record["conversation_memory"],
            "paper": _serialize_paper_detail(record),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat generation failed: {exc}") from exc
