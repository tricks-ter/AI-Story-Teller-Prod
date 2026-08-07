# api/main.py
import json
import traceback
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import AsyncGenerator, List
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# DO NOT import zai, psycopg2, or database here globally! 
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

class MessageItem(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    session_id: str = "default-session"
    messages: List[MessageItem]
    model: str = "glm-4.7-flash"
    max_tokens: int = Field(default=4096, ge=256, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=1.5)
    enable_thinking: bool = True

@app.get("/api/health")
def health():
    # DIAGNOSTIC: Test imports dynamically to catch the silent Vercel crash
    diagnostics = {}
    try:
        from zai import ZaiClient
        diagnostics["zai_sdk"] = "OK"
    except Exception as e:
        diagnostics["zai_sdk"] = f"FAILED: {str(e)}"

    try:
        import psycopg2
        diagnostics["psycopg2"] = "OK"
    except Exception as e:
        diagnostics["psycopg2"] = f"FAILED: {str(e)}"

    try:
        import database
        diagnostics["database_module"] = "OK"
    except Exception as e:
        diagnostics["database_module"] = f"FAILED: {str(e)}"

    # If ANY critical module failed, return the exact error as JSON instead of crashing
    if "FAILED" in str(diagnostics):
        return JSONResponse(status_code=500, content={"status": "CRITICAL IMPORT FAILURE", "diagnostics": diagnostics})

    return {"status": "ok", "diagnostics": diagnostics, "api_key_set": bool(os.getenv("ZAI_API_KEY"))}

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    if not request.messages: raise HTTPException(status_code=400, detail="messages must not be empty")

    async def generate() -> AsyncGenerator[str, None]:
        yield f"data: {json.dumps({'type': 'status', 'message': 'Connecting...'})}\n\n"
        
        # Lazy load everything inside the generator
        try:
            import database
            from zai import ZaiClient
            database.db.init_tables() 
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Server startup error: {str(e)}'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        last_msg = request.messages[-1]
        full_content = ""
        if last_msg.role == "user":
            try:
                title = last_msg.content[:50] if len(last_msg.content) > 50 else "New Chat"
                database.db.ensure_session(request.session_id, title)
                database.db.add_message(request.session_id, "user", last_msg.content)
            except Exception as e:
                yield f"data: {json.dumps({'type': 'status', 'message': f'DB Warning: {str(e)}'})}\n\n"

        API_KEY = os.getenv("ZAI_API_KEY", "")
        client = None
        if API_KEY:
            try: client = ZaiClient(api_key=API_KEY)
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': f'ZAI Client Error: {str(e)}'})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
        
        if not client:
            yield f"data: {json.dumps({'type': 'error', 'message': 'ZAI_API_KEY is missing.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        history = [{"role": m.role, "content": m.content} for m in request.messages]
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                model=request.model, messages=history, stream=True,
                max_tokens=request.max_tokens, temperature=request.temperature,
                thinking={"type": "enabled" if request.enable_thinking else "disabled"}
            ))
            
            for chunk in response:
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None)
                content = getattr(delta, "content", None)
                if reasoning: yield f"data: {json.dumps({'type': 'thinking', 'content': reasoning})}\n\n"
                if content:
                    full_content += content
                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'ZAI API Error: {str(e)}'})}\n\n"
        
        if full_content:
            try: database.db.add_message(request.session_id, "assistant", full_content)
            except Exception: pass
                
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
