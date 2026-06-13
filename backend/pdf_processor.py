import os
import math
import re
from collections import Counter
import fitz  # PyMuPDF

def process_pdf(file_path: str, original_filename: str = None) -> dict:
    """
    Validates a local PDF file, checks page count, and extracts document metadata.
    
    Inputs:
        file_path (str): Absolute path to the PDF file.
        original_filename (str, optional): The original name of the uploaded file.
        
    Outputs:
        dict: A dictionary containing:
            - is_valid (bool): True if PDF is successfully opened.
            - page_count (int): Total number of pages.
            - title (str): PDF metadata title (or filename if empty).
            - author (str): PDF metadata author.
            - subject (str): PDF metadata subject.
            - error (str): Error message if validation failed.
    """
    result = {
        "is_valid": False,
        "page_count": 0,
        "title": "",
        "author": "Unknown",
        "subject": "",
        "error": None
    }
    
    if not os.path.exists(file_path):
        result["error"] = f"File not found at path: {file_path}"
        return result
        
    try:
        # Open PDF file using PyMuPDF
        doc = fitz.open(file_path)
        result["is_valid"] = True
        result["page_count"] = len(doc)
        
        # Read metadata
        meta = doc.metadata or {}
        
        # Get title from metadata or fallback to original_filename / basename
        title = meta.get("title", "").strip()
        if not title:
            fallback_source = original_filename if original_filename else os.path.basename(file_path)
            title = os.path.splitext(fallback_source)[0]
            # Clean up underscores and dashes in title for display
            title = title.replace("_", " ").replace("-", " ").title()
            
        result["title"] = title
        result["author"] = meta.get("author", "").strip() or "Unknown"
        result["subject"] = meta.get("subject", "").strip() or ""
        
        # Close document
        doc.close()
        
    except Exception as e:
        result["is_valid"] = False
        result["error"] = f"Failed to parse PDF: {str(e)}"
        
    return result


def extract_pdf_text(file_path: str, max_chars: int = 30000, max_pages: int | None = None) -> str:
    """
    Extracts readable text from a PDF file for downstream summarization and chat.

    Inputs:
        file_path (str): Absolute path to the PDF file.
        max_chars (int): Hard character cap to keep prompts compact.
        max_pages (int | None): Optional page limit for extraction.

    Outputs:
        str: Extracted text, truncated to the configured maximum length.
    """
    if not os.path.exists(file_path):
        return ""

    collected_text = []
    total_chars = 0

    try:
        doc = fitz.open(file_path)
        page_limit = min(len(doc), max_pages) if max_pages is not None else len(doc)

        for page_index in range(page_limit):
            page_text = doc[page_index].get_text("text").strip()
            if not page_text:
                continue

            collected_text.append(f"\n\n[Page {page_index + 1}]\n{page_text}")
            total_chars += len(page_text)
            if total_chars >= max_chars:
                break

        doc.close()
    except Exception:
        return ""

    text = "".join(collected_text).strip()
    return text[:max_chars]


def build_pdf_chunks(
    file_path: str,
    max_chars: int = 30000,
    chunk_words: int = 180,
    overlap_words: int = 40
) -> list[dict]:
    """
    Splits PDF text into overlapping chunks for retrieval-augmented generation.

    Outputs:
        list[dict]: Each chunk includes chunk_id, page, text, and word_count.
    """
    if not os.path.exists(file_path):
        return []

    chunks: list[dict] = []
    chunk_id = 0

    try:
        doc = fitz.open(file_path)
        for page_index in range(len(doc)):
            if sum(len(chunk["text"]) for chunk in chunks) >= max_chars:
                break

            page_text = doc[page_index].get_text("text").strip()
            if not page_text:
                continue

            words = page_text.split()
            if not words:
                continue

            step = max(1, chunk_words - overlap_words)
            for start_index in range(0, len(words), step):
                chunk_words_list = words[start_index:start_index + chunk_words]
                if not chunk_words_list:
                    continue

                chunk_text = " ".join(chunk_words_list).strip()
                if not chunk_text:
                    continue

                chunks.append({
                    "chunk_id": chunk_id,
                    "page": page_index + 1,
                    "text": chunk_text,
                    "word_count": len(chunk_words_list)
                })
                chunk_id += 1

                if sum(len(chunk["text"]) for chunk in chunks) >= max_chars:
                    break

        doc.close()
    except Exception:
        return []

    return chunks


def retrieve_relevant_chunks(query: str, chunks: list[dict], top_k: int = 4) -> list[dict]:
    """
    Retrieves the most relevant PDF chunks for a user query using TF-IDF style scoring.
    """
    if not query.strip() or not chunks:
        return []

    def tokenize(text: str) -> list[str]:
        return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2]

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    chunk_tokens = [tokenize(chunk["text"]) for chunk in chunks]
    document_frequency = Counter()
    for tokens in chunk_tokens:
        document_frequency.update(set(tokens))

    total_chunks = len(chunks)
    query_terms = Counter(query_tokens)
    scored_chunks = []

    for chunk, tokens in zip(chunks, chunk_tokens):
        if not tokens:
            continue

        chunk_term_frequency = Counter(tokens)
        score = 0.0
        for term, q_freq in query_terms.items():
            tf = chunk_term_frequency.get(term, 0)
            if not tf:
                continue
            idf = math.log((1 + total_chunks) / (1 + document_frequency.get(term, 0))) + 1.0
            score += (tf / len(tokens)) * idf * q_freq

        if score > 0:
            scored_chunks.append({
                **chunk,
                "score": score,
            })

    scored_chunks.sort(key=lambda item: item["score"], reverse=True)
    return scored_chunks[:top_k]
