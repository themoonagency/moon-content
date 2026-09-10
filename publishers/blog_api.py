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
from urllib.parse import urlsplit

import requests

from config import config

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
}


def _radacina() -> str:
    """Doar schema + domeniul din adresa API. `split("/api/")` intorcea adresa
    INTREAGA cand endpointul n-avea „/api/" in el (de exemplu
    „…/wp-json/moon/v1/articole"), si linkul articolului iesea 404 —
    inclusiv in postarile de Facebook si Instagram."""
    u = urlsplit(config.BLOG_API_URL or "")
    if u.scheme and u.netloc:
        return f"{u.scheme}://{u.netloc}"
    return "https://" + config.CLIENT_DOMAIN if config.CLIENT_DOMAIN else ""


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
        # Un 200 cu HTML inseamna aproape sigur ca am nimerit o pagina de
        # mentenanta sau de login, nu API-ul. Inainte il luam drept succes si
        # marcam ciorna „publicata" desi pe blog nu ajunsese nimic.
        raise RuntimeError(
            "Blogul a raspuns " + str(resp.status_code) + " dar nu cu JSON — "
            "verifica adresa API si tokenul. Inceput: " + resp.text[:160]
        )

    if not isinstance(data, dict) or data.get("ok") is False:
        raise RuntimeError(f"Blogul a refuzat articolul: {str((isinstance(data, dict) and data.get('eroare')) or data)[:300]}")

    slug = data.get("slug") or ""
    link = data.get("url") or ""
    if not link and not slug:
        raise RuntimeError("Blogul a raspuns fara `url` si fara `slug` — nu stiu unde a ajuns articolul.")
    if link.startswith("/"):
        link = _radacina() + link
    elif not link and slug:
        link = _radacina() + "/blog/" + slug
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


def actualizeaza_articol(slug: str | None, html_content: str) -> None:
    """Rescrie continutul unui articol deja publicat — il folosim ca sa lipim
    datele structurate, care au nevoie de adresa finala a articolului.
    Daca blogul nu stie PUT, nu insistam: articolul e publicat oricum."""
    if not slug:
        return
    adresa = config.BLOG_API_URL.rstrip("/") + "/" + str(slug).strip("/")
    try:
        r = requests.put(adresa, json={"content": html_content}, headers=_antete(), timeout=45)
        if r.status_code >= 400:
            print(f"  blogul nu accepta actualizarea ({r.status_code}) — sar peste datele structurate")
    except requests.RequestException as e:
        print(f"  blogul nu raspunde la actualizare: {str(e)[:120]}")
