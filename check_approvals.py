"""
Rulare frecventă (cron la 15 min): citește răspunsurile de pe Telegram
(click pe "Aprobă"/"Respinge") și publică ciornele aprobate pe WordPress
+ Facebook + Instagram. Marchează ciornele expirate (peste
AUTO_PUBLISH_AFTER_HOURS) conform config.AUTO_PUBLISH_IF_NO_RESPONSE.

Offset-ul de Telegram (ca să nu recitim aceleași mesaje) se ține într-un
fișier separat de stare, comis înapoi în repo de workflow.
"""
import json
import os
import traceback
from datetime import datetime, timezone

from config import config
from state import get_draft, update_draft, pending_drafts
from telegram_bot import get_updates, answer_callback, send_notice
from publishers import wordpress, meta

OFFSET_FILE = os.path.join(config.STATE_DIR, "telegram_offset.json")


def _load_offset() -> int | None:
    if not os.path.exists(OFFSET_FILE):
        return None
    with open(OFFSET_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("offset")


def _save_offset(offset: int) -> None:
    os.makedirs(config.STATE_DIR, exist_ok=True)
    with open(OFFSET_FILE, "w", encoding="utf-8") as f:
        json.dump({"offset": offset}, f)


def _image_path(draft_id: str) -> str:
    return f"{config.STATE_DIR}/img_{draft_id}.png"


def publish_draft(draft_id: str) -> None:
    draft = get_draft(draft_id)
    if not draft:
        send_notice(f"⚠️ Ciorna {draft_id} nu a fost găsită (poate a fost deja procesată).")
        return

    image_bytes = None
    img_path = _image_path(draft_id)
    if os.path.exists(img_path):
        with open(img_path, "rb") as f:
            image_bytes = f.read()

    try:
        wp_result = wordpress.publish_article(
            title=draft["seo_title"],
            html_content=draft["article_html"],
            meta_description=draft["meta_description"],
            image_bytes=image_bytes,
        )
    except Exception as e:
        send_notice(f"❌ Publicare WordPress eșuată pentru ciorna {draft_id}:\n`{e}`")
        traceback.print_exc()
        return

    fb_result = ig_result = None
    image_url = wp_result.get("image_url")

    if image_url:
        try:
            fb_result = meta.publish_facebook_photo(image_url, draft["facebook_text"])
        except Exception as e:
            send_notice(f"⚠️ Publicare Facebook eșuată (articolul TOT a mers pe WordPress):\n`{e}`")
            traceback.print_exc()

        try:
            ig_result = meta.publish_instagram_photo(image_url, draft["instagram_text"])
        except Exception as e:
            send_notice(f"⚠️ Publicare Instagram eșuată (articolul TOT a mers pe WordPress):\n`{e}`")
            traceback.print_exc()
    else:
        send_notice("⚠️ Nu există imagine — s-a publicat doar articolul, fără Facebook/Instagram.")

    update_draft(
        draft_id,
        status="published",
        wp_link=wp_result.get("link"),
        fb_post_id=(fb_result or {}).get("post_id"),
        ig_media_id=(ig_result or {}).get("id"),
    )

    if os.path.exists(img_path):
        os.remove(img_path)

    send_notice(
        f"✅ Publicat: *{draft['seo_title']}*\n"
        f"WordPress: {wp_result.get('link')}\n"
        f"Facebook: {'ok' if fb_result else 'eșuat/lipsă'}\n"
        f"Instagram: {'ok' if ig_result else 'eșuat/lipsă'}"
    )


def process_telegram_updates() -> None:
    offset = _load_offset()
    updates = get_updates(offset=offset)

    for update in updates:
        _save_offset(update["update_id"] + 1)

        callback = update.get("callback_query")
        if not callback:
            continue

        data = callback.get("data", "")
        if ":" not in data:
            continue
        action, draft_id = data.split(":", 1)

        if action == "approve":
            answer_callback(callback["id"], "Se publică...")
            update_draft(draft_id, status="approved")
            publish_draft(draft_id)
        elif action == "reject":
            answer_callback(callback["id"], "Respinsă.")
            update_draft(draft_id, status="rejected")
            send_notice(f"🗑️ Ciorna {draft_id} a fost respinsă, nu se publică.")


def process_auto_publish_timeouts() -> None:
    if not config.AUTO_PUBLISH_IF_NO_RESPONSE:
        return
    now = datetime.now(timezone.utc)
    for draft in pending_drafts():
        created = datetime.fromisoformat(draft["created_at"])
        age_hours = (now - created).total_seconds() / 3600
        if age_hours >= config.AUTO_PUBLISH_AFTER_HOURS:
            send_notice(f"⏰ Ciorna {draft['id']} nu a primit răspuns în {config.AUTO_PUBLISH_AFTER_HOURS}h — publicare automată.")
            update_draft(draft["id"], status="approved")
            publish_draft(draft["id"])


def main() -> None:
    process_telegram_updates()
    process_auto_publish_timeouts()


if __name__ == "__main__":
    main()
