import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from dotenv import load_dotenv
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", ""),
    "database": os.getenv("MYSQL_DATABASE", "research_summariser"),
    "autocommit": False,
}

_pool: Optional[MySQLConnectionPool] = None


def get_pool() -> MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = MySQLConnectionPool(pool_name="research_summariser_pool", pool_size=5, **MYSQL_CONFIG)
    return _pool


@contextmanager
def get_connection() -> Iterator[mysql.connector.connection.MySQLConnection]:
    connection = get_pool().get_connection()
    try:
        yield connection
    finally:
        connection.close()


def ensure_schema() -> None:
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                google_sub VARCHAR(255) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                picture TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS papers (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT UNSIGNED NOT NULL,
                summary_id VARCHAR(64) NOT NULL UNIQUE,
                original_filename VARCHAR(512) NOT NULL,
                title VARCHAR(512) NOT NULL,
                author VARCHAR(255) NOT NULL,
                page_count INT NOT NULL DEFAULT 0,
                original_pdf LONGBLOB NOT NULL,
                summary_pdf LONGBLOB NOT NULL,
                summary_data JSON NOT NULL,
                document_text LONGTEXT NOT NULL,
                document_chunks JSON NOT NULL,
                conversation_history JSON NOT NULL,
                conversation_memory LONGTEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                CONSTRAINT fk_papers_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_papers_user_created (user_id, created_at),
                INDEX idx_papers_user_updated (user_id, updated_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        connection.commit()


def upsert_user(user: Dict[str, Any]) -> Dict[str, Any]:
    ensure_schema()
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            INSERT INTO users (google_sub, email, name, picture)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              email = VALUES(email),
              name = VALUES(name),
              picture = VALUES(picture)
            """,
            (user["sub"], user.get("email", ""), user.get("name", ""), user.get("picture", "")),
        )
        connection.commit()
        cursor.execute("SELECT * FROM users WHERE google_sub = %s", (user["sub"],))
        return cursor.fetchone()


def get_user_by_sub(google_sub: str) -> Optional[Dict[str, Any]]:
    ensure_schema()
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE google_sub = %s", (google_sub,))
        return cursor.fetchone()


def list_papers_for_user(user_id: int) -> List[Dict[str, Any]]:
    ensure_schema()
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT summary_id, original_filename, title, author, page_count,
                   created_at, updated_at, conversation_history
            FROM papers
            WHERE user_id = %s
            ORDER BY updated_at DESC, created_at DESC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        for row in rows:
            history = row.get("conversation_history") or []
            if isinstance(history, str):
                row["conversation_history"] = json.loads(history)
        return rows


def get_paper_for_user(user_id: int, summary_id: str) -> Optional[Dict[str, Any]]:
    ensure_schema()
    with get_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT *
            FROM papers
            WHERE user_id = %s AND summary_id = %s
            LIMIT 1
            """,
            (user_id, summary_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        for key in ["summary_data", "document_chunks", "conversation_history"]:
            value = row.get(key)
            if isinstance(value, str):
                row[key] = json.loads(value)
        return row


def create_paper(
    user_id: int,
    summary_id: str,
    original_filename: str,
    title: str,
    author: str,
    page_count: int,
    original_pdf: bytes,
    summary_pdf: bytes,
    summary_data: Dict[str, Any],
    document_text: str,
    document_chunks: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]],
    conversation_memory: str,
) -> None:
    ensure_schema()
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO papers (
                user_id, summary_id, original_filename, title, author, page_count,
                original_pdf, summary_pdf, summary_data, document_text,
                document_chunks, conversation_history, conversation_memory
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                summary_id,
                original_filename,
                title,
                author,
                page_count,
                original_pdf,
                summary_pdf,
                json.dumps(summary_data, ensure_ascii=False),
                document_text,
                json.dumps(document_chunks, ensure_ascii=False),
                json.dumps(conversation_history, ensure_ascii=False),
                conversation_memory,
            ),
        )
        connection.commit()


def update_paper_conversation(
    user_id: int,
    summary_id: str,
    conversation_history: List[Dict[str, Any]],
    conversation_memory: str,
) -> None:
    ensure_schema()
    with get_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE papers
            SET conversation_history = %s,
                conversation_memory = %s
            WHERE user_id = %s AND summary_id = %s
            """,
            (json.dumps(conversation_history, ensure_ascii=False), conversation_memory, user_id, summary_id),
        )
        if cursor.rowcount == 0:
            raise RuntimeError("Paper update failed.")
        connection.commit()
