import os
import sys
import json
import uuid
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import requests

from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session

# Load environment variables
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(filename)s:%(lineno)d) %(message)s"
)
logger = logging.getLogger(__name__)

# Base and Database setup
Base = declarative_base()
basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, "instance")
os.makedirs(instance_path, exist_ok=True)
db_path = os.path.join(instance_path, "anyhelp.db")
DATABASE_URL = f"sqlite:///{db_path}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

class ChatModel(Base):
    __tablename__ = 'chats'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False, default="New Chat")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship('MessageModel', back_populates='chat', cascade='all, delete-orphan', order_by='MessageModel.timestamp.asc()')

    def to_dict(self, include_messages=False):
        data = {
            'id': self.id,
            'title': self.title or 'New Chat',
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else datetime.utcnow().isoformat() + 'Z',
            'updated_at': self.updated_at.isoformat() + 'Z' if self.updated_at else datetime.utcnow().isoformat() + 'Z',
            'message_count': len(self.messages) if self.messages else 0
        }
        if include_messages:
            data['messages'] = [m.to_dict() for m in self.messages]
        return data

class MessageModel(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String(36), ForeignKey('chats.id', ondelete='CASCADE'), nullable=False)
    role = Column(String(20), nullable=False)
    text = Column(Text, nullable=False, default='')
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    chat = relationship('ChatModel', back_populates='messages')

    def to_dict(self):
        return {
            'id': self.id,
            'chat_id': self.chat_id,
            'role': self.role,
            'text': self.text or '',
            'timestamp': self.timestamp.strftime('%I:%M %p') if self.timestamp else datetime.utcnow().strftime('%I:%M %p')
        }

Base.metadata.create_all(bind=engine)

def safe_str(val, default="") -> str:
    if val is None or not isinstance(val, str):
        return default
    return val.strip()

# Gemini SDK Setup
genai_available = False
try:
    import google.generativeai as genai
    gemini_key = safe_str(os.environ.get("GEMINI_API_KEY"))
    if gemini_key and gemini_key != "your_gemini_api_key_here":
        genai.configure(api_key=gemini_key)
    genai_available = True
except Exception as e:
    logger.warning(f"google.generativeai package warning: {e}")

AVAILABLE_MODELS = [
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-pro"
]

SYSTEM_INSTRUCTION = (
    "You are Any Help, an advanced, highly intelligent, friendly, and helpful AI assistant. "
    "Provide clear, accurate, and comprehensive answers using GitHub Flavored Markdown. "
    "Format code snippets with appropriate language tags, use tables, bullet points, and bold text when helpful."
)

# Initialize FastAPI app
app = FastAPI(title="Any Help AI Assistant", version="3.5")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static and Templates
app.mount("/static", StaticFiles(directory="backend/static"), name="static")
templates = Jinja2Templates(directory="backend/templates")

import jinja2
from fastapi import Request
from typing import Any

# Custom url_for helper to support both FastAPI (path=...) and Flask (filename=...) signatures in index.html
@jinja2.pass_context
def custom_url_for(context: dict, name: str, **path_params: Any) -> str:
    request = context.get("request")
    if not request:
        raise ValueError("Request object not found in template context.")
    if name == "static" and "filename" in path_params:
        path_params["path"] = path_params.pop("filename")
    return str(request.url_for(name, **path_params))

templates.env.globals["url_for"] = custom_url_for

# Pydantic Request Models
class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None
    stream: Optional[bool] = True

class NewChatRequest(BaseModel):
    title: Optional[str] = "New Chat"

# Multi-turn history formatter
def format_history_for_gemini(messages):
    formatted = []
    last_role = None
    for msg in messages:
        role = "user" if msg.role == "user" else "model"
        text = safe_str(msg.text)
        if not text or text.startswith("⚠️ **Notice**"):
            continue
        if not formatted and role != "user":
            continue
        if role == last_role:
            if formatted:
                formatted[-1]["parts"][0]["text"] += "\n\n" + text
            continue
        formatted.append({"role": role, "parts": [{"text": text}]})
        last_role = role
    return formatted

def get_demo_ai_response(prompt: str):
    p_lower = prompt.lower()
    if any(k in p_lower for k in ["hello", "hi", "hey"]):
        reply = (
            "Hello! 👋 I am **Any Help**, your AI assistant for coding, writing, problem-solving, and brainstorming.\n\n"
            "To connect me to live **Google Gemini AI**:\n"
            "1. Open `.env` in the project root.\n"
            "2. Set `GEMINI_API_KEY=AIzaSy...` ([Get free key from Google AI Studio](https://aistudio.google.com/)).\n"
            "3. Restart the server and start asking questions!"
        )
    elif any(k in p_lower for k in ["python", "code", "fastapi", "flask", "function"]):
        reply = (
            "Here is a clean Python FastAPI example with async endpoints and error handling:\n\n"
            "```python\n"
            "from fastapi import FastAPI, HTTPException\n"
            "from pydantic import BaseModel\n\n"
            "app = FastAPI()\n\n"
            "class Item(BaseModel):\n"
            "    name: str\n"
            "    price: float\n\n"
            "@app.post('/items')\n"
            "async def create_item(item: Item):\n"
            "    return {'status': 'success', 'data': item}\n"
            "```\n\n"
            "Set your `GEMINI_API_KEY` in `.env` to generate code for any stack in real-time."
        )
    else:
        reply = (
            f"You asked: *\"{prompt}\"*\n\n"
            "To get live, high-precision responses from the **Google Gemini API**:\n\n"
            "1. Open `.env` and set `GEMINI_API_KEY=your_key`.\n"
            "2. Restart your server (`python main.py` or `python app.py`)."
        )
    for i, w in enumerate(reply.split(" ")):
        yield w + (" " if i < len(reply.split(" ")) - 1 else "")

def stream_gemini_response(api_key: str, message: str, history_messages: list):
    clean_history = format_history_for_gemini(history_messages)
    if genai_available:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        for model_name in AVAILABLE_MODELS:
            try:
                model = genai.GenerativeModel(model_name=model_name, system_instruction=SYSTEM_INSTRUCTION)
                sdk_history = [{"role": item["role"], "parts": [item["parts"][0]["text"]]} for item in clean_history]
                chat_session = model.start_chat(history=sdk_history)
                response = chat_session.send_message(message, stream=True)
                has_streamed = False
                for chunk in response:
                    text_chunk = ""
                    try:
                        text_chunk = chunk.text
                    except Exception:
                        if hasattr(chunk, 'candidates') and chunk.candidates:
                            for part in chunk.candidates[0].content.parts:
                                if hasattr(part, 'text') and part.text:
                                    text_chunk += part.text
                    if text_chunk:
                        has_streamed = True
                        yield text_chunk
                if has_streamed:
                    return
            except Exception as e:
                logger.warning(f"FastAPI SDK stream model {model_name} failed: {e}")
                continue

    # Fallback to REST API
    contents = list(clean_history)
    contents.append({"role": "user", "parts": [{"text": message}]})
    for model_name in AVAILABLE_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": contents,
            "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048}
        }
        try:
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=35)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        words = parts[0].get("text", "").split(" ")
                        for i, w in enumerate(words):
                            yield w + (" " if i < len(words) - 1 else "")
                        return
        except Exception:
            continue
    raise Exception("Google Gemini API is unreachable. Please verify GEMINI_API_KEY in `.env`.")


# =========================================================================
# FastAPI Routes
# =========================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/health")
async def health_check():
    api_key = safe_str(os.environ.get("GEMINI_API_KEY"))
    is_configured = bool(api_key and api_key != "your_gemini_api_key_here")
    return {
        "status": "online",
        "app_name": "Any Help",
        "database": "connected",
        "api_configured": is_configured,
        "framework": "FastAPI"
    }

@app.get("/api/chats")
async def get_chats():
    db_session = SessionLocal()
    try:
        chats = db_session.query(ChatModel).order_by(ChatModel.updated_at.desc()).all()
        return {"success": True, "chats": [c.to_dict(include_messages=False) for c in chats]}
    finally:
        db_session.close()

@app.post("/api/new-chat")
@app.post("/api/chats")
async def create_new_chat(payload: Optional[NewChatRequest] = None):
    db_session = SessionLocal()
    try:
        title = safe_str(payload.title if payload else "New Chat", default="New Chat")
        chat = ChatModel(id=str(uuid.uuid4()), title=title)
        db_session.add(chat)
        db_session.commit()
        return {"success": True, "chat": chat.to_dict(include_messages=True)}
    except Exception as e:
        db_session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_session.close()

@app.get("/api/chats/{chat_id}")
async def get_chat_by_id(chat_id: str):
    db_session = SessionLocal()
    try:
        chat = db_session.query(ChatModel).filter(ChatModel.id == chat_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found.")
        return {"success": True, "chat": chat.to_dict(include_messages=True)}
    finally:
        db_session.close()

@app.delete("/api/chats/{chat_id}")
async def delete_chat_by_id(chat_id: str):
    db_session = SessionLocal()
    try:
        chat = db_session.query(ChatModel).filter(ChatModel.id == chat_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found.")
        db_session.delete(chat)
        db_session.commit()
        return {"success": True, "message": "Chat deleted."}
    except Exception as e:
        db_session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db_session.close()

@app.delete("/api/chats")
async def clear_all_chat_records():
    db_session = SessionLocal()
    try:
        db_session.query(MessageModel).delete()
        db_session.query(ChatModel).delete()
        db_session.commit()
        return {"success": True, "message": "All chats cleared."}
    finally:
        db_session.close()

@app.delete("/api/messages/{message_id}")
async def delete_single_message(message_id: int):
    db_session = SessionLocal()
    try:
        msg = db_session.query(MessageModel).filter(MessageModel.id == message_id).first()
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found.")
        db_session.delete(msg)
        db_session.commit()
        return {"success": True, "message": "Message deleted."}
    finally:
        db_session.close()

@app.post("/api/chat")
async def handle_chat(req: ChatRequest):
    user_message = safe_str(req.message)
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    db_session = SessionLocal()
    try:
        chat_obj = None
        if req.chat_id:
            chat_obj = db_session.query(ChatModel).filter(ChatModel.id == req.chat_id).first()

        if not chat_obj:
            title = user_message[:35].strip() + ("..." if len(user_message) > 35 else "")
            chat_obj = ChatModel(id=str(uuid.uuid4()), title=title)
            db_session.add(chat_obj)
            db_session.flush()
        elif chat_obj.title == "New Chat" and len(chat_obj.messages) == 0:
            chat_obj.title = user_message[:35].strip() + ("..." if len(user_message) > 35 else "")

        history = db_session.query(MessageModel).filter(MessageModel.chat_id == chat_obj.id).order_by(MessageModel.timestamp.asc()).all()

        user_msg = MessageModel(chat_id=chat_obj.id, role="user", text=user_message, timestamp=datetime.utcnow())
        db_session.add(user_msg)
        chat_obj.updated_at = datetime.utcnow()
        db_session.commit()

        api_key = safe_str(os.environ.get("GEMINI_API_KEY"))
        has_valid_key = bool(api_key and api_key != "your_gemini_api_key_here")

        chat_id_val = chat_obj.id
        chat_title_val = chat_obj.title

        def generate_sse():
            session = SessionLocal()
            try:
                full_chunks = []
                yield f"data: {json.dumps({'type': 'start', 'chat_id': chat_id_val, 'title': chat_title_val})}\n\n"

                try:
                    if not has_valid_key:
                        gen = get_demo_ai_response(user_message)
                    else:
                        gen = stream_gemini_response(api_key, user_message, history)

                    for token in gen:
                        if token:
                            full_chunks.append(token)
                            yield f"data: {json.dumps({'type': 'chunk', 'text': token})}\n\n"

                except Exception as err:
                    err_text = f"\n\n⚠️ **AI Notice**: {str(err)}"
                    full_chunks.append(err_text)
                    yield f"data: {json.dumps({'type': 'chunk', 'text': err_text})}\n\n"

                final_text = "".join(full_chunks).strip() or "No response generated."
                ai_msg = MessageModel(chat_id=chat_id_val, role="assistant", text=final_text, timestamp=datetime.utcnow())
                session.add(ai_msg)
                
                target = session.query(ChatModel).filter(ChatModel.id == chat_id_val).first()
                if target:
                    target.updated_at = datetime.utcnow()
                session.commit()

                yield f"data: {json.dumps({'type': 'done', 'chat_id': chat_id_val, 'title': chat_title_val, 'full_text': final_text, 'message_id': ai_msg.id, 'timestamp': ai_msg.timestamp.strftime('%I:%M %p')})}\n\n"
            finally:
                session.close()

        return StreamingResponse(generate_sse(), media_type="text/event-stream")

    finally:
        db_session.close()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("FLASK_PORT", 5000))
    print(f"🚀 Any Help FastAPI server running on http://localhost:{port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
