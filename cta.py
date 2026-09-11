"""
Indemnul la actiune (CTA) de pe articol — construit intr-un singur loc.

Modelul scrie doar fraza de incheiere; forma o dam noi, ca sa arate la fel de fiecare
data si sa duca unde trebuie. Din 11 sept (mp19) clientul alege din panou:
  cta_tip       text | link (subliniat) | buton (plin) | contur | caseta (banda cu buton)
  cta_culoare   #rrggbb (implicit rosul MOON); textul butonului iese alb sau inchis,
                dupa cum se citeste mai bine pe culoarea aleasa
  cta_buton     textul de pe buton (implicit fraza din `cta`)
  cta_deasupra  un rand scurt deasupra butonului
  cta_pozitie   final | intro (dupa primul paragraf de sub titlu) | ambele

ATENTIE: acelasi HTML il produce src/motor/cta.js din moon-post (motorul din worker si
previzualizarea din panou). Testele din ambele parti verifica aceleasi siruri exacte —
o schimbare de stil se face in AMANDOUA locurile.
"""

from __future__ import annotations
import html as html_lib
import re

from config import config

CULOARE_IMPLICITA = "#ff2f4d"
TIPURI = ("text", "link", "buton", "contur", "caseta")
POZITII = ("final", "intro", "ambele")


def _esc(t: str) -> str:
    return html_lib.escape(t or "", quote=True)


def culoare(v: str) -> str:
    """#rrggbb curat. „#0af" se intelege; orice altceva cade pe rosul implicit."""
    s = str(v or "").strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", s):
        return s
    if re.fullmatch(r"#[0-9a-f]{3}", s):
        return "#" + "".join(ch * 2 for ch in s[1:])
    return CULOARE_IMPLICITA


def _rgb(c: str) -> tuple:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def text_pe(c: str) -> str:
    """Alb pe culori destul de inchise (contrast >= 3 cu albul, cat cere un buton cu
    litere groase), altfel aproape negru. Rosul MOON ramane cu text alb."""
    def lin(x):
        x = x / 255
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(c)
    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#ffffff" if 1.05 / (lum + 0.05) >= 3 else "#111111"


def nuanta(c: str, cat: float = 0.12) -> str:
    """Culoarea amestecata cu alb (fundalul casetei). Rotunjire in sus de la .5, la fel
    ca Math.round din JS — round() din Python rotunjeste „la par" si ar iesi alt hex."""
    return "#" + "".join(f"{int(255 + (x - 255) * cat + 0.5):02x}" for x in _rgb(c))


def _adresa_buna(link: str) -> bool:
    l = (link or "").strip().lower()
    return l.startswith(("https://", "http://", "mailto:", "tel:")) or (l.startswith("/") and not l.startswith("//"))


def bloc() -> str:
    """HTML-ul indemnului, sau "" cand nu e nimic de pus (doar text, fara link, fara text)."""
    fraza = (config.CLIENT_CTA or "").strip()
    buton = (getattr(config, "CLIENT_CTA_BUTON", "") or "").strip() or fraza
    link = (config.CLIENT_CTA_LINK or "").strip()
    tip = (config.CLIENT_CTA_TIP or "text").strip().lower()
    if tip == "text" or not buton or not link or not _adresa_buna(link):
        return ""
    if tip not in TIPURI:
        tip = "link"
    c = culoare(getattr(config, "CLIENT_CTA_CULOARE", ""))
    deasupra = (getattr(config, "CLIENT_CTA_DEASUPRA", "") or "").strip()
    href = _esc(link)
    plin = (f"display:inline-block;background:{c};color:{text_pe(c)};text-decoration:none;"
            f"padding:14px 26px;border-radius:999px;font-weight:700;border:2px solid {c}")
    if tip == "link":
        return (f'<p class="moon-cta" style="margin:28px 0">' + (_esc(deasupra) + " " if deasupra else "") +
                f'<a href="{href}" style="color:{c};text-decoration:underline;font-weight:700">{_esc(buton)}</a></p>')
    if tip == "caseta":
        return (f'<div class="moon-cta" style="margin:28px 0;padding:22px 24px;border-radius:14px;'
                f'background:{nuanta(c)};border-left:5px solid {c};color:#111111">' +
                (f'<p style="margin:0 0 12px;font-weight:600;color:#111111">{_esc(deasupra)}</p>' if deasupra else "") +
                f'<a href="{href}" style="{plin}">{_esc(buton)}</a></div>')
    stil = plin if tip == "buton" else (
        f"display:inline-block;background:transparent;color:{c};text-decoration:none;"
        f"padding:12px 24px;border-radius:999px;font-weight:700;border:2px solid {c}")
    return ('<div class="moon-cta" style="margin:28px 0">' +
            (f'<p style="margin:0 0 10px;font-weight:600">{_esc(deasupra)}</p>' if deasupra else "") +
            f'<a href="{href}" style="{stil}">{_esc(buton)}</a></div>')


def _deja_legat(html: str, link: str) -> bool:
    """Exista deja un link catre adresa indemnului?"""
    tipar = r'<a\b[^>]*href=["\']' + re.escape(link.rstrip("/")) + r'/?["\']'
    return bool(re.search(tipar, html or "", re.I))


def _dupa_intro(h: str, b: str) -> str:
    """Dupa primul paragraf de sub titlu (raspunsul scurt din capul articolului)."""
    m = re.search(r"</h1\s*>", h, re.I)
    start = m.end() if m else 0
    p = re.compile(r"</p\s*>", re.I).search(h, start)
    la = p.end() if p else start
    return h[:la] + b + h[la:]


def pune(html: str) -> str:
    b = bloc()
    if not b:
        return html
    pozitie = (getattr(config, "CLIENT_CTA_POZITIE", "") or "final").strip().lower()
    if pozitie not in POZITII:
        pozitie = "final"
    h = html or ""
    if pozitie in ("intro", "ambele"):
        h = _dupa_intro(h, b)
    if pozitie in ("final", "ambele"):
        # Daca modelul a pus fraza ca text simplu, ea devine indemnul. Daca a si legat-o,
        # o lasam in pace. Altfel indemnul se pune la final oricum.
        simplu = f"<p>{_esc((config.CLIENT_CTA or '').strip())}</p>"
        if (config.CLIENT_CTA or "").strip() and simplu in h:
            h = h.replace(simplu, b, 1)
        elif not _deja_legat(html or "", (config.CLIENT_CTA_LINK or "").strip()):
            h = h + b
    return h
