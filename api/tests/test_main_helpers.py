import os, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from main import _recent_duplicate

def test_duplicate_within_window():
    row = {"role": "user", "content": "attack", "created_at": datetime.now(timezone.utc) - timedelta(seconds=10)}
    assert _recent_duplicate(row, "attack")

def test_not_duplicate_outside_window():
    row = {"role": "user", "content": "attack", "created_at": datetime.now(timezone.utc) - timedelta(seconds=200)}
    assert not _recent_duplicate(row, "attack")

def test_not_duplicate_different_content():
    row = {"role": "user", "content": "attack", "created_at": datetime.now(timezone.utc)}
    assert not _recent_duplicate(row, "defend")

def test_not_duplicate_assistant_role():
    row = {"role": "assistant", "content": "attack", "created_at": datetime.now(timezone.utc)}
    assert not _recent_duplicate(row, "attack")
