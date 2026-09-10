"""
Partea de SEO si GEO care se face DUPA ce modelul a scris articolul: datele
structurate, curatarea HTML-ului si micile verificari care fac diferenta intre
un articol care e gasit si unul care nu e.

De ce aici si nu in prompt: modelul e bun la scris, dar prost la formate exacte.
Un JSON-LD scris de model iese aproape bun — ceea ce nu ajuta la nimic. Asa ca
promptul cere continut, iar forma o punem noi, de fiecare data la fel de corect.

Ce s-a luat in seama (cercetare, septembrie 2026):
  - regasirea e pe BUCATI de pagina, nu pe pagina intreaga: fiecare sectiune
    trebuie sa se inteleaga scoasa din context;
  - ce ajuta la regasire sta in titlu, descriere, H2-uri si date structurate —
    indesatul corpului cu cifre si termeni scade regasirea, nu o creste;
  - FAQPage si HowTo nu mai produc nimic vizibil in Google din mai 2026,
    deci nu le mai emitem;
  - `dateModified` se atinge doar cand chiar s-a schimbat textul.
"""

from __future__ import annotations
import html as html_lib
import json
import re
from datetime import datetime, timezone

from config import config

# atribute si tag-uri care n-au ce cauta intr-un articol venit de la un model
_TAG_RAU = re.compile(r"<\s*(script|style|iframe|object|embed|form|input|link|meta)\b[^>]*>.*?<\s*/\s*\1\s*>",
                      re.I | re.S)
_TAG_RAU_SINGUR = re.compile(r"<\s*(script|style|iframe|object|embed|form|input|link|meta)\b[^>]*/?>", re.I)
# „\s" nu ajunge: `<img/onerror=alert(1) src=x>` foloseste „/" ca separator,
# iar valoarea poate fi si fara ghilimele.
_ATRIB_RAU = re.compile(r"[\s/](on[a-z]+|style|srcset|formaction)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
# „jav&#x09;ascript:" si prietenii: scoatem spatiile albe din schema inainte de test
_HREF_RAU = re.compile(r'href\s*=\s*(?:(["\'])\s*[^"\']*\1|[^\s>]+)', re.I)
_SCHEMA_REA = re.compile(r'^(?:javascript|data|vbscript):', re.I)


def curata_html(html: str) -> str:
    """Scoate din articol ce n-ar trebui sa ajunga niciodata pe site-ul unui
    client: script-uri, stiluri in linie, atribute `on…` si linkuri
    „javascript:". Articolul vine de la un model, iar modelul citeste paginile
    clientului — deci il tratam ca text venit din afara, nu ca text de-al nostru."""
    h = _TAG_RAU.sub(" ", html or "")
    h = _TAG_RAU_SINGUR.sub(" ", h)
    # se repeta pana nu mai gaseste nimic: `<img o/nerror=…>` ascuns dupa altul
    for _ in range(3):
        nou = _ATRIB_RAU.sub(" ", h)
        if nou == h:
            break
        h = nou
    h = _HREF_RAU.sub(_href_curat, h)
    # ce a mai ramas din script-uri imbricate
    h = re.sub(r"</\s*(script|style|iframe|object|embed|form)\s*>", " ", h, flags=re.I)
    return h.strip()


def _href_curat(m) -> str:
    brut = m.group(0)
    val = brut.split("=", 1)[1].strip().strip("\"'")
    val = html_lib.unescape(val)
    # browserele ignora spatiile albe DIN INTERIORUL schemei: „jav\tascript:" e
    # acelasi lucru cu „javascript:". Le scoatem pe toate inainte de test.
    curat = re.sub(r"[\s\x00-\x20]", "", val)
    return 'href="#"' if _SCHEMA_REA.match(curat) else brut


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def cuvinte(html: str) -> int:
    return len([w for w in _text(html).split(" ") if w])


def _radacina() -> str:
    d = (config.CLIENT_DOMAIN or "").strip().rstrip("/")
    if not d:
        return ""
    return d if d.startswith(("http://", "https://")) else "https://" + d


def date_structurate(ciorna: dict, adresa: str, adresa_imagine: str | None = None) -> str:
    """JSON-LD pentru articol, ca un singur graf cu @id-uri incrucisate — asa
    arata schema scrisa de om, nu trei blocuri lipite unul dupa altul.
    Fara FAQPage, fara HowTo, fara Speakable: nu mai produc nimic."""
    baza = _radacina()
    if not baza or not adresa:
        return ""
    acum = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    org_id = f"{baza}/#organization"
    graf: list[dict] = []

    articol = {
        "@type": "BlogPosting",
        "@id": adresa + "#article",
        "isPartOf": {"@id": adresa + "#webpage"},
        "mainEntityOfPage": {"@id": adresa + "#webpage"},
        "headline": (ciorna.get("seo_title") or "")[:110],
        "description": ciorna.get("meta_description") or "",
        "inLanguage": "ro-RO",
        "datePublished": acum,
        # se pune egal cu data publicarii; nu se atinge decat la o modificare reala
        "dateModified": acum,
        "publisher": {"@id": org_id},
        "wordCount": cuvinte(ciorna.get("article_html") or ""),
    }
    if ciorna.get("intrebare") and ciorna.get("raspuns_scurt"):
        # intrebarea la care raspunde pagina, in clar — asta cauta motoarele cu AI
        articol["about"] = {"@type": "Thing", "name": ciorna.get("topic_title") or ciorna["intrebare"]}
        articol["abstract"] = ciorna["raspuns_scurt"]
    if adresa_imagine:
        articol["image"] = {"@type": "ImageObject", "url": adresa_imagine, "width": 1536, "height": 1024}

    if config.AUTOR_NUME:
        autor_id = (config.AUTOR_URL or (baza + "/echipa/")) + "#person"
        articol["author"] = {"@id": autor_id}
        persoana = {
            "@type": "Person", "@id": autor_id, "name": config.AUTOR_NUME,
            "worksFor": {"@id": org_id},
        }
        if config.AUTOR_URL:
            persoana["url"] = config.AUTOR_URL
        if config.AUTOR_ROL:
            persoana["jobTitle"] = config.AUTOR_ROL
        graf.append(persoana)
    else:
        # fara autor real, semneaza firma — mai onest decat un nume inventat
        articol["author"] = {"@id": org_id}

    graf.insert(0, articol)
    graf.append({"@type": "WebPage", "@id": adresa + "#webpage", "url": adresa,
                 "breadcrumb": {"@id": adresa + "#breadcrumb"}})
    graf.append({
        "@type": "BreadcrumbList", "@id": adresa + "#breadcrumb",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Acasă", "item": baza + "/"},
            {"@type": "ListItem", "position": 2, "name": "Blog", "item": baza + "/blog/"},
            {"@type": "ListItem", "position": 3, "name": (ciorna.get("seo_title") or "")[:110]},
        ],
    })
    org = {"@type": "Organization", "@id": org_id, "name": config.CLIENT_NAME, "url": baza + "/"}
    if config.ORG_CUI:
        # CUI-ul se poate verifica la ANAF: e unul dintre putinele semnale de
        # incredere pe care le poate da o firma mica din Romania
        org["vatID"] = config.ORG_CUI
    if config.ORG_ORAS:
        org["address"] = {"@type": "PostalAddress", "addressLocality": config.ORG_ORAS,
                          "addressCountry": "RO"}
    if config.LOGO_URL:
        org["logo"] = {"@type": "ImageObject", "url": config.LOGO_URL}
    graf.append(org)

    corp = json.dumps({"@context": "https://schema.org", "@graph": graf},
                      ensure_ascii=False, separators=(",", ":"))
    # json.dumps NU escapeaza „<". Un titlu care contine „</script>" ar inchide
    # blocul mai devreme si restul ar deveni marcaj viu pe site-ul clientului.
    corp = corp.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return '<script type="application/ld+json">' + corp + "</script>"


def controale(ciorna: dict) -> list[str]:
    """Verificarile de dinainte de publicare. Nu opresc nimic — se scriu pe
    ciorna, ca omul sa vada la ce sa se uite. Un articol care pica doua-trei
    dintre ele merita citit inainte de aprobare."""
    p: list[str] = []
    html = ciorna.get("article_html") or ""
    text = _text(html)
    n = cuvinte(html)

    if n < 500:
        p.append(f"articolul are doar {n} de cuvinte — prea scurt ca sa fie luat drept sursa")
    if len(ciorna.get("seo_title") or "") > 65:
        p.append("titlul trece de 65 de caractere si va fi taiat in Google")
    md = ciorna.get("meta_description") or ""
    if not md:
        p.append("lipseste meta description")
    elif len(md) > 160:
        p.append("meta description trece de 160 de caractere")
    if html.count("<h1") != 1:
        p.append(f"articolul are {html.count('<h1')} titluri H1 in loc de unul")
    if html.count("<h2") < 2:
        p.append("articolul are sub doua sectiuni H2")

    # raspunsul trebuie sa fie sus: primele ~60 de cuvinte de text, nu la final
    inceput = " ".join(text.split(" ")[:60]).lower()
    for d in ("in lumea de azi", "in era digitala", "traim intr-o lume", "nu e un secret",
              "in peisajul actual", "cu totii stim"):
        if d in inceput:
            p.append(f"articolul incepe cu un cliseu („{d}…")
            break

    # linkuri interne catre site-ul clientului
    gazda = (config.CLIENT_DOMAIN or "").replace("https://", "").replace("http://", "").strip("/")
    interne = len(re.findall(r'href=["\'][^"\']*' + re.escape(gazda), html, re.I)) if gazda else 0
    if gazda and interne < 2:
        p.append(f"doar {interne} link(uri) catre paginile clientului — vrem 3-5")
    externe = len(re.findall(r'href=["\']https?://(?!' + re.escape(gazda) + r')', html, re.I)) if gazda else 0
    if externe == 0:
        p.append("niciun link catre o sursa din afara")

    if not re.search(r"\d", text):
        p.append("articolul nu contine nicio cifra")
    return p
