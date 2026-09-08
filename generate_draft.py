"""
Rulare zilnică (cron): generează articolul + postările sociale + imaginea
pentru ziua curentă, salvează ciorna și o trimite pe Telegram la aprobare.

NU publică nimic — publicarea se face în check_approvals.py, după click pe
"Aprobă" (sau automat, dacă AUTO_PUBLISH_IF_NO_RESPONSE=true în config).
"""
import sys
import traceback

from content_gen import generate_authority_draft
from image_gen import generate_image
from state import save_draft, record_topic
from telegram_bot import send_for_approval, send_notice
from config import config


def main() -> None:
    try:
        content = generate_authority_draft()
    except Exception as e:
        send_notice(f"⚠️ *Moon Content* — generarea de text a eșuat pentru {config.CLIENT_NAME}:\n`{e}`")
        traceback.print_exc()
        sys.exit(1)

    try:
        image_bytes = generate_image(content["image_prompt"])
    except Exception as e:
        # Nu blocăm tot fluxul dacă doar imaginea eșuează — trimitem fără poză
        print(f"Avertisment: generarea imaginii a eșuat: {e}")
        image_bytes = None

    draft = {
        "client_slug": config.CLIENT_SLUG,
        "topic_title": content["topic_title"],
        "angle": content["angle"],
        "seo_title": content["seo_title"],
        "meta_description": content["meta_description"],
        "article_html": content["article_html"],
        "facebook_text": content["facebook_text"],
        "instagram_text": content["instagram_text"],
        "has_image": image_bytes is not None,
    }
    draft_id = save_draft(draft)

    # salvăm imaginea temporar pe disc, lângă starea proiectului, ca
    # check_approvals.py să o poată re-folosi la publicare fără să o
    # regenereze (regenerarea ar costa din nou și ar da altă imagine)
    if image_bytes:
        with open(f"{config.STATE_DIR}/img_{draft_id}.jpg", "wb") as f:
            f.write(image_bytes)

    record_topic(content["topic_title"], content["angle"])

    send_for_approval(
        draft_id=draft_id,
        title=content["seo_title"],
        article_preview=content["article_html"],
        facebook_text=content["facebook_text"],
        instagram_text=content["instagram_text"],
        image_bytes=image_bytes,
    )
    print(f"Ciornă {draft_id} generată și trimisă spre aprobare: {content['topic_title']}")


if __name__ == "__main__":
    main()
