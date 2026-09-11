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
    "poza": "the article photograph as background, heavily darkened and blurred so the "
            "text stays readable",
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


def _puncte(continut: dict, cate: int) -> list:
    """Punctele de pe afiș, scoase din articol. Întâi H2-urile (sunt deja
    titluri scurte, scrise de model); dacă nu-s destule, primele propoziții."""
    if cate <= 0:
        return []
    html = continut.get("article_html") or ""
    out = [_curat(x, 80) for x in re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S | re.I)]
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


def cere(continut: dict) -> str:
    """Cererea trimisă modelului. Separată, ca s-o pot testa fără să dau bani."""
    cate = CATE.get((config.IG_TEXT_CAT or "mediu").strip().lower(), 3)
    sablon = SABLOANE.get((config.IG_SABLON or "lista").strip().lower(), SABLOANE["lista"])
    sablon = sablon.replace("{n}", str(max(3, cate)))
    titlu = _curat(continut.get("seo_title") or continut.get("topic_title") or "", 90)
    puncte = _puncte(continut, cate)

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


def scrie(continut: dict) -> str:
    """Promptul afișului. Nu cheamă niciun model de text — se construiește din
    articolul deja scris, deci nu costă nimic în plus față de generarea pozei."""
    return cere(continut)
