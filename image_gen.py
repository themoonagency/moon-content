"""
Generare imagine, de la OpenAI (Images API) sau de la Gemini / Nano Banana
(Interactions API) — se alege singur, după modelul pus în panou. Întoarce bytes JPEG
(convertit din PNG-ul original), cu logo-ul THE MOON Agency suprapus în
colț — gata de trimis mai departe la WordPress / Meta / Telegram.
Instagram Graph API acceptă strict JPEG pentru poze, respinge PNG cu o
eroare vagă ("media URI doesn't meet our requirements").
"""

from __future__ import annotations
import base64
import io
import math
import re
import time
import requests
from PIL import Image, ImageDraw, ImageFont

import retea

from config import config

OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"
GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

# panoul foloseste cuvinte romanesti; OpenAI vrea low/medium/high
_CALITATE = {"mica": "low", "medie": "medium", "mare": "high"}

# Gemini nu ia „1536x1024", ia proportie + marime. Traducem.
_PROPORTIE = {"1536x1024": "3:2", "1024x1024": "1:1", "1024x1536": "2:3"}
_MARIME_G = {"mica": "512px", "medie": "1K", "mare": "2K"}

# Formatele pe care le poate cere omul din panou -> ce intelege fiecare furnizor.
# OpenAI stie doar trei marimi, deci pentru 16:9 / 4:3 / 4:5 ii cerem cea mai
# apropiata si taiem noi pe centru la proportia ceruta. Gemini le ia direct.
FORMATE = {
    "16:9": ("1536x1024", "16:9", 16 / 9),
    "3:2": ("1536x1024", "3:2", 3 / 2),
    "4:3": ("1536x1024", "4:3", 4 / 3),
    "1:1": ("1024x1024", "1:1", 1.0),
    "4:5": ("1024x1536", "4:5", 4 / 5),
    "9:16": ("1024x1536", "9:16", 9 / 16),
}


def forma(cheie: str | None) -> tuple:
    """(marime OpenAI, proportie Gemini, raport) pentru un format din panou."""
    return FORMATE.get((cheie or "").strip(), FORMATE["3:2"])


def _gemini_format(size: str | None, proportie: str | None = None) -> dict:
    marime = _MARIME_G.get(config.OPENAI_IMAGE_QUALITY, "2K")
    # varianta „lite" stie doar 1K; cerand mai mult, apelul pica
    if "lite" in (config.MODEL_IMAGINE or "").lower():
        marime = "1K"
    return {
        "type": "image",
        "mime_type": "image/png",
        "aspect_ratio": proportie or _PROPORTIE.get(size or config.OPENAI_IMAGE_SIZE, "3:2"),
        "image_size": marime,
    }


def _taie_la(img, raport: float | None):
    """Taie pe centru pana la proportia ceruta. Fara asta, un client care cere
    4:5 pentru Instagram primea tot o poza lata, cu benzi puse de platforma."""
    if not raport:
        return img
    lat, inalt = img.size
    if abs(lat / inalt - raport) < 0.02:
        return img
    if lat / inalt > raport:                     # prea lata -> taiem din laturi
        nou = int(round(inalt * raport))
        x = (lat - nou) // 2
        return img.crop((x, 0, x + nou, inalt))
    nou = int(round(lat / raport))               # prea inalta -> taiem sus si jos
    y = (inalt - nou) // 2
    return img.crop((0, y, lat, y + nou))


def _gemini_imagine(intrare: list, size: str | None = None, proportie: str | None = None) -> bytes:
    """Un apel la Interactions API. `intrare` e lista de bucati: text si,
    optional, poza de pornire (pentru compunerea din produs)."""
    resp = retea.post(
        GEMINI_INTERACTIONS_URL,
        headers={"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"},
        json={"model": config.MODEL_IMAGINE, "input": intrare,
              "response_format": _gemini_format(size, proportie)},
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    b64 = ((data.get("interaction") or {}).get("output_image") or {}).get("data")
    if not b64:
        # unele raspunsuri pun poza in pasi, nu direct in output_image
        for pas in (data.get("interaction") or {}).get("steps") or []:
            b64 = ((pas or {}).get("output_image") or {}).get("data")
            if b64:
                break
    if not b64:
        raise RuntimeError(f"Raspuns Gemini fara imagine: {str(data)[:400]}")
    return base64.b64decode(b64)

# Logo-ul e AL CLIENTULUI și vine din panou (config.LOGO_URL). Fără el, imaginea
# iese curată — nu punem logo-ul agenției peste postările altcuiva.
_LOGO_CACHE: dict[str, bytes] = {}


def _logo_bytes() -> bytes | None:
    url = (config.LOGO_URL or "").strip()
    if not url:
        return None
    if url in _LOGO_CACHE:
        return _LOGO_CACHE[url]
    try:
        r = requests.get(url, timeout=30)
        if r.status_code < 400 and len(r.content) > 100:
            _LOGO_CACHE[url] = r.content
            return r.content
    except requests.RequestException:
        pass
    print("  avertisment: nu am putut lua logoul clientului")
    return None


# Cat de lat e logoul, ca procent din latimea imaginii, si unde sta.
_LOGO_LAT = {"mic": 0.14, "mediu": 0.20, "mare": 0.28}


def _apply_logo(img: Image.Image) -> Image.Image:
    """Suprapune logo-ul clientului. Colțul, mărimea și „fără logo" vin din
    panou (Cum arată imaginile). Fără logo pus, imaginea rămâne curată."""
    loc = (config.IMAGINE_LOGO_LOC or "dreapta-jos").strip().lower()
    if loc == "fara":
        return img
    date = _logo_bytes()
    if not date:
        return img

    logo = Image.open(io.BytesIO(date)).convert("RGBA")
    proc = _LOGO_LAT.get((config.IMAGINE_LOGO_MARIME or "mic").strip().lower(), 0.14)
    target_w = max(40, int(img.width * proc))
    ratio = target_w / logo.width
    logo = logo.resize((target_w, max(1, int(logo.height * ratio))), Image.LANCZOS)

    m = int(img.width * 0.03)
    dreapta, jos = img.width - logo.width - m, img.height - logo.height - m
    centru = (img.width - logo.width) // 2
    pozitii = {
        "dreapta-jos": (dreapta, jos), "stanga-jos": (m, jos),
        "dreapta-sus": (dreapta, m), "stanga-sus": (m, m),
        "centru-jos": (centru, jos),
    }
    base = img.convert("RGBA")
    base.alpha_composite(logo, dest=pozitii.get(loc, pozitii["dreapta-jos"]))
    return base.convert("RGB")


def _png_to_jpeg(png_bytes: bytes, cu_logo: bool = True, raport: float | None = None) -> bytes:
    img = Image.open(io.BytesIO(png_bytes))
    if img.mode in ("RGBA", "LA", "P"):
        # JPEG nu are canal alpha — punem fundal alb sub orice transparență.
        background = Image.new("RGB", img.size, (255, 255, 255))
        img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1])
        img = background
    else:
        img = img.convert("RGB")

    img = _taie_la(img, raport)
    if cu_logo:
        img = _apply_logo(img)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


# Firewallurile de hosting (Wordfence, Imunify360, Cloudflare) refuza des un user-agent
# de robot sau o poza ceruta „din senin", fara pagina de pe care vine. Pe 11 sept poza
# lui La Favorite n-a venit de pe evero.ro. Cerem ca un browser deschis pe pagina
# produsului — e poza publica a clientului, pe care oricum o publicam pentru el.
ANTETE_POZA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
}
POZA_PAUZA = 2   # secunde intre cele doua incercari; testele o pun pe 0


def image_from_url(url: str, cu_logo: bool = True, referer: str | None = None) -> bytes:
    """Poza produsului din magazin, adusă ca JPEG. Cu `cu_logo=False` NU se pune
    logoul — cazul în care poza urmează să intre în compunerea „wow", unde logoul
    se adaugă la final, peste imaginea compusă. `referer` = pagina produsului."""
    antete = dict(ANTETE_POZA)
    if referer:
        antete["Referer"] = referer
    ultima: Exception | None = None
    for incercare in (1, 2):
        try:
            r = requests.get(url, timeout=60, headers=antete)
            r.raise_for_status()
            if len(r.content) < 500:
                raise RuntimeError("poza e prea mică sau lipsește")
            return _png_to_jpeg(r.content, cu_logo=cu_logo)
        except Exception as e:  # noqa: BLE001 — 403 de firewall, timeout, HTML în loc de poză
            ultima = e
            if incercare == 1 and POZA_PAUZA:
                time.sleep(POZA_PAUZA)
    raise RuntimeError(f"poza produsului nu a venit ({str(ultima)[:160]})")


OPENAI_EDITS_URL = "https://api.openai.com/v1/images/edits"


def compune_din_produs(poza: bytes, prompt: str, size: str | None = None) -> bytes:
    """Ia poza REALĂ a produsului și o pune într-o scenă editorială, păstrând
    produsul așa cum e. Costă cât o generare obișnuită, dar iese o imagine care
    arată a reclamă, nu a poză de catalog pe fundal alb.

    Se folosește /images/edits, nu /generations: modelul primește poza ca punct
    de plecare, deci produsul rămâne produsul, nu unul inventat care seamănă.
    """
    intreg = (
        prompt.strip()
        + " Keep the product itself exactly as in the provided image: same shape, same colours, "
          "same label and text, no redesign, no added or altered branding. Do not add any text, "
          "words or logos to the image. Photorealistic editorial product photography."
    )
    if config.FURNIZOR_IMAGINE == "gemini":
        return _png_to_jpeg(_gemini_imagine([
            {"type": "text", "text": intreg[:3500]},
            {"type": "image", "mime_type": "image/png",
             "data": base64.b64encode(_ca_png(poza)).decode()},
        ], size))
    fisiere = {
        "image": ("produs.png", _ca_png(poza), "image/png"),
        "model": (None, config.MODEL_IMAGINE),
        "prompt": (None, intreg[:3500]),
        "size": (None, size or config.OPENAI_IMAGE_SIZE),
        "quality": (None, _CALITATE.get(config.OPENAI_IMAGE_QUALITY, "high")),
        "n": (None, "1"),
    }
    resp = retea.post(
        OPENAI_EDITS_URL,
        headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
        files=fisiere,
        timeout=180,
    )
    resp.raise_for_status()
    b64 = resp.json()["data"][0]["b64_json"]
    return _png_to_jpeg(base64.b64decode(b64))


def _ca_png(date: bytes) -> bytes:
    """API-ul de editare cere PNG. Pozele din feed sunt aproape mereu JPEG."""
    img = Image.open(io.BytesIO(date))
    if img.mode not in ("RGBA", "RGB"):
        img = img.convert("RGBA")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def generate_image(prompt: str, size: str | None = None,
                   format_cerut: str | None = None, cu_logo: bool = True) -> bytes:
    """`format_cerut` e cheia din panou („16:9", „4:5", …). Dacă lipsește, se
    folosește mărimea din setările generale, ca înainte. `cu_logo=False` pentru
    imaginile care își pun singure brandul (afișul de Instagram)."""
    marime, proportie, raport = forma(format_cerut) if format_cerut else (None, None, None)
    if config.FURNIZOR_IMAGINE == "gemini":
        return _png_to_jpeg(
            _gemini_imagine([{"type": "text", "text": prompt}], size, proportie),
            cu_logo=cu_logo, raport=raport)
    headers = {
        "Authorization": f"Bearer {config.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.MODEL_IMAGINE,
        "prompt": prompt,
        "size": marime or size or config.OPENAI_IMAGE_SIZE,
        "quality": _CALITATE.get(config.OPENAI_IMAGE_QUALITY, "high"),
        "n": 1,
    }
    resp = retea.post(OPENAI_IMAGES_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    b64 = data["data"][0]["b64_json"]
    png_bytes = base64.b64decode(b64)
    return _png_to_jpeg(png_bytes, cu_logo=cu_logo, raport=raport)


# ---------------------------------------------------------------- afisul de Instagram
#
# Pana pe 11 sept afisul se cerea in 2:3 (OpenAI nu stie 4:5) si se TAIA pe centru la
# 4:5: 128 px sus si 128 px jos. Pe o fotografie nu se vede; pe un afis taietura a luat
# titlul de sus si banda de jos. Logoul nu se punea deloc, iar banda o desena modelul
# (cand voia). Acum modelul deseneaza doar continutul, iar codul:
#   1. alege marimea de generare cea mai apropiata de zona in care intra continutul,
#   2. il incadreaza INTREG in formatul cerut (nu taie nimic; restul = culoarea fundalului),
#   3. pune dedesubt subsolul: linia de accent + adresa (banda) si logoul clientului.

IG_LATIME = 1080
SUBSOL_PROC = 0.10                     # cat din inaltime ia subsolul
_RAPORT_IG = {"4:5": 4 / 5, "1:1": 1.0, "9:16": 9 / 16}
_MARIMI_OPENAI = {"1024x1024": 1.0, "1024x1536": 2 / 3, "1536x1024": 3 / 2}
_PROPORTII_GEMINI = {"1:1": 1.0, "2:3": 2 / 3, "3:2": 3 / 2, "3:4": 3 / 4, "4:3": 4 / 3,
                     "4:5": 4 / 5, "5:4": 5 / 4, "9:16": 9 / 16, "16:9": 16 / 9}
_FONTURI = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",      # runnerul GitHub (Ubuntu)
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",          # Mac
    "/Library/Fonts/Arial Bold.ttf",
]


def _cel_mai_apropiat(tinta: float, optiuni: dict) -> str:
    return min(optiuni, key=lambda k: abs(math.log(optiuni[k] / tinta)))


def zona_continut(format_cerut: str | None, cu_subsol: bool) -> float:
    """Raportul latime/inaltime al zonei in care intra ce deseneaza modelul."""
    raport = _RAPORT_IG.get((format_cerut or "").strip(), 4 / 5)
    return raport / (1 - SUBSOL_PROC) if cu_subsol else raport


def _culoare_hex(text: str) -> tuple | None:
    m = re.search(r"#?\b([0-9a-fA-F]{6})\b", text or "")
    return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4)) if m else None


def _fundal_din(img: Image.Image) -> tuple:
    """Culoarea fundalului afisului: mediana colturilor (acolo nu e text)."""
    px = []
    for x0, y0 in ((0, 0), (img.width - 8, 0), (0, img.height - 8), (img.width - 8, img.height - 8)):
        px.extend(img.crop((x0, y0, x0 + 8, y0 + 8)).getdata())
    return tuple(sorted(p[i] for p in px)[len(px) // 2] for i in range(3))


def _luminanta(c: tuple) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _font(marime: int):
    for cale in _FONTURI:
        try:
            return ImageFont.truetype(cale, marime)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=marime)
    except TypeError:                   # Pillow vechi
        return ImageFont.load_default()


def logo_imagine() -> Image.Image | None:
    date = _logo_bytes()
    if not date:
        return None
    try:
        return Image.open(io.BytesIO(date)).convert("RGBA")
    except Exception:  # noqa: BLE001 — un logo stricat nu opreste afisul
        print("  avertisment: logoul clientului nu se poate citi ca imagine")
        return None


def compune_afis(continut_png: bytes, format_cerut: str | None, banda: bool, handle: str,
                 accent: str, logo: Image.Image | None) -> bytes:
    """Afisul final: continutul intreg, incadrat, plus subsolul desenat de cod."""
    raport = _RAPORT_IG.get((format_cerut or "").strip(), 4 / 5)
    W, H = IG_LATIME, round(IG_LATIME / raport)
    img = Image.open(io.BytesIO(continut_png)).convert("RGB")
    fundal = _fundal_din(img)
    subsol = bool(banda) or logo is not None
    hs = round(H * SUBSOL_PROC) if subsol else 0

    panza = Image.new("RGB", (W, H), fundal)
    zona_h = H - hs
    k = min(W / img.width, zona_h / img.height)
    nw, nh = max(1, round(img.width * k)), max(1, round(img.height * k))
    panza.paste(img.resize((nw, nh), Image.LANCZOS), ((W - nw) // 2, (zona_h - nh) // 2))

    if subsol:
        d = ImageDraw.Draw(panza)
        y0 = H - hs
        m = round(W * 0.06)
        text_c = (245, 245, 245) if _luminanta(fundal) < 140 else (18, 18, 22)
        acc = _culoare_hex(accent) or text_c
        if banda:
            d.rectangle([m, y0, W - m, y0 + max(4, round(H * 0.004))], fill=acc)
        x_liber = m
        if logo is not None:
            lh = round(hs * 0.52)
            lw = max(1, round(logo.width * lh / logo.height))
            if lw > W * 0.42:
                lw = round(W * 0.42)
                lh = max(1, round(logo.height * lw / logo.width))
            mic = logo.resize((lw, lh), Image.LANCZOS)
            baza = panza.convert("RGBA")
            baza.alpha_composite(mic, dest=(m, y0 + (hs - lh) // 2))
            panza = baza.convert("RGB")
            d = ImageDraw.Draw(panza)
            x_liber = m + lw + round(W * 0.04)
        text = (handle or "").strip() if banda else ""
        if text:
            marime = round(hs * 0.30)
            f = _font(marime)
            while marime > 12 and d.textlength(text, font=f) > (W - m) - x_liber:
                marime -= 2
                f = _font(marime)
            x = (W - m) - d.textlength(text, font=f)
            d.text((x, y0 + hs / 2), text, font=f, fill=text_c, anchor="lm")

    out = io.BytesIO()
    panza.save(out, format="JPEG", quality=92)
    return out.getvalue()


def afis_instagram(prompt: str) -> bytes:
    """Genereaza continutul afisului in marimea cea mai potrivita si il compune."""
    logo = logo_imagine() if config.IG_LOGO else None
    subsol = bool(config.IG_BANDA) or logo is not None
    zona = zona_continut(config.IG_FORMAT, subsol)
    if config.FURNIZOR_IMAGINE == "gemini":
        png = _gemini_imagine([{"type": "text", "text": prompt}], None,
                              _cel_mai_apropiat(zona, _PROPORTII_GEMINI))
    else:
        resp = retea.post(OPENAI_IMAGES_URL, headers={
            "Authorization": f"Bearer {config.OPENAI_API_KEY}", "Content-Type": "application/json",
        }, json={
            "model": config.MODEL_IMAGINE, "prompt": prompt,
            "size": _cel_mai_apropiat(zona, _MARIMI_OPENAI),
            "quality": _CALITATE.get(config.OPENAI_IMAGE_QUALITY, "high"), "n": 1,
        }, timeout=120)
        resp.raise_for_status()
        png = base64.b64decode(resp.json()["data"][0]["b64_json"])
    return compune_afis(png, config.IG_FORMAT, bool(config.IG_BANDA),
                        config.IG_HANDLE or config.CLIENT_DOMAIN or "", config.IG_ACCENT, logo)
