"""
Clientul de API către panoul MOON Post. Înlocuiește complet vechiul state.py:
starea nu mai stă în fișiere JSON comise în repo (două cronuri care comit în
același repo se calcă între ele, iar datele clienților ar fi publice), ci în
D1, în spatele panoului.

Toate apelurile merg cu antetul X-Cron-Key.
"""

from __future__ import annotations
import requests

from config import config

TIMEOUT = 45


class PanouIndisponibil(RuntimeError):
    pass


def _url(cale: str) -> str:
    if not config.PANEL_URL:
        raise PanouIndisponibil("Lipsește PANEL_URL din mediu (secretul din GitHub).")
    if not config.CRON_KEY:
        raise PanouIndisponibil("Lipsește CRON_KEY din mediu (secretul din GitHub).")
    return f"{config.PANEL_URL}/api/cron{cale}"


def _cere(metoda: str, cale: str, **kw) -> dict:
    antete = kw.pop("headers", {})
    antete["X-Cron-Key"] = config.CRON_KEY
    resp = requests.request(metoda, _url(cale), headers=antete, timeout=TIMEOUT, **kw)
    if resp.status_code >= 400:
        raise PanouIndisponibil(f"{resp.status_code} de la panou pe {cale}: {resp.text[:300]}")
    date = resp.json()
    if not date.get("ok"):
        raise PanouIndisponibil(f"Panoul a refuzat {cale}: {date.get('eroare')}")
    return date


# ---------- clienți ----------

def clienti(scadenti: bool = False, client_id: int | None = None,
            forteaza: bool = False, coada: bool = False) -> list[dict]:
    """Clienții activi, cu cheile lor. Motorul e singurul care le vede în clar.

    scadenti=True întoarce doar clienții cărora le e scadentă o postare în ora
    curentă — panoul face calculul, după programul fiecăruia — și adaugă pe
    fiecare `slot` și `canale`. forteaza=True ignoră programul (pornire manuală
    din panou)."""
    p = {}
    if coada:
        # doar clientii apasati din butonul „Genereaza acum"
        p["coada"] = "1"
    if scadenti:
        p["scadenti"] = "1"
    if forteaza:
        p["forteaza"] = "1"
    if client_id:
        p["client_id"] = client_id
    return _cere("GET", "/clients", params=p).get("clienti", [])


# ---------- ciorne ----------

def creeaza_ciorna(client_id: int, continut: dict) -> str:
    date = _cere("POST", "/drafts", json={"client_id": client_id, **continut})
    return date["id"]


def ciorne(stare: str = "aprobat", client_id: int | None = None) -> list[dict]:
    p = {"stare": stare}
    if client_id:
        p["client_id"] = client_id
    return _cere("GET", "/drafts", params=p).get("ciorne", [])


def actualizeaza(draft_id: str, **campuri) -> None:
    _cere("POST", f"/drafts/{draft_id}", json=campuri)


def urca_imagine(draft_id: str, jpeg: bytes) -> str:
    """Urcă imaginea în R2 și întoarce URL-ul public — Meta trebuie să o poată
    descărca, iar panoul o arată la aprobare."""
    date = _cere("POST", f"/image/{draft_id}", data=jpeg,
                 headers={"Content-Type": "image/jpeg"})
    return date["url"]


# ---------- anti-repetiție ----------

def subiecte_recente(client_id: int, zile: int = 45) -> list[str]:
    return _cere("GET", "/topics", params={"client_id": client_id, "zile": zile}).get("titluri", [])
