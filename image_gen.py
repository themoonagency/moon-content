"""
Generare imagine cu OpenAI Images API (gpt-image-1). Întoarce bytes PNG,
gata de trimis mai departe la WordPress / Meta / Telegram.
"""
import base64
import requests

from config import config

OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"


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
    return base64.b64decode(b64)
