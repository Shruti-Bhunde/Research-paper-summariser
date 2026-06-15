import json
import os
import shutil
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
from database import get_connection

app = FastAPI

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





def _load_paper_record(user_id: str, summary_id: str):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT
        p.*,
        s.summary_json
    FROM papers p
    JOIN summaries s
        ON p.summary_id = s.summary_id
    WHERE p.summary_id = %s
      AND p.google_sub = %s
    """, (summary_id, user_id))

    record = cursor.fetchone()

    if not record:
        cursor.close()
        conn.close()
        raise HTTPException(
            status_code=404,
            detail="Paper not found for this account."
        )

    # Retrieve all chat logs associated with this paper from database
    cursor.execute("""
    SELECT role, content
    FROM chats
    WHERE summary_id = %s
    ORDER BY id ASC
    """, (summary_id,))
    chats = cursor.fetchall()

    cursor.close()
    conn.close()

    record["summary"] = json.loads(record["summary_json"])

    record["metadata"] = {
        "title": record["title"],
        "author": record["author"],
        "page_count": record["page_count"]
    }
    
    record["conversation_history"] = chats
    record["conversation_memory"] = _conversation_to_text(chats)

    return record


def _list_user_records(user_id: str):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT
        p.*,
        (SELECT COUNT(*) FROM chats c WHERE c.summary_id = p.summary_id) as chat_turns
    FROM papers p
    WHERE p.google_sub = %s
    ORDER BY p.updated_at DESC
    """, (user_id,))

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return rows


def _conversation_to_text(conversation_history: List[Dict[str, Any]], limit: int = 14) -> str:
    recent_turns = conversation_history[-limit:]
    if not recent_turns:
        return "No prior conversation."

    return "\n".join(
        f"{'User' if turn.get('role') == 'user' else 'Assistant'}: {turn.get('content', '')}"
        for turn in recent_turns
    )





def _serialize_paper_list_item(record: Dict[str, Any]) -> Dict[str, Any]:
    summary = record.get("summary", {})
    metadata = record.get("metadata", {})
    chat_turns = record.get("chat_turns") or 0
    return {
        "summary_id": record["summary_id"],
        "title": summary.get("title") or metadata.get("title") or record.get("title") or "Untitled Paper",
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "author": metadata.get("author", "Unknown") or record.get("author") or "Unknown",
        "page_count": metadata.get("page_count", 0) or record.get("page_count") or 0,
        "original_filename": record.get("original_filename", ""),
        "chat_turns": chat_turns,
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
    # create_user(user)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT IGNORE INTO users
    (
        google_sub,
        email,
        name,
        picture
    )
    VALUES (%s,%s,%s,%s)
    """,
    (
        user["sub"],
        user["email"],
        user["name"],
        user["picture"]
    ))

    conn.commit()
    conn.close()
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


@app.delete("/api/papers/{summary_id}")
async def delete_paper(summary_id: str, authorization: Optional[str] = Header(default=None)):
    """Delete a paper, its summary, all chat history, and the associated PDF files."""
    user = _get_user_from_authorization(authorization)

    # Verify the paper belongs to this user before deleting anything
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT summary_id FROM papers WHERE summary_id = %s AND google_sub = %s",
        (summary_id, user["sub"]),
    )
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Paper not found for this account.")

    # Delete in FK-safe order: chats → summaries → papers
    cursor.execute("DELETE FROM chats WHERE summary_id = %s", (summary_id,))
    cursor.execute("DELETE FROM summaries WHERE summary_id = %s", (summary_id,))
    cursor.execute("DELETE FROM papers WHERE summary_id = %s AND google_sub = %s", (summary_id, user["sub"]))
    conn.commit()
    cursor.close()
    conn.close()

    # Remove on-disk files (original PDF, summary PDF, etc.)
    paper_dir = _safe_paper_dir(user["sub"], summary_id)
    if paper_dir.exists():
        shutil.rmtree(paper_dir, ignore_errors=True)

    return {"success": True, "deleted": summary_id}


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

    pdf_info = process_pdf(str(original_pdf_path), original_filename=file.filename)
    if not pdf_info["is_valid"]:
        raise HTTPException(status_code=400, detail=pdf_info["error"])

    document_text = extract_pdf_text(str(original_pdf_path))
    document_chunks = build_pdf_chunks(str(original_pdf_path))

    ai_summary = summarize_pdf(str(original_pdf_path))
    if "error" in ai_summary:
        raise HTTPException(status_code=500, detail=ai_summary["error"])

    # Format the title with the "Summary - " prefix
    raw_title = ai_summary.get("title") or pdf_info["title"]
    if raw_title and not raw_title.startswith("Summary - "):
        formatted_title = f"Summary - {raw_title}"
    else:
        formatted_title = raw_title or "Untitled Paper"

    ai_summary["title"] = formatted_title
    pdf_info["title"] = formatted_title

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
    conn = get_connection()
    cursor = conn.cursor()

    # Save paper metadata
    cursor.execute("""
    INSERT INTO papers
    (
        summary_id,
        google_sub,
        title,
        author,
        page_count,
        original_filename,
        original_pdf_path,
        summary_pdf_path,
        created_at,
        updated_at
    )
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """,
    (
        summary_id,
        user["sub"],
        pdf_info["title"],
        pdf_info["author"],
        pdf_info["page_count"],
        file.filename,
        str(original_pdf_path),
        str(summary_pdf_path),
        _utc_now(),
        _utc_now()
    ))

    # Save AI summary JSON
    cursor.execute("""
    INSERT INTO summaries
    (
        summary_id,
        summary_json
    )
    VALUES (%s, %s)
    """,
    (
        summary_id,
        json.dumps(ai_summary)
    ))

    conn.commit()
    conn.close()

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

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT role, content
    FROM chats
    WHERE summary_id = %s
    ORDER BY id ASC
    """, (payload.summary_id,))

    conversation_history = cursor.fetchall()

    cursor.close()
    conn.close()
    if payload.history and not conversation_history:
        conversation_history = [
            {"role": item.role, "content": item.content}
            for item in payload.history
        ]

    conversation_history.append({"role": "user", "content": payload.message})
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO chats
    (
        summary_id,
        role,
        content
    )
    VALUES (%s,%s,%s)
    """,
    (
        payload.summary_id,
        "user",
        payload.message
    ))

    conn.commit()
    cursor.close()
    conn.close()

    pdf_path = record.get("original_pdf_path")
    chunks = build_pdf_chunks(pdf_path) if pdf_path else []
    relevant_chunks = retrieve_relevant_chunks(payload.message, chunks, top_k=4)
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
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO chats
        (
            summary_id,
            role,
            content
        )
        VALUES (%s,%s,%s)
        """,
        (
            payload.summary_id,
            "assistant",
            assistant_reply
        ))

        conn.commit()
        cursor.close()
        conn.close()

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

        return {
            "reply": assistant_reply,
            "sources": sources,
            "conversation_history": conversation_history,
            "conversation_memory": record["conversation_memory"],
            "paper": _serialize_paper_detail(record),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat generation failed: {exc}") from exc
