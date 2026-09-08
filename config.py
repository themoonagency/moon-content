"""
Configurare Moon Content — totul vine din variabile de mediu (GitHub Secrets
în producție, sau un fișier .env local pentru testare). Nu se pun NICIODATĂ
chei/token-uri direct în cod.

Variabile necesare (vezi README.md pentru cum se completează în GitHub):
  WP_URL, WP_USER, WP_APP_PASSWORD
  META_SYSTEM_USER_TOKEN, META_PAGE_ID, META_IG_ID
  GEMINI_API_KEY
  OPENAI_API_KEY
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import os

def _req(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(f"Lipsește variabila de mediu obligatorie: {name}")
    return val

def _opt(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class Config:
    # --- WordPress ---
    WP_URL = _opt("WP_URL", "https://themoonagency.ro")
    WP_USER = _opt("WP_USER", "MOON")
    WP_APP_PASSWORD = _opt("WP_APP_PASSWORD")  # application password, nu parola de login

    # --- Meta (Facebook + Instagram) ---
    META_SYSTEM_USER_TOKEN = _opt("META_SYSTEM_USER_TOKEN")
    META_PAGE_ID = _opt("META_PAGE_ID", "104878805077409")
    META_IG_ID = _opt("META_IG_ID", "17841447599150680")
    META_GRAPH_VERSION = _opt("META_GRAPH_VERSION", "v21.0")

    # --- Gemini (generare text) ---
    GEMINI_API_KEY = _opt("GEMINI_API_KEY")
    GEMINI_MODEL = _opt("GEMINI_MODEL", "gemini-3.6-flash")

    # --- OpenAI (generare imagini) ---
    OPENAI_API_KEY = _opt("OPENAI_API_KEY")
    OPENAI_IMAGE_MODEL = _opt("OPENAI_IMAGE_MODEL", "gpt-image-1")

    # --- Telegram (aprobare) ---
    TELEGRAM_BOT_TOKEN = _opt("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = _opt("TELEGRAM_CHAT_ID", "895952654")

    # --- Comportament ---
    # Client pentru care rulăm ACUM (identifică state-ul și tonul de voce).
    # Faza 1 = "the-moon-agency" (flux "autoritate", fără catalog).
    CLIENT_SLUG = _opt("CLIENT_SLUG", "the-moon-agency")
    CLIENT_NAME = _opt("CLIENT_NAME", "THE MOON Agency")
    CLIENT_DOMAIN = _opt("CLIENT_DOMAIN", "themoonagency.ro")
    CLIENT_NICHE = _opt(
        "CLIENT_NICHE",
        "marketing digital, reclame Google/Meta/TikTok, automatizări AI pentru agenții și magazine online",
    )
    CLIENT_TONE = _opt("CLIENT_TONE", "expert, direct, fără fraze de umplutură, dar prietenos")

    # Fereastra de auto-aprobare: dacă nimeni nu răspunde pe Telegram în
    # atâtea ore, ciornă rămâne NEpublicată (mai sigur la început) — se
    # schimbă în True după ce validăm calitatea câteva săptămâni.
    AUTO_PUBLISH_IF_NO_RESPONSE = _opt("AUTO_PUBLISH_IF_NO_RESPONSE", "false").lower() == "true"
    AUTO_PUBLISH_AFTER_HOURS = int(_opt("AUTO_PUBLISH_AFTER_HOURS", "6"))

    STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
    DRAFTS_FILE = os.path.join(STATE_DIR, f"drafts_{CLIENT_SLUG}.json")
    TOPICS_FILE = os.path.join(STATE_DIR, f"topics_{CLIENT_SLUG}.json")


config = Config()
