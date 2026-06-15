
# AI Research Paper Summariser


AI Research Paper Summariser is an intelligent web application designed to help researchers, students, and academic enthusiasts understand research papers more efficiently.

Users can upload a research paper in PDF format, after which the system extracts and processes the document to generate a concise, structured summary highlighting the paper's key ideas, methodology, findings, limitations, and future research directions. The generated summary can be downloaded as a PDF for future reference.

To support deeper exploration, the application also provides a dedicated AI-powered chat assistant for each uploaded paper. Using Retrieval-Augmented Generation (RAG), the assistant retrieves relevant information directly from the paper and answers user questions with contextual accuracy. Each paper maintains its own conversational context, allowing users to continue discussions and gain a better understanding of complex research topics.

The project combines Generative AI, document processing, semantic retrieval, conversational memory, and full-stack web development to create an interactive research assistance platform.



## Problem Statement

Research papers are often lengthy and difficult for students to understand quickly. This project reduces the time required to grasp a paper's main ideas by automatically generating concise, structured summaries using generative AI.
## Features

- Google OAuth Authentication
- PDF Upload and Processing
- AI-Generated Research Paper Summaries
- Key Contributions Extraction
- Summary History Management
- Chat Assistant and Chat History
- Responsive User Interface
## Tech Stack

### Frontend
- React
- Vite

### Backend
- FastAPI
- Python

### Database
- MySQL

### AI Integration
- Google Gemini API

### Authentication
- Google OAuth 2.0
## Architecture
<img width="1408" height="768" alt="Gemini_Generated_Image_awor31awor31awor" src="https://github.com/user-attachments/assets/864d5f92-63dd-4118-9e91-02c74722334f" />

## API Endpoints

### Authentication

#### Google Login

```http
POST /api/auth/google
```

Authenticates a user using a Google credential token and creates the user account if it does not already exist.

**Request Body**

| Field      | Type   | Description                   |
| ---------- | ------ | ----------------------------- |
| credential | string | Google OAuth credential token |

**Response**

Returns authenticated user information and previously uploaded papers.

---

### User Information

#### Get Current User

```http
GET /api/me
```

Returns the authenticated user's profile and uploaded papers.

**Headers**

| Header        | Type   | Description  |
| ------------- | ------ | ------------ |
| Authorization | string | Bearer token |

---

### Research Papers

#### Get All Papers

```http
GET /api/papers
```

Returns all papers uploaded by the authenticated user.

**Headers**

| Header        | Type   | Description  |
| ------------- | ------ | ------------ |
| Authorization | string | Bearer token |

---

#### Get Paper Details

```http
GET /api/papers/{summary_id}
```

Returns detailed information for a specific research paper.

**Parameters**

| Parameter  | Type   | Description             |
| ---------- | ------ | ----------------------- |
| summary_id | string | Unique paper identifier |

**Headers**

| Header        | Type   | Description  |
| ------------- | ------ | ------------ |
| Authorization | string | Bearer token |

---

#### Download Paper PDF

```http
GET /api/papers/{summary_id}/pdf
```

Downloads either the original uploaded paper or the generated summary PDF.

**Parameters**

| Parameter  | Type   | Description             |
| ---------- | ------ | ----------------------- |
| summary_id | string | Unique paper identifier |
| kind       | string | original or summary     |

**Headers**

| Header        | Type   | Description  |
| ------------- | ------ | ------------ |
| Authorization | string | Bearer token |

---

#### Delete Paper

```http
DELETE /api/papers/{summary_id}
```

Deletes:

* Paper metadata
* Generated summary
* Chat history
* Stored PDF files

**Parameters**

| Parameter  | Type   | Description             |
| ---------- | ------ | ----------------------- |
| summary_id | string | Unique paper identifier |

**Headers**

| Header        | Type   | Description  |
| ------------- | ------ | ------------ |
| Authorization | string | Bearer token |

---

### AI Summarization

#### Upload and Summarize Research Paper

```http
POST /api/summarize
```

Uploads a PDF research paper and generates:

* Structured AI summary
* Summary PDF
* Metadata extraction
* Vector chunks for retrieval

**Request**

| Field | Type     | Description    |
| ----- | -------- | -------------- |
| file  | PDF File | Research paper |

**Headers**

| Header        | Type   | Description  |
| ------------- | ------ | ------------ |
| Authorization | string | Bearer token |

**Response**

Returns:

* Generated summary
* Paper metadata
* Download links
* Paper identifier

---

### AI Chat Assistant

#### Chat With Research Paper

```http
POST /api/chat
```

Ask questions about a previously uploaded research paper using Retrieval-Augmented Generation (RAG).

The assistant:

* Retrieves relevant document chunks
* Uses conversation history as memory
* Generates context-aware responses
* Returns source references

**Request Body**

| Field      | Type   | Description                   |
| ---------- | ------ | ----------------------------- |
| summary_id | string | Research paper identifier     |
| message    | string | User question                 |
| history    | array  | Previous conversation history |

**Headers**

| Header        | Type   | Description  |
| ------------- | ------ | ------------ |
| Authorization | string | Bearer token |

**Response**

Returns:

* AI-generated answer
* Retrieved source chunks
* Updated conversation history
* Conversation memory

```
```



## Screenshots
<img width="1919" height="1022" alt="image" src="https://github.com/user-attachments/assets/f8a7304b-8a01-4096-a26f-7ec48daafb08" />
<img width="1919" height="1017" alt="image" src="https://github.com/user-attachments/assets/4c9f579a-5438-4d06-9f49-cbe8ac28b1a0" />
<img width="1906" height="1011" alt="image" src="https://github.com/user-attachments/assets/31bd0996-356c-476d-9600-d97bebdc7620" />


## Run Locally

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/research-paper-summariser.git
cd research-paper-summariser
```

---

### 2. Backend Setup

Navigate to the backend folder:

```bash
cd backend
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate the virtual environment:

**Windows**

```bash
venv\Scripts\activate
```

**macOS/Linux**

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Update a `.env.example` file in the backend directory and rename it to `.env`:

Start the FastAPI server:

```bash
uvicorn main:app --reload
```

Backend will run at:

```text
http://localhost:8000
```

---

### 3. Database Setup

Connect your project to your local database and run the queries from `schema.sql` from backend


---

### 4. Frontend Setup

Open a new terminal and navigate to the frontend folder:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Update a `.env.example` file and rename it to `.env`

Note- You will require to generate your own GOOGLE_CLIENT_ID and then paste it.

Start the development server:

```bash
npm run dev
```

Frontend will run at:

```text
http://localhost:5173
```

---




## Usage

    1. Sign in using Google Authentication.
    2. Upload a research paper in PDF format.
    3. Generate an AI-powered summary.
    4. Download the generated summary PDF.
    5. Ask questions using the paper-specific AI Chat  Assistant.
    6. View and manage previously uploaded papers.


## Learning Outcomes

Through this project I learned:

- Document Processing
   - PDF text extraction
   - Metadata extraction

- Generative AI
   - Gemini 2.5 Flash for summarization

- Retrieval-Augmented Generation (RAG)
   - Paper is chunked into smaller sections
   - Relevant chunks are retrieved for each query
   - Retrieved context is injected into prompts

- Conversational Memory
   - Previous chat messages are stored in MySQL
   - Conversation history is included in prompts
   - Follow-up questions maintain context

- Source Grounding
   - Responses include supporting chunks
   - Reduces hallucinations
## Future Improvements

- Multi paper comparison
- Search option for chats
## Author

### Shruti Bhunde

- GitHub: https://github.com/Shruti-Bhunde
- LinkedIn: www.linkedin.com/in/shruti-bhunde-bb9ab0388
