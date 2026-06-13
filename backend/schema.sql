-- Active: 1771502508247@@127.0.0.1@3306@research_summarizer
CREATE DATABASE IF NOT EXISTS research_summarizer;
USE research_summarizer;

CREATE TABLE users (
    google_sub VARCHAR(255) PRIMARY KEY,
    email VARCHAR(255),
    name VARCHAR(255),
    picture TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE papers (
    summary_id VARCHAR(36) PRIMARY KEY,

    google_sub VARCHAR(255) NOT NULL,

    title VARCHAR(1000),
    author VARCHAR(500),
    page_count INT,

    original_filename VARCHAR(500),

    original_pdf_path TEXT,
    summary_pdf_path TEXT,

    created_at DATETIME,
    updated_at DATETIME,

    FOREIGN KEY (google_sub)
        REFERENCES users(google_sub)
        ON DELETE CASCADE
);

CREATE TABLE summaries (
    summary_id VARCHAR(36) PRIMARY KEY,

    summary_json JSON,

    FOREIGN KEY (summary_id)
        REFERENCES papers(summary_id)
        ON DELETE CASCADE
);

CREATE TABLE chats (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,

    summary_id VARCHAR(36) NOT NULL,

    role ENUM('user','assistant') NOT NULL,

    content LONGTEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (summary_id)
        REFERENCES papers(summary_id)
        ON DELETE CASCADE
);