import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import json
import re
import asyncio
import urllib.request
from urllib.parse import unquote
from typing import AsyncGenerator, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

# ---------------- Layer 1: User-Agent parsing (fallback) ----------------
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
        model = mm.group(1).strip() if mm else ""
        if model in ("", "K"): model = "Android device"
        info.update({"device": model, "os": "Android", "os_version": (mv.group(1) if mv else ""), "type": "mobile"})
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
    if b: info["browser"], info["browser_version"] = "Edge", b.group(1)
    else:
        b = re.search(r"OPR/([\d\.]+)", ua)
        if b: info["browser"], info["browser_version"] = "Opera", b.group(1)
        else:
            b = re.search(r"Firefox/([\d\.]+)", ua)
            if b: info["browser"], info["browser_version"] = "Firefox", b.group(1)
            else:
                b = re.search(r"Chrome/([\d\.]+)", ua)
                if b: info["browser"], info["browser_version"] = "Chrome", b.group(1)
                else:
                    b = re.search(r"Version/([\d\.]+)", ua)
                    if b and "Safari" in ua: info["browser"], info["browser_version"] = "Safari", b.group(1)
    return info

# ---------------- Layer 2: Geo from Vercel headers + free IP APIs ----------------
def get_geo_info(headers):
    city = headers.get("x-vercel-ip-city")
    return {
        "city": unquote(city) if city else "Unknown",
        "region": headers.get("x-vercel-ip-country-region") or "Unknown",
        "country": headers.get("x-vercel-ip-country") or "Unknown",
        "latitude": headers.get("x-vercel-ip-latitude"),
        "longitude": headers.get("x-vercel-ip-longitude"),
        "isp": None,
    }

def _http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=2.5) as r:
        return json.loads(r.read().decode())

def fetch_ip_geo(ip):
    result = {}
    try:
        d = _http_json(f"https://ipwho.is/{ip}")
        if d.get("success", True) and d.get("city"):
            result = {"city": d.get("city"), "region": d.get("region"), "country": d.get("country_code"),
                      "latitude": str(d.get("latitude")), "longitude": str(d.get("longitude")),
                      "isp": (d.get("connection") or {}).get("isp")}
    except Exception: pass
    if not result.get("city"):
        try:
            d = _http_json(f"http://ip-api.com/json/{ip}?fields=status,city,regionName,countryCode,lat,lon,isp")
            if d.get("status") == "success":
                result = {"city": d.get("city"), "region": d.get("regionName"), "country": d.get("countryCode"),
                          "latitude": str(d.get("lat")), "longitude": str(d.get("lon")), "isp": d.get("isp")}
        except Exception: pass
    return result

def build_metadata(req, client_info):
    ua = req.headers.get("user-agent", "")
    dev = parse_device_info(ua)
    ci = client_info or {}

    # Layer 3: upgrade device details using browser Client Hints (beats reduced UA)
    model = (ci.get("ua_model") or "").strip()
    if model and model not in ("K", "Unknown"):
        dev["device"] = model
    if ci.get("ua_platform"):
        dev["os"] = ci.get("ua_platform")
    pv = (ci.get("ua_platform_version") or "").strip()
    if pv:
        if dev["os"] == "Windows":
            try:
                dev["os_version"] = "11" if int(pv.split(".")[0]) >= 13 else "10"
            except Exception: dev["os_version"] = pv
        else:
            dev["os_version"] = pv

    ip = (req.headers.get("x-forwarded-for") or "").split(",")[0].strip() or req.headers.get("x-real-ip") or "unknown"
    geo = get_geo_info(req.headers)
    if (not geo.get("city") or geo["city"] == "Unknown") and ip not in ("unknown", "", "127.0.0.1") and not ip.startswith(("10.", "192.168.", "172.")):
        for k, v in fetch_ip_geo(ip).items():
            if v and (not geo.get(k) or geo.get(k) == "Unknown"):
                geo[k] = v

    return {"device": dev, "location": geo, "client": ci, "ip": ip, "user_agent": ua}

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
    client_info: Optional[dict] = None

@app.get("/api/health")
def health():
    diagnostics = {}
    try:
        from zai import ZaiClient
        diagnostics["zai_sdk"] = "OK"
    except Exception as e: diagnostics["zai_sdk"] = f"FAILED: {str(e)}"
    try:
        import psycopg2
        diagnostics["psycopg2"] = "OK"
    except Exception as e: diagnostics["psycopg2"] = f"FAILED: {str(e)}"
    try:
        import database
        diagnostics["database_module"] = "OK"
    except Exception as e: diagnostics["database_module"] = f"FAILED: {str(e)}"
    if "FAILED" in str(diagnostics):
        return JSONResponse(status_code=500, content={"status": "CRITICAL IMPORT FAILURE", "diagnostics": diagnostics})
    return {"status": "ok", "diagnostics": diagnostics, "api_key_set": bool(os.getenv("ZAI_API_KEY"))}

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest, req: Request):
    if not request.messages: raise HTTPException(status_code=400, detail="messages must not be empty")
    request_metadata = build_metadata(req, request.client_info)

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
                model=(request.model if request.model in ("glm-4.7-flash", "glm-4.5-flash") else "glm-4.7-flash"), messages=history, stream=True,
                max_tokens=request.max_tokens, temperature=min(request.temperature, 1.0),
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
