"""
Publicare pe Facebook (Pagină) și Instagram, cu System User token
("Moon Content" — vezi setup în README).

Facebook: un singur apel, poză + text, direct pe Pagină.
Instagram: flux în doi pași (container -> publish), cerut de Graph API.
Instagram NU acceptă imagini trimise ca fișier direct — cere un URL public.
De-asta, poza se urcă întâi pe WordPress (Media Library, deja publică),
și se refolosește URL-ul de acolo pentru Instagram.
"""
import time
import requests

from config import config

GRAPH = f"https://graph.facebook.com/{config.META_GRAPH_VERSION}"


def _raise_with_body(resp: requests.Response) -> None:
    """Ca raise_for_status(), dar include mesajul de eroare al Graph API —
    Meta explică de obicei exact motivul (parametru invalid, format
    neacceptat, permisiune lipsă etc.)."""
    if resp.status_code >= 400:
        raise requests.exceptions.HTTPError(
            f"{resp.status_code} for url {resp.url}\nRăspuns Meta: {resp.text[:800]}",
            response=resp,
        )


def _page_access_token() -> str:
    """System User token -> page access token (necesar pt. postare pe Pagină)."""
    url = f"{GRAPH}/{config.META_PAGE_ID}"
    resp = requests.get(url, params={
        "fields": "access_token",
        "access_token": config.META_SYSTEM_USER_TOKEN,
    }, timeout=30)
    _raise_with_body(resp)
    return resp.json()["access_token"]


def publish_facebook_photo(image_url: str, message: str) -> dict:
    page_token = _page_access_token()
    url = f"{GRAPH}/{config.META_PAGE_ID}/photos"
    resp = requests.post(url, data={
        "url": image_url,
        "caption": message,
        "access_token": page_token,
    }, timeout=60)
    _raise_with_body(resp)
    result = resp.json()  # conține "id" (poza) și "post_id"

    # Luăm link-ul public direct, ca să poată fi verificat imediat (nu se
    # presupune doar că a mers — se arată exact unde a apărut).
    post_id = result.get("post_id")
    if post_id:
        try:
            link_resp = requests.get(f"{GRAPH}/{post_id}", params={
                "fields": "permalink_url",
                "access_token": page_token,
            }, timeout=30)
            if link_resp.status_code < 400:
                result["permalink_url"] = link_resp.json().get("permalink_url")
        except requests.RequestException:
            pass  # linkul e un bonus — dacă eșuează, tot restul publicării rămâne valabil

    return result


def publish_instagram_photo(image_url: str, caption: str, poll_seconds: int = 3, max_polls: int = 20) -> dict:
    page_token = _page_access_token()

    # Pas 1: creează containerul media
    create_url = f"{GRAPH}/{config.META_IG_ID}/media"
    resp = requests.post(create_url, data={
        "image_url": image_url,
        "caption": caption,
        "access_token": page_token,
    }, timeout=60)
    _raise_with_body(resp)
    creation_id = resp.json()["id"]

    # Pas 2: așteaptă ca Instagram să proceseze imaginea
    status_url = f"{GRAPH}/{creation_id}"
    for _ in range(max_polls):
        status_resp = requests.get(status_url, params={
            "fields": "status_code",
            "access_token": page_token,
        }, timeout=30)
        _raise_with_body(status_resp)
        status = status_resp.json().get("status_code")
        if status == "FINISHED":
            break
        time.sleep(poll_seconds)
    else:
        raise RuntimeError("Instagram nu a terminat procesarea imaginii la timp.")

    # Pas 3: publică
    publish_url = f"{GRAPH}/{config.META_IG_ID}/media_publish"
    publish_resp = requests.post(publish_url, data={
        "creation_id": creation_id,
        "access_token": page_token,
    }, timeout=60)
    _raise_with_body(publish_resp)
    result = publish_resp.json()  # conține "id" (media id publicat)

    # Link public către postare (Instagram nu-l dă direct din media_publish,
    # trebuie cerut separat pe id-ul media-ului publicat).
    media_id = result.get("id")
    if media_id:
        try:
            link_resp = requests.get(f"{GRAPH}/{media_id}", params={
                "fields": "permalink",
                "access_token": page_token,
            }, timeout=30)
            if link_resp.status_code < 400:
                result["permalink_url"] = link_resp.json().get("permalink")
        except requests.RequestException:
            pass

    return result
