"""
Generare imagine cu OpenAI Images API (gpt-image-1). Întoarce bytes JPEG
(convertit din PNG-ul original), gata de trimis mai departe la WordPress /
Meta / Telegram — Instagram Graph API acceptă strict JPEG pentru poze,
respinge PNG cu o eroare vagă ("media URI doesn't meet our requirements").
"""
import base64
import io
import requests
from PIL import Image

from config import config

OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"


def _png_to_jpeg(png_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(png_bytes))
    if img.mode in ("RGBA", "LA", "P"):
        # JPEG nu are canal alpha — punem fundal alb sub orice transparență.
        background = Image.new("RGB", img.size, (255, 255, 255))
        img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1])
        img = background
    else:
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
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
