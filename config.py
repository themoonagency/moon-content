"""
Configurare MOON Post.

Motorul nu mai are un singur client fixat în GitHub Secrets. Rulează pentru
TOȚI clienții activi din panou: pentru fiecare, `config.aplica(client)` pune
în `config` cheile și preferințele acelui client, apoi restul codului merge
neschimbat (toate modulele au `from config import config`, deci văd aceleași
valori).

În Secrets rămân doar două lucruri, ale panoului:
  PANEL_URL   adresa panoului MOON Post (ex. https://post.moonchat.ro)
  CRON_KEY    cheia cu care intră motorul (aceeași valoare ca secretul din worker)
"""

from __future__ import annotations
import os
import re


def _opt(name: str, default: str = "") -> str:
    # Actions trimite variabilele nesetate ca string gol, nu lipsă
    val = os.environ.get(name, "").strip()
    return val if val else default


class Config:
    # --- panoul (singurele valori din mediu) ---
    PANEL_URL = _opt("PANEL_URL").rstrip("/")
    CRON_KEY = _opt("CRON_KEY")

    # --- clientul curent (completate de aplica()) ---
    CLIENT_ID = 0
    CLIENT_SLUG = ""
    CLIENT_NAME = ""
    CLIENT_DOMAIN = ""
    CLIENT_NICHE = ""
    CLIENT_TONE = "expert, direct, fără fraze de umplutură, dar prietenos"
    CLIENT_SUBIECTE = ""
    CLIENT_CTA = ""
    CLIENT_CTA_LINK = ""      # unde duce indemnul
    CLIENT_CTA_TIP = "text"   # text | link | buton
    FLUX = "autoritate"

    WP_URL = ""
    WP_USER = ""
    WP_APP_PASSWORD = ""

    # unde sta blogul: "wp" | "api" | "manual" (platforme fara API de articole)
    BLOG_TIP = ""
    BLOG_API_URL = ""
    BLOG_API_TOKEN = ""

    META_SYSTEM_USER_TOKEN = ""
    META_PAGE_ID = ""
    META_IG_ID = ""
    META_GRAPH_VERSION = "v21.0"

    GEMINI_API_KEY = ""
    GEMINI_MODEL = "gemini-3.6-flash"

    OPENAI_API_KEY = ""
    OPENAI_IMAGE_MODEL = "gpt-image-2"
    # numele „gemini_model" / „openai_model" au ramas din vremea cand un furnizor
    # facea textul si celalalt pozele. Acum panoul trimite MODEL_TEXT si
    # MODEL_IMAGINE, si oricare din ele poate fi de la oricare furnizor.
    # cat detaliu cere modelul (mica/medie/mare) si ce format (peisaj/patrat/portret)
    OPENAI_IMAGE_QUALITY = "mare"
    OPENAI_IMAGE_SIZE = "1536x1024"

    TELEGRAM_BOT_TOKEN = ""
    TELEGRAM_CHAT_ID = ""

    # --- Google Business Profile ---
    GOOGLE_CLIENT_ID = ""       # aplicatia noastra, din panou
    GOOGLE_CLIENT_SECRET = ""
    GBP_REFRESH_TOKEN = ""      # tokenul clientului
    GBP_LOCATION = ""           # locations/1234567890

    # slotul de program pentru care rulăm acum (vine de la panou)
    SLOT = 0
    CANALE = ["wp"]
    # paginile citite de panou de pe site-ul clientului: [{url, titlu, rezumat}]
    SITE = []
    # subiectul bifat de om, daca e vreunul la rand: {"id", "titlu", "unghi"}
    IDEE = None
    LOGO_URL = ""          # logoul clientului, suprapus pe imaginile generate

    def aplica(self, client: dict) -> None:
        """Încarcă în config un client venit de la panou (/api/cron/clients)."""
        c = client.get("config") or {}
        self.CLIENT_ID = client.get("id")
        self.CLIENT_SLUG = client.get("slug") or ""
        self.CLIENT_NAME = client.get("nume") or ""
        self.CLIENT_DOMAIN = client.get("domeniu") or ""
        self.FLUX = client.get("flux") or "autoritate"

        self.CLIENT_NICHE = c.get("nisa") or ""
        self.CLIENT_TONE = c.get("ton") or Config.CLIENT_TONE
        self.CLIENT_SUBIECTE = c.get("subiecte") or ""
        self.CLIENT_CTA = c.get("cta") or ""
        self.CLIENT_CTA_LINK = (c.get("cta_link") or "").strip()
        self.CLIENT_CTA_TIP = c.get("cta_tip") or "text"

        self.WP_URL = (c.get("wp_url") or "").rstrip("/")
        self.WP_USER = c.get("wp_user") or ""
        self.WP_APP_PASSWORD = c.get("wp_app_password") or ""

        self.BLOG_TIP = c.get("blog_tip") or ""
        self.BLOG_API_URL = (c.get("blog_api_url") or "").rstrip("/")
        self.BLOG_API_TOKEN = c.get("blog_api_token") or ""

        self.META_SYSTEM_USER_TOKEN = c.get("meta_token") or ""
        self.META_PAGE_ID = c.get("meta_page_id") or ""
        self.META_IG_ID = c.get("meta_ig_id") or ""
        self.META_GRAPH_VERSION = c.get("meta_graph") or Config.META_GRAPH_VERSION

        self.GEMINI_API_KEY = c.get("gemini_key") or ""
        self.GEMINI_MODEL = c.get("gemini_model") or Config.GEMINI_MODEL

        self.OPENAI_API_KEY = c.get("openai_key") or ""
        self.OPENAI_IMAGE_MODEL = c.get("openai_model") or Config.OPENAI_IMAGE_MODEL
        self.OPENAI_IMAGE_QUALITY = c.get("openai_calitate") or Config.OPENAI_IMAGE_QUALITY
        self.OPENAI_IMAGE_SIZE = c.get("openai_marime") or Config.OPENAI_IMAGE_SIZE

        # modelele, fara sa mai presupunem ce furnizor face ce
        self.MODEL_TEXT = c.get("model_text") or self.GEMINI_MODEL
        self.MODEL_IMAGINE = c.get("model_imagine") or self.OPENAI_IMAGE_MODEL

        self.TELEGRAM_BOT_TOKEN = c.get("telegram_bot_token") or ""
        self.TELEGRAM_CHAT_ID = c.get("telegram_chat_id") or ""

        self.GOOGLE_CLIENT_ID = c.get("google_client_id") or ""
        self.GOOGLE_CLIENT_SECRET = c.get("google_client_secret") or ""
        self.GBP_REFRESH_TOKEN = c.get("gbp_refresh_token") or ""
        self.GBP_LOCATION = c.get("gbp_location") or ""

        # panoul spune ce slot e scadent și pe ce canale merge postarea asta
        self.SLOT = int(client.get("slot") or 0)
        self.CANALE = list(client.get("canale") or ["wp"])
        self.SITE = list(client.get("site") or [])
        self.IDEE = client.get("idee") or None
        self.LOGO_URL = c.get("logo_url") or ""

    @staticmethod
    def furnizor(model: str) -> str:
        """Din ce casa e modelul. „gpt-…" si „o3/o4…" sunt OpenAI, restul Gemini."""
        m = (model or "").strip().lower()
        return "openai" if m.startswith("gpt") or re.match(r"^o\d", m) else "gemini"

    @property
    def FURNIZOR_TEXT(self) -> str:
        return self.furnizor(self.MODEL_TEXT)

    @property
    def FURNIZOR_IMAGINE(self) -> str:
        return self.furnizor(self.MODEL_IMAGINE)

    def lipsuri_generare(self) -> list[str]:
        """Cerem doar cheile de care chiar avem nevoie: daca textul si poza vin
        amandoua de la Gemini, cheia OpenAI nu ne trebuie deloc."""
        nevoie = {self.FURNIZOR_TEXT, self.FURNIZOR_IMAGINE}
        lipsa = []
        if "gemini" in nevoie and not self.GEMINI_API_KEY:
            lipsa.append("cheia Gemini")
        if "openai" in nevoie and not self.OPENAI_API_KEY:
            lipsa.append("cheia OpenAI")
        return lipsa

    @property
    def BLOG_MANUAL(self) -> bool:
        """Blogul se pune de mana (ex. Gomag, care n-are API de articole).
        Articolul ramane in panou, de unde se copiaza; restul canalelor merg."""
        return self.BLOG_TIP == "manual"

    @property
    def BLOG_PE_API(self) -> bool:
        """Clientul are blog pe API propriu? Atunci nu mai trecem prin WordPress."""
        if self.BLOG_TIP in ("wp", "manual"):
            return False
        return bool(self.BLOG_API_URL and self.BLOG_API_TOKEN)

    def lipsuri_publicare(self) -> list[str]:
        lipsa = []
        if self.BLOG_PE_API or self.BLOG_MANUAL:
            return lipsa
        if not (self.WP_URL and self.WP_USER and self.WP_APP_PASSWORD):
            lipsa.append("datele blogului: fie WordPress (adresă, utilizator, parolă de APLICAȚIE), "
                         "fie adresa și tokenul API-ului propriu")
        return lipsa


config = Config()
