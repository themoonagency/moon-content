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


CLASA_SEMNATURA = "moon-autor"
_SEMNATURA_VECHE = re.compile(r'<p\b[^>]*class="' + CLASA_SEMNATURA + r'"[^>]*>.*?</p>\s*', re.I | re.S)


def semnatura() -> str:
    """Randul vizibil „Scris de <nume>, <rol>". Pana pe 11 sept autorul intra DOAR in
    datele structurate, care se lipeau printr-o actualizare pe care blogul pe API n-o
    accepta — asa ca pe themoonagency.ro/blog nu se vedea niciun autor. Semnatura din
    text nu depinde de nimic: pleaca odata cu articolul. Fara autor real semneaza firma."""
    esc = lambda t: html_lib.escape(t or "", quote=True)
    nume = (config.AUTOR_NUME or "").strip()
    firma = (config.CLIENT_NAME or "").strip()
    if nume:
        cine = f"<strong>{esc(nume)}</strong>"
        url = (config.AUTOR_URL or "").strip()
        if url.lower().startswith(("http://", "https://")):
            cine = f'<a href="{esc(url)}" rel="author">{cine}</a>'
        rol = (config.AUTOR_ROL or "").strip()
        text = "Scris de " + cine + (f", {esc(rol)}" if rol else "")
    elif firma:
        text = f"Scris de echipa <strong>{esc(firma)}</strong>"
    else:
        return ""
    return (f'<p class="{CLASA_SEMNATURA}" style="font-size:0.9em;opacity:0.8;margin:0 0 20px">'
            f"{text}</p>")


def cu_semnatura(html: str) -> str:
    """Pune semnatura sub titlu (sau la inceput, daca articolul n-are H1). Se poate
    chema de oricate ori: scoate intai semnatura veche, deci la publicare pleaca cea
    din setarile de ACUM, nu cea de la generare."""
    h = _SEMNATURA_VECHE.sub("", html or "")
    bloc = semnatura()
    if not bloc:
        return h
    m = re.search(r"</h1\s*>", h, re.I)
    if m:
        return h[:m.end()] + bloc + h[m.end():]
    return bloc + h


def autor_pentru_blog() -> dict:
    """Campurile autorului si ale firmei, trimise in POST catre blogul pe API. Site-ul
    le poate randa si pune in datele lui structurate fara sa mai astepte o actualizare."""
    nume = (config.AUTOR_NUME or "").strip()
    autor = {"type": "Person" if nume else "Organization",
             "name": nume or (config.CLIENT_NAME or "").strip()}
    if nume and (config.AUTOR_ROL or "").strip():
        autor["role"] = config.AUTOR_ROL.strip()
    # doar http(s): site-ul poate randa author.url ca link, iar un "javascript:" ar fi XSS pe blogul clientului
    if nume and (config.AUTOR_URL or "").strip().lower().startswith(("http://", "https://")):
        autor["url"] = config.AUTOR_URL.strip()
    org = {"name": (config.CLIENT_NAME or "").strip()}
    if (config.ORG_CUI or "").strip():
        org["vat_id"] = config.ORG_CUI.strip()
    if (config.ORG_ORAS or "").strip():
        org["city"] = config.ORG_ORAS.strip()
    if _radacina():
        org["url"] = _radacina() + "/"
    return {"author": autor, "organization": org}


def controale(ciorna: dict) -> list[str]:
    """Verificarile de dinainte de publicare. Nu opresc nimic — se scriu pe
    ciorna, ca omul sa vada la ce sa se uite. Un articol care pica doua-trei
    dintre ele merita citit inainte de aprobare."""
    p: list[str] = []
    html = ciorna.get("article_html") or ""
    text = _text(html)
    n = cuvinte(html)

    # Articolul de catalog „doar din magazin" e scurt DINADINS (300-450 de cuvinte, fara surse):
    # pragul de 500 si „niciun link extern" il marcau mereu, iar „prea scurt" oprea aprobarea automata.
    catalog_scurt = config.FLUX == "catalog" and (getattr(config, "CATALOG_ARTICOL", "") or "magazin") != "complet"
    if n < (250 if catalog_scurt else 500):
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

    # Linkuri interne. Indemnul (CTA) il punem NOI dupa generare, deci nu se
    # pune la socoteala: altfel un articol fara niciun link intern raporta 1.
    gazda = (config.CLIENT_DOMAIN or "").replace("https://", "").replace("http://", "").strip("/")
    cta = (config.CLIENT_CTA_LINK or "").strip().rstrip("/")
    toate = re.findall(r'href=["\']([^"\']*' + re.escape(gazda) + r'[^"\']*)["\']', html, re.I) if gazda else []
    interne = [u for u in toate if u.rstrip("/") != cta]
    # cate pagini reale stie motorul ca exista pe site-ul clientului
    pagini = len([x for x in (config.SITE or []) if (x.get("url") or "").strip()])
    if gazda and len(interne) < 2:
        if pagini == 0:
            # cauza adevarata, nu simptomul: fara pagini citite, promptul nici
            # nu are voie sa ceara linkuri interne — ar iesi adrese inventate
            p.append("site-ul clientului n-a fost citit, deci articolul n-are spre ce sa "
                     "trimita: apasa Citeste site-ul in ecranul clientului")
        elif pagini < 3:
            p.append(f"doar {len(interne)} link(uri) interne, dar stim doar {pagini} pagini de pe site "
                     "— mai citeste o data site-ul, ca sa aiba de unde alege")
        else:
            p.append(f"doar {len(interne)} link(uri) catre paginile clientului — vrem 3-5")
    externe = len(re.findall(r'href=["\']https?://(?!' + re.escape(gazda) + r')', html, re.I)) if gazda else 0
    if externe == 0 and not catalog_scurt:
        p.append("niciun link catre o sursa din afara")

    if not re.search(r"\d", text):
        p.append("articolul nu contine nicio cifra")
    return p
