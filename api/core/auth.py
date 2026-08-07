import os, sys, hashlib, secrets
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
for _p in (PARENT_DIR, BASE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database import db

def hash_password(password: str, salt: str = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"{salt}${dk.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(hash_password(password, salt), stored)

def create_token(user_id: str, remember_me: bool) -> str:
    token = secrets.token_urlsafe(32)
    hours = 24 * 30 if remember_me else 12
    expires = datetime.now(timezone.utc) + timedelta(hours=hours)
    db.execute_query(
        "INSERT INTO auth_tokens (token, user_id, expires_at) VALUES (%s, %s, %s)",
        (token, user_id, expires), fetch="none", commit=True)
    return token

def get_user_by_token(token: str):
    if not token: return None
    return db.execute_query(
        "SELECT u.id, u.username, u.role FROM auth_tokens t "
        "JOIN users u ON u.id = t.user_id "
        "WHERE t.token = %s AND t.expires_at > NOW()",
        (token,), fetch="one")
