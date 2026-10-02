import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import json, logging, uuid
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager
from datetime import datetime, timezone
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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

app = FastAPI(title="InkMind API", version="7.7.0", lifespan=lifespan)
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
if not allowed_origins:
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True if allowed_origins != ["*"] else False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    starterLocation: Optional[str] = None
    tone: Optional[str] = None
    coverImage: Optional[str] = None
    bannerImage: Optional[str] = None
    characterImage: Optional[str] = None
    client_telemetry: Optional[dict] = None

class StoryUpdateRequest(BaseModel):
    title: Optional[str] = None
    genre: Optional[str] = None
    premise: Optional[str] = None
    cover_image: Optional[str] = None
    banner_image: Optional[str] = None
    is_public: Optional[bool] = None
    starter_location: Optional[str] = None
    tone: Optional[str] = None

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
    image: Optional[str] = ""
    banner: Optional[str] = ""
    kind: Optional[str] = None
    data_url: Optional[str] = None

class CharacterUpdateRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    background: Optional[str] = None
    image: Optional[str] = None

class LikeRequest(BaseModel):
    # Empty body = toggle (backward compatible). Explicit liked = idempotent set (queue-safe).
    liked: Optional[bool] = None

class StoryCommentRequest(BaseModel):
    content: str

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
    is_public = story.get("is_public", True)
    # Private sagas can only be accessed by the creator or legacy system
    if not is_public and owner != user["id"] and owner not in (None, "", LEGACY_USER_ID):
        raise HTTPException(status_code=403, detail="This saga is private")

def require_story_owner(story: dict, user: dict):
    if story.get("creator_id") != user["id"] and story.get("creator_id") not in (None, "", LEGACY_USER_ID):
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
    pt = require_own_playthrough(playthrough_id, user)
    msgs = db.get_playthrough_messages(playthrough_id, limit=200)
    if len(msgs) <= 30:
        return {"status": "skipped", "reason": "not_enough_messages", "count": len(msgs)}

    meta = pt.get("metadata") or {}
    last_compressed_count = int(meta.get("last_compressed_count", 0))
    if len(msgs) - last_compressed_count < 20:
        return {"status": "skipped", "reason": "already_compressed_recently", "count": len(msgs)}

    batch = msgs[last_compressed_count : last_compressed_count + 40]
    if not batch:
        return {"status": "skipped", "reason": "no_new_batch"}

    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in batch)
    if not API_KEY:
        raise HTTPException(status_code=500, detail="ZAI_API_KEY missing.")
    client = ZaiClient(api_key=API_KEY)

    existing_summary = meta.get("memory_summary", "")
    system_prompt = "Summarize this RPG chapter chronicle into a compact memory (max 250 words). Keep key decisions, names, places, and relationships."
    if existing_summary:
        user_prompt = f"Previous Memory:\n{existing_summary}\n\nNew Chapter Chronicle:\n{transcript}\n\nProvide an integrated updated memory summary."
    else:
        user_prompt = transcript

    resp = call_with_retry(
        lambda: client.chat.completions.create(
            model="glm-4.5-flash",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=600, temperature=0.3),
        max_attempts=2, label="compress")
    summary = (resp.choices[0].message.content or "").strip()
    if not summary:
        raise HTTPException(status_code=502, detail="Summarizer returned empty text.")
    db_ext.set_memory_summary(playthrough_id, summary)

    def fn(cur):
        cur.execute("SELECT metadata FROM playthroughs WHERE id = %s", (playthrough_id,))
        row = cur.fetchone()
        if row:
            rmeta = (row["metadata"] if isinstance(row["metadata"], dict) else {}) or {}
            rmeta["last_compressed_count"] = last_compressed_count + len(batch)
            cur.execute("UPDATE playthroughs SET metadata = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                        (json.dumps(rmeta), playthrough_id))
        return True
    db._with_conn(fn, commit=True)

    return {"status": "compressed", "messages": len(msgs), "compressed_up_to": last_compressed_count + len(batch)}

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
    chars = db.get_story_characters(story_id)
    try:
        imgs = {c["id"]: (c.get("image") or "") for c in db_ext.get_cast_with_images(story_id)}
        for c in chars:
            c["image"] = imgs.get(c["id"], "")
    except Exception:
        pass
    return {"story": story, "characters": chars}

@router.delete("/stories/{story_id}")
def delete_story(story_id: str, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    if not db_ext.can_manage_story(story, user["id"]):
        raise HTTPException(status_code=403, detail="Only the author can delete this saga")
    if not db_ext.delete_story_full(story_id):
        raise HTTPException(status_code=500, detail="Could not delete story")
    return {"status": "deleted", "story_id": story_id}

@router.get("/art/stories")
def get_art_stories(ids: str = "", raw: Request = None):
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    if not id_list:
        return db_ext.get_all_story_art()
    return db_ext.get_story_art_by_ids(id_list)

@router.get("/stories/{story_id}/cast")
def get_story_cast(story_id: str, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    check_story_access(story, user)
    return db_ext.get_cast_with_images(story_id)

@router.post("/stories/{story_id}/characters/{char_id}/art")
def upload_character_art(story_id: str, char_id: str, req: ArtUpdateRequest, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    if not db_ext.can_manage_story(story, user["id"]):
        raise HTTPException(status_code=403, detail="Only the author can update character art")
    image_url = req.data_url or req.image or ""
    if image_url and len(image_url) > 900_000:
        raise HTTPException(status_code=413, detail="Image too large.")
    if not db_ext.set_character_image_by_id(story_id, char_id, image_url):
        raise HTTPException(status_code=500, detail="Could not update character art")
    return {"status": "updated", "character_id": char_id}

@router.patch("/stories/{story_id}/characters/{char_id}")
def update_character_route(story_id: str, char_id: str, req: CharacterUpdateRequest, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    if not db_ext.can_manage_story(story, user["id"]):
        raise HTTPException(status_code=403, detail="Only the author can update character details")
    fields = req.model_dump(exclude_unset=True)
    if not fields: return {"status": "nothing_to_update"}
    if not db_ext.update_character_details(story_id, char_id, fields):
        raise HTTPException(status_code=500, detail="Could not update character details")
    return {"status": "updated", "character_id": char_id}

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
    if req.is_public is not None:
        fields["is_public"] = req.is_public

    # Update metadata fields if starter_location or tone provided
    if req.starter_location is not None or req.tone is not None:
        smeta = (story.get("metadata") if isinstance(story.get("metadata"), dict) else {}) or {}
        if req.starter_location is not None: smeta["starter_location"] = req.starter_location.strip()
        if req.tone is not None: smeta["tone"] = req.tone.strip()
        db.execute_query("UPDATE stories SET metadata = %s WHERE id = %s", (json.dumps(smeta), story_id), fetch="none", commit=True)

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
    if req.kind in ("cover", "portrait") and req.data_url:
        image = req.data_url
    elif req.kind == "banner" and req.data_url:
        banner = req.data_url
    elif req.data_url and not image and not banner:
        image = req.data_url

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

    sse_headers = {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(generate(), media_type="text/event-stream", headers=sse_headers)

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

    sse_headers = {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(generate(), media_type="text/event-stream", headers=sse_headers)

# ── Social: likes & comments (any logged-in user on accessible sagas) ──
@router.get("/stories/social")
def stories_social(raw: Request):
    user = require_user(raw)
    return db_ext.get_all_story_social_counts()

@router.get("/stories/{story_id}/social")
def story_social(story_id: str, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    check_story_access(story, user)
    return db_ext.get_story_social(story_id, user["id"])

@router.post("/stories/{story_id}/like")
def like_story(story_id: str, req: LikeRequest, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    check_story_access(story, user)
    if req.liked is None:
        return db_ext.toggle_story_like(story_id, user["id"])
    return db_ext.set_story_like(story_id, user["id"], req.liked)

@router.post("/stories/{story_id}/comments")
def post_comment(story_id: str, req: StoryCommentRequest, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    check_story_access(story, user)
    content = req.content.strip()
    if not content or len(content) > 500:
        raise HTTPException(status_code=400, detail="Comment must be 1–500 characters")
    row = db_ext.add_story_comment(story_id, user["id"], user["username"], content)
    if not row: raise HTTPException(status_code=500, detail="Could not post comment. Try again.")
    return {"id": row["id"], "created_at": str(row["created_at"]), "username": user["username"], "content": content, "user_id": user["id"]}

@router.delete("/stories/{story_id}/comments/{comment_id}")
def delete_comment(story_id: str, comment_id: int, raw: Request):
    user = require_user(raw)
    story = db.get_story(story_id)
    if not story: raise HTTPException(status_code=404, detail="Story not found")
    existing = db.execute_query("SELECT user_id FROM story_comments WHERE id = %s AND story_id = %s", (comment_id, story_id), fetch="one")
    if not existing:
        raise HTTPException(status_code=404, detail="Comment not found")
    if not db_ext.delete_story_comment(comment_id, user["id"], story.get("creator_id")):
        raise HTTPException(status_code=403, detail="You can only delete your own comments")
    return {"status": "deleted"}

app.include_router(router)

