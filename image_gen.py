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
import requests
from PIL import Image

from config import config

OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"
GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"

# panoul foloseste cuvinte romanesti; OpenAI vrea low/medium/high
_CALITATE = {"mica": "low", "medie": "medium", "mare": "high"}

# Gemini nu ia „1536x1024", ia proportie + marime. Traducem.
_PROPORTIE = {"1536x1024": "3:2", "1024x1024": "1:1", "1024x1536": "2:3"}
_MARIME_G = {"mica": "512px", "medie": "1K", "mare": "2K"}


def _gemini_format(size: str | None) -> dict:
    marime = _MARIME_G.get(config.OPENAI_IMAGE_QUALITY, "2K")
    # varianta „lite" stie doar 1K; cerand mai mult, apelul pica
    if "lite" in (config.MODEL_IMAGINE or "").lower():
        marime = "1K"
    return {
        "type": "image",
        "mime_type": "image/png",
        "aspect_ratio": _PROPORTIE.get(size or config.OPENAI_IMAGE_SIZE, "3:2"),
        "image_size": marime,
    }


def _gemini_imagine(intrare: list, size: str | None = None) -> bytes:
    """Un apel la Interactions API. `intrare` e lista de bucati: text si,
    optional, poza de pornire (pentru compunerea din produs)."""
    resp = requests.post(
        GEMINI_INTERACTIONS_URL,
        headers={"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"},
        json={"model": config.MODEL_IMAGINE, "input": intrare,
              "response_format": _gemini_format(size)},
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


def _apply_logo(img: Image.Image) -> Image.Image:
    """Suprapune logo-ul clientului în colțul din dreapta-jos. Dacă nu are logo
    pus în panou, întoarce imaginea neschimbată."""
    date = _logo_bytes()
    if not date:
        return img

    logo = Image.open(io.BytesIO(date)).convert("RGBA")
    target_w = int(img.width * 0.16)  # ~16% din lățimea imaginii
    ratio = target_w / logo.width
    logo = logo.resize((target_w, int(logo.height * ratio)), Image.LANCZOS)

    margin = int(img.width * 0.03)
    position = (img.width - logo.width - margin, img.height - logo.height - margin)

    base = img.convert("RGBA")
    base.alpha_composite(logo, dest=position)
    return base.convert("RGB")


def _png_to_jpeg(png_bytes: bytes, cu_logo: bool = True) -> bytes:
    img = Image.open(io.BytesIO(png_bytes))
    if img.mode in ("RGBA", "LA", "P"):
        # JPEG nu are canal alpha — punem fundal alb sub orice transparență.
        background = Image.new("RGB", img.size, (255, 255, 255))
        img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1])
        img = background
    else:
        img = img.convert("RGB")

    if cu_logo:
        img = _apply_logo(img)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


def image_from_url(url: str, cu_logo: bool = True) -> bytes:
    """Poza produsului din magazin, adusă ca JPEG. Cu `cu_logo=False` NU se pune
    logoul — cazul în care poza urmează să intre în compunerea „wow", unde logoul
    se adaugă la final, peste imaginea compusă."""
    r = requests.get(url, timeout=60, headers={"User-Agent": "MoonPost/1.0"})
    r.raise_for_status()
    if len(r.content) < 500:
        raise RuntimeError("Poza produsului e prea mică sau lipsește.")
    return _png_to_jpeg(r.content, cu_logo=cu_logo)


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
    resp = requests.post(
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


def generate_image(prompt: str, size: str | None = None) -> bytes:
    if config.FURNIZOR_IMAGINE == "gemini":
        return _png_to_jpeg(_gemini_imagine([{"type": "text", "text": prompt}], size))
    headers = {
        "Authorization": f"Bearer {config.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.MODEL_IMAGINE,
        "prompt": prompt,
        "size": size or config.OPENAI_IMAGE_SIZE,
        "quality": _CALITATE.get(config.OPENAI_IMAGE_QUALITY, "high"),
        "n": 1,
    }
    resp = requests.post(OPENAI_IMAGES_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    b64 = data["data"][0]["b64_json"]
    png_bytes = base64.b64decode(b64)
    return _png_to_jpeg(png_bytes)
