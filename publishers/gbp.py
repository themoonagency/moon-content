"""
Publicare pe Profilul Google al clientului (Google Business Profile).

Fluxul e altfel decât la Meta: aplicația Google e a NOASTRĂ (client id + secret,
o singură dată, în panou), iar fiecare client ne dă acces din contul lui — de
acolo iese un „refresh token" pe care îl ținem pe client. Din el se scoate, la
fiecare rulare, un token de acces valabil o oră.

Accesul la API se dă doar cu aprobare de la Google (cerere trimisă,
Case ID 9-3978000041181). Până atunci codul stă aici, gata, dar canalul „gbp"
pur și simplu nu e bifat în programul niciunui client.
"""

from __future__ import annotations
import requests

from config import config

TOKEN_URL = "https://oauth2.googleapis.com/token"
POSTARI = "https://mybusiness.googleapis.com/v4"


def _raise_with_body(resp: requests.Response) -> None:
    if resp.status_code >= 400:
        raise requests.exceptions.HTTPError(
            f"{resp.status_code} pentru {resp.url}\nRăspuns Google: {resp.text[:800]}",
            response=resp,
        )


def _access_token() -> str:
    if not (config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET and config.GBP_REFRESH_TOKEN):
        raise RuntimeError("Lipsesc datele de Google (aplicația din panou sau tokenul clientului).")
    resp = requests.post(TOKEN_URL, data={
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "refresh_token": config.GBP_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }, timeout=30)
    _raise_with_body(resp)
    return resp.json()["access_token"]


def publish_local_post(text: str, link: str | None = None, image_url: str | None = None) -> dict:
    """O postare pe profil („What's new"). Textul e limitat la 1500 de caractere;
    linkul devine butonul „Află mai multe"."""
    if not config.GBP_LOCATION:
        raise RuntimeError("Lipsește ID-ul locației (locations/...).")
    token = _access_token()

    corp: dict = {
        "languageCode": "ro",
        "summary": (text or "")[:1500],
        "topicType": "STANDARD",
    }
    if link:
        corp["callToAction"] = {"actionType": "LEARN_MORE", "url": link}
    if image_url:
        corp["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": image_url}]

    url = f"{POSTARI}/{config.GBP_LOCATION}/localPosts"
    resp = requests.post(url, json=corp, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    _raise_with_body(resp)
    d = resp.json()
    return {"id": d.get("name"), "permalink_url": d.get("searchUrl")}
