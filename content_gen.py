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
import json
import re
import time
import requests

from config import config
from state import recent_topic_titles

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}"
)

SYSTEM_PROMPT = f"""
Ești redactorul AI al agenției {config.CLIENT_NAME} ({config.CLIENT_DOMAIN}).
Nișa clientului: {config.CLIENT_NICHE}.
Ton de voce: {config.CLIENT_TONE}.

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
   - Se încheie cu un CTA spre serviciile {config.CLIENT_NAME}
2. Un TEXT PENTRU FACEBOOK (sub 400 caractere), NU e copy-paste din articol
   — unghi propriu, CTA propriu, poate pune o întrebare la final.

3. Un TEXT PENTRU INSTAGRAM (sub 300 caractere), ton mai vizual/scurt,
   3-5 hashtag-uri relevante la final.

4. Un PROMPT DE IMAGINE (în engleză, pentru un generator de imagini):
   descriere concretă a unei imagini relevante pentru articol — stil
   fotografic modern, curat, fără text suprapus în imagine, fără logo-uri
   sau mărci concurente, fără persoane reale identificabile.

REGULI STRICTE:
- NU repeta subiecte tratate recent (lista e mai jos) — alege altceva.
- NU inventa cifre sau citate. Dacă nu ești sigur de o cifră, nu o pune.
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


def _call_gemini(payload: dict, max_retries: int = 4) -> dict:
    """Apel Gemini cu reîncercare la 429 (limită de rată) — cotele Gemini
    sunt pe proiect și se pot atinge temporar, mai ales pe modele mari."""
    delay = 8
    last_error = None
    for attempt in range(max_retries):
        resp = requests.post(GEMINI_URL, json=payload, timeout=90)
        if resp.status_code == 429:
            last_error = resp
            time.sleep(delay)
            delay = min(delay * 2, 60)
            continue
        resp.raise_for_status()
        return resp.json()
    last_error.raise_for_status()


def generate_authority_draft() -> dict:
    used_topics = recent_topic_titles(days=45)
    used_block = "\n".join(f"- {t}" for t in used_topics) or "(niciunul încă)"

    prompt = SYSTEM_PROMPT + f"\n\nSubiecte tratate în ultimele 45 de zile (NU le relua):\n{used_block}\n"

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
