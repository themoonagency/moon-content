"""
Publicare pe WordPress prin REST API, cu Application Password (rol Autor
e suficient — nu are nevoie de rol de Administrator).
"""
import requests
from requests.auth import HTTPBasicAuth

from config import config


def _auth() -> HTTPBasicAuth:
    return HTTPBasicAuth(config.WP_USER, config.WP_APP_PASSWORD)


def _raise_with_body(resp: requests.Response) -> None:
    """Ca raise_for_status(), dar include corpul răspunsului în eroare —
    esențial pt. diagnostic (WordPress/hosting-ul explică de obicei EXACT
    de ce a respins cererea: plugin de securitate, autentificare, etc.)."""
    if resp.status_code >= 400:
        raise requests.exceptions.HTTPError(
            f"{resp.status_code} {resp.reason} for url {resp.url}\n"
            f"Răspuns server (primele 1000 caractere): {resp.text[:1000]}",
            response=resp,
        )


def upload_media(image_bytes: bytes, filename: str = "moon-content.png") -> dict:
    """Încarcă imaginea în Media Library. Întoarce {"id": ..., "url": ...} —
    URL-ul e necesar pt. Meta (Facebook/Instagram cer o adresă publică,
    nu acceptă fișierul trimis direct)."""
    url = f"{config.WP_URL}/wp-json/wp/v2/media"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "image/png",
    }
    resp = requests.post(url, headers=headers, data=image_bytes, auth=_auth(), timeout=60)
    _raise_with_body(resp)
    data = resp.json()
    return {"id": data["id"], "url": data.get("source_url")}


def create_post(
    title: str,
    html_content: str,
    excerpt: str = "",
    featured_media_id: int | None = None,
    status: str = "publish",
) -> dict:
    """Creează un articol de blog. status='draft' pentru testare fără publicare live."""
    url = f"{config.WP_URL}/wp-json/wp/v2/posts"
    payload = {
        "title": title,
        "content": html_content,
        "status": status,
        "excerpt": excerpt,
    }
    if featured_media_id:
        payload["featured_media"] = featured_media_id

    resp = requests.post(url, json=payload, auth=_auth(), timeout=60)
    _raise_with_body(resp)
    data = resp.json()
    return {"id": data["id"], "link": data.get("link")}


def publish_article(title: str, html_content: str, meta_description: str, image_bytes: bytes | None) -> dict:
    media = upload_media(image_bytes) if image_bytes else {"id": None, "url": None}
    post = create_post(
        title=title,
        html_content=html_content,
        excerpt=meta_description,
        featured_media_id=media["id"],
        status="publish",
    )
    post["image_url"] = media["url"]
    return post
