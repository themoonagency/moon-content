"""
Generare conținut cu Gemini pentru fluxul "autoritate" (fără catalog de
produse — servicii / site de prezentare). Fluxul "catalog" pentru magazine
online e în content_gen_catalog.py (Faza 3, de scris separat).

Pași:
  1. Gemini caută ultimele noutăți din nișa clientului (grounding cu Google
     Search, activat direct din API — nu mai trebuie o cheie separată de
     căutare).
  2. Alege UN subiect care nu a mai fost tratat recent (vezi state.py).
  3. Scrie articolul de blog (SEO+GEO) + 2 postări sociale scurte (FB/IG),
     fiecare cu CTA propriu, nu copy-paste din articol.

Returnează un dict gata de pus în draft (vezi state.save_draft).
"""

from __future__ import annotations
import json
import re
import time
import requests

from config import config
import panel

def _gemini_url() -> str:
    # se calculeaza la fiecare apel: modelul si cheia sunt ale clientului curent
    return (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}"
    )

_LINK = re.compile(r'<a\b[^>]*href=["\'](https?://[^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)


def _link_merge(url: str) -> bool:
    """Chiar exista pagina? Modelele inventeaza adrese de sursa care suna bine
    si dau 404 — un articol cu link mort arata mai rau decat unul fara link."""
    antete = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")}
    for metoda in ("HEAD", "GET"):
        try:
            r = requests.request(metoda, url, headers=antete, timeout=12, allow_redirects=True)
            if r.status_code < 400:
                return True
            if r.status_code in (403, 405) and metoda == "HEAD":
                continue          # unele servere refuza HEAD, incercam GET
            return False
        except requests.RequestException:
            continue
    return False


def curata_linkurile(html: str, permise: set | None = None) -> tuple:
    """Scoate linkurile care nu raspund, pastrand textul. Intoarce si cate a scos."""
    permise = permise or set()
    verdict = {}
    scoase = [0]

    def inlocuieste(m):
        url, text = m.group(1), m.group(2)
        if url in permise or url.rstrip("/") in permise:
            return m.group(0)
        if url not in verdict:
            verdict[url] = _link_merge(url)
        if verdict[url]:
            return m.group(0)
        scoase[0] += 1
        print(f"  link mort scos: {url}")
        return text

    return _LINK.sub(inlocuieste, html or ""), scoase[0]


def _pagini_site() -> str:
    """Paginile citite de panou de pe site-ul clientului. Fara ele, botul scrie
    generic despre domeniu si inventeaza linkuri interne care nu exista."""
    if not config.SITE:
        return ""
    randuri = []
    for p in config.SITE[:20]:
        titlu = (p.get("titlu") or "").strip()
        url = (p.get("url") or "").strip()
        rez = (p.get("rezumat") or "").strip()
        if not url:
            continue
        randuri.append(f"- {titlu} — {url}" + (f"\n  {rez}" if rez else ""))
    if not randuri:
        return ""
    return (
        "\n\nPAGINILE REALE DE PE SITE-UL CLIENTULUI (astea sunt serviciile lui, "
        "asa cum le prezinta el):\n" + "\n".join(randuri) +
        "\n\nFoloseste-le ca material: scrie despre ce chiar ofera, nu despre domeniu in general. "
        "Astea sunt singurele adrese de pe site-ul clientului pe care ai voie sa le folosesti. "
        "Cand trimiti cititorul spre un serviciu, pune LINK catre pagina exacta din lista de mai sus "
        "(2-3 linkuri interne in articol, in text, nu la final). "
        "NU inventa pagini, servicii, preturi sau adrese care nu apar in lista."
    )


def _subiect_impus() -> str:
    """Subiectul bifat de om in panou bate alegerea AI-ului."""
    idee = config.IDEE or {}
    titlu = (idee.get("titlu") or "").strip()
    if not titlu:
        return ""
    unghi = (idee.get("unghi") or "").strip()
    return (
        "\n\nSUBIECTUL E DEJA ALES, nu cauta altul:\n"
        f"- subiect: {titlu}\n" + (f"- unghiul cerut: {unghi}\n" if unghi else "") +
        "Scrie despre exact asta. Poti cauta stiri recente ca sa-l sustii, dar nu schimba tema."
    )


def _system_prompt() -> str:
    return f"""
Ești redactorul AI al agenției {config.CLIENT_NAME} ({config.CLIENT_DOMAIN}).
Nișa clientului: {config.CLIENT_NICHE}.
Ton de voce: {config.CLIENT_TONE}.
{("Subiecte preferate de client (alege din zona asta cand se poate): " + config.CLIENT_SUBIECTE) if config.CLIENT_SUBIECTE else ""}

Scrii conținut pentru fluxul "autoritate" — fără produse, fără catalog.
Cauți o noutate/tendință recentă și relevantă din nișă, apoi scrii:

1. Un ARTICOL DE BLOG (600-900 cuvinte), optimizat SEO și GEO:
   - Titlu unic, atractiv, sub 65 caractere
   - Meta description sub 155 caractere
   - Un singur H1 (= titlul), apoi structură cu H2/H3
   - Răspunde clar la o întrebare concretă chiar din prima secțiune
     (ușor de citat de un AI — ChatGPT/Perplexity/Gemini)
   - Include, dacă citezi o cifră sau un fapt din știre, sursa (nume + link
     dacă îl ai)
   - Se încheie cu un CTA spre serviciile {config.CLIENT_NAME}{(", formulat asa: " + config.CLIENT_CTA) if config.CLIENT_CTA else ""}
     NU pune tu link sau buton la CTA — se adaugă automat după generare.
2. Un TEXT PENTRU FACEBOOK (sub 400 caractere), NU e copy-paste din articol
   — unghi propriu, CTA propriu, poate pune o întrebare la final.

3. Un TEXT PENTRU INSTAGRAM (sub 300 caractere), ton mai vizual/scurt,
   3-5 hashtag-uri relevante la final.

4. Un PROMPT DE IMAGINE (în engleză, pentru un generator de imagini) —
   TREBUIE să fie foarte concret și descriptiv, NU generic. Reguli stricte
   pentru promptul de imagine:
   - Pornește de la un ELEMENT VIZUAL SPECIFIC din articol (nu "modern tech
     office", nu "person using laptop with charts" — alege un detaliu
     concret: un obiect, o scenă, o metaforă vizuală legată de subiectul
     exact al articolului)
   - Descrie explicit: compoziția (prim-plan/fundal, unghi de cameră),
     iluminarea (ex. "dramatic side lighting", "soft morning light"),
     paleta de culori (preferă accente de roșu/coral pe fundal închis —
     identitatea vizuală a agenției — fără să ceară text sau logo-uri
     suprapuse, alea se adaugă separat)
   - Stil: fotografie editorială high-end sau ilustrație 3D modernă,
     NICIODATĂ stil de stock photo generic sau clip-art
   - 2-4 propoziții, cât mai concret posibil — un generator de imagini
     produce rezultate mult mai bune din descrieri specifice decât din
     concepte abstracte
   - Fără text suprapus în imagine, fără logo-uri sau mărci concurente,
     fără persoane reale identificabile

REGULI STRICTE:
- NU repeta subiecte tratate recent (lista e mai jos) — alege altceva.
- NU inventa cifre sau citate. Dacă nu ești sigur de o cifră, nu o pune.
- NU inventa ADRESE WEB. Pui un link doar dacă adresa exactă a apărut în rezultatele
  căutării pe care tocmai ai făcut-o. Dacă vrei să citezi o sursă și nu ai adresa ei
  exactă, scrie doar numele sursei, fără link. Un link inventat care dă 404 strică
  mai mult decât lipsa lui — oricum le verificăm pe toate înainte de publicare.
- Răspunde DOAR cu un obiect JSON valid, fără text în plus, fără ```json.
- FOARTE IMPORTANT pentru JSON valid: în interiorul textelor (title, article_html
  etc.) NU folosi niciodată ghilimele duble drepte ("). Dacă ai nevoie de un
  citat sau de accent pe un cuvânt, folosește ghilimele unghiulare « » sau
  apostrof simplu ('), niciodată ".

Format JSON exact:
{{
  "topic_title": "...",
  "angle": "un rezumat de o propoziție al unghiului ales",
  "seo_title": "...",
  "meta_description": "...",
  "article_html": "<h1>...</h1><p>...</p>...",
  "facebook_text": "...",
  "instagram_text": "...",
  "image_prompt": "..."
}}
"""



def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    # Gemini (mai ales cu grounding activ) poate adăuga text în plus înainte/după
    # obiectul JSON (ex. note despre surse) — păstrăm doar ce e între prima
    # și ultima acoladă.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    # strict=False permite caractere de control (linii noi brute) în interiorul
    # șirurilor — articolul HTML vine des cu \n literali, nu escapați, ceea ce
    # strică parsarea JSON strictă altfel.
    return json.loads(text, strict=False)


REPAIR_PROMPT = """Textul de mai jos ar trebui să fie un obiect JSON valid, dar
are o eroare de sintaxă (probabil ghilimele duble nescăpate în interiorul unui
text, sau alt caracter care strică JSON-ul). Repară-l și răspunde DOAR cu
obiectul JSON corect, fără alt text, fără ```json. Păstrează tot conținutul —
schimbă doar ce e strict necesar ca JSON-ul să fie valid (ex. înlocuiește
ghilimelele duble din interiorul textelor cu ghilimele unghiulare « » sau
apostrof simplu).

TEXT DE REPARAT:
{broken}
"""


def _repair_json(broken_text: str) -> dict:
    payload = {
        "contents": [{"role": "user", "parts": [{"text": REPAIR_PROMPT.format(broken=broken_text)}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 8192},
    }
    data = _call_gemini(payload)
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return _extract_json(text)


# consumul ultimei generări, citit de generate_draft.py și trimis în panou
CONSUM = {"tokens_in": 0, "tokens_out": 0}


def _aduna_consum(data: dict) -> None:
    u = (data or {}).get("usageMetadata") or {}
    CONSUM["tokens_in"] += int(u.get("promptTokenCount") or 0)
    CONSUM["tokens_out"] += int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0)


def _call_gemini(payload: dict, max_retries: int = 4) -> dict:
    """Apel Gemini cu reîncercare la 429 (limită de rată) — cotele Gemini
    sunt pe proiect și se pot atinge temporar, mai ales pe modele mari."""
    delay = 8
    last_error = None
    for attempt in range(max_retries):
        resp = requests.post(_gemini_url(), json=payload, timeout=90)
        if resp.status_code == 429:
            last_error = resp
            time.sleep(delay)
            delay = min(delay * 2, 60)
            continue
        resp.raise_for_status()
        data = resp.json()
        _aduna_consum(data)
        return data
    last_error.raise_for_status()


def generate_authority_draft() -> dict:
    CONSUM["tokens_in"] = CONSUM["tokens_out"] = 0
    used_topics = panel.subiecte_recente(config.CLIENT_ID, zile=45)
    if config.BLOG_PE_API:
        # blogul propriu isi stie articolele; le luam si pe alea, ca sa nu repetam
        from publishers import blog_api
        for t in blog_api.articole_existente():
            if t not in used_topics:
                used_topics.append(t)
    used_block = "\n".join(f"- {t}" for t in used_topics) or "(niciunul încă)"

    prompt = (_system_prompt() + _pagini_site() + _subiect_impus() +
              f"\n\nSubiecte tratate în ultimele 45 de zile (NU le relua):\n{used_block}\n")

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 8192,
        },
    }

    data = _call_gemini(payload)

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Răspuns Gemini neașteptat: {json.dumps(data)[:500]}") from e

    try:
        parsed = _extract_json(text)
    except json.JSONDecodeError:
        # JSON invalid (de obicei ghilimele nescăpate în text) — încercăm o
        # reparație automată printr-un al doilea apel Gemini, mai ieftin
        # decât să pierdem toată generarea și subiectul ales.
        parsed = _repair_json(text)

    required = [
        "topic_title", "angle", "seo_title", "meta_description",
        "article_html", "facebook_text", "instagram_text", "image_prompt",
    ]
    missing = [k for k in required if not parsed.get(k)]
    if missing:
        raise RuntimeError(f"Câmpuri lipsă din răspunsul Gemini: {missing}")

    return parsed
