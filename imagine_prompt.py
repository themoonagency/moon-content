"""
Promptul de imagine, scris DUPA ce articolul e gata.

De ce separat: până acum promptul de imagine era un punct dintr-o listă, într-o
cerere de două mii de cuvinte care mai cerea și un articol, și două postări.
Primea cea mai puțină atenție, ieșea „laptop pe birou cu grafice" și nu avea
legătură cu ce scrisese modelul mai sus. Aici primește o cerere numai a lui, cu
articolul terminat în față — deci imaginea ilustrează IDEEA articolului, nu
subiectul lui în general.

Costă un apel mic (~1.200 tokeni intrare, ~150 ieșire ≈ 0,0005 USD pe flash).
Dacă apelul pică, rămâne promptul din generarea mare, deci nu blochează nimic.
"""

from __future__ import annotations
import re

from config import config

# Clișeele care fac o imagine să pară pusă „ca să fie ceva". Lista e explicită
# dinadins: un model care primește „nu fi generic" rămâne generic, unul care
# primește lista exactă o ocolește.
INTERZISE = [
    "laptop or computer screen showing charts, graphs or dashboards",
    "glowing holograms, floating UI panels, futuristic interfaces",
    "circuit boards, neural networks, glowing nodes and connecting lines",
    "robots, androids, humanoid AI, brains made of light",
    "lightbulbs as ideas, upward arrows, bar charts as decoration",
    "handshakes, chess pieces, jigsaw puzzles, ladders, mountain summits",
    "generic open-plan offices, people in suits pointing at a whiteboard",
    "stock-photo smiles, staged teamwork around a table",
    "abstract 'digital transformation' backgrounds, binary code, matrix rain",
    "world maps with glowing connection lines",
    "anything that would work equally well for any other article",
]

# Ce ÎNLOCUIEȘTE clișeul. Pentru servicii — unde nu există un produs de pus în
# poză — răspunsul bun e aproape mereu un moment omenesc, într-un loc real, cu
# obiecte care se pot atinge.
CAI = [
    "un MOMENT dintr-o zi de lucru reală, surprins la firul ierbii: mâinile "
    "cuiva care face exact lucrul despre care e articolul, într-un loc concret "
    "(o tejghea, un atelier, o bucătărie de restaurant, o parcare, un birou mic "
    "și trăit, nu un open-space de catalog)",
    "o NATURĂ STATICĂ cu obiecte adevărate care spun povestea: hârtii, un "
    "carnet, o factură, ambalaje, unelte, o cană pe jumătate băută — aranjate ca "
    "și cum tocmai a plecat cineva de acolo",
    "o METAFORĂ FIZICĂ făcută din lucruri reale, fotografiată ca atare (nu "
    "desenată, nu randată): două grămezi inegale, un raft gol lângă unul plin, "
    "un ceas lăsat pe masă lângă un teanc de comenzi",
    "un DETALIU foarte apropiat dintr-un obiect din poveste, cu textură: "
    "hârtie, lemn, metal zgâriat, un ecran stins care reflectă camera",
]


# Cele opt feluri de imagine din panou. Textul e ce ajunge in prompt.
FELURI = {
    "foto": "Fotografie editorială reală, ca dintr-un reportaj: lumină naturală, "
            "adâncime mică de câmp, imperfecțiuni păstrate.",
    "still": "Natură statică fotografiată de sus sau din lateral, obiecte reale, fără oameni.",
    "ilustratie": "Ilustrație editorială desenată de mână, cu textură de hârtie și tușe "
                  "vizibile — NU randare 3D, NU vectorial curat, NU „modern flat”.",
    "editorial": "Fotografie editorială ca în reviste: compoziție construită, un singur subiect "
                 "clar, spațiu gol lăsat dinadins în cadru.",
    "minimal": "Minimal: UN singur obiect, fundal simplu și uniform, mult spațiu gol, "
               "o singură sursă de lumină.",
    "render3d": "Randare 3D curată, materiale mate, umbre moi, fără reflexii exagerate "
                "și fără aspect de joc video.",
    "abstract": "Forme și gradiente, fără obiecte recognoscibile — culoare, textură și "
                "compoziție, atât.",
    "colaj": "Colaj grafic: decupaje cu margini vizibile, straturi suprapuse, "
             "hârtie texturată sub ele.",
}

LUMINA = {
    "naturala": "lumină naturală de zi, dintr-o fereastră",
    "calda": "lumină caldă, joasă, de apus",
    "studio": "lumină de studio, egală, fără umbre dure",
    "contrast": "contrast puternic, umbre adânci, o singură sursă",
    "inchisa": "fundal închis, subiectul luminat punctual",
}


def _stil() -> str:
    """Stilul vizual al CLIENTULUI, nu al agenției. Înainte era codat dur
    «accente de roșu/coral pe fundal închis» — identitatea THE MOON — și îl
    primeau toți clienții, de la sala de fitness la magazinul de parfumuri.
    De aici veneau imaginile «prea tech»."""
    fel = (config.IMAGINE_STIL or "foto").strip().lower()
    randuri = [FELURI.get(fel) or FELURI["foto"]]

    lumina = LUMINA.get((config.IMAGINE_LUMINA or "").strip().lower())
    if lumina:
        randuri.append(f"Lumina: {lumina}.")

    paleta = (config.IMAGINE_PALETA or "").strip()
    randuri.append(f"Paleta: {paleta}." if paleta
                   else "Paleta: culori naturale, potrivite locului din imagine. "
                        "NU fundal închis cu accente neon — arată a reclamă de software.")
    evita = (config.IMAGINE_EVITA or "").strip()
    if evita:
        randuri.append(f"Clientul nu vrea să apară: {evita}.")
    return " ".join(randuri)


def _regula_text() -> str:
    """Text pe poza de blog: implicit NU. Pe blog titlul e deja lângă imagine,
    iar textul dublat arată prost în Google Imagini. Dacă omul îl cere, îl cerem
    scurt și așezat, nu un paragraf peste poză."""
    fel = (config.IMAGINE_TEXT_PE_POZA or "nu").strip().lower()
    if fel == "titlu":
        return ("- Un SINGUR rând de text pe imagine, maximum 6 cuvinte, scos din titlul "
                "articolului, așezat într-o zonă goală a cadrului. Fără alt text.")
    if fel == "titlu_sub":
        return ("- Text pe imagine: un titlu de maximum 6 cuvinte și un singur rând sub el, "
                "de maximum 10 cuvinte, într-o zonă goală a cadrului. Fără alt text.")
    return "- Fără text, litere, cifre sau logo-uri în imagine."


def _cerinte() -> str:
    """Ce a scris clientul, cu cuvintele lui. Stă LA FINAL dinadins: e ultimul
    lucru pe care îl citește modelul, deci bate listele bifate mai sus."""
    cer = (config.IMAGINE_CERINTE or "").strip()
    if not cer:
        return ""
    return ("\nCE A CERUT CLIENTUL, CU CUVINTELE LUI (bate tot ce scrie mai sus, "
            "în afară de lista NU FOLOSI NICIODATĂ)\n" + cer[:1200])


def _text(html: str, cate: int = 1400) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()[:cate]


def cere(continut: dict) -> str:
    """Cererea trimisă modelului. Separată, ca s-o pot testa fără să dau bani."""
    nisa = config.CLIENT_NICHE or "serviciile clientului"
    return f"""
Ești fotoeditor la o revistă de business. Alegi imaginea care însoțește articolul
de mai jos. NU scrii articolul — doar alegi ce se vede în poză.

ARTICOL
Titlu: {continut.get('seo_title') or continut.get('topic_title') or ''}
Ideea în două rânduri: {continut.get('raspuns_scurt') or continut.get('angle') or ''}
Din text: {_text(continut.get('article_html') or '')}
Domeniul clientului: {nisa}

CUM ALEGI
1. Scrie-ți în minte care e TENSIUNEA articolului — ce se schimbă, ce pierde
   cineva, ce câștigă. Imaginea ilustrează ASTA, nu subiectul în general.
   Un articol despre costuri nu arată „bani”, arată momentul în care cineva se
   uită la un preț și se oprește.
2. Alege UNA dintre căile astea (nu le amesteca):
{chr(10).join('   - ' + c for c in CAI)}
3. Trebuie să fie o scenă care s-ar putea fotografia AZI, cu un aparat, într-un
   loc care există. Dacă ai nevoie de efecte ca să se înțeleagă, ai ales greșit.
4. Pune UN detaliu care leagă imaginea de articolul ăsta și de niciun altul.

NU FOLOSI NICIODATĂ
{chr(10).join('- ' + x for x in INTERZISE)}

STILUL CLIENTULUI
{_stil()}

REGULI DE FORMĂ
- Scrii în ENGLEZĂ, 45-75 de cuvinte, într-un singur paragraf.
- Spui, în ordine: ce se vede (subiect + acțiune) · unde · un detaliu anume ·
  cadrul și obiectivul (ex. „shot on 35mm, waist-level, shallow depth of field”) ·
  lumina · paleta · starea.
{_regula_text()}
- Fără fețe de oameni recognoscibile: mâini, siluete, spatele cuiva, da.
- Fără mărci, fără produse ale concurenței.
- Răspunde DOAR cu paragraful. Fără ghilimele, fără explicații, fără „Prompt:”.
{_cerinte()}
""".strip()


def _pare_slab(prompt: str) -> list:
    """Verificare ieftină: dacă promptul conține tocmai clișeele interzise, mai
    cerem o dată. Ieftin, și prinde exact cazul de care se plânge omul."""
    t = (prompt or "").lower()
    gasite = []
    for cuv, eticheta in [
        ("dashboard", "dashboard"), ("hologram", "hologramă"), ("glowing", "„glowing”"),
        ("circuit", "circuite"), ("neural", "rețea neuronală"), ("futuristic", "futurist"),
        ("robot", "robot"), ("lightbulb", "bec"), ("light bulb", "bec"),
        ("handshake", "strângere de mână"), ("binary code", "cod binar"),
        ("digital transformation", "„digital transformation”"),
        ("floating ui", "UI plutitor"), ("data visualization", "grafic"),
        ("charts", "grafice"), ("graphs", "grafice"), ("neon", "neon"),
    ]:
        if cuv in t:
            gasite.append(eticheta)
    if len(t.split()) < 25:
        gasite.append("prea scurt")
    return gasite


def scrie(continut: dict, cheama) -> str:
    """Promptul de imagine pentru articolul ăsta. `cheama` e funcția care
    vorbește cu modelul (o primim ca parametru ca să putem testa fără rețea).
    Dacă nu iese nimic bun, întoarce '' și rămâne promptul din generarea mare."""
    intrebare = cere(continut)
    ultim = ""
    for incercare in range(2):
        cerere = intrebare if incercare == 0 else (
            intrebare + "\n\nÎNCERCAREA ANTERIOARĂ A FOST RESPINSĂ pentru că folosea: "
            + ", ".join(_pare_slab(ultim)) + ". Alege altă cale din lista de mai sus, "
            "cu obiecte fizice și un loc real."
        )
        try:
            date = cheama({
                "contents": [{"role": "user", "parts": [{"text": cerere}]}],
                "generationConfig": {"temperature": 1.0, "maxOutputTokens": 400},
            })
            ultim = (date["candidates"][0]["content"]["parts"][0]["text"] or "").strip()
        except Exception as e:  # noqa: BLE001 — imaginea nu merită să oprească postarea
            print(f"  promptul de imagine nu a putut fi scris: {str(e)[:150]}")
            return ""
        ultim = ultim.strip().strip('"').strip()
        probleme = _pare_slab(ultim)
        if not probleme:
            return ultim
        print(f"  promptul de imagine avea clișee ({', '.join(probleme)}) — mai cer o dată")
    return ultim or ""
