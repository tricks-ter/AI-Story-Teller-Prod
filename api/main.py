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
import db_ext
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

app = FastAPI(title="InkMind API", version="7.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

API_KEY = os.getenv("ZAI_API_KEY", "")
DEFAULT_MODEL = "glm-4.7-flash"

REASON_TEXT = {
    "backpack_full": "Backpack is full — free up space first.",
    "not_found": "Item not found.",
    "not_owner": "That item isn't yours.",
    "not_equippable": "That item can't be equipped.",
    "not_equipped": "That item isn't equipped.",
    "not_usable": "That item can't be used.",
    "quest_locked": "Quest items can't be dropped.",
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
    isPublic: bool = True
    client_telemetry: Optional[dict] = None

class StoryUpdateRequest(BaseModel):
    title: Optional[str] = None
    genre: Optional[str] = None
    premise: Optional[str] = None
    cover_image: Optional[str] = None
    banner_image: Optional[str] = None

class AuthRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = False
    client_telemetry: Optional[dict] = None

class ItemActionRequest(BaseModel):
    item_id: str
    character_id: Optional[str] = None

class NoteCreateRequest(BaseModel):
    content: str
    priority: int = 5

class VisibilityRequest(BaseModel):
    is_public: bool

class ArtUpdateRequest(BaseModel):
    image: str = ""
    banner: str = ""

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

def get_bearer_token(raw: Request) -> Optional[str]:
    header = raw.headers.get("authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return None

def check_story_access(story: dict, user: dict):
    owner = story.get("creator_id")
    if owner and owner != user["id"] and owner != LEGACY_USER_ID:
        raise HTTPException(status_code=403, detail="This saga belongs to another author")
    if not story.get("is_public", True) and owner != user["id"]:
        raise HTTPException(status_code=403, detail="This saga is private")

def require_story_owner(story: dict, user: dict):
    if story.get("creator_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Only the author can manage this saga")

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

def _resolve_player_char(playthrough_id: str, requested: Optional[str]):
    if requested: return requested
    chars = db.get_playthrough_characters(playthrough_id)
    player = next((c for c in chars if c["is_player"]), None)
    return (player or (chars[0] if chars else None))["id"] if chars else None

def _recent_duplicate(last_row, content, window=90):
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
        "preferences": {}, "energy_credits": 0, "login_count": 1,
        "last_login_at": datetime.now(timezone.utc).isoformat(), "created_via": "signup",
    }
    ok = db.create_user_with_token(user_id, username, hash_password(req.password), token, expires,
                                    metadata=initial_meta, telemetry=req.client_telemetry)
    if not ok: raise HTTPException(status_code=500, detail="Could not save account. Please try again.")
    final_meta = dict(initial_meta)
    final_meta["signup_telemetry"] = req.client_telemetry
    return {"token": token, "user": {"id": user_id, "username": username, "role": "user", "metadata": final_meta}}

@router.post("/auth/login")
def login(req: AuthRequest):
    try: db.purge_expired_tokens()
    except Exception: pass
    row = db.get_user_by_username(req.username.strip())
    if not row or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    fresh_meta = db.touch_user_login(row["id"], telemetry=req.client_telemetry)
    token, expires = make_token(row["id"], req.remember_me)
    db.add_auth_token(token, row["id"], expires)
    return {"token": token, "user": {"id": row["id"], "username": row["username"], "role": row["role"], "metadata": fresh_meta}}

@router.post("/auth/logout")
def logout(raw: Request):
    token = get_bearer_token(raw)
    if token: db.delete_auth_token(token)
    return {"status": "logged_out"}

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

# NOTE: declared BEFORE /stories/{story_id} so "art" is not captured as a story id.
@router.get("/stories/art")
def stories_art(raw: Request):
    user = require_user(raw)
    return db_ext.get_all_story_art()

@router.get("/playthroughs")
def list_playthroughs(raw: Request):
    user = require_user(raw)
    return db.list_playthroughs_for_user(user["id"])

@router.get("/playthroughs/{playthrough_id}/messages")
def get_playthrough_messages(playthrough_id: str, raw: Request, limit: int = 100):
    user = require_user(raw)
    require_own_playthrough(playthrough_id, user)
    return db.get_playthrough_messages(playthrough_id, limit=min(max(int(limit), 1), 200))

@router.get("/playthroughs/{playthrough_id}/map")
def get_map(playthrough_id: str, raw: Request):
    user = require_user(raw)
    pt = require_own_playthrough(playthrough_id, user)
    current = (pt.get("metadata") or {}).get("current_location")
    locs = db.get_playthrough_map(playthrough_id)
    for l in locs:
        l["is_current"] = (l["name"] == current)
    return {"current": current, "locations": locs}

@router.get("/playthroughs/{playthrough_id}/inventory")
def get_inventory(playthrough_id: str, raw: Request):
    user = require_user(raw)
    require_own_playthrough(playthrough_id, user)
    db_ext.dedupe_stackables(playthrough_id)  # self-healing: merge duplicate coins/materials
    db.ensure_playthrough_inventory(playthrough_id)
    items = db.list_playthrough_items(playthrough_id)
    equipment = db.list_playthrough_equipment(playthrough_id)
    equipped_ids = {e["item_id"] for e in equipment}
    for it in items:
        it["equipped"] = it["id"] in equipped_ids
    backpacks, bonuses, abilities = [], {}, {}
    for bp in db.list_playthrough_backpacks(playthrough_id):
        backpacks.append({**bp, "capacity": db.backpack_capacity(bp["level"]), "used": db.backpack_used_capacity(bp["character_id"])})
        bonuses[bp["character_id"]] = db.compute_equipped_bonuses(bp["character_id"])
    for c in db.get_playthrough_characters(playthrough_id):
        ab = (c.get("metadata") or {}).get("abilities", [])
        abilities[c["id"]] = ab if isinstance(ab, list) else []
    return {"items": items, "equipment": equipment, "backpacks": backpacks, "bonuses": bonuses, "abilities": abilities}

@router.get("/playthroughs/{playthrough_id}/world-nodes")
def get_world_nodes_route(playthrough_id: str, raw: Request):
    user = require_user(raw)
    require_own_playthrough(playthrough_id, user)
    return db_ext.get_world_nodes_full(playthrough_id)

@router.get("/playthroughs/{playthrough_id}/world-events")
def get_world_events_route(playthrough_id: str, raw: Request, limit: int = 20):
    user = require_user(raw)
    require_own_playthrough(playthrough_id, user)
    return db_ext.get_recent_world_events(playthrough_id, min(max(int(limit), 1), 50))

@router.post("/playthroughs/{playthrough_id}/compress")
def compress_memory(playthrough_id: str, raw: Request):
    from zai import ZaiClient
    user = require_user(raw)
    require_own_playthrough(playthrough_id, user)
    msgs = db.get_playthrough_messages(playthrough_id, limit=200)
    if len(msgs) <= 50:
        return {"status": "skipped", "reason": "not_enough_messages", "count": len(msgs)}
    oldest = msgs[:40]
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in oldest)
    if not API_KEY:
        raise HTTPException(status_code=500, detail="ZAI_API_KEY missing.")
    client = ZaiClient(api_key=API_KEY)
    resp = call_with_retry(
        lambda: client.chat.completions.create(
            model="glm-4.5-flash",
            messages=[
                {"role": "system", "content": "Summarize this RPG chapter chronicle into a compact memory (max 250 words). Keep names, places, outcomes and relationships."},
                {"role": "user", "content": transcript},
            ],
            max_tokens=600, temperature=0.3),
        max_attempts=2, label="compress")
    summary = (resp.choices[0].message.content or "").strip()
    if not summary:
        raise HTTPException(status_code=502, detail="Summarizer returned empty text.")
    db_ext.set_memory_summary(playthrough_id, summary)
    return {"status": "compressed", "messages": len(msgs)}

@router.post("/playthroughs/{playthrough_id}/equip")
def equip_item(playthrough_id: str, req: ItemActionRequest, raw: Request):
    user = require_user(raw)
    require_own_playthrough(playthrough_id, user)
    char_id = _resolve_player_char(playthrough_id, req.character_id)
    if not char_id: raise HTTPException(status_code=400, detail="No character found")
    res = db.equip_item(playthrough_id, char_id, req.item_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=REASON_TEXT.get(res.get("reason"), "Could not equip item."))
    return {"status": "equipped"}

@router.post("/playthroughs/{playthrough_id}/unequip")
def unequip_item(playthrough_id: str, req: ItemActionRequest, raw: Request):
    user = require_user(raw)
    require_own_playthrough(playthrough_id, user)
    char_id = _resolve_player_char(playthrough_id, req.character_id)
    if not char_id: raise HTTPException(status_code=400, detail="No character found")
    res = db.unequip_item(playthrough_id, char_id, req.item_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=REASON_TEXT.get(res.get("reason"), "Could not unequip item."))
    return {"status": "unequipped"}

@router.post("/playthroughs/{playthrough_id}/use")
def use_item(playthrough_id: str, req: ItemActionRequest, raw: Request):
    user = require_user(raw)
    require_own_playthrough(playthrough_id, user)
    char_id = _resolve_player_char(playthrough_id, req.character_id)
    if not char_id: raise HTTPException(status_code=400, detail="No character found")
    res = db.use_item(playthrough_id, char_id, req.item_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=REASON_TEXT.get(res.get("reason"), "Could not use item."))
    return {"status": "used", "name": res.get("name")}

@router.post("/playthroughs/{playthrough_id}/drop")
def drop_item(playthrough_id: str, req: ItemActionRequest, raw: Request):
    user = require_user(raw)
    require_own_playthrough(playthrough_id, user)
    char_id = _resolve_player_char(playthrough_id, req.character_id)
    if not char_id: raise HTTPException(status_code=400, detail="No character found")
    res = db.drop_item(playthrough_id, char_id, req.item_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=REASON_TEXT.get(res.get("reason"), "Could not drop item."))
    return {"status": "dropped", "name": res.get("name")}

@router.post("/playthroughs/{playthrough_id}/complete")
def complete_playthrough(playthrough_id: str, raw: Request):
    user = require_user(raw)
    require_own_playthrough(playthrough_id, user)
    db.complete_playthrough(playthrough_id)
    return {"status": "completed"}

@router.get("/stories/{story_id}")
def get_story_detail(story_id: str, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    check_story_access(story, user)
    return {"story": story, "characters": db.get_story_characters(story_id)}

@router.patch("/stories/{story_id}")
def update_story(story_id: str, req: StoryUpdateRequest, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    if not db_ext.can_manage_story(story, user["id"]):
        raise HTTPException(status_code=403, detail="Only the author can manage this saga")
    fields = {}
    if req.title is not None:
        t = req.title.strip()
        if not t: raise HTTPException(status_code=400, detail="Title can't be empty")
        fields["title"] = t[:120]
    if req.genre is not None:
        g = req.genre.strip()
        if g: fields["genre"] = g[:60]
    if req.premise is not None:
        p = req.premise.strip()
        if p: fields["premise"] = p[:2000]
    if req.cover_image is not None:
        if len(req.cover_image) > 900_000: raise HTTPException(status_code=413, detail="Image too large.")
        fields["cover_image"] = req.cover_image
    if req.banner_image is not None:
        if len(req.banner_image) > 900_000: raise HTTPException(status_code=413, detail="Image too large.")
        fields["banner_image"] = req.banner_image
    if not fields:
        return {"status": "nothing_to_update"}
    if not db_ext.update_story_fields(story_id, fields):
        raise HTTPException(status_code=500, detail="Could not save changes. Try again.")
    return {"status": "updated", "fields": list(fields.keys())}

@router.post("/stories/{story_id}/art")
def set_story_art(story_id: str, req: ArtUpdateRequest, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    if not db_ext.can_manage_story(story, user["id"]):
        raise HTTPException(status_code=403, detail="Only the author can manage this saga")
    image = req.image or ""
    banner = req.banner or ""
    if len(image) > 900_000 or len(banner) > 900_000:
        raise HTTPException(status_code=413, detail="Image too large — pick a smaller picture.")
    if image and not image.startswith("data:image"):
        raise HTTPException(status_code=400, detail="Unsupported image format.")
    if banner and not banner.startswith("data:image"):
        raise HTTPException(status_code=400, detail="Unsupported image format.")
    if image and not db_ext.set_story_art(story_id, image):
        raise HTTPException(status_code=500, detail="Could not save the picture. Try again.")
    if banner and not db_ext.set_story_banner(story_id, banner):
        raise HTTPException(status_code=500, detail="Could not save the banner. Try again.")
    return {"status": "updated"}

@router.get("/stories/{story_id}/messages")
def get_story_messages(story_id: str, raw: Request, limit: int = 50, base_only: bool = True):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    check_story_access(story, user)
    return db.get_story_messages(story_id, limit=min(max(int(limit), 1), 200), base_only=base_only)

@router.get("/stories/{story_id}/notes")
def get_story_notes(story_id: str, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    check_story_access(story, user)
    return db.list_story_notes_full(story_id)

@router.post("/stories/{story_id}/notes")
def create_story_note(story_id: str, req: NoteCreateRequest, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    require_story_owner(story, user)
    content = req.content.strip()
    if not content or len(content) > 500:
        raise HTTPException(status_code=400, detail="Note must be 1–500 characters")
    note_id = db.add_story_note(story_id, content, priority=max(1, min(10, req.priority)))
    if not note_id: raise HTTPException(status_code=500, detail="Could not save note")
    return {"id": note_id, "status": "created"}

@router.post("/stories/{story_id}/notes/{note_id}/toggle")
def toggle_story_note(story_id: str, note_id: int, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    require_story_owner(story, user)
    current = next((n for n in db.list_story_notes_full(story_id) if n["id"] == note_id), None)
    if not current: raise HTTPException(status_code=404, detail="Note not found")
    db.toggle_story_note(note_id, not current["is_active"])
    return {"status": "toggled"}

@router.delete("/stories/{story_id}/notes/{note_id}")
def delete_story_note(story_id: str, note_id: int, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    require_story_owner(story, user)
    db.delete_story_note(note_id)
    return {"status": "deleted"}

@router.post("/stories/{story_id}/visibility")
def set_visibility(story_id: str, req: VisibilityRequest, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    require_story_owner(story, user)
    db.set_story_visibility(story_id, req.is_public)
    return {"status": "updated", "is_public": req.is_public}

@router.post("/stories/{story_id}/play")
def play_story(story_id: str, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    check_story_access(story, user)
    pt = ensure_playthrough(story_id, user)
    db.ensure_playthrough_inventory(pt["id"])
    return {"playthrough": pt, "story": story, "characters": db.get_playthrough_characters(pt["id"])}

@router.post("/stories")
def create_new_story(request: StoryCreateRequest, raw: Request):
    user = require_user(raw)
    story_id = str(uuid.uuid4())
    char_id = str(uuid.uuid4())
    story_meta = {
        "system_prompt": f"You are a master storyteller in the {request.genre} genre.",
        "rules": "Keep responses immersive and descriptive."
    }
    char_meta = {"stats": {"Health": 100, "Mana": 50}, "inventory": ["Adventurer's Kit"]}
    telemetry = request.client_telemetry
    db.create_story(story_id, request.title, request.genre, request.premise, metadata=story_meta,
                    creator_id=user["id"], telemetry=telemetry, is_public=request.isPublic)
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
    check_story_access(story, user)

    pt = ensure_playthrough(story_id, user)
    pid = pt["id"]
    telemetry = request.client_telemetry

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
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": request.user_action}]
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

        meta = {"model": request.model, "temperature": request.temperature, "chars": len(clean_text)}
        db.add_playthrough_message(story_id, pid, "assistant", clean_text, msg_type="narration",
                                   metadata=meta, telemetry=telemetry)

        fresh = db.get_playthrough(pid)
        yield f"data: {json.dumps({'type': 'state_update', 'clean_content': clean_text, 'updates': result['applied'], 'rejected': result['rejected'], 'day': fresh['current_day'], 'time_of_day': fresh['time_of_day'], 'status': fresh['status']})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, raw: Request):
    from zai import ZaiClient
    if not request.messages: raise HTTPException(status_code=400, detail="messages must not be empty")
    user = get_auth_user(raw)
    uid = user["id"] if user else None

    base_meta = {"model": request.model, "temperature": request.temperature, "enable_thinking": request.enable_thinking, "stream": True}
    telemetry = request.client_telemetry

    last_msg = request.messages[-1]
    if last_msg.role == "user":
        db.ensure_session(request.session_id, last_msg.content[:50] if len(last_msg.content) > 50 else "New Chat", user_id=uid)
        if not _recent_duplicate(db.get_last_session_message(request.session_id), last_msg.content):
            db.add_message(request.session_id, "user", last_msg.content, metadata={**base_meta, "role": "user"}, user_id=uid, telemetry=telemetry)

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
