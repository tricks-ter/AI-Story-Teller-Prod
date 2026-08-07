# api/main.py
import asyncio, json, os, logging
from typing import AsyncGenerator
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from zai import ZaiClient
from database import db

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(title="GLM Chat API", version="2.2.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False, 
    allow_methods=["*"], allow_headers=["*"]
)

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

router = APIRouter(prefix="/api")

@router.get("/health")
def health(): 
    return {"status": "ok", "db_enabled": db.database_url is not None, "api_key_set": bool(API_KEY)}

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    if not request.messages: raise HTTPException(status_code=400, detail="messages must not be empty")

    async def generate() -> AsyncGenerator[str, None]:
        # 1. Immediate heartbeat to Vercel to prevent 10s timeout
        yield f"data: {json.dumps({'type': 'status', 'message': 'Connecting...'})}\n\n"
        
        last_msg = request.messages[-1]
        full_content = ""

        # 2. Safely save user message (moved inside generator to prevent blocking)
        if last_msg.role == "user":
            try:
                title = last_msg.content[:50] if len(last_msg.content) > 50 else "New Chat"
                db.ensure_session(request.session_id, title)
                db.add_message(request.session_id, "user", last_msg.content)
            except Exception as e:
                logger.error(f"Failed to save user message: {e}")

        # 3. Safely initialize ZAI client (prevents crash if key is malformed)
        client = None
        if API_KEY:
            try: client = ZaiClient(api_key=API_KEY)
            except Exception as e:
                logger.error(f"ZaiClient init failed: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': 'Invalid API Key configuration.'})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
        
        if not client:
            yield f"data: {json.dumps({'type': 'error', 'message': 'ZAI_API_KEY is missing in Vercel Environment Variables.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        # 4. Stream from Z.AI
        history = [{"role": m.role, "content": m.content} for m in request.messages]
        try:
            yield f"data: {json.dumps({'type': 'status', 'message': 'Generating response...'})}\n\n"
            loop = asyncio.get_event_loop()
            
            def call_zai():
                return client.chat.completions.create(
                    model=request.model, messages=history, stream=True,
                    max_tokens=request.max_tokens, temperature=request.temperature,
                    thinking={"type": "enabled" if request.enable_thinking else "disabled"}
                )
            
            # Run blocking SDK call in thread pool to keep event loop free
            response = await loop.run_in_executor(None, call_zai)
            
            for chunk in response:
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None)
                content = getattr(delta, "content", None)
                if reasoning: yield f"data: {json.dumps({'type': 'thinking', 'content': reasoning})}\n\n"
                if content:
                    full_content += content
                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
        except Exception as e:
            logger.error(f"ZAI API call failed: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        
        # 5. Safely save assistant message at the end
        if full_content:
            try: db.add_message(request.session_id, "assistant", full_content)
            except Exception as e: logger.error(f"Failed to save assistant message: {e}")
                
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})

app.include_router(router)
