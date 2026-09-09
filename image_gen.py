"""
Generare imagine cu OpenAI Images API (gpt-image-1). Întoarce bytes JPEG
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


def compune_din_produs(poza: bytes, prompt: str, size: str = "1024x1024") -> bytes:
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
    fisiere = {
        "image": ("produs.png", _ca_png(poza), "image/png"),
        "model": (None, config.OPENAI_IMAGE_MODEL),
        "prompt": (None, intreg[:3500]),
        "size": (None, size),
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


def generate_image(prompt: str, size: str = "1024x1024") -> bytes:
    headers = {
        "Authorization": f"Bearer {config.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.OPENAI_IMAGE_MODEL,
        "prompt": prompt,
        "size": size,
        "n": 1,
    }
    resp = requests.post(OPENAI_IMAGES_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    b64 = data["data"][0]["b64_json"]
    png_bytes = base64.b64decode(b64)
    return _png_to_jpeg(png_bytes)
