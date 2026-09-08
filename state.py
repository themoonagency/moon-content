"""
Stare persistentă simplă, pe fișiere JSON în /state — comisă înapoi în
repo de workflow-ul GitHub Actions după fiecare rulare (vezi .github/workflows).
Nu e nevoie de o bază de date pentru volumul de 1 postare/zi per client.

Două fișiere per client (CLIENT_SLUG):
  drafts_<client>.json  -> ciorne în așteptare / publicate / respinse
  topics_<client>.json  -> subiecte deja tratate, cu dată, pt. anti-repetiție
"""
import json
import os
import uuid
from datetime import datetime, timezone

from config import config


def _load(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------- Ciorne (drafts) ----------

def load_drafts() -> dict:
    return _load(config.DRAFTS_FILE, {})


def save_draft(draft: dict) -> str:
    drafts = load_drafts()
    draft_id = draft.get("id") or uuid.uuid4().hex[:10]
    draft["id"] = draft_id
    draft.setdefault("status", "pending")  # pending | approved | rejected | published
    draft.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    drafts[draft_id] = draft
    _save(config.DRAFTS_FILE, drafts)
    return draft_id


def get_draft(draft_id: str) -> dict | None:
    return load_drafts().get(draft_id)


def update_draft(draft_id: str, **fields) -> None:
    drafts = load_drafts()
    if draft_id not in drafts:
        return
    drafts[draft_id].update(fields)
    drafts[draft_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(config.DRAFTS_FILE, drafts)


def pending_drafts() -> list[dict]:
    return [d for d in load_drafts().values() if d.get("status") == "pending"]


# ---------- Subiecte folosite (anti-repetiție) ----------

def load_used_topics() -> list[dict]:
    return _load(config.TOPICS_FILE, [])


def record_topic(topic_title: str, angle: str) -> None:
    topics = load_used_topics()
    topics.append({
        "title": topic_title,
        "angle": angle,
        "date": datetime.now(timezone.utc).date().isoformat(),
    })
    # păstrăm ultimele 200, suficient pentru anti-repetiție pe câteva luni
    topics = topics[-200:]
    _save(config.TOPICS_FILE, topics)


def recent_topic_titles(days: int = 45) -> list[str]:
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    return [t["title"] for t in load_used_topics() if t["date"] >= cutoff]
