"""
Publicare pe un blog care expune un API propriu (alternativa la WordPress).

Contractul asteptat de la site-ul clientului:
    POST <BLOG_API_URL>   Authorization: Bearer <token>
        {"title", "excerpt", "content" (HTML), "image", "date", "tags"}
        -> {"ok": true, "slug": "...", "url": "/blog/slug"}
    GET  <BLOG_API_URL>   Authorization: Bearer <token>
        -> lista articolelor existente (pentru anti-duplicat)

Imaginea NU se urca aici: motorul o pune deja in R2 prin panou si trimite
adresa publica in campul "image".
"""

from __future__ import annotations
from datetime import datetime, timezone

import requests

from config import config

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
}


def _antete() -> dict:
    return {**_HEADERS, "Authorization": f"Bearer {config.BLOG_API_TOKEN}"}


def _explica(resp: requests.Response) -> None:
    if resp.status_code >= 400:
        raise requests.exceptions.HTTPError(
            f"{resp.status_code} {resp.reason} pentru {resp.url}\n"
            f"Raspuns server (primele 1000 caractere): {resp.text[:1000]}",
            response=resp,
        )


def publish_article(
    title: str,
    html_content: str,
    meta_description: str,
    image_url: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Trimite articolul. Intoarce {"id", "link", "image_url"} ca WordPress,
    ca sa poata fi folosit la fel mai departe (Facebook/Instagram)."""
    payload = {
        "title": title,
        "excerpt": meta_description or "",
        "content": html_content,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if image_url:
        payload["image"] = image_url
    if tags:
        payload["tags"] = [t for t in tags if t][:8]

    resp = requests.post(config.BLOG_API_URL, json=payload, headers=_antete(), timeout=60)
    _explica(resp)
    try:
        data = resp.json()
    except ValueError:
        data = {}

    if data.get("ok") is False:
        raise RuntimeError(f"Blogul a refuzat articolul: {str(data.get('eroare') or data)[:300]}")

    slug = data.get("slug") or ""
    link = data.get("url") or ""
    if link.startswith("/"):
        baza = config.BLOG_API_URL.split("/api/")[0].rstrip("/")
        if not baza and config.CLIENT_DOMAIN:
            baza = "https://" + config.CLIENT_DOMAIN
        link = baza + link
    return {"id": slug or None, "link": link, "image_url": image_url}


def articole_existente(limita: int = 60) -> list[str]:
    """Titlurile articolelor deja publicate, ca sa nu repetam subiecte.
    Nu arunca niciodata: anti-duplicatul e util, nu obligatoriu."""
    try:
        resp = requests.get(config.BLOG_API_URL, headers=_antete(), timeout=30)
        if resp.status_code >= 400:
            return []
        data = resp.json()
    except Exception:
        return []

    lista = data if isinstance(data, list) else None
    if lista is None and isinstance(data, dict):
        for cheie in ("articole", "posts", "items", "data"):
            if isinstance(data.get(cheie), list):
                lista = data[cheie]
                break
    if not isinstance(lista, list):
        return []

    titluri = []
    for a in lista[:limita]:
        if isinstance(a, dict):
            t = a.get("title") or a.get("titlu") or ""
        else:
            t = str(a)
        t = str(t).strip()
        if t:
            titluri.append(t)
    return titluri
