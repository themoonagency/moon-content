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
            r = requests.post(f"{_api()}/sendPhoto", data=date,
                              files={"photo": ("previzualizare.jpg", image_bytes, "image/jpeg")}, timeout=60)
        else:
            date["text"] = caption[:4000]
            r = requests.post(f"{_api()}/sendMessage", data=date, timeout=30)
        _verifica(r, date)
    except requests.RequestException as e:
        print(f"  Telegram: nu am putut trimite ciorna ({str(e)[:150]})")


def anunta(text: str) -> None:
    """Mesaj scurt (publicat / eroare). Nu ridică niciodată excepție."""
    if not activ():
        return
    date = {"chat_id": config.TELEGRAM_CHAT_ID, "text": text[:4000], "parse_mode": "Markdown",
            "disable_web_page_preview": True}
    try:
        _verifica(requests.post(f"{_api()}/sendMessage", data=date, timeout=30), date)
    except requests.RequestException as e:
        print(f"  Telegram: anuntul n-a plecat ({str(e)[:150]})")


def _verifica(r, date: dict) -> None:
    """Telegram raspunde 400 „can't parse entities" cand un titlu are un `_` sau
    un `*` — pana acum nu verificam nimic, deci anunturile pur si simplu nu mai
    ajungeau si nu scria nicaieri de ce. La eroare de formatare reincercam o
    data ca text simplu, ca mesajul sa ajunga oricum."""
    if r is None or r.status_code < 400:
        return
    corp = (r.text or "")[:200]
    if "parse" in corp.lower() or "entities" in corp.lower():
        fara = dict(date)
        fara.pop("parse_mode", None)
        try:
            r2 = requests.post(f"{_api()}/sendMessage", data=fara, timeout=30)
            if r2.status_code < 400:
                print("  Telegram: trimis fara formatare (titlul avea _ sau *)")
                return
        except requests.RequestException:
            pass
    print(f"  Telegram a raspuns {r.status_code}: {corp}")
