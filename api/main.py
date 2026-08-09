import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import json, logging, uuid
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from database import db, LEGACY_USER_ID
from core.auth import hash_password, verify_password, make_token, get_user_by_token
from core.prompt_assembler import PromptAssembler
from core.state_resolver import resolve_state
from core.state_applier import apply_state_updates
from core.resilience import call_with_retry, UpstreamRateLimited, extract_status, extract_retry_after, friendly_upstream

load_dotenv()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting API...")
    try: db.init_tables()
    except Exception as e: logger.error(f"DB Init Warning: {e}")
    yield

app = FastAPI(title="InkMind API", version="6.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

API_KEY = os.getenv("ZAI_API_KEY", "")
DEFAULT_MODEL = "glm-4.7-flash"

REASON_TEXT = {
    "backpack_full": "Backpack is full — free up space first.",
    "not_found": "Item not found.",
    "not_owner": "That item isn't yours.",
    "not_equippable": "That item can't be equipped.",
    "not_equipped": "That item isn't equipped.",
    "character_not_found": "Character not found.",
    "item_not_found": "Item not found.",
}

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
    client_telemetry: Optional[dict] = None

class StoryContinueRequest(BaseModel):
    user_action: str
    model: str = DEFAULT_MODEL
    max_tokens: int = Field(default=4096, ge=256, le=8192)
    temperature: float = Field(default=0.7, ge=0.0, le=1.5)
    enable_thinking: bool = True
    client_telemetry: Optional[dict] = None

class StoryCreateRequest(BaseModel):
    title: str
    genre: str
    premise: str
    characterName: str
    characterRole: str
    characterBackground: str
    client_telemetry: Optional[dict] = None

class AuthRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = False
    client_telemetry: Optional[dict] = None

class ItemActionRequest(BaseModel):
    item_id: str
    character_id: Optional[str] = None

router = APIRouter(prefix="/api")

def get_auth_user(raw: Request) -> Optional[dict]:
    header = raw.headers.get("authorization", "")
    if header.startswith("Bearer "):
        return get_user_by_token(header[7:].strip())
    return None

def require_user(raw: Request) -> dict:
    user = get_auth_user(raw)
    if not user:
        raise HTTPException(status_code=401, detail="Login required")
    return user

def check_story_access(story: dict, user: dict):
    owner = story.get("creator_id")
    if owner and owner != user["id"] and owner != LEGACY_USER_ID:
        raise HTTPException(status_code=403, detail="This saga belongs to another author")

def ensure_playthrough(story_id: str, user: dict):
    pt = db.get_active_playthrough(story_id, user["id"])
    if not pt:
        pt = db.create_playthrough(story_id, user["id"])
    return pt

def require_own_playthrough(playthrough_id: str, user: dict):
    pt = db.get_playthrough(playthrough_id)
    if not pt: raise HTTPException(status_code=404, detail="Playthrough not found")
    if pt["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not your playthrough")
    return pt

def _recent_duplicate(last_row, content, window=90):
    """Idempotency guard: True if the same user message was stored within `window` seconds."""
    if not last_row or last_row.get("role") != "user" or last_row.get("content") != content:
        return False
    ts = last_row.get("created_at")
    if not ts: return False
    try:
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() <= window
    except Exception:
        return False

@router.get("/health")
def health(): return {"status": "ok", "db_enabled": db.database_url is not None}

@router.post("/auth/signup")
def signup(req: AuthRequest):
    username = req.username.strip()
    if len(username) < 3: raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(req.password) < 6: raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if db.get_user_by_username(username): raise HTTPException(status_code=409, detail="Username already taken")
    user_id = str(uuid.uuid4())
    token, expires = make_token(user_id, req.remember_me)
    initial_meta = {
        "preferences": {},
        "energy_credits": 0,
        "login_count": 1,
        "last_login_at": datetime.now(timezone.utc).isoformat(),
        "created_via": "signup",
    }
    ok = db.create_user_with_token(user_id, username, hash_password(req.password), token, expires,
                                    metadata=initial_meta, telemetry=req.client_telemetry)
    if not ok: raise HTTPException(status_code=500, detail="Could not save account. Please try again.")
    final_meta = dict(initial_meta)
    final_meta["signup_telemetry"] = req.client_telemetry
    return {"token": token, "user": {"id": user_id, "username": username, "role": "user", "metadata": final_meta}}

@router.post("/auth/login")
def login(req: AuthRequest):
    row = db.get_user_by_username(req.username.strip())
    if not row or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    fresh_meta = db.touch_user_login(row["id"], telemetry=req.client_telemetry)
    token, expires = make_token(row["id"], req.remember_me)
    db.add_auth_token(token, row["id"], expires)
    return {"token": token, "user": {"id": row["id"], "username": row["username"], "role": row["role"], "metadata": fresh_meta}}

@router.get("/auth/me")
def me(raw: Request):
    user = require_user(raw)
    return {"id": user["id"], "username": user["username"], "role": user["role"], "metadata": user.get("metadata") or {}}

@router.get("/stories")
def list_stories(raw: Request, scope: str = "all"):
    user = require_user(raw)
    if scope == "mine":
        return db.list_stories_for_user(user["id"])
    return db.list_all_stories(user["id"])

@router.get("/playthroughs")
def list_playthroughs(raw: Request):
    user = require_user(raw)
    return db.list_playthroughs_for_user(user["id"])

@router.get("/playthroughs/{playthrough_id}/messages")
def get_playthrough_messages(playthrough_id: str, raw: Request, limit: int = 100):
    user = require_user(raw)
    require_own_playthrough(playthrough_id, user)
    return db.get_playthrough_messages(playthrough_id, limit=min(max(int(limit), 1), 200))

@router.get("/playthroughs/{playthrough_id}/inventory")
def get_inventory(playthrough_id: str, raw: Request):
    user = require_user(raw)
    require_own_playthrough(playthrough_id, user)
    db.ensure_playthrough_inventory(playthrough_id)
    items = db.list_playthrough_items(playthrough_id)
    equipment = db.list_playthrough_equipment(playthrough_id)
    equipped_ids = {e["item_id"] for e in equipment}
    for it in items:
        it["equipped"] = it["id"] in equipped_ids
    backpacks = []
    bonuses = {}
    for bp in db.list_playthrough_backpacks(playthrough_id):
        cap = db.backpack_capacity(bp["level"])
        used = db.backpack_used_capacity(bp["character_id"])
        backpacks.append({**bp, "capacity": cap, "used": used})
        bonuses[bp["character_id"]] = db.compute_equipped_bonuses(bp["character_id"])
    return {"items": items, "equipment": equipment, "backpacks": backpacks, "bonuses": bonuses}

@router.post("/playthroughs/{playthrough_id}/equip")
def equip_item(playthrough_id: str, req: ItemActionRequest, raw: Request):
    user = require_user(raw)
    require_own_playthrough(playthrough_id, user)
    char_id = req.character_id
    if not char_id:
        chars = db.get_playthrough_characters(playthrough_id)
        player = next((c for c in chars if c["is_player"]), None)
        char_id = (player or (chars[0] if chars else None))["id"] if chars else None
    if not char_id: raise HTTPException(status_code=400, detail="No character found")
    res = db.equip_item(playthrough_id, char_id, req.item_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=REASON_TEXT.get(res.get("reason"), "Could not equip item."))
    return {"status": "equipped"}

@router.post("/playthroughs/{playthrough_id}/unequip")
def unequip_item(playthrough_id: str, req: ItemActionRequest, raw: Request):
    user = require_user(raw)
    require_own_playthrough(playthrough_id, user)
    char_id = req.character_id
    if not char_id:
        chars = db.get_playthrough_characters(playthrough_id)
        player = next((c for c in chars if c["is_player"]), None)
        char_id = (player or (chars[0] if chars else None))["id"] if chars else None
    if not char_id: raise HTTPException(status_code=400, detail="No character found")
    res = db.unequip_item(playthrough_id, char_id, req.item_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=REASON_TEXT.get(res.get("reason"), "Could not unequip item."))
    return {"status": "unequipped"}

@router.get("/stories/{story_id}")
def get_story_detail(story_id: str, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    return {"story": story, "characters": db.get_story_characters(story_id)}

@router.get("/stories/{story_id}/messages")
def get_story_messages(story_id: str, raw: Request, limit: int = 50, base_only: bool = True):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    return db.get_story_messages(story_id, limit=min(max(int(limit), 1), 200), base_only=base_only)

@router.post("/stories/{story_id}/play")
def play_story(story_id: str, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    pt = ensure_playthrough(story_id, user)
    db.ensure_playthrough_inventory(pt["id"])
    return {
        "playthrough": pt,
        "story": story,
        "characters": db.get_playthrough_characters(pt["id"]),
    }

@router.post("/stories")
def create_new_story(request: StoryCreateRequest, raw: Request):
    user = require_user(raw)
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

    telemetry = request.client_telemetry
    db.create_story(story_id, request.title, request.genre, request.premise, metadata=story_meta,
                    creator_id=user["id"], telemetry=telemetry)
    db.add_story_character(char_id, story_id, request.characterName, request.characterRole,
                           request.characterBackground, metadata=char_meta, telemetry=telemetry)

    intro_msg = f"Welcome to {request.title}. You are {request.characterName}, a {request.characterRole}. {request.premise}"
    db.add_story_message(story_id, "system", intro_msg, msg_type="intro", telemetry=telemetry)

    return {"story_id": story_id, "status": "created", "title": request.title}

@router.post("/stories/{story_id}/continue")
async def continue_story(story_id: str, request: StoryContinueRequest, raw: Request):
    from zai import ZaiClient
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")

    pt = ensure_playthrough(story_id, user)
    pid = pt["id"]
    telemetry = request.client_telemetry

    # Idempotency guard: safe automatic retries never duplicate the action
    if not _recent_duplicate(db.get_last_playthrough_message(pid), request.user_action):
        db.add_playthrough_message(story_id, pid, "user", request.user_action, msg_type="action", telemetry=telemetry)

    assembler = PromptAssembler(pid)
    system_prompt = assembler.assemble_full_prompt(request.user_action)

    client = ZaiClient(api_key=API_KEY) if API_KEY else None
    full_content = ""

    async def generate() -> AsyncGenerator[str, None]:
        nonlocal full_content
        if not client:
            yield f"data: {json.dumps({'type': 'error', 'message': 'ZAI_API_KEY missing.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.user_action}
            ]
            response = call_with_retry(
                lambda: client.chat.completions.create(
                    model=request.model, messages=messages, stream=True,
                    max_tokens=request.max_tokens, temperature=request.temperature,
                    thinking={"type": "enabled" if request.enable_thinking else "disabled"}
                ),
                max_attempts=3, label="story")
            for chunk in response:
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None)
                content = getattr(delta, "content", None)
                if reasoning:
                    yield f"data: {json.dumps({'type': 'thinking', 'content': reasoning})}\n\n"
                if content:
                    full_content += content
                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
        except UpstreamRateLimited as e:
            yield f"data: {json.dumps({'type': 'error', 'code': 429, 'retry_after': e.retry_after, 'message': friendly_upstream(429, str(e))})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return
        except Exception as e:
            status = extract_status(e)
            yield f"data: {json.dumps({'type': 'error', 'code': status, 'retry_after': extract_retry_after(e), 'message': friendly_upstream(status, str(e))})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        clean_text, state_updates = resolve_state(full_content)
        result = apply_state_updates(pid, state_updates)
        applied = result["applied"]
        rejected = result["rejected"]

        meta = {"model": request.model, "temperature": request.temperature, "chars": len(clean_text)}
        db.add_playthrough_message(story_id, pid, "assistant", clean_text, msg_type="narration",
                                   metadata=meta, telemetry=telemetry)

        fresh = db.get_playthrough(pid)
        yield f"data: {json.dumps({'type': 'state_update', 'clean_content': clean_text, 'updates': applied, 'rejected': rejected, 'day': fresh['current_day'], 'time_of_day': fresh['time_of_day']})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, raw: Request):
    from zai import ZaiClient
    if not request.messages: raise HTTPException(status_code=400, detail="messages must not be empty")
    user = get_auth_user(raw)
    uid = user["id"] if user else None

    base_meta = {
        "model": request.model,
        "temperature": request.temperature,
        "enable_thinking": request.enable_thinking,
        "stream": True,
    }

    telemetry = request.client_telemetry

    last_msg = request.messages[-1]
    if last_msg.role == "user":
        db.ensure_session(request.session_id, last_msg.content[:50] if len(last_msg.content) > 50 else "New Chat", user_id=uid)
        if not _recent_duplicate(db.get_last_session_message(request.session_id), last_msg.content):
            db.add_message(request.session_id, "user", last_msg.content,
                           metadata={**base_meta, "role": "user"},
                           user_id=uid, telemetry=telemetry)

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
            response = call_with_retry(
                lambda: client.chat.completions.create(
                    model=request.model, messages=history, stream=True,
                    max_tokens=request.max_tokens, temperature=request.temperature,
                    thinking={"type": "enabled" if request.enable_thinking else "disabled"}
                ),
                max_attempts=3, label="chat")
            for chunk in response:
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None)
                content = getattr(delta, "content", None)
                if reasoning: yield f"data: {json.dumps({'type': 'thinking', 'content': reasoning})}\n\n"
                if content:
                    full_content += content
                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
        except UpstreamRateLimited as e:
            yield f"data: {json.dumps({'type': 'error', 'code': 429, 'retry_after': e.retry_after, 'message': friendly_upstream(429, str(e))})}\n\n"
        except Exception as e:
            status = extract_status(e)
            yield f"data: {json.dumps({'type': 'error', 'code': status, 'retry_after': extract_retry_after(e), 'message': friendly_upstream(status, str(e))})}\n\n"

        if full_content:
            db.add_message(request.session_id, "assistant", full_content,
                           metadata={**base_meta, "role": "assistant", "chars": len(full_content)},
                           user_id=uid, telemetry=telemetry)
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

app.include_router(router)
