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


def _bifa(v) -> bool:
    """Bifele din panou vin ca True/False, dar un config mai vechi le poate avea
    ca sir („true", „on"). Un sir gol si lipsa inseamna acelasi lucru: stins."""
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "da", "on", "yes")


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

    SCHELETE_RECENTE: list = []
    # stilul vizual e AL CLIENTULUI, nu al agentiei
    IMAGINE_STIL = "foto"
    IMAGINE_PALETA = ""
    IMAGINE_EVITA = ""
    IMAGINE_LUMINA = ""            # naturala | calda | studio | contrast | inchisa
    IMAGINE_FORMAT = "16:9"        # 16:9 | 3:2 | 4:3 | 1:1
    IMAGINE_TEXT_PE_POZA = "nu"    # nu | titlu | titlu_sub
    IMAGINE_LOGO_LOC = "dreapta-jos"
    IMAGINE_LOGO_MARIME = "mic"    # mic | mediu | mare
    # Cerintele scrise de client, cu cuvintele lui. Se pun ULTIMELE in prompt,
    # ca instructiune finala: ce scrie omul bate ce a bifat din liste.
    IMAGINE_CERINTE = ""

    # A doua imagine, cea de Instagram: construita, cu text mare pe ea. Pe blog
    # castiga textul, pe Instagram castiga poza — deci nu e aceeasi imagine.
    IG_SEPARATA = False
    IG_SABLON = "lista"            # lista | titlu | citat | cifra | produs | inainte_dupa | pasi
    IG_FORMAT = "4:5"              # 4:5 | 1:1 | 9:16
    IG_TEXT_CAT = "mediu"          # putin | mediu | mult
    IG_FUNDAL = "inchis"           # inchis | deschis | brand | poza | gradient
    IG_ACCENT = ""
    IG_FONT = "gros"               # gros | elegant | simplu
    IG_BANDA = False
    IG_HANDLE = ""
    IG_CERINTE = ""
    AUTOR_NUME = ""
    AUTOR_URL = ""
    AUTOR_ROL = ""
    ORG_CUI = ""
    ORG_ORAS = ""

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
        # formele ultimelor articole, ca sa nu iasa doua la fel una dupa alta
        self.SCHELETE_RECENTE = list(client.get("schelete_recente") or [])
        # cine semneaza articolele — conteaza si pentru Google, si pentru motoarele cu AI
        self.AUTOR_NUME = c.get("autor_nume") or ""
        self.AUTOR_URL = c.get("autor_url") or ""
        self.AUTOR_ROL = c.get("autor_rol") or ""
        self.ORG_CUI = c.get("cui") or ""
        self.ORG_ORAS = c.get("oras") or ""
        self.IMAGINE_STIL = c.get("imagine_stil") or Config.IMAGINE_STIL
        self.IMAGINE_PALETA = c.get("imagine_paleta") or ""
        self.IMAGINE_EVITA = c.get("imagine_evita") or ""
        self.IMAGINE_LUMINA = c.get("imagine_lumina") or ""
        self.IMAGINE_FORMAT = c.get("imagine_format") or Config.IMAGINE_FORMAT
        self.IMAGINE_TEXT_PE_POZA = c.get("imagine_text_pe_poza") or Config.IMAGINE_TEXT_PE_POZA
        self.IMAGINE_LOGO_LOC = c.get("imagine_logo_loc") or Config.IMAGINE_LOGO_LOC
        self.IMAGINE_LOGO_MARIME = c.get("imagine_logo_marime") or Config.IMAGINE_LOGO_MARIME
        self.IMAGINE_CERINTE = (c.get("imagine_cerinte") or "").strip()

        self.IG_SEPARATA = _bifa(c.get("ig_separata"))
        self.IG_SABLON = c.get("ig_sablon") or Config.IG_SABLON
        self.IG_FORMAT = c.get("ig_format") or Config.IG_FORMAT
        self.IG_TEXT_CAT = c.get("ig_text_cat") or Config.IG_TEXT_CAT
        self.IG_FUNDAL = c.get("ig_fundal") or Config.IG_FUNDAL
        self.IG_ACCENT = (c.get("ig_accent") or "").strip()
        self.IG_FONT = c.get("ig_font") or Config.IG_FONT
        self.IG_BANDA = _bifa(c.get("ig_banda"))
        self.IG_HANDLE = (c.get("ig_handle") or "").strip()
        self.IG_CERINTE = (c.get("ig_cerinte") or "").strip()
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

    def lipsuri_publicare(self, canale: list | None = None) -> list[str]:
        """Ce lipseste ca sa putem publica pe canalele cerute. Inainte se uita
        doar la blog, asa ca un client fara token de Meta „publica" zilnic si
        primea in tacere un „Facebook a esuat" ingropat intr-o nota."""
        lipsa = []
        c = list(canale or ["wp"])
        if "wp" in c and not (self.BLOG_PE_API or self.BLOG_MANUAL):
            if not (self.WP_URL and self.WP_USER and self.WP_APP_PASSWORD):
                lipsa.append("datele blogului: fie WordPress (adresă, utilizator, parolă de APLICAȚIE), "
                             "fie adresa și tokenul API-ului propriu")
        if ("fb" in c or "ig" in c) and not self.META_SYSTEM_USER_TOKEN:
            lipsa.append("tokenul Meta")
        if "fb" in c and not self.META_PAGE_ID:
            lipsa.append("ID-ul paginii de Facebook")
        if "ig" in c and not self.META_IG_ID:
            lipsa.append("ID-ul contului de Instagram")
        if "gbp" in c and not (self.GBP_REFRESH_TOKEN and self.GBP_LOCATION):
            lipsa.append("accesul la Profilul Google")
        return lipsa


config = Config()
