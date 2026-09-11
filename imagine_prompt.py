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
from datetime import date
import random
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
    "a notebook or notepad with a handwritten list, a pen and a cup of coffee on a "
    "wooden desk — it has been used four times already, it is the new cliche",
    "anything that would work equally well for any other article",
]

# Ce ÎNLOCUIEȘTE clișeul: FELUL cadrului, nu ce e în el. Până pe 11 sept căile
# aveau exemple concrete (depozit, rampă de marfă, ambalaje, comenzi, tejghea), iar
# modelul copia exemplele în loc să ia lumea articolului: un articol despre cât
# costă SEO a primit un depozit cu „FULFILL FASTER" pe un panou. Aici stă doar
# forma; locul, obiectele și oamenii vin din articol.
CAI = [
    ("moment", "un MOMENT dintr-o zi de lucru reală, surprins pe viu: mâinile cuiva care "
               "face exact lucrul despre care e articolul, în locul în care se face de obicei"),
    ("natura-statica", "o NATURĂ STATICĂ cu obiectele adevărate ale subiectului, aranjate ca "
                       "și cum tocmai a plecat cineva de lângă ele. NU pe un birou și NU cu un carnet."),
    ("metafora", "o METAFORĂ FIZICĂ făcută din lucruri reale din lumea subiectului, "
                 "fotografiată ca atare (nu desenată, nu randată): un contrast sau o comparație "
                 "care se vede dintr-o privire"),
    ("detaliu", "un DETALIU foarte apropiat al unui obiect central pentru subiect, cu textură "
                "vizibilă: materialul, uzura, lumina pe el"),
    ("locul-gol", "LOCUL în care se întâmplă subiectul articolului, fotografiat larg, fără "
                  "oameni și fără obiecte puse anume — doar locul, așa cum e"),
    ("de-sus", "SCENA VĂZUTĂ DE SUS, de la înălțimea unui om în picioare: tot spațiul de "
               "lucru al subiectului, plan larg, nu prim-plan, cu aer în jur"),
    ("in-miscare", "CEVA ÎN MIȘCARE din lumea subiectului, prins cu o urmă de blur: un gest, "
                   "un obiect care trece, o ușă, o foaie"),
]


def _cale() -> tuple:
    """Aceeași rotație ca la scheletul articolului. Lăsat să aleagă singur,
    modelul lua de fiecare dată calea cea mai sigură — de-aia ieșeau patru poze
    la rând cu un carnet pe un birou de lemn. Alegem NOI, și ocolim ce s-a
    folosit ultima oară."""
    i = (date.today().toordinal() + int(config.CLIENT_ID or 0)) % len(CAI)
    return CAI[i]


def _deja_vazute() -> str:
    """Scenele ultimelor poze ale clientului. Blocul ăsta e singurul lucru care
    știe ce a mai ieșit; fără el fiecare generare pornește de la zero și nimeni
    nu observă că a nimerit a cincea oară în același loc."""
    vechi = [str(x).strip() for x in (config.IMAGINI_RECENTE or []) if str(x).strip()]
    if not vechi:
        return ""
    return ("\n\nPOZELE ANTERIOARE ALE ACESTUI CLIENT (nu repeta scena, locul, obiectul "
            "principal sau unghiul din niciuna):\n"
            + "\n".join("- " + x[:180] for x in vechi[:6]))


# Cele opt feluri de imagine din panou. Textul e ce ajunge in prompt.
FELURI = {
    "foto": "Fotografie editorială reală cu un CONCEPT clar, ca dintr-un reportaj de revistă: "
            "lumină naturală, adâncime mică de câmp, imperfecțiuni păstrate.",
    "still": "Natură statică fotografiată de sus sau din lateral, obiecte reale, fără oameni.",
    "ilustratie": "Ilustrație editorială conceptuală, ca pe coperta unei reviste de business: o idee "
                  "vizuală deșteaptă, desenată de mână, cu textură de hârtie și tușe vizibile — "
                  "NU randare 3D, NU vectorial curat, NU „modern flat”.",
    "editorial": "Fotografie editorială ca în reviste: compoziție construită, un singur subiect "
                 "clar, spațiu gol lăsat dinadins în cadru.",
    "minimal": "Minimal: UN singur obiect-simbol pentru ideea articolului, fundal simplu și uniform, "
               "mult spațiu gol, o singură sursă de lumină.",
    "render3d": "Randare 3D conceptual: o scenă-metaforă construită din forme și obiecte simple, "
                "materiale mate, umbre moi, lumină de studio, fără reflexii exagerate și fără "
                "aspect de joc video.",
    "izometric": "Scenă izometrică 3D, ca o machetă văzută de sus la 30°: o mini-lume care arată "
                 "ideea articolului (locuri, etape, fluxuri) cu obiecte mici și clare, culori curate, "
                 "fundal simplu.",
    "duoton": "Fotografie editorială în duoton — două culori puternice, luate din paleta clientului — "
              "cu contrast grafic de afiș și un singur subiect clar.",
    "abstract": "Forme și gradiente, fără obiecte recognoscibile — culoare, textură și "
                "compoziție, atât.",
    "colaj": "Colaj grafic: decupaje cu margini vizibile, straturi suprapuse, "
             "hârtie texturată sub ele.",
    "coperta": "Fotografie editorială conceptuală pentru o COPERTĂ de articol: subiectul stă în "
               "treimea dreaptă a cadrului, iar jumătatea stângă e calmă, simplă și mai întunecată — "
               "acolo se așază titlul, pus separat. Fără niciun text în imagine.",
}

# Felurile care se fotografiază (li se cere o scenă care există). Celelalte se construiesc.
FOTOGRAFICE = {"foto", "still", "editorial", "minimal", "duoton", "coperta"}

# Rulaj fără nimic bifat: un amestec care arată diferit de la o postare la alta.
RULAJ_IMPLICIT = ["foto", "ilustratie", "render3d", "izometric", "coperta"]


def fel_azi() -> str:
    """Felul pozei pentru ciorna în lucru: cel ales de `alege_fel()` la începutul ei,
    altfel cel din panou (un „rulaj" nealeas încă înseamnă fotografie)."""
    fel = (config.FEL_AZI or config.IMAGINE_STIL or "foto").strip().lower()
    return fel if fel in FELURI else "foto"


def alege_fel() -> str:
    """Felul pozei principale pentru postarea asta. Pe „rulaj" se alege ALEATOR dintre
    felurile bifate în panou, fără ultimele două folosite (dacă rămâne din ce alege).
    Pus pe 11 sept: toate pozele THE MOON Agency ieșeau la fel — foto, negru-alb-roșu."""
    fel = (config.IMAGINE_STIL or "foto").strip().lower()
    if fel != "rulaj":
        return fel if fel in FELURI else "foto"
    bifate = [x.strip().lower() for x in str(config.IMAGINE_RULAJ or "").split(",")]
    bifate = list(dict.fromkeys(x for x in bifate if x in FELURI)) or list(RULAJ_IMPLICIT)
    recente = [str(x).strip().lower() for x in (config.FELURI_RECENTE or []) if x]
    for cate in (2, 1):
        rest = [x for x in bifate if x not in recente[:cate]]
        if rest:
            return random.choice(rest)
    return random.choice(bifate)

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
    randuri = [FELURI[fel_azi()]]

    lumina = LUMINA.get((config.IMAGINE_LUMINA or "").strip().lower())
    if lumina:
        randuri.append(f"Lumina: {lumina}.")

    paleta = (config.IMAGINE_PALETA or "").strip()
    # Paleta e o DIRECTIE. Pusa ca regula, colora fiecare poza la fel (THE MOON Agency:
    # negru-alb-rosu pe toate, 11 sept) si pozele nu se mai deosebeau una de alta.
    randuri.append(f"Paleta clientului, ca direcție: {paleta}. Folosește-o la accente, lumină sau "
                   f"un obiect — nu vopsi tot cadrul în ea; pozele trebuie să arate diferit una de alta."
                   if paleta
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
    if fel_azi() == "coperta":
        fel = "nu"          # pe coperta titlul il scrie codul, deci modelul nu scrie nimic
    if fel == "titlu":
        return ("- Un SINGUR rând de text pe imagine, maximum 6 cuvinte, scos din titlul "
                "articolului, așezat într-o zonă goală a cadrului. Fără alt text.")
    if fel == "titlu_sub":
        return ("- Text pe imagine: un titlu de maximum 6 cuvinte și un singur rând sub el, "
                "de maximum 10 cuvinte, într-o zonă goală a cadrului. Fără alt text.")
    return ("- Fără text, litere, cifre sau logo-uri în imagine — nici în scenă: fără panouri, "
            "firme, afișe, etichete sau ștampile cu litere pe ele.")


def fara_text_la_generare() -> str:
    """Regula de text pusă și pe cererea către modelul de IMAGINE. Paragraful scris
    de fotoeditor n-o ducea mai departe, iar pe 11 sept poza de blog a ieșit cu
    „FULFILL FASTER" pe un panou, deși clientul alesese „fără text"."""
    fel = (config.IMAGINE_TEXT_PE_POZA or "nu").strip().lower()
    if fel in ("titlu", "titlu_sub") and fel_azi() != "coperta":
        return ""
    return " No text, letters, numbers, signs, labels or logos anywhere in the image."


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
    nume_cale, forma_cale = _cale()
    titlu = continut.get('seo_title') or continut.get('topic_title') or ''
    regula_scena = ("Trebuie să fie o scenă care s-ar putea fotografia AZI, cu un aparat, într-un\n"
                    "   loc care există. Dacă ai nevoie de efecte ca să se înțeleagă, ai ales greșit."
                    if fel_azi() in FOTOGRAFICE else
                    "Imaginea se CONSTRUIEȘTE în stilul de mai jos, dar ideea trebuie să se înțeleagă\n"
                    "   dintr-o privire, fără explicații și fără efecte puse ca să umple cadrul.")
    return f"""
Ești fotoeditor la o revistă de business. Alegi imaginea care însoțește articolul
de mai jos. NU scrii articolul — doar alegi ce se vede în poză.

ARTICOL
Titlu: {continut.get('seo_title') or continut.get('topic_title') or ''}
Ideea în două rânduri: {continut.get('raspuns_scurt') or continut.get('angle') or ''}
Din text: {_text(continut.get('article_html') or '')}
Domeniul clientului: {nisa}

CUM ALEGI
1. Titlul e subiectul: „{titlu}". Scrie ÎNTÂI trei idei vizuale diferite, câte un rând,
   care pornesc de la ce promite titlul, nu de la domeniul clientului în general. La un
   subiect abstract (un serviciu, un preț, o strategie, o creștere) caută o METAFORĂ
   VIZUALĂ care se înțelege dintr-o privire — nu obiectele obișnuite ale meseriei.
2. Păstrează ideea care NU s-ar potrivi la alt articol al aceluiași client. Dacă una ar merge
   la orice articol despre {nisa}, e prea generală: aruncă-o.
3. Gândește-te la TENSIUNEA articolului — ce se schimbă, ce pierde cineva, ce câștigă.
   Un articol despre costuri nu arată „bani”, arată momentul în care cineva se uită la
   un preț și se oprește.
4. CALEA DE AZI E ALEASĂ ca punct de plecare pentru cadru: {nume_cale}
   {forma_cale}
   O schimbi doar dacă ideea aleasă cere alt cadru. Calea spune doar FELUL cadrului: locul,
   obiectele și oamenii vin din lumea articolului — cine vede poza lângă titlu trebuie să
   înțeleagă legătura fără explicații. Nu te lua după un cuvânt din text („e-commerce",
   „livrare") ca să muți scena în altă meserie decât cea despre care e articolul.
5. {regula_scena}
6. Pune UN detaliu care leagă imaginea de articolul ăsta și de niciun altul.

NU FOLOSI NICIODATĂ
{chr(10).join('- ' + x for x in INTERZISE)}

STILUL CLIENTULUI
{_stil()}

REGULI DE FORMĂ
- Promptul final îl scrii în ENGLEZĂ, 45-75 de cuvinte, într-un singur paragraf.
- Spui, în ordine: ce se vede (subiect + acțiune) · unde · un detaliu anume ·
  cadrul (și obiectivul, dacă e fotografie: „shot on 35mm, waist-level, shallow depth of field”) ·
  lumina · paleta · starea.
{_regula_text()}
- Fără fețe de oameni recognoscibile: mâini, siluete, spatele cuiva, da.
- Fără mărci, fără produse ale concurenței.
- Răspunzi EXACT în forma asta, fără alt text:
IDEI:
1. <prima idee, un rând, în română>
2. <a doua>
3. <a treia>
ALEASA: <numărul ideii păstrate>
PROMPT: <paragraful final, în engleză>
{_deja_vazute()}
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
    # Cliseul care s-a nascut chiar din reparatia anterioara: carnetul cu lista
    # scrisa de mana, pixul si cana de cafea pe un birou de lemn. Nu e „glowing
    # hologram", deci trecea de toate verificarile — dar a iesit de patru ori la
    # rand si asta se vede pe un grid de Instagram mai tare decat orice cliseu.
    if ("notebook" in t or "notepad" in t or "journal" in t) and (
            "desk" in t or "coffee" in t or "mug" in t or "pen " in t):
        gasite.append("carnet pe birou (deja folosit)")
    if len(t.split()) < 25:
        gasite.append("prea scurt")
    return gasite


def doar_promptul(raspuns: str) -> str:
    """Din „IDEI … ALEASA … PROMPT: …" rămâne doar paragraful final. Un răspuns fără
    „PROMPT:" (model vechi, răspuns scurt) se ia întreg, ca înainte."""
    t = (raspuns or "").strip()
    m = re.search(r"PROMPT\s*:\s*(.+)\Z", t, re.S | re.I)
    if m:
        t = m.group(1)
    return t.strip().strip('"').strip()


def scrie(continut: dict, cheama) -> str:
    """Promptul de imagine pentru articolul ăsta. `cheama` e funcția care
    vorbește cu modelul (o primim ca parametru ca să putem testa fără rețea).
    Dacă nu iese nimic bun, întoarce '' și rămâne promptul din generarea mare."""
    intrebare = cere(continut)
    ultim = ""
    for incercare in range(2):
        cerere = intrebare if incercare == 0 else (
            intrebare + "\n\nÎNCERCAREA ANTERIOARĂ A FOST RESPINSĂ pentru că folosea: "
            + ", ".join(_pare_slab(ultim)) + ". Rămâi pe calea cerută, dar schimbă "
            "complet scena: alt loc, alte obiecte, alt unghi — fizice și reale."
        )
        try:
            date = cheama({
                "contents": [{"role": "user", "parts": [{"text": cerere}]}],
                "generationConfig": {"temperature": 1.0, "maxOutputTokens": 900},
            })
            ultim = (date["candidates"][0]["content"]["parts"][0]["text"] or "").strip()
        except Exception as e:  # noqa: BLE001 — imaginea nu merită să oprească postarea
            print(f"  promptul de imagine nu a putut fi scris: {str(e)[:150]}")
            return ""
        ultim = doar_promptul(ultim)
        probleme = _pare_slab(ultim)
        if not probleme:
            return ultim
        print(f"  promptul de imagine avea clișee ({', '.join(probleme)}) — mai cer o dată")
    return ultim or ""
