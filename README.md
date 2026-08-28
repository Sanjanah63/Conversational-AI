# Any Help – Modern AI Assistant

A clean, production-ready AI Chatbot application with Python backend (FastAPI / Flask), SQLite database persistence, and a modern dark purple/pink frontend powered by Google Gemini API.

---

## 🛠️ Architecture & Zero-Warning Design

- **Zero-CDN Architecture**: All vendor libraries (`marked.min.js`, `purify.min.js`, `prism.min.js`, `icons.css`, `prism.min.css`) are hosted locally in `static/vendor/`. This completely resolves Chrome & Edge **"Tracking Prevention blocked access to storage"** warnings.
- **Embedded SVG Favicon**: Prevents automatic browser `404 Not Found (favicon.ico)` console errors.
- **Python Backend Options**:
  - **FastAPI** (`main.py`): High-performance asynchronous backend with Server-Sent Events (`StreamingResponse`).
  - **Flask** (`app.py`): Classic threaded Flask backend with SSE streaming.
- **Multi-Turn Memory**: Sanitizes database conversation history to guarantee strict alternating `user` $\leftrightarrow$ `model` turns for Google Gemini.
- **Persistent SQLite Database**: Stores chat sessions, message timestamps, and cascade deletions.

---

## 🚀 Quick Start Guide

### 1. Create and Activate Virtual Environment
```powershell
cd "d:\ai chatbot"
python -m venv venv
.\venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Add Your Gemini API Key in `.env`
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
FLASK_PORT=5000
FLASK_DEBUG=True
```
*(Obtain a free key from [Google AI Studio](https://aistudio.google.com/))*

### 4. Run the Backend Server

**Option A: Run with FastAPI & Uvicorn (Recommended)**
```bash
python main.py
# or: uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

**Option B: Run with Flask**
```bash
python app.py
```

### 5. Open in Browser
Navigate to [http://localhost:5000](http://localhost:5000) and check your Chrome DevTools Console (`F12`). It will be completely clean!
