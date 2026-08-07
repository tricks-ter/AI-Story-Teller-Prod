import asyncio, json, os, random, logging, uuid
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from zai import ZaiClient
from database import db

load_dotenv()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting API...")
    try: db.init_tables()
    except Exception as e: logger.error(f"DB Init Warning: {e}")
    yield

app = FastAPI(title="InkMind API", version="2.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

API_KEY = os.getenv("ZAI_API_KEY", "")
DEFAULT_MODEL = "glm-4.7-flash"

class MessageItem(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    session_id: str = "default-session"
    messages: list[MessageItem]
    model: str = DEFAULT_MODEL
    max_tokens: int = Field(default=4096, ge=256, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=1.5)
    enable_thinking: bool = True

class StoryCreateRequest(BaseModel):
    title: str
    genre: str
    premise: str
    characterName: str
    characterRole: str
    characterBackground: str

router = APIRouter(prefix="/api")

@router.get("/health")
def health(): return {"status": "ok", "db_enabled": db.database_url is not None}

@router.post("/stories")
def create_new_story(request: StoryCreateRequest):
    story_id = str(uuid.uuid4())
    char_id = str(uuid.uuid4())
    
    story_meta = {
        "system_prompt": f"You are a master storyteller in the {request.genre} genre.",
        "rules": "Keep responses immersive and descriptive."
    }
    
    char_meta = {
        "stats": {"Health": 100, "Mana": 50},
        "inventory": ["Starter Item"]
    }

    db.create_story(story_id, request.title, request.genre, request.premise, metadata=story_meta)
    db.add_story_character(char_id, story_id, request.characterName, request.characterRole, request.characterBackground, metadata=char_meta)
    
    intro_msg = f"Welcome to {request.title}. You are {request.characterName}, a {request.characterRole}. {request.premise}"
    db.add_story_message(story_id, "system", intro_msg, msg_type="intro")

    return {"story_id": story_id, "status": "created", "title": request.title}

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    if not request.messages: raise HTTPException(status_code=400, detail="messages must not be empty")
    last_msg = request.messages[-1]
    if last_msg.role == "user":
        db.ensure_session(request.session_id, last_msg.content[:50] if len(last_msg.content) > 50 else "New Chat")
        db.add_message(request.session_id, "user", last_msg.content)

    client = ZaiClient(api_key=API_KEY) if API_KEY else None
    history = [{"role": m.role, "content": m.content} for m in request.messages]
    full_content = ""

    async def generate() -> AsyncGenerator[str, None]:
        nonlocal full_content
        if not client:
            yield f"data: {json.dumps({'type': 'content', 'content': 'ZAI_API_KEY missing.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        try:
            response = client.chat.completions.create(
                model=request.model, messages=history, stream=True,
                max_tokens=request.max_tokens, temperature=request.temperature,
                thinking={"type": "enabled" if request.enable_thinking else "disabled"}
            )
            for chunk in response:
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None)
                content = getattr(delta, "content", None)
                if reasoning: yield f"data: {json.dumps({'type': 'thinking', 'content': reasoning})}\n\n"
                if content:
                    full_content += content
                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        if full_content: db.add_message(request.session_id, "assistant", full_content)
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

app.include_router(router)
