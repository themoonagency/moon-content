"""
Telegram — canal SECUNDAR de anunțuri. Aprobarea se face în panoul MOON Post.

Înainte, butoanele „Aprobă"/„Respinge" din Telegram erau singura cale, iar
răspunsul se citea cu getUpdates, ținând un offset într-un fișier comis în
repo. La mai mulți clienți asta nu mai merge (un singur bot, un singur offset,
stare partajată). Acum Telegram doar anunță și dă un buton care duce în panou,
unde ciorna se vede întreagă și se poate corecta înainte de aprobare.

Dacă un client nu și-a pus bot, se sare tăcut peste el.
"""

from __future__ import annotations
import json
import requests

from config import config


def _api() -> str:
    return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


def activ() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def _link_panou(draft_id: str) -> str:
    return f"{config.PANEL_URL}/admin#ciorna-{draft_id}" if config.PANEL_URL else ""


def anunta_ciorna(draft_id: str, title: str, facebook_text: str,
                  instagram_text: str, image_bytes: bytes | None,
                  avertisment: str = "") -> None:
    """Anunță ciorna nouă. Butonul duce în panou, unde se aprobă."""
    if not activ():
        return
    caption = (
        f"📝 *Ciornă nouă — {config.CLIENT_NAME}*\n\n"
        f"*Titlu:* {title}\n\n"
        f"*Facebook:*\n{facebook_text}\n\n"
        f"*Instagram:*\n{instagram_text}"
    )
    if avertisment:
        caption += f"\n\n⚠️ {avertisment}"
    caption += "\n\n_Se aprobă din panou._"

    link = _link_panou(draft_id)
    reply = json.dumps({"inline_keyboard": [[{"text": "Deschide în panou", "url": link}]]}) if link else None

    date = {"chat_id": config.TELEGRAM_CHAT_ID, "parse_mode": "Markdown"}
    if reply:
        date["reply_markup"] = reply
    try:
        if image_bytes:
            date["caption"] = caption[:1024]
            requests.post(f"{_api()}/sendPhoto", data=date,
                          files={"photo": ("previzualizare.jpg", image_bytes, "image/jpeg")}, timeout=60)
        else:
            date["text"] = caption[:4000]
            requests.post(f"{_api()}/sendMessage", data=date, timeout=30)
    except requests.RequestException:
        pass  # un anunț ratat nu blochează fluxul


def anunta(text: str) -> None:
    """Mesaj scurt (publicat / eroare). Nu ridică niciodată excepție."""
    if not activ():
        return
    try:
        requests.post(f"{_api()}/sendMessage", data={
            "chat_id": config.TELEGRAM_CHAT_ID, "text": text[:4000], "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }, timeout=30)
    except requests.RequestException:
        pass
