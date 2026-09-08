"""
Trimite ciorna pe Telegram pentru aprobare, cu butoane inline
"✅ Aprobă" / "❌ Respinge". Răspunsul (callback_query) e citit separat,
în check_approvals.py, care rulează pe alt cron (la 15 min).
"""
import json
import requests

from config import config

API = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


def send_for_approval(draft_id: str, title: str, article_preview: str,
                       facebook_text: str, instagram_text: str,
                       image_bytes: bytes | None) -> None:
    caption = (
        f"📝 *Ciornă nouă — {config.CLIENT_NAME}*\n\n"
        f"*Titlu:* {title}\n\n"
        f"*Facebook:*\n{facebook_text}\n\n"
        f"*Instagram:*\n{instagram_text}\n\n"
        f"_Articol complet: {len(article_preview)} caractere — vezi WordPress după aprobare._"
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Aprobă și publică", "callback_data": f"approve:{draft_id}"},
            {"text": "❌ Respinge", "callback_data": f"reject:{draft_id}"},
        ]]
    }

    if image_bytes:
        resp = requests.post(
            f"{API}/sendPhoto",
            data={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "caption": caption[:1024],  # limita Telegram pt. caption
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(keyboard),
            },
            files={"photo": ("preview.jpg", image_bytes, "image/jpeg")},
            timeout=60,
        )
    else:
        resp = requests.post(
            f"{API}/sendMessage",
            data={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": caption,
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(keyboard),
            },
            timeout=30,
        )
    resp.raise_for_status()


def send_notice(text: str) -> None:
    """Mesaj simplu, fără butoane — pt. confirmări/erori."""
    requests.post(f"{API}/sendMessage", data={
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }, timeout=30)


def get_updates(offset: int | None = None) -> list[dict]:
    params = {"timeout": 5}
    if offset is not None:
        params["offset"] = offset
    resp = requests.get(f"{API}/getUpdates", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("result", [])


def answer_callback(callback_query_id: str, text: str) -> None:
    requests.post(f"{API}/answerCallbackQuery", data={
        "callback_query_id": callback_query_id,
        "text": text,
    }, timeout=15)
