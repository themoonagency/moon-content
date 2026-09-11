"""
Afișul de Instagram — a doua imagine a unei ciorne.

De ce separat de poza de blog: pe blog câștigă textul, imaginea doar îl
însoțește. Pe Instagram e pe dos — omul derulează și se oprește la ce citește
PE poză, nu la ce scrie sub ea. Aceeași fotografie editorială, mutată acolo,
trece neobservată.

Deci aici nu cerem o fotografie, ci un AFIȘ: titlu mare, câteva puncte scurte,
o linie de accent, banda de brand jos. Textul nu-l scrie clientul — se scoate
din articolul deja generat și se scurtează cât încape.

Costă încă o generare de imagine pe postare. De asta bifa se pune de la pachetul
Zilnic în sus, unde prețul o acoperă.
"""

from __future__ import annotations
import html as html_lib
import re

from config import config

# Cate puncte incap fara sa se micsoreze literele sub ce se poate citi pe telefon.
CATE = {"putin": 0, "mediu": 3, "mult": 5}

SABLOANE = {
    "lista": "a bold poster: one large headline at the top, a short accent rule under it, "
             "then {n} rows, each with a simple flat icon on the left and a two-to-four word "
             "bold label with one short line of text under it",
    "titlu": "a single huge headline filling most of the frame, one short line under it, "
             "and a lot of empty space — nothing else",
    "citat": "a large pull quote in quotation marks, centered, with a small attribution line "
             "under it and a thin accent rule above",
    "cifra": "one very large number or percentage taking the upper half, and a single "
             "explanatory sentence under it",
    "produs": "the product photographed large on the left two thirds, and {n} short benefit "
              "lines stacked on the right, each with a small icon",
    "inainte_dupa": "the frame split in two halves with a thin divider, labelled BEFORE and "
                    "AFTER in the client's language, each half with one short line of text",
    "pasi": "{n} numbered steps stacked vertically, each number in a filled circle, "
            "each step a short bold line",
}

FUNDAL = {
    "inchis": "near-black background (#0b0b0f), text in white",
    "deschis": "near-white background (#f6f6f8), text in near-black",
    "brand": "a solid background in the client's brand colour, text in whichever of "
             "white or near-black actually contrasts with it",
    # modelul NU primeste poza de blog: isi face singur o fotografie pe subiect (asa scrie si in panou)
    "poza": "a photograph that fits the article's subject as background, heavily darkened and "
            "blurred so the text stays readable",
    "gradient": "a smooth gradient built from the client's brand colours, text in whichever "
                "of white or near-black actually contrasts with it",
}

FONT = {
    "gros": "a heavy, wide grotesque sans-serif, tight letter spacing",
    "elegant": "an elegant serif with high contrast strokes",
    "simplu": "a plain, light sans-serif with generous letter spacing",
}


# Cuvinte dupa care o fraza nu se poate opri: „…pentru e-commerce în" arata a greseala.
LEGATURI = {"în", "in", "de", "din", "pentru", "la", "cu", "pe", "și", "si", "sau", "un", "o",
            "a", "al", "ale", "ai", "că", "ca", "care", "mai", "despre", "prin", "spre", "fără",
            "fara", "sub", "după", "dupa", "între", "intre", "ce", "cum", "cât", "cat", "și/sau"}


def _curat(t: str, cate: int) -> str:
    """Text curat, scurtat DOAR la cuvinte intregi. Pana pe 11 sept se taia la 60 de
    caractere oriunde pica, iar pe afis au iesit „…SEO și GEO pentru e-commerce în"
    si „…pentru un". Un H2 care incape ramane intreg; unul prea lung se opreste la
    ultimul cuvant plin, fara legatura atarnata la coada, cu „…"."""
    t = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()
    if len(t) <= cate:
        return t
    cuv = t[:cate + 1].split(" ")[:-1]
    while cuv and cuv[-1].lower().strip(",;:–-") in LEGATURI:
        cuv.pop()
    return " ".join(cuv).rstrip(" ,;:–-") + "…"


# Un H2 pana la atata incape intreg pe afis (trei randuri); peste, se rescrie scurt.
LIMITA_PUNCT = 80
TINTA_SCURT = 65

CERE_SCURT = """Scurtează titlurile de mai jos pentru un afiș de Instagram. Fiecare devine
o etichetă de cel mult {tinta} de caractere, în română cu diacritice, cu ACELAȘI sens,
formulată complet: fără „…", fără cuvinte tăiate, fără ghilimele. Nu adăuga cifre,
prețuri sau informații care nu sunt în titlu. Răspunde DOAR cu lista numerotată, câte
una pe rând, în aceeași ordine.

{lista}"""


def _scurtate(lungi: list, cheama) -> list | None:
    """Rescrie scurt, printr-un apel ieftin de text, H2-urile care nu incap. Pana pe 11 sept
    se taiau cu „…" (pe afisul THE MOON: „…un venit de 22 de ori mai mare decât…"). Intoarce
    None daca raspunsul nu e bun — atunci ramane taierea la cuvant intreg."""
    if not lungi or cheama is None:
        return None
    lista = "\n".join(f"{i}. {x}" for i, x in enumerate(lungi, 1))
    try:
        date = cheama({"contents": [{"role": "user", "parts": [{"text": CERE_SCURT.format(tinta=TINTA_SCURT, lista=lista)}]}],
                       "generationConfig": {"temperature": 0.3, "maxOutputTokens": 400}})
        text = date["candidates"][0]["content"]["parts"][0]["text"] or ""
    except Exception as e:  # noqa: BLE001 — afisul nu merita sa opreasca postarea
        print(f"  punctele afisului n-au putut fi scurtate: {str(e)[:120]}")
        return None
    randuri = [re.sub(r"^\s*\d+[.)]\s*", "", r).strip().strip('"„”«»') for r in text.splitlines()]
    randuri = [r for r in randuri if r]
    if len(randuri) != len(lungi):
        return None
    if any(len(r) > LIMITA_PUNCT or "…" in r or "..." in r or len(r) < 4 for r in randuri):
        return None
    return randuri


def _puncte(continut: dict, cate: int, cheama=None) -> list:
    """Punctele de pe afiș, scoase din articol. Întâi H2-urile (sunt deja
    titluri scurte, scrise de model); dacă nu-s destule, primele propoziții.
    Un H2 prea lung se rescrie scurt (`cheama`), iar fără model se taie la cuvânt întreg."""
    if cate <= 0:
        return []
    html = continut.get("article_html") or ""
    h2 = [_curat(x, 10 ** 6) for x in re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S | re.I)]
    h2 = [x for x in h2 if len(x) > 3][:cate]
    lungi = [x for x in h2 if len(x) > LIMITA_PUNCT]
    scurte = dict(zip(lungi, _scurtate(lungi, cheama) or [])) if lungi else {}
    out = [scurte.get(x) or _curat(x, LIMITA_PUNCT) for x in h2]
    out = [x for x in out if len(x) > 3]
    if len(out) < cate:
        text = _curat(html, 1200)
        for fraza in re.split(r"(?<=[.!?])\s+", text):
            fraza = fraza.strip()
            if 20 < len(fraza) <= 90 and fraza not in out:
                out.append(fraza)
            if len(out) >= cate:
                break
    return out[:cate]


def cere(continut: dict, cheama=None) -> str:
    """Cererea trimisă modelului. Separată, ca s-o pot testa fără să dau bani."""
    cate = CATE.get((config.IG_TEXT_CAT or "mediu").strip().lower(), 3)
    sablon = SABLOANE.get((config.IG_SABLON or "lista").strip().lower(), SABLOANE["lista"])
    sablon = sablon.replace("{n}", str(max(3, cate)))
    titlu = _curat(continut.get("seo_title") or continut.get("topic_title") or "", 90)
    puncte = _puncte(continut, cate, cheama)

    accent = (config.IG_ACCENT or "").strip() or "a single strong accent colour"

    cerinte = (config.IG_CERINTE or "").strip()
    cerinte = ("\n\nWHAT THE CLIENT ASKED FOR, IN THEIR OWN WORDS (this outranks everything "
               "above except the text you must render)\n" + cerinte[:800]) if cerinte else ""

    randuri = [f'Headline (render exactly, do not translate, do not rewrite): "{titlu}"']
    for i, p in enumerate(puncte, 1):
        randuri.append(f'Point {i} (render exactly): "{p}"')

    return f"""
Design a social media poster image. This is a GRAPHIC DESIGN task, not a photograph.

LAYOUT
{sablon}.

TEXT TO RENDER — spell every character exactly as given, in Romanian, with the
Romanian diacritics kept (ă â î ș ț). Do not add any other words.
{chr(10).join(randuri)}

STYLE
- Background: {FUNDAL.get((config.IG_FUNDAL or 'inchis').strip().lower(), FUNDAL['inchis'])}.
- Type: {FONT.get((config.IG_FONT or 'gros').strip().lower(), FONT['gros'])}.
- Accent colour: {accent}. Used for the rule under the headline, the icons and nothing else.
- Client's palette: {(config.IMAGINE_PALETA or 'neutral').strip()}.
- Flat vector icons, single colour, no gradients inside them, no emoji.
- Generous margins. Nothing closer than 6% of the width to any edge.
- Do not draw a logo, a footer strip, a handle or a web address: the client's footer
  with logo and address is added afterwards, below this image.

RULES
- The headline must be the largest thing in the frame and readable on a phone at
  thumbnail size.
- No lorem ipsum, no placeholder text, no watermark, no stock-photo look.
- No extra decorative text, no fake UI, no fake logos of other brands.
- Everything must fit: if a line is long, make the type smaller, never cut a word.
{cerinte}

Answer with the image only.
""".strip()


def scrie(continut: dict, cheama=None) -> str:
    """Promptul afișului, construit din articolul deja scris. Modelul de text e chemat doar
    când un H2 nu încape pe afiș (un apel mic, sub o zecime de ban), ca să nu apară „…"."""
    return cere(continut, cheama)
