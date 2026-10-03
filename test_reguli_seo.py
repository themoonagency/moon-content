"""
Regulile SEO din 2 oct 2026 (auditul celor 4 site-uri), in motorul Python de rezerva — aceleasi cazuri
ca moon-post/test-poarta.mjs (motorul principal, din worker), plus titlul dublat din continut.
  - poarta de limba si de bani (poarta.py): „mențîn", „Că firmă mică", sume in titlu/descriere,
    preturile MOON in text;
  - schema pe site-urile noastre: publisher = organizatia site-ului, autorul Felix Dumitru, fara
    Organization, breadcrumb doar unde trebuie, datePublished = prima publicare;
  - publicarea cap-coada (check_approvals.publica) si generarea (generate_draft.pentru_client).
Fara retea: `requests` e inlocuit cu un fals. Ruleaza: python3 test_reguli_seo.py
"""

from __future__ import annotations
import json
import os
import sys

os.environ["PANEL_URL"] = "https://app.moonpost.ro"
os.environ["CRON_KEY"] = "cheie-test"
sys.dont_write_bytecode = True

import requests

from config import config
import poarta as P
import seo
from siteuri_moon import PERSOANA_FELIX, nume_autor, site_moon

PICA: list = []


def cer(cond, nume, extra=None):
    print(("  ok   " if cond else "  PICA ") + nume + ("" if cond or extra is None else f"  -> {str(extra)[:900]}"))
    if not cond:
        PICA.append(nume)


def ld(html):
    """Graful JSON-LD dintr-un HTML, sau None."""
    h = str(html or "")
    a = h.find('<script type="application/ld+json">')
    if a < 0:
        return None
    a += len('<script type="application/ld+json">')
    return json.loads(h[a:h.index("</script>", a)])


def noduri(g, tip):
    return [x for x in ((g or {}).get("@graph") or []) if tip in ([x["@type"]] if isinstance(x["@type"], str) else x["@type"])]


def client(domeniu, **cfg):
    return {"id": 9, "slug": "x", "nume": cfg.pop("nume", "MOON Post"), "domeniu": domeniu, "flux": "autoritate",
            "slot": 0, "canale": ["wp"], "config": cfg}


# un JPEG minim, doar cu antetul SOF0 (1536 x 1024), cat sa treaca de verificarea „< 100 de octeti"
JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00,
              0x01, 0x00, 0x00, 0xFF, 0xC0, 0x00, 0x11, 0x08, 0x04, 0x00, 0x06, 0x00, 0x03]) + bytes(370)

print("MOON Post (motorul Python) - poarta de limba si de bani, schema pe site-urile noastre\n")

# ================================================================== limba
print("-- limba: „î\" in interiorul cuvantului, „Că\" / „Ca\" --")
v = {"când", "până", "mâine"}
cer(P.verifica_cuvant("mențîn", v)["corect"] == "mențin" and P.verifica_cuvant("Susțîne", v)["corect"] == "Susține",
    "„mențîn\" -> „mențin\" (urma bug-ului: „in\" lipit dupa ț)")
cer(all(P.verifica_cuvant(w, v) is None for w in ["neîncredere", "reînnoire", "preîntâmpina", "dezîngheț", "bineînțeles",
                                                   "reîmprospătare", "nemaiîntâlnit", "început", "coborî", "hotărî"]),
    "compusele cu prefix, „î\" la inceput si verbele in „î\" sunt corecte")
cer(P.verifica_cuvant("cînd", v)["corect"] == "când" and P.verifica_cuvant("pînă", v)["corect"] == "până",
    "ortografia veche: „â\" cand articolul foloseste forma cu „â\"")
cer(P.verifica_cuvant("sînt", v)["corect"] == "sunt" and P.verifica_cuvant("Comparăție", v)["corect"] == "Comparație",
    "greselile cunoscute")
nesigur = P.verifica_cuvant("cîte", v)
cer(nesigur and nesigur["corect"] is None, "fara forma de comparat: greseala ramane semnalata, necorectata")
cer(P.verifica_cuvant("Bîrlad", v) is None, "un nume propriu in ortografia veche nu e atins")
cer(P.ca_e_gresit("firmă") and P.ca_e_gresit("antreprenor") and not P.ca_e_gresit("e") and not P.ca_e_gresit("nu")
    and not P.ca_e_gresit("firma") and not P.ca_e_gresit("vindem") and not P.ca_e_gresit("Google"),
    "„Că\" + substantiv nearticulat = greseala; verb, pronume, articulat, nume propriu = nu")
c = {"meta_description": "Că firmă mică, îți mențîn ritmul. Știi că e greu? Că e greu, știm.", "seo_title": "Ghid: că firmă mică"}
r = P.poarta_determinista(c, domeniu="client.ro")
cer(c["meta_description"] == "Ca firmă mică, îți mențin ritmul. Știi că e greu? Că e greu, știm." and not r["ramase"],
    "descrierea: „Ca firmă mică\" si „mențin\"; „că e\" ramane", c["meta_description"])
cer(c["seo_title"] == "Ghid: că firmă mică", "„că\" in mijlocul frazei nu se atinge")
cer(not hasattr(P, "repun_diacritice") and not hasattr(seo, "repun_diacritice"),
    "motorul Python n-are completarea automata de diacritice care rupea „mențin\" (nimic de reparat acolo)")

# ================================================================== bani
print("\n-- bani: preturile MOON si sumele din titlu/descriere --")
c = {
    "meta_description": "Copywriter sau automatizare AI: articole de blog la 199 lei pe lună, reducător de costuri pentru firme mici.",
    "article_html": "<h1>T</h1><p>Un copywriter cere 150–300 lei pe articol. Cu MOON Post plătești 199 lei pe lună și primești tot.</p>"
                    "<table><tr><td>Rar</td><td>199 lei/lună</td></tr></table><p>Pachetul Zilnic costă doar 399 lei pe lună.</p>"
                    "<p>Statistica: <a href=\"https://exemplu.ro\">un studiu</a> spune că firmele dau 2.000 lei pe lună pe reclame.</p>",
    "facebook_text": "MOON Post scrie pentru tine de la 199 lei pe lună.",
}
r = P.poarta_determinista(c, domeniu="moonpost.ro")
cer(c["meta_description"] == "Copywriter sau automatizare AI: articole de blog cu abonament lunar, reducător de costuri pentru firme mici.",
    "descrierea: „la 199 lei pe lună\" -> „cu abonament lunar\"", c["meta_description"])
cer("150–300 lei pe articol" in c["article_html"], "pretul pietei (copywriterul) ramane")
cer("Cu MOON Post plătești un <a href=\"https://moonpost.ro/preturi\">abonament lunar</a>, în funcție de cât de des publici" in c["article_html"],
    "pretul MOON Post din text -> „abonament lunar, în funcție de …\" cu link spre /preturi", c["article_html"])
cer('<td><a href="https://moonpost.ro/preturi">În funcție de pachet</a></td>' in c["article_html"]
    and "Pachetul Zilnic merge pe abonament lunar" in c["article_html"]
    and c["article_html"].count('href="https://moonpost.ro/preturi"') == 2,
    "celula de tabel -> „În funcție de pachet\" cu linkul ei; „costă doar 399 lei\" inlocuit; in text linkul o singura data",
    c["article_html"])
cer("2.000 lei pe lună pe reclame" in c["article_html"], "un buget de reclame (nu e pret MOON) ramane in text")
cer(c["facebook_text"] == "MOON Post scrie pentru tine cu abonament lunar, în funcție de cât de des publici." and not r["ramase"],
    "textul de Facebook: fara pret, fara link", c["facebook_text"])
t = {"seo_title": "Google Ads: buget de 1.500 lei pe lună", "meta_description": "Cât costă o campanie Google Ads: de la 50 lei pe zi.",
     "article_html": "<p>Bugetul minim e 50 lei pe zi.</p>"}
r2 = P.poarta_determinista(t, domeniu="themoonagency.ro")
cer(len(r2["ramase"]) == 2 and all(x["tip"] == "bani" for x in r2["ramase"]) and t["article_html"] == "<p>Bugetul minim e 50 lei pe zi.</p>",
    "themoonagency.ro: o suma in titlu/descriere e problema; bugetul din articol ramane", r2["ramase"])
s = {"seo_title": "Cât costă schimbul de ulei DSG: 900 lei", "meta_description": "Între 900 și 1.500 de lei, în funcție de cutie."}
r3 = P.poarta_determinista(s, domeniu="servicepopescu.ro")
cer(not r3["ramase"] and s["meta_description"] == "Între 900 și 1.500 de lei, în funcție de cutie.",
    "la un client oarecare, preturile lui din titlu/descriere raman (regula e pentru site-urile noastre)")
m = {"article_html": "<p>Clientul a ales MOON Chat la 39 € pe lună.</p>"}
P.poarta_determinista(m, domeniu="magazin.ro")
cer('<a href="https://moonchat.ro/preturi">abonament lunar</a>, în funcție de numărul de conversații' in m["article_html"],
    "pretul unui produs MOON numit e scos la orice client", m["article_html"])
cer(P.valori("1.199 lei") == [1199] and P.valori("30–100 €") == [30, 100] and P.are_suma("€39")
    and not P.are_suma("în 2026, 3 pași"), "sumele: valori si recunoastere")
cer("NU pui nicio sumă" in P.bloc_reguli("moonchat.ro") and "BANI" not in P.bloc_reguli("x.ro")
    and "„Ca” (nu „Că”)" in P.bloc_reguli("x.ro"), "regula de bani intra in prompt doar pe site-urile noastre")

print("\n-- bani in tabele, liste si etichete (2 oct: „199 lei - 399 lei\" din comparatia de pe moonpost.ro) --")
# tabelul din moonpost.ro/blog/copywriter-sau-automatizare-ai-pentru-blogul-firmei-mici (articolul are deja un link spre preturi)
TABEL = ('<p>Răspuns cu <a href="https://moonpost.ro/preturi">abonament lunar</a>, în funcție de cât de des publici.</p>'
         '<table><caption>Comparație între copywriter și automatizarea conținutului cu AI</caption><thead><tr><th>Criteriu de comparație</th>'
         '<th>Copywriter freelancer</th><th>Automatizare conținut cu AI</th></tr></thead><tbody><tr><td>Cost lunar mediu</td>'
         '<td>1.400 lei - 3.000 lei (pentru 4 articole)</td><td>199 lei - 399 lei (necomisionat, număr extins de materiale)</td></tr>'
         '<tr><td>Includere postări social media</td><td>Se plătește separat (100-150 lei/postare)</td><td>Inclusă automat</td></tr></tbody></table>')
import re as _re
_etichete = lambda h: ",".join(_re.findall(r"</?(?:table|caption|thead|tbody|tr|th|td)\b", h, _re.I))
c = {"article_html": TABEL}
r = P.poarta_determinista(c, campuri=["article_html"], domeniu="moonpost.ro")
cer('<td><a href="https://moonpost.ro/preturi">În funcție de pachet</a> (necomisionat, număr extins de materiale)</td>' in c["article_html"]
    and not _re.search("199|399", c["article_html"])
    and any(x.startswith("tabel: «199 lei - 399 lei» → «În funcție de pachet»") for x in r["reparate"]),
    "moonpost.ro: „199 lei - 399 lei\" din celula -> „În funcție de pachet\" cu link (si cand articolul are deja un link)",
    [c["article_html"], r["reparate"]])
cer("<td>1.400 lei - 3.000 lei (pentru 4 articole)</td>" in c["article_html"] and "(100-150 lei/postare)" in c["article_html"]
    and _etichete(c["article_html"]) == _etichete(TABEL) and not r["ramase"], "preturile copywriterului raman; tabelul are aceleasi celule")
a = {"article_html": TABEL}
P.poarta_determinista(a, campuri=["article_html"], domeniu="themoonagency.ro")
cer(a["article_html"] == TABEL, "acelasi tabel pe themoonagency.ro (fara produs propriu, fara nume MOON): neatins")
CH = '<table><tr><th>Plan</th><th>MOON Chat</th><th>Tidio</th></tr><tr><td>Preț lunar</td><td>29 €</td><td>29 €</td></tr></table>'
b = {"article_html": CH}
P.poarta_determinista(b, campuri=["article_html"], domeniu="moonchat.ro")
cer(b["article_html"] == ('<table><tr><th>Plan</th><th>MOON Chat</th><th>Tidio</th></tr><tr><td>Preț lunar</td><td><a href="https://moonchat.ro/preturi">'
                          'În funcție de pachet</a></td><td>29 €</td></tr></table>'),
    "coloana „MOON Chat\" -> „În funcție de pachet\"; coloana concurentului ramane", b["article_html"])
UNU = '<table><tr><th>Ce</th><th>Chatbot AI</th></tr><tr><td>Cost lunar</td><td>29 €</td></tr></table>'
u1 = {"article_html": UNU}
P.poarta_determinista(u1, campuri=["article_html"], domeniu="moonchat.ro")
cer(u1["article_html"] == UNU, "un singur pret fara numele produsului, intr-o celula: ramane (poate fi al unui concurent)")
st = {"article_html": "<p>Cu MOON Post plătești <strong>199 lei</strong> pe lună.</p><ul><li>MOON Chat: de la <b>29</b> € pe lună</li></ul>"}
P.poarta_determinista(st, campuri=["article_html"], domeniu="themoonagency.ro")
cer(st["article_html"] == ('<p>Cu MOON Post plătești un <a href="https://moonpost.ro/preturi">abonament lunar</a>, în funcție de cât de des publici.</p>'
                           "<ul><li>MOON Chat: cu abonament lunar, în funcție de numărul de conversații</li></ul>"),
    "suma rupta de <strong>/<b> (si intr-un <li>): inlocuita, fara etichete goale ramase", st["article_html"])
iv = {"article_html": "<p>MOON Post costă 199 lei – 399 lei pe lună.</p>"}
P.poarta_determinista(iv, campuri=["article_html"], domeniu="themoonagency.ro")
cer(iv["article_html"] == '<p>MOON Post merge pe <a href="https://moonpost.ro/preturi">abonament lunar</a>, în funcție de cât de des publici.</p>',
    "intervalul cu moneda la ambele capete e o singura suma (o singura inlocuire)", iv["article_html"])
cer(P.valori("199 lei - 399 lei") == [199, 399]
    and P.produs_in_tabel("Cost lunar mediu · Automatizare · 199 lei - 399 lei", "199 lei - 399 lei", {"produs": "post"}) == "post"
    and P.produs_in_tabel("Cost · Copywriter · 199 lei - 399 lei", "199 lei - 399 lei", {"produs": "post"}) == "",
    "produs_in_tabel: intervalul de pachete MOON + cost lunar = pret MOON; fara „lunar/abonament/pachet\" nu")

print("\n-- poarta cu modelul (campurile scurte ramase) --")
config.aplica(client("themoonagency.ro", nume="THE MOON Agency"))


def raspunde(obj):
    return lambda payload: {"candidates": [{"content": {"parts": [{"text": json.dumps(obj, ensure_ascii=False)}]},
                                            "finishReason": "STOP"}]}


c = {"seo_title": "Google Ads: buget de 1.500 lei pe lună", "meta_description": "Ghid scurt.", "article_html": "<p>x</p>"}
r = P.poarta(c, cheama=raspunde({"seo_title": "Google Ads: cât buget îți trebuie la început"}))
cer(c["seo_title"] == "Google Ads: cât buget îți trebuie la început" and not r["ramase"] and "rescrise de model" in " ".join(r["jurnal"]),
    "titlul cu suma e rescris de model si verificat din nou", [c["seo_title"], r])
d = {"seo_title": "Google Ads: buget de 1.500 lei pe lună", "article_html": "<p>x</p>"}
r = P.poarta(d, cheama=raspunde({"seo_title": "Google Ads: buget de 900 lei"}))
cer(d["seo_title"] == "Google Ads: buget de 1.500 lei pe lună" and len(r["ramase"]) == 1 and r["ramase"][0].startswith("suma de bani in titlu"),
    "raspunsul modelului care tot are suma e refuzat; ramane problema grava (nu pleaca singura)", r)
e = {"seo_title": "Google Ads: buget de 1.500 lei pe lună", "article_html": "<p>x</p>"}
r = P.poarta(e, model=False)
cer(len(r["ramase"]) == 1, "fara model: doar se semnaleaza")


def cade(payload):
    raise RuntimeError("model cazut")


r = P.poarta(dict(e), cheama=cade)
cer(len(r["ramase"]) == 1, "modelul cazut nu opreste generarea: problema ramane semnalata")

# ================================================================== schema, autor
print("\n-- schema pe site-urile noastre, autorul --")
cer(nume_autor("Dumitru Felix") == "Felix Dumitru" and nume_autor(" dumitru  FELIX ") == "Felix Dumitru"
    and nume_autor("Ana Pop") == "Ana Pop", "„Dumitru Felix\" -> „Felix Dumitru\"")
config.aplica(client("client.ro", autor_nume="Dumitru Felix"))
cer(config.AUTOR_NUME == "Felix Dumitru", "si la un client oarecare")
ORG = {"themoonagency.ro": "https://themoonagency.ro/#organization", "moonpost.ro": "https://moonpost.ro/#organizatie",
       "moonchat.ro": "https://moonchat.ro/#organizatie", "moonsite.ro": "https://moonsite.ro/#org"}
for dom, org in ORG.items():
    config.aplica(client(dom, nume="X", autor_nume="Dumitru Felix", autor_rol="Fondator", cui="50686976", oras="Bucuresti",
                         logo_url="https://app.moonpost.ro/img/logo.png"))
    adresa = "https://" + dom + "/blog/un-articol"
    g = ld(seo.date_structurate({"seo_title": "Titlu", "meta_description": "Descriere", "article_html": "<p>a b c</p>"}, adresa,
                                "https://app.moonpost.ro/img/d1.jpg",
                                {"publicat": "2026-09-14T08:00:00Z", "modificat": "2026-10-02T10:00:00Z", "latime": 1536, "inaltime": 1024}))
    art = (noduri(g, "BlogPosting") or [{}])[0]
    bc = noduri(g, "BreadcrumbList")
    cer(not noduri(g, "Organization") and art.get("publisher", {}).get("@id") == org,
        dom + ": fara Organization proprie, publisher = " + org, g)
    cer(json.dumps(noduri(g, "Person")[0]) == json.dumps(PERSOANA_FELIX) and art["author"]["@id"] == PERSOANA_FELIX["@id"],
        dom + ": autorul = obiectul Person comun (Felix Dumitru)")
    cer(art.get("datePublished") == "2026-09-14T08:00:00+00:00" and art.get("dateModified") == "2026-10-02T10:00:00+00:00"
        and art["image"]["width"] == 1536 and "vatID" not in json.dumps(g) and "Bucuresti" not in json.dumps(g),
        dom + ": datePublished = prima publicare, dateModified = acum, fara vatID/oras", art)
    if dom == "moonsite.ro":
        cer(not bc, "moonsite.ro: fara BreadcrumbList (site-ul il face singur)")
    else:
        cer(len(bc) == 1 and bc[0]["@id"] == adresa + "#breadcrumb" and bc[0]["itemListElement"][0]["item"] == "https://" + dom + "/"
            and bc[0]["itemListElement"][1]["item"] == "https://" + dom + "/blog",
            dom + ": un singur breadcrumb, Acasă -> Blog spre /blog fara bara", bc)
    ap = seo.autor_pentru_blog()
    cer('<a href="https://themoonagency.ro/echipa" rel="author"><strong>Felix Dumitru</strong></a>, Fondator' in seo.cu_semnatura("<h1>T</h1>")
        and ap["author"]["name"] == "Felix Dumitru" and "vat_id" not in ap["organization"], dom + ": semnatura si autorul trimis blogului")
config.aplica(client("servicepopescu.ro", nume="Service", autor_nume="Andrei Popescu"))
g1 = ld(seo.date_structurate({"seo_title": "T"}, "https://servicepopescu.ro/blog/x", None, {"acum": "2026-09-11T04:30:05Z"}))
g2 = ld(seo.date_structurate({"seo_title": "T"}, "https://servicepopescu.ro/blog/x", None, {"publicat": None}))
cer(noduri(g1, "BlogPosting")[0]["datePublished"] == "2026-09-11T04:30:05+00:00" and "datePublished" not in noduri(g2, "BlogPosting")[0]
    and noduri(g1, "Organization") and noduri(g1, "Person")[0]["name"] == "Andrei Popescu",
    "client oarecare: graful vechi (cu firma lui); publicat None = data necunoscuta, lasata deoparte (nu „azi\")")
cer(site_moon("https://www.moonpost.ro/blog") and site_moon("brutaria-ion.moonsite.ro") is None,
    "site_moon: dupa gazda, fara subdomeniile clientilor")
import check_approvals
from publishers import blog_api
cer(check_approvals.dimensiuni_jpeg(JPEG) == (1536, 1024) and check_approvals.dimensiuni_jpeg(bytes(2000)) is None,
    "marimea JPEG-ului din antet")
cer(blog_api.adresa_webp("https://app.moonpost.ro/img/p1.jpg") == "https://app.moonpost.ro/img/p1.webp"
    and blog_api.adresa_webp("https://x.ro/poza.png") == "", "varianta WebP doar pentru JPG-urile de pe /img/")

# ================================================================== titlul dublat
print("\n-- continutul trimis spre site: fara titlul dublat, fara H1 --")
T = "Cum îți menții blogul viu?"
cer(seo.fara_titlu_dublat("<h1>Cum iti mentii BLOGUL viu</h1><p>a</p>", T) == "<p>a</p>",
    "H1-ul egal cu titlul (fara diacritice, alte litere, fara semne) se scoate")
cer(seo.fara_titlu_dublat("<h1>Cum îți menții blogul viu</h1>\n<h2 class=\"x\">Cum îți menții blogul viu?</h2><p>a</p>", T) == "<p>a</p>",
    "si H2-ul dublura de dupa el")
cer(seo.fara_titlu_dublat("<h1>Ghidul complet</h1><p>a</p><h1>Pasul 2</h1>", T) == "<h2>Ghidul complet</h2><p>a</p><h2>Pasul 2</h2>",
    "un H1 cu alt text devine H2 (textul nu se pierde)")
cer(seo.fara_titlu_dublat("<p>a</p><h2>Ceva</h2><h2>Cum îți menții blogul viu</h2>", T) == "<p>a</p><h2>Ceva</h2><h2>Cum îți menții blogul viu</h2>",
    "un H2 egal cu titlul, dar care nu e primul titlu de sectiune, ramane")
cer(seo.fara_titlu_dublat("<h1>Cum îți menții blogul viu în 2026</h1><h3>Primul pas</h3><p>a</p>", T) == "<h2>Primul pas</h2><p>a</p>",
    "un titlu aproape egal (acelasi sir de cuvinte, plus o coada) iese; primul titlu ramas, H3, devine H2")
cer(not seo.titlu_aproape_egal("Cât costă un domeniu .ro pe an?", "Domeniu .ro: cum îl cumperi și cât costă pe an")
    and not seo.titlu_aproape_egal("Cât costă un chatbot AI?", "Chatbot cu AI: ce alegi și cât costă un chatbot AI pentru magazin"),
    "nu e dublura: aceleasi cuvinte in alta ordine sau o sectiune mult mai scurta")
T2 = "Cât costă un chatbot AI pentru un magazin online în 2026"
CORP = '<p class="moon-autor">Scris de Felix Dumitru</p><p>Răspunsul scurt.</p><h2>Ce influențează prețul</h2><p>a</p><h3>Detalii</h3><p>b</p>'
cer(seo.fara_titlu_dublat("<h2>" + T2 + "</h2>\n" + CORP, T2) == CORP
    and seo.fara_titlu_dublat("<h1>CAT COSTA un chatbot <em>AI</em> pentru un magazin online, in 2026?</h1>" + CORP, T2) == CORP,
    "titlul ca H2 (moonsite.ro) sau fara diacritice, cu alte majuscule, semne si taguri: iese")
cer(seo.titlu_aproape_egal("Domeniu .ro: cum îl cumperi și cât costă pe an", "Domeniu .ro: cum îl iei și cât costă pe an")
    and seo.titlu_aproape_egal("Copywriter sau automatizare AI pentru blogul firmei mici", "Copywriter sau automatizare cu AI: ce alegi pentru blogul firmei?")
    and seo.titlu_aproape_egal("Cât costă o campanie Google Ads în 2026? Prețuri și Bugete", "Cât costă o campanie Google Ads în 2026?")
    and seo.titlu_aproape_egal("Q&A despre SEO local", "Q&amp;A despre SEO local")
    and not seo.titlu_aproape_egal(T2, "Ce factori influențează prețul de implementare al unui chatbot AI?")
    and not seo.titlu_aproape_egal("SEO local", "SEO tehnic"),
    "aproape egal: exemplele de pe site-uri; sectiunile cu cateva cuvinte comune nu sunt dubluri")
cer(seo.fara_titlu_dublat("<h1>" + T2 + "</h1><h2>Cât costă un chatbot AI pentru magazin online în 2026?</h2><p>a</p><h1 class=\"x\">Alt titlu</h1><h3>z</h3>", T2)
    == '<p>a</p><h2 class="x">Alt titlu</h2><h3>z</h3>'
    and seo.fara_titlu_dublat("<h2>Titlul vechi al articolului de azi</h2><p>a</p>", ["Alt titlu nou", "Titlul vechi al articolului de azi"]) == "<p>a</p>"
    and seo.fara_titlu_dublat("<h1>X</h1><p>a</p>", "") == "<h2>X</h2><p>a</p>",
    "H1-titlu + H2 care il repeta ies; alt H1 devine H2; lista de titluri; fara titlu doar H1 -> H2")
config.aplica(client("moonpost.ro", autor_nume="Dumitru Felix"))
h = seo.pentru_site('<h1>Cum îți menții blogul viu</h1><p class="moon-autor">Scris de vechi</p><h2>Cum iti mentii blogul viu</h2><p>a</p>', T)
cer(h.startswith('<p class="moon-autor"') and h.count("moon-autor") == 1 and "Felix Dumitru" in h and "<h1" not in h
    and "<h2" not in h and h.endswith("<p>a</p>"), "pentru_site: semnatura de acum sus, o singura data, fara titlu si fara H1", h)

# ================================================================== publicarea (check_approvals)
print("\n-- publicarea: poarta, marimea pozei, WebP, data primei publicari, titlul --")
import panel
APELURI: list = []
STARI: list = []


class Raspuns:
    def __init__(self, date=None, cod=200, continut=b""):
        self.status_code, self._date, self.content = cod, date, continut
        self.text = json.dumps(date) if date is not None else ""
        self.url, self.reason = "", "OK"

    def json(self):
        return self._date


def fals(metoda):
    def f(url, **kw):
        APELURI.append({"met": metoda, "url": url, "corp": kw.get("json")})
        if "/img/" in url:
            return Raspuns(None, 200, JPEG)
        if url.endswith("/api/blog") and metoda == "POST":
            return Raspuns({"ok": True, "slug": "titlu", "url": "/blog/titlu"})
        if "/api/blog/" in url and metoda == "PUT":
            return Raspuns({"ok": True})
        if "/wp-json/wp/v2/media" in url:
            return Raspuns({"id": 55, "source_url": "https://servicepopescu.ro/wp/poza.jpg"})
        if "/wp-json/wp/v2/posts" in url:
            return Raspuns({"id": 99, "link": "https://servicepopescu.ro/articol/", "date_gmt": "2026-10-02T09:15:00"})
        return Raspuns({"eroare": "neasteptat " + url}, 500)
    return f


requests.get, requests.post, requests.put = fals("GET"), fals("POST"), fals("PUT")
panel.actualizeaza = lambda draft_id, **k: STARI.append({"id": draft_id, **k})

cl = client("moonpost.ro", blog_tip="api", blog_api_url="https://moonpost.ro/api/blog", blog_api_token="t", autor_nume="Dumitru Felix")
ciorna = {"id": "p1", "seo_title": "Cum îți mențîn blogul viu", "meta_description": "Că firmă mică, ai articole la 199 lei pe lună, fără bătăi de cap.",
          "article_html": "<h1>Cum îți mențin blogul viu</h1><p>Cu MOON Post plătești 199 lei pe lună.</p><h2>A</h2><p>b</p>",
          "canale": "wp", "are_imagine": 1, "imagine_key": "p1.jpg", "rezultat": {}}
config.aplica(cl)
check_approvals.publica(dict(ciorna))
post = next((a for a in APELURI if a["met"] == "POST"), {"corp": {}})["corp"]
cer(STARI and STARI[-1].get("stare") == "publicat" and post.get("title") == "Cum îți mențin blogul viu"
    and post.get("excerpt") == "Ca firmă mică, ai articole cu abonament lunar, fără bătăi de cap." and "199" not in post.get("content", ""),
    "corecturile sigure pleaca pe blog (titlu, descriere, articol)", [STARI[-1:], post])
cer(post.get("image_width") == 1536 and post.get("image_height") == 1024 and post.get("image_webp") == "https://app.moonpost.ro/img/p1.webp"
    and post.get("image") == "https://app.moonpost.ro/img/p1.jpg" and post.get("author", {}).get("name") == "Felix Dumitru",
    "blogul primeste marimea reala a pozei, varianta WebP si autorul", post)
cer("<h1" not in post.get("content", "") and post.get("content", "").startswith('<p class="moon-autor"')
    and post.get("content", "").count("moon-autor") == 1,
    "articolul trimis nu mai incepe cu titlul si n-are H1; semnatura sus, o data", post.get("content", "")[:200])
put = next((a for a in APELURI if a["met"] == "PUT"), {"corp": {}, "url": ""})
g = ld(put["corp"].get("content"))
art = (noduri(g, "BlogPosting") or [{}])[0]
rez = STARI[-1].get("rezultat") or {}
cer(put["url"] == "https://moonpost.ro/api/blog/titlu" and art.get("datePublished") == rez.get("publicat_la", "").replace("Z", "+00:00")
    and rez.get("publicat_la") == post.get("date") and art.get("image", {}).get("width") == 1536
    and art.get("publisher", {}).get("@id") == "https://moonpost.ro/#organizatie" and not noduri(g, "Organization")
    and art.get("headline") == "Cum îți mențin blogul viu",
    "datele structurate: datePublished = data trimisa la POST, tinuta in rezultat.publicat_la; schema noua", [rez, art])
cer(list(put["corp"].keys()) == ["content"], "a doua trecere (datele structurate) trimite doar continutul, ca motorul principal",
    list(put["corp"].keys()))

APELURI.clear(); STARI.clear()
config.aplica(client("themoonagency.ro", nume="THE MOON Agency", blog_tip="api", blog_api_url="https://themoonagency.ro/api/blog",
                     blog_api_token="t"))
check_approvals.publica(dict(ciorna, seo_title="Google Ads: buget de 1.500 lei pe lună"))
cer(STARI and STARI[-1].get("stare") == "eroare" and "nu pleacă pe blog" in STARI[-1].get("eroare", "")
    and "suma de bani in titlu" in STARI[-1].get("eroare", "") and not [a for a in APELURI if a["met"] in ("POST", "PUT")],
    "o suma care nu se poate scoate sigur din titlu: articolul NU pleaca, motivul e scris", [STARI, APELURI])

APELURI.clear(); STARI.clear()
config.aplica(client("servicepopescu.ro", nume="Service Popescu", wp_url="https://servicepopescu.ro", wp_user="u",
                     wp_app_password="p", autor_nume="Andrei Popescu", cui="RO123"))
check_approvals.publica(dict(ciorna, id="w1", seo_title="Schimb de ulei DSG: 900 lei", meta_description="Între 900 și 1.500 de lei.",
                             article_html="<h1>Schimb de ulei DSG: 900 lei</h1><p>Text.</p>"))
wp_post = [a for a in APELURI if a["met"] == "POST" and "/wp-json/wp/v2/posts" in a["url"]]
rez = (STARI[-1].get("rezultat") or {}) if STARI else {}
g = ld((wp_post[-1]["corp"] or {}).get("content") if len(wp_post) == 2 else "")
cer(len(wp_post) == 2 and wp_post[0]["corp"]["title"] == "Schimb de ulei DSG: 900 lei" and "<h1" not in wp_post[0]["corp"]["content"]
    and rez.get("publicat_la") == "2026-10-02T09:15:00Z" and rez.get("wp_id") == 99
    and noduri(g, "BlogPosting")[0]["datePublished"] == "2026-10-02T09:15:00+00:00" and noduri(g, "Organization")
    and noduri(g, "BlogPosting")[0]["image"] == {"@type": "ImageObject", "url": "https://servicepopescu.ro/wp/poza.jpg", "width": 1536, "height": 1024},
    "WordPress, client oarecare: pretul lui ramane, data primei publicari si wp_id tinute, schema veche cu data WordPress",
    [rez, wp_post and wp_post[0]["corp"]])

APELURI.clear(); STARI.clear()
config.aplica(cl)
check_approvals.publica(dict(ciorna, rezultat={"wp_link": "https://moonpost.ro/blog/titlu", "publicat_la": "2026-09-14T08:00:00Z"}))
cer(not [a for a in APELURI if "/api/blog" in a["url"]] and (STARI[-1].get("rezultat") or {}).get("publicat_la") == "2026-09-14T08:00:00Z",
    "reluarea dupa ce articolul e deja pe site: nu se republica, data primei publicari ramane", STARI[-1:])

# ================================================================== generarea (generate_draft)
print("\n-- generarea: poarta pe ciorna noua --")
import content_gen
import generate_draft
CIORNE: list = []
generate_draft.panel.creeaza_ciorna = lambda cid, cont: CIORNE.append(cont) or "g1"
generate_draft.curata_linkurile = lambda h, permise=None: (h, 0)
generate_draft._imagini = lambda continut, produs, probleme, prompt_deja_scris=False: {
    "imagine": None, "poza_costa": False, "eroare_img": "", "imagine_ig": None, "prompt_ig": ""}
generate_draft.tg.anunta_ciorna = lambda *a, **k: None
ARTICOL = {"topic_title": "Blog fără bătăi de cap", "angle": "a", "seo_title": "Cum îți mențîn blogul viu",
           "meta_description": "Că firmă mică, ai articole la 199 lei pe lună, fără bătăi de cap și fără agenție.",
           "article_html": "<h1>Cum îți mențin blogul viu</h1><p>Cu MOON Post plătești 199 lei pe lună.</p>",
           "facebook_text": "MOON Post: 199 lei pe lună.", "instagram_text": "i", "image_prompt": "p",
           "intrebare": "", "raspuns_scurt": ""}
generate_draft.generate_authority_draft = lambda: dict(ARTICOL)
MODEL: list = []
content_gen.cheama_modelul = lambda payload, **k: MODEL.append(payload) or raspunde({"seo_title": "Blog: buget de 900 lei"})(payload)
generate_draft.pentru_client(client("moonpost.ro", gemini_key="g", openai_key="o", autor_nume="Dumitru Felix"))
c0 = CIORNE[-1] if CIORNE else {}
cer(c0.get("seo_title") == "Cum îți mențin blogul viu" and c0.get("meta_description", "").startswith("Ca firmă mică, ai articole cu abonament lunar")
    and "199" not in c0.get("article_html", "") and "199" not in c0.get("facebook_text", "") and not MODEL
    and any(x.startswith("autocorectat: limba si sume") for x in c0.get("seo_probleme", [])),
    "ciorna noua pleaca in panou corectata, cu „autocorectat: …\" (informativ), fara apel de model", c0)
CIORNE.clear()
generate_draft.generate_authority_draft = lambda: dict(ARTICOL, seo_title="Google Ads: buget de 1.500 lei pe lună")
generate_draft.pentru_client(client("themoonagency.ro", gemini_key="g", openai_key="o"))
c1 = CIORNE[-1] if CIORNE else {}
cer(c1.get("seo_title") == "Google Ads: buget de 1.500 lei pe lună" and MODEL
    and (c1.get("seo_probleme") or [""])[0].startswith("suma de bani in titlu"),
    "suma din titlu pe themoonagency.ro: modelul incearca, raspunsul tot cu suma e refuzat, ramane problema grava (prima)", c1.get("seo_probleme"))

print("\n" + (f"{len(PICA)} TESTE PICA: " + "; ".join(PICA) if PICA else "toate trec"))
sys.exit(1 if PICA else 0)
