"""
Fluxul „catalog": postări despre un produs anume din magazinul clientului.

Diferența față de fluxul „autoritate" nu e doar promptul. Aici NU inventăm nimic:
numele, prețul, linkul și descrierea vin din catalogul sincronizat în panou, iar
panoul alege și ce produs urmează la rând (`client["produs"]`) — motorul doar
scrie despre ce primește. Așa rotația și anti-repetiția stau într-un singur loc.
"""

from __future__ import annotations
import json

from config import config
from content_gen import CONSUM, _call_gemini, _extract_json, _repair_json


def _pret(p: dict) -> str:
    if p.get("pret") in (None, ""):
        return ""
    m = p.get("moneda") or "RON"
    s = f"{p['pret']} {m}"
    vechi = p.get("pret_vechi")
    if vechi and float(vechi) > float(p["pret"]):
        s += f" (redus de la {vechi} {m})"
    return s


def _conexe(p: dict) -> str:
    l = p.get("conexe") or []
    if not l:
        return "  (magazinul nu are alte produse potrivite acum)"
    randuri = []
    for c in l:
        pret = f"{c['pret']} {c.get('moneda') or 'RON'}" if c.get("pret") not in (None, "") else "fără preț"
        randuri.append(f"  - {c['nume']} — {pret} — {c['url']}")
    return "\n".join(randuri)


def _prompt(p: dict) -> str:
    return f"""
Ești redactorul magazinului {config.CLIENT_NAME} ({config.CLIENT_DOMAIN}).
Ton de voce: {config.CLIENT_TONE}.

Scrii despre UN SINGUR produs din catalog. Datele lui, exact așa cum sunt în magazin:

  Nume: {p.get('nume')}
  Preț: {_pret(p) or 'nespecificat'}
  Categorie: {p.get('categorii') or '—'}
  Marcă: {p.get('brand') or '—'}
  Link: {p.get('url')}
  Descriere din magazin: {(p.get('descriere') or '')[:900]}

Alte produse din magazin, care pot merge împreună cu el:
{_conexe(p)}

REGULI STRICTE, mai importante decât stilul:
- NU inventa caracteristici, dimensiuni, materiale, garanții sau comparații cu alte produse.
  Dacă descrierea din magazin nu spune ceva, nu spui nici tu.
- NU inventa reduceri sau termene („doar azi", „ultimele bucăți") dacă nu reies din datele de mai sus.
- Prețul se scrie EXACT ca mai sus, sau deloc.
- Linkul se pune ca atare, fără parametri adăugați.
- Scrii în română, cu diacritice.

Produci:

1. Un ARTICOL SCURT de blog (300-450 cuvinte): la ce folosește produsul, cui i se
   potrivește, ce e de știut înainte de cumpărare. Un singur H1 (titlul), apoi H2.
   OBLIGATORIU, dacă lista de mai sus nu e goală, o secțiune spre final cu titlul
   „Merge bine cu" și 2-3 dintre acele produse, fiecare pe rândul lui, ca link
   <a href="LINKUL EXACT">Numele produsului</a> urmat de o propoziție scurtă care
   spune DE CE merge cu produsul principal. Nu inventa produse care nu sunt în listă
   și nu schimba linkurile.
   Se încheie cu un îndemn și linkul produsului principal.
{('   Îndemnul preferat al clientului: ' + config.CLIENT_CTA) if config.CLIENT_CTA else ''}

2. Un TEXT PENTRU FACEBOOK (sub 400 caractere) — un unghi, nu o listă de specificații.
   Include prețul și linkul.

3. Un TEXT PENTRU INSTAGRAM (sub 300 caractere), 3-5 hashtaguri la final.
   Pe Instagram linkul nu e clicabil, deci trimite la „linkul din bio".

4. Un PROMPT DE IMAGINE în engleză. Poza reală a produsului va fi punctul de plecare,
   iar promptul spune doar CE E ÎN JURUL LUI: suprafața pe care stă, fundalul,
   lumina, recuzita, atmosfera. Reguli:
   - NU descrie produsul în sine (forma, culoarea, eticheta) — el rămâne neschimbat.
   - Scenă concretă, potrivită cu la ce se folosește produsul, nu „studio background".
   - Spune lumina și unghiul (ex. „soft window light from the left, 45-degree angle").
   - Fără text, fără logo-uri, fără persoane recognoscibile.
   - 2-3 propoziții.

Răspunde DOAR cu un obiect JSON valid, fără text în plus, fără ```json.
În interiorul textelor NU folosi ghilimele duble drepte; folosește « » sau apostrof.

Format exact:
{{
  "topic_title": "...",
  "angle": "o propoziție despre unghiul ales",
  "seo_title": "...",
  "meta_description": "...",
  "article_html": "<h1>...</h1><p>...</p>...",
  "facebook_text": "...",
  "instagram_text": "...",
  "image_prompt": "..."
}}
"""


def genereaza_pentru_produs(produs: dict) -> dict:
    """Întoarce același dict ca fluxul de autoritate, ca restul codului să nu știe
    din care flux vine ciorna."""
    CONSUM["tokens_in"] = CONSUM["tokens_out"] = 0

    payload = {
        "contents": [{"role": "user", "parts": [{"text": _prompt(produs)}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096},
    }
    date = _call_gemini(payload)
    try:
        text = date["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Răspuns Gemini neașteptat: {json.dumps(date)[:500]}") from e

    try:
        parsed = _extract_json(text)
    except json.JSONDecodeError:
        parsed = _repair_json(text)

    lipsa = [k for k in ("seo_title", "article_html", "facebook_text", "instagram_text") if not parsed.get(k)]
    if lipsa:
        raise RuntimeError(f"Câmpuri lipsă din răspunsul Gemini: {lipsa}")

    parsed.setdefault("topic_title", produs.get("nume") or "")
    parsed.setdefault("angle", "postare de catalog")
    parsed.setdefault("meta_description", "")
    parsed.setdefault("image_prompt", "")
    return parsed
