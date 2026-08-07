import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
import re
import asyncio
from urllib.parse import unquote
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import AsyncGenerator, List

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

# ---------------- Device + Location detection (no extra libraries) ----------------
def parse_device_info(ua):
    ua = ua or ""
    info = {"device": "Unknown", "os": "Unknown", "os_version": "", "browser": "Unknown", "browser_version": "", "type": "desktop"}

    m = re.search(r"iPhone OS (\d+(?:[_\.]\d+)*)", ua)
    if m:
        info.update({"device": "iPhone", "os": "iOS", "os_version": m.group(1).replace("_", "."), "type": "mobile"})
    elif "iPad" in ua:
        info.update({"device": "iPad", "os": "iPadOS", "type": "tablet"})
    elif "Android" in ua:
        mv = re.search(r"Android ([\d\.]+)", ua)
        mm = re.search(r"Android [\d\.]+; ([^;]+?)(?: Build|\))", ua)
        info.update({"device": (mm.group(1).strip() if mm else "Android device"), "os": "Android", "os_version": (mv.group(1) if mv else ""), "type": "mobile"})
    elif "Windows NT" in ua:
        nt = re.search(r"Windows NT ([\d\.]+)", ua)
        mapping = {"10.0": "10/11", "6.3": "8.1", "6.2": "8", "6.1": "7"}
        v = nt.group(1) if nt else ""
        info.update({"device": "Windows PC", "os": "Windows", "os_version": mapping.get(v, v)})
    elif "Mac OS X" in ua:
        mv = re.search(r"Mac OS X ([\d_]+)", ua)
        info.update({"device": "Mac", "os": "macOS", "os_version": (mv.group(1).replace("_", ".") if mv else "")})
    elif "Linux" in ua:
        info.update({"device": "Linux PC", "os": "Linux"})

    b = re.search(r"Edg(?:e|A|iOS)?/([\d\.]+)", ua)
    if b:
        info["browser"], info["browser_version"] = "Edge", b.group(1)
    else:
        b = re.search(r"OPR/([\d\.]+)", ua)
        if b:
            info["browser"], info["browser_version"] = "Opera", b.group(1)
        else:
            b = re.search(r"Firefox/([\d\.]+)", ua)
            if b:
                info["browser"], info["browser_version"] = "Firefox", b.group(1)
            else:
                b = re.search(r"Chrome/([\d\.]+)", ua)
                if b:
                    info["browser"], info["browser_version"] = "Chrome", b.group(1)
                else:
                    b = re.search(r"Version/([\d\.]+)", ua)
                    if b and "Safari" in ua:
                        info["browser"], info["browser_version"] = "Safari", b.group(1)
    return info

def get_geo_info(headers):
    city = headers.get("x-vercel-ip-city")
    return {
        "country": headers.get("x-vercel-ip-country") or "Unknown",
        "region": headers.get("x-vercel-ip-country-region") or "Unknown",
        "city": unquote(city) if city else "Unknown",
        "latitude": headers.get("x-vercel-ip-latitude"),
        "longitude": headers.get("x-vercel-ip-longitude"),
    }

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

    if "FAILED" in str(diagnostics):
        return JSONResponse(status_code=500, content={"status": "CRITICAL IMPORT FAILURE", "diagnostics": diagnostics})
    return {"status": "ok", "diagnostics": diagnostics, "api_key_set": bool(os.getenv("ZAI_API_KEY"))}

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest, req: Request):
    if not request.messages: raise HTTPException(status_code=400, detail="messages must not be empty")

    # Build device + geo metadata from request headers
    ua = req.headers.get("user-agent", "")
    client_ip = (req.headers.get("x-forwarded-for") or "").split(",")[0].strip() or req.headers.get("x-real-ip") or "unknown"
    request_metadata = {
        "device": parse_device_info(ua),
        "location": get_geo_info(req.headers),
        "ip": client_ip,
        "user_agent": ua,
    }

    async def generate() -> AsyncGenerator[str, None]:
        yield f"data: {json.dumps({'type': 'status', 'message': 'Connecting...'})}\n\n"

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
                database.db.add_message(request.session_id, "user", last_msg.content, metadata=request_metadata)
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
            try: database.db.add_message(request.session_id, "assistant", full_content, metadata=request_metadata)
            except Exception: pass

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
