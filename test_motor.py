"""
Test local al motorului, fără rețea: înlocuim `requests` cu un fals care
răspunde ca panoul, Gemini, OpenAI, WordPress și Meta. Verifică fluxul întreg
pe doi clienți, inclusiv cazul „fără imagine".

Rulează:  python test_motor.py
"""

from __future__ import annotations
import base64
import io
import json
import os
import sys

os.environ["PANEL_URL"] = "https://post.exemplu.ro"
os.environ["CRON_KEY"] = "cheie-test"

import requests
from PIL import Image

PICA = []


def cer(cond, nume, extra=None):
    print(("  ok   " if cond else "  PICA ") + nume + ("" if cond or extra is None else f"  -> {extra}"))
    if not cond:
        PICA.append(nume)


def _png(culoare=(10, 10, 14)):
    b = io.BytesIO()
    Image.new("RGB", (64, 64), culoare).save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode()


# ---------------- panoul fals ----------------

PANOU = {
    "clienti": [
        {"id": 1, "slug": "the-moon-agency", "nume": "THE MOON Agency", "domeniu": "themoonagency.ro",
         "flux": "autoritate", "plan": "activ", "slot": 0, "canale": ["wp", "fb", "ig"], "config": {
             "wp_url": "https://themoonagency.ro", "wp_user": "MOON", "wp_app_password": "app-pass",
             "meta_token": "sys-token", "meta_page_id": "104878805077409", "meta_ig_id": "17841447599150600",
             "gemini_key": "g-key", "openai_key": "o-key", "nisa": "marketing digital",
             "cta": "Scrie-ne.",
             "logo_url": "https://post.exemplu.ro/img/logo-1.png"}},
        {"id": 2, "slug": "client-fara-chei", "nume": "Client fara chei", "domeniu": "exemplu.ro",
         "flux": "autoritate", "plan": "proba", "slot": 0, "canale": ["wp"],
         "config": {"wp_url": "https://exemplu.ro"}},
    ],
    "drafts": {}, "imagini": {}, "topics": {"1": ["Subiect vechi"]},
}
APELURI = []
BLOG_API = []
FB_TEXTE = []
IG_TEXTE = []
IMAGINE_PICA = False


class Raspuns:
    def __init__(self, date=None, cod=200, continut=b""):
        self.status_code = cod
        self._date = date if date is not None else {}
        self.content = continut
        self.text = json.dumps(self._date, ensure_ascii=False) if date is not None else ""
        self.url = ""
        self.reason = "OK"

    def json(self):
        return self._date

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code}")


def fals_request(metoda, url, **kw):
    APELURI.append((metoda, url))
    corp = kw.get("json") or {}

    # --- panoul ---
    if "/api/cron/clients" in url:
        return Raspuns({"ok": True, "clienti": PANOU["clienti"]})
    if "/api/cron/topics" in url:
        cid = str((kw.get("params") or {}).get("client_id"))
        return Raspuns({"ok": True, "titluri": PANOU["topics"].get(cid, [])})
    if "/api/cron/drafts" in url and metoda == "POST" and url.rstrip("/").endswith("drafts"):
        did = corp.get("id") or ("d%03d" % (len(PANOU["drafts"]) + 1))
        # panoul real intoarce canalele ca text "wp,fb,ig", nu ca lista
        can = corp.get("canale") or ["wp"]
        PANOU["drafts"][did] = {**corp, "id": did, "stare": "ciorna",
                                "canale": ",".join(can) if isinstance(can, list) else str(can)}
        return Raspuns({"ok": True, "id": did})
    if "/api/cron/drafts/" in url and metoda == "POST":
        did = url.rsplit("/", 1)[-1]
        PANOU["drafts"].setdefault(did, {"id": did}).update(corp)
        return Raspuns({"ok": True})
    if "/api/cron/drafts" in url and metoda == "GET":
        stare = (kw.get("params") or {}).get("stare")
        return Raspuns({"ok": True, "ciorne": [d for d in PANOU["drafts"].values() if d.get("stare") == stare]})
    if "/api/cron/image/" in url and metoda == "POST":
        did = url.rsplit("/", 1)[-1]
        PANOU["imagini"][did] = kw.get("data")
        PANOU["drafts"].setdefault(did, {}).update({"are_imagine": True, "imagine_key": did + ".jpg"})
        return Raspuns({"ok": True, "url": f"https://post.exemplu.ro/img/{did}.jpg"})
    if "poza-produs" in url and metoda == "GET":
        b = io.BytesIO()
        Image.new("RGB", (400, 400), (200, 40, 60)).save(b, format="JPEG")
        return Raspuns(None, 200, b.getvalue())
    if "logo-1.png" in url and metoda == "GET":
        b = io.BytesIO()
        Image.new("RGBA", (200, 50), (255, 47, 77, 255)).save(b, format="PNG")
        return Raspuns(None, 200, b.getvalue())
    if "/img/" in url and metoda == "GET":
        did = url.rsplit("/", 1)[-1].replace(".jpg", "")
        return Raspuns(None, 200, PANOU["imagini"].get(did, b""))

    # --- Gemini ---
    if "generativelanguage.googleapis.com/v1beta/interactions" in url:
        corp_g = kw.get("json") or {}
        CERERI_IMAGINE.append(corp_g)
        return Raspuns({"interaction": {"output_image": {"data": _png((10, 40, 60))}}})

    if "generativelanguage" in url:
        continut = {
            "topic_title": "Subiect nou de test", "angle": "unghi",
            "seo_title": "Titlu SEO de test", "meta_description": "descriere",
            "article_html": "<h1>Titlu</h1><p>text</p>", "facebook_text": "fb",
            "instagram_text": "ig", "image_prompt": "o scena concreta",
        }
        return Raspuns({"candidates": [{"content": {"parts": [{"text": json.dumps(continut)}]}}],
                        "usageMetadata": {"promptTokenCount": 1200, "candidatesTokenCount": 800}})

    # --- OpenAI ---
    if "api.openai.com/v1/responses" in url:
        corp_o = kw.get("json") or {}
        CERERI_TEXT.append(corp_o)
        continut = {
            "topic_title": "Subiect scris de ChatGPT", "angle": "unghi",
            "seo_title": "Titlu SEO de test", "meta_description": "descriere",
            "article_html": "<h1>Titlu</h1><p>text</p>", "facebook_text": "fb",
            "instagram_text": "ig", "image_prompt": "o scena concreta",
        }
        return Raspuns({"output": [{"type": "message", "role": "assistant",
                                    "content": [{"type": "output_text", "text": json.dumps(continut)}]}],
                        "usage": {"input_tokens": 1100, "output_tokens": 700}})

    if "api.openai.com" in url:
        if IMAGINE_PICA:
            return Raspuns({"error": "limita"}, 429)
        if "/images/edits" in url:
            # compunerea „wow": trebuie sa primeasca poza produsului ca fisier
            assert "files" in kw and "image" in kw["files"], "edits fara poza de pornire"
            return Raspuns({"data": [{"b64_json": _png((30, 30, 40))}]})
        corp = kw.get("json") or {}
        assert corp.get("quality") == "high", f"calitatea nu ajunge la OpenAI: {corp.get('quality')}"
        assert corp.get("size") == "1536x1024", f"marimea nu ajunge la OpenAI: {corp.get('size')}"
        return Raspuns({"data": [{"b64_json": _png()}]})

    # --- WordPress ---
    if "/wp-json/wp/v2/media" in url:
        return Raspuns({"id": 55, "source_url": "https://themoonagency.ro/wp/poza.jpg"})
    if "/wp-json/wp/v2/posts" in url:
        return Raspuns({"id": 99, "link": "https://themoonagency.ro/articol-de-test/"})

    # --- blog pe API propriu ---
    if url.endswith("/api/blog"):
        if metoda == "GET":
            return Raspuns([{"title": "Articol deja pe site", "slug": "articol-deja-pe-site"}])
        BLOG_API.append(corp)
        return Raspuns({"ok": True, "slug": "titlu-seo-de-test", "url": "/blog/titlu-seo-de-test"})

    # --- Google Business Profile ---
    if "oauth2.googleapis.com" in url:
        return Raspuns({"access_token": "ya29-test"})
    if "mybusiness.googleapis.com" in url:
        return Raspuns({"name": "locations/123/localPosts/9", "searchUrl": "https://g.page/postare"})

    # --- Meta ---
    if "graph.facebook.com" in url:
        if url.endswith(("/photos",)):
            FB_TEXTE.append(str((kw.get("data") or kw.get("json") or {}).get("caption")
                                or (kw.get("data") or {}).get("message") or ""))
            return Raspuns({"id": "1", "post_id": "p1"})
        if url.endswith("/feed"):
            return Raspuns({"id": "p2"})
        if url.endswith("/media"):
            IG_TEXTE.append(str((kw.get("data") or kw.get("json") or {}).get("caption") or ""))
            return Raspuns({"id": "c1"})
        if url.endswith("/media_publish"):
            return Raspuns({"id": "m1"})
        return Raspuns({"access_token": "page-token", "permalink_url": "https://fb.com/postare",
                        "permalink": "https://instagram.com/p/x", "status_code": "FINISHED"})

    # --- Telegram (clientul de test n-are bot, n-ar trebui apelat) ---
    if "api.telegram.org" in url:
        return Raspuns({"ok": True})

    raise AssertionError("URL neasteptat in test: " + url)


CERERI_TEXT: list = []
CERERI_IMAGINE: list = []

requests.request = fals_request
requests.get = lambda url, **kw: fals_request("GET", url, **kw)
requests.post = lambda url, **kw: fals_request("POST", url, **kw)

import generate_draft
import check_approvals
from config import config

print("MOON Post - test motor\n")

# 1. generare pe toti clientii
generate_draft.main_ = generate_draft.main
try:
    generate_draft.main()
except SystemExit:
    pass

cer(len(PANOU["drafts"]) == 1, "clientul fara chei e sarit, celalalt primeste ciorna", list(PANOU["drafts"]))
d = list(PANOU["drafts"].values())[0]
cer(d["seo_title"] == "Titlu SEO de test", "ciorna are titlul de la Gemini")
cer(d.get("are_imagine") is True, "imaginea a fost urcata in panou")
cer(any("api.telegram.org" in u for _, u in APELURI) is False, "fara bot configurat, Telegram nu e apelat")

# 2. publicare
d["stare"] = "aprobat"
APELURI.clear()
check_approvals.main()
cer(d["stare"] == "publicat", "ciorna trece in publicat", d.get("stare"))
cer(d["rezultat"]["wp_link"].endswith("/articol-de-test/"), "linkul de WordPress ajunge in panou")
cer(any(u.endswith("/photos") for _, u in APELURI), "Facebook: postare cu poza")
cer(any(u.endswith("/media_publish") for _, u in APELURI), "Instagram: postare publicata")

# 3. cazul fara imagine — inainte, Facebook si Instagram se sareau tacut
IMAGINE_PICA = True
PANOU["drafts"].clear(); PANOU["imagini"].clear(); APELURI.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
d2 = list(PANOU["drafts"].values())[0]
cer(d2.get("are_imagine") is False, "ciorna fara imagine e marcata explicit", d2.get("are_imagine"))
cer("nu are imagine" in (d2.get("eroare") or "") and "429" in (d2.get("eroare") or ""),
    "panoul spune de ce lipseste imaginea", d2.get("eroare"))

d2["stare"] = "aprobat"
APELURI.clear()
check_approvals.main()
cer(any(u.endswith("/feed") for _, u in APELURI), "fara imagine, Facebook primeste postare cu LINK")
cer(not any(u.endswith("/media_publish") for _, u in APELURI), "fara imagine, Instagram e sarit")
cer("Instagram sărit" in (d2.get("eroare") or ""), "panoul explica de ce lipseste Instagram", d2.get("eroare"))
cer(d2["stare"] == "publicat", "articolul TOT s-a publicat pe WordPress")

# 4. canalele din program sunt respectate la publicare
PANOU["drafts"].clear(); PANOU["imagini"].clear(); APELURI.clear()
IMAGINE_PICA = False
PANOU["clienti"][0]["canale"] = ["wp"]          # doar blogul
try:
    generate_draft.main()
except SystemExit:
    pass
d3 = list(PANOU["drafts"].values())[0]
cer(d3.get("canale") == "wp", "canalele slotului ajung pe ciorna", d3.get("canale"))
d3["stare"] = "aprobat"
APELURI.clear()
check_approvals.main()
cer(not any("graph.facebook.com" in u for _, u in APELURI),
    "cu doar blogul in program, Meta nu e apelat deloc")
cer(any("/wp-json/wp/v2/posts" in u for _, u in APELURI), "articolul tot se publica")

# 5. slotul se trimite mai departe, ca panoul sa stie ce a rulat
cer(d3.get("slot") == 0, "slotul ajunge pe ciorna")

# 6. consumul de tokeni si logoul clientului
import image_gen
image_gen._LOGO_CACHE.clear()   # altfel logoul ramane din rularile de mai sus
PANOU["drafts"].clear(); PANOU["imagini"].clear(); APELURI.clear()
PANOU["clienti"][0]["canale"] = ["wp", "fb", "ig"]
try:
    generate_draft.main()
except SystemExit:
    pass
d4 = list(PANOU["drafts"].values())[0]
cer(d4.get("tokens_in") == 1200 and d4.get("tokens_out") == 800,
    "consumul de tokeni ajunge in panou", [d4.get("tokens_in"), d4.get("tokens_out")])
cer(d4.get("imagini") == 1 and d4.get("model_imagine") == "gpt-image-2"
    and d4.get("calitate_imagine") == "mare",
    "se raporteaza imaginea, cu modelul si calitatea folosite",
    [d4.get("imagini"), d4.get("model_imagine"), d4.get("calitate_imagine")])
cer(any("logo-1.png" in u for _, u in APELURI), "logoul clientului e descarcat si pus pe imagine")

# fara logo pus in panou, imaginea iese curata
image_gen._LOGO_CACHE.clear()
PANOU["clienti"][0]["config"]["logo_url"] = ""
PANOU["drafts"].clear(); APELURI.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
cer(not any("logo-1.png" in u for _, u in APELURI),
    "fara logo pus, nu se pune logoul altcuiva pe imagine")

# 7. Profilul Google: se publica doar daca e in canalele ciornei
import image_gen
image_gen._LOGO_CACHE.clear()
PANOU["clienti"][0]["config"].update({
    "google_client_id": "gc", "google_client_secret": "gs",
    "gbp_refresh_token": "refresh", "gbp_location": "locations/123"})
PANOU["clienti"][0]["canale"] = ["wp", "gbp"]
PANOU["drafts"].clear(); APELURI.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
d5 = list(PANOU["drafts"].values())[0]
d5["stare"] = "aprobat"
APELURI.clear()
check_approvals.main()
cer(any("localPosts" in u for _, u in APELURI), "postarea ajunge pe Profilul Google")
cer(d5["rezultat"].get("gbp_link") == "https://g.page/postare", "linkul de Google ajunge in panou",
    d5["rezultat"])
cer(not any("graph.facebook.com" in u for _, u in APELURI),
    "cu wp+gbp in program, Meta ramane neatins")

# 8. fluxul catalog: scriem despre produsul primit de la panou
image_gen._LOGO_CACHE.clear()
PANOU["clienti"][0]["flux"] = "catalog"
PANOU["clienti"][0]["canale"] = ["wp", "fb"]
PRODUS = {
    "ext_id": "SKU-77", "nume": "Parfum Test 100ml", "url": "https://exemplu.ro/p/77",
    "pret": 249, "pret_vechi": 299, "moneda": "RON", "categorii": "Parfumuri > Barbati",
    "descriere": "Note de lemn si citrice.", "imagine": "https://cdn.exemplu/poza-produs.jpg",
    "mod_imagine": "catalog",
    "conexe": [
        {"nume": "Set cadou", "url": "https://exemplu.ro/p/88", "pret": 99, "moneda": "RON"},
        {"nume": "Deodorant asortat", "url": "https://exemplu.ro/p/99", "pret": 49, "moneda": "RON"},
    ],
}
PANOU["clienti"][0]["produs"] = dict(PRODUS)
PANOU["drafts"].clear(); APELURI.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
d6 = list(PANOU["drafts"].values())[0]
cer(d6.get("produs_ext_id") == "SKU-77", "ciorna retine despre ce produs e", d6.get("produs_ext_id"))
cer(any("poza-produs" in u for _, u in APELURI), "poza vine din catalog")
cer(not any("api.openai.com" in u for _, u in APELURI),
    "pe modul catalog, OpenAI nu e apelat deloc")
cer(d6.get("imagini") == 0, "poza neatinsa nu intra la costuri", d6.get("imagini"))
cer(d6.get("are_imagine") is True, "ciorna are totusi imagine")

# 9. modul „wow": poza reala devine punctul de plecare al unei scene
image_gen._LOGO_CACHE.clear()
PANOU["clienti"][0]["produs"] = dict(PRODUS, mod_imagine="wow")
PANOU["drafts"].clear(); APELURI.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
d7 = list(PANOU["drafts"].values())[0]
cer(any("/images/edits" in u for _, u in APELURI),
    "modul wow trece poza prin compunere, nu prin generare de la zero")
cer(not any("/images/generations" in u for _, u in APELURI),
    "nu se genereaza o imagine inventata cand exista poza reala")
cer(d7.get("imagini") == 1, "imaginea compusa se pune la costuri", d7.get("imagini"))

# daca compunerea pica, ramanem cu poza din catalog, nu fara imagine
IMAGINE_PICA = True
image_gen._LOGO_CACHE.clear()
PANOU["drafts"].clear(); APELURI.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
d8 = list(PANOU["drafts"].values())[0]
cer(d8.get("are_imagine") is True and d8.get("imagini") == 0,
    "cand compunerea pica, ramane poza din catalog si nu se factureaza",
    [d8.get("are_imagine"), d8.get("imagini")])
IMAGINE_PICA = False

# 10. produsele conexe ajung in promptul de catalog
from content_gen_catalog import _prompt
pr = _prompt(PRODUS)
cer("Set cadou" in pr and "https://exemplu.ro/p/88" in pr,
    "produsele conexe intra in prompt cu linkurile lor")
cer("Merge bine cu" in pr, "promptul cere sectiunea de recomandari in articol")
cer("NU descrie produsul in sine" in pr.replace("î", "i").replace("ă", "a").replace("ș", "s"),
    "promptul de imagine descrie scena, nu produsul")

# fara produs la rand, clientul de catalog e sarit
PANOU["clienti"][0]["produs"] = None
PANOU["drafts"].clear()
try:
    generate_draft.main()
except SystemExit:
    pass
cer(len(PANOU["drafts"]) == 0, "fara produs la rand, nu se genereaza nimic")
PANOU["clienti"][0]["flux"] = "autoritate"

# 11. blog pe API propriu, in loc de WordPress
PANOU["clienti"][0]["config"].update({
    "blog_api_url": "https://themoonagency.ro/api/blog", "blog_api_token": "token-de-test"})
PANOU["drafts"].clear(); APELURI.clear(); BLOG_API.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
d9 = list(PANOU["drafts"].values())[0]
cer(any(u.endswith("/api/blog") for m, u in APELURI if m == "GET"),
    "anti-duplicat: se citesc articolele deja publicate pe blogul propriu")

d9["stare"] = "aprobat"
APELURI.clear()
check_approvals.main()
cer(d9["stare"] == "publicat", "ciorna se publica prin API-ul propriu", d9.get("stare"))
cer(len(BLOG_API) == 1, "s-a trimis exact un articol", len(BLOG_API))
trimis = BLOG_API[0]
cer(trimis["title"] == "Titlu SEO de test" and trimis["content"].startswith("<"),
    "articolul pleaca cu titlu si HTML")
cer(str(trimis.get("image", "")).startswith("https://"),
    "imaginea pleaca ca adresa publica, nu ca fisier", trimis.get("image"))
cer(d9["rezultat"]["wp_link"] == "https://themoonagency.ro/blog/titlu-seo-de-test",
    "linkul relativ e completat cu domeniul", d9["rezultat"].get("wp_link"))
cer(not any("/wp-json/" in u for _, u in APELURI),
    "cu API propriu nu se mai atinge WordPress")
cer(any(u.endswith("/photos") for _, u in APELURI), "Facebook merge si pe fluxul cu API propriu")

# fara token, se cere completarea datelor de blog
PANOU["clienti"][0]["config"].pop("blog_api_token")
PANOU["clienti"][0]["config"].pop("wp_app_password")
config.aplica(PANOU["clienti"][0])
cer(len(config.lipsuri_publicare()) == 1 and "blog" in config.lipsuri_publicare()[0].lower(),
    "fara WordPress si fara API propriu, publicarea se opreste cu mesaj clar",
    config.lipsuri_publicare())

# 12. blog manual (Gomag): articolul ramane in panou, Facebook merge
PANOU["clienti"][0]["config"].update({"blog_tip": "manual",
    "wp_url": "https://exemplu.ro", "wp_user": "MOON", "wp_app_password": "app-pass"})
PANOU["clienti"][0]["canale"] = ["wp", "fb"]
PANOU["drafts"].clear(); APELURI.clear(); BLOG_API.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
d10 = list(PANOU["drafts"].values())[0]
d10["stare"] = "aprobat"
APELURI.clear()
check_approvals.main()
cer(d10["stare"] == "publicat", "cu blog manual, ciorna se publica pe restul canalelor", d10.get("stare"))
cer(not any("/wp-json/" in u for _, u in APELURI) and not BLOG_API,
    "blogul nu e atins deloc pe manual", [u for _, u in APELURI])
cer(any(u.endswith("/photos") for _, u in APELURI), "Facebook merge si pe blog manual")
cer("copiaza de mana" in (d10.get("eroare") or ""),
    "ciorna spune ca articolul se copiaza de mana", d10.get("eroare"))
config.aplica(PANOU["clienti"][0])
cer(config.lipsuri_publicare() == [], "pe manual nu se cer date de blog", config.lipsuri_publicare())
PANOU["clienti"][0]["config"]["blog_tip"] = "wp"

# 13. linkuri inventate, CTA cu buton, si adresa articolului pe Facebook/Instagram
from content_gen import curata_linkurile

LINKURI_VII = {"https://openai.com/chiar-exista"}


def _fals_link(metoda, url, **kw):
    if url in LINKURI_VII:
        return Raspuns({}, 200)
    return Raspuns({}, 404)


_req_vechi = requests.request
requests.request = _fals_link
html_curatat, scoase = curata_linkurile(
    '<p>Vezi <a href="https://openai.com/chiar-exista">sursa buna</a> si '
    '<a href="https://openai.com/index/inventat-de-model/">sursa inventata</a>.</p>')
requests.request = _req_vechi
cer(scoase == 1, "linkul inventat e scos", scoase)
cer("sursa inventata" in html_curatat and "inventat-de-model" not in html_curatat,
    "textul ramane, doar linkul mort dispare", html_curatat)
cer("chiar-exista" in html_curatat, "linkul valid nu e atins")

# paginile clientului nu se mai verifica: le-am citit noi de pe site
requests.request = _fals_link
html2, scoase2 = curata_linkurile(
    '<p><a href="https://themoonagency.ro/meta-ads">Meta Ads</a></p>',
    {"https://themoonagency.ro/meta-ads"})
requests.request = _req_vechi
cer(scoase2 == 0 and "meta-ads" in html2, "paginile citite de pe site sunt de incredere", html2)

# CTA ca buton
PANOU["clienti"][0]["config"].update({
    "cta": "Solicita un audit gratuit", "cta_link": "https://themoonagency.ro/contact", "cta_tip": "buton"})
PANOU["clienti"][0]["canale"] = ["wp", "fb", "ig"]
PANOU["drafts"].clear(); APELURI.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
d11 = list(PANOU["drafts"].values())[0]
cer('href="https://themoonagency.ro/contact"' in d11["article_html"],
    "indemnul primeste linkul ales in panou")
cer("border-radius" in d11["article_html"], "pe buton iese buton, nu link simplu")

# adresa articolului ajunge in textele de social
d11["stare"] = "aprobat"
APELURI.clear()
check_approvals.main()
cer(any("themoonagency.ro/articol-de-test" in t for t in FB_TEXTE),
    "Facebook primeste adresa articolului", FB_TEXTE[-1:] )
cer(any("Articolul complet: https://themoonagency.ro/articol-de-test" in t
        for t in IG_TEXTE), "Instagram primeste adresa intreaga, cu https://", IG_TEXTE[-1:])

# 14. orice furnizor, pe orice fel: text de la ChatGPT, poza de la Nano Banana
PANOU["clienti"][0]["config"].update({
    "model_text": "gpt-5.6-luna", "model_imagine": "gemini-3.1-flash-image"})
PANOU["clienti"][0]["canale"] = ["wp", "fb"]
PANOU["drafts"].clear(); APELURI.clear(); CERERI_TEXT.clear(); CERERI_IMAGINE.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
d12 = list(PANOU["drafts"].values())[0]
cer(bool(CERERI_TEXT) and CERERI_TEXT[0].get("model") == "gpt-5.6-luna",
    "textul poate veni de la ChatGPT, nu doar de la Gemini", CERERI_TEXT[:1])
cer(any(t.get("type") == "web_search" for t in (CERERI_TEXT[0].get("tools") or [])),
    "si pe ChatGPT modelul are voie sa caute pe net", CERERI_TEXT[0].get("tools"))
cer(bool(CERERI_IMAGINE) and CERERI_IMAGINE[0].get("model") == "gemini-3.1-flash-image",
    "poza poate veni de la Nano Banana, nu doar de la OpenAI", CERERI_IMAGINE[:1])
cer((CERERI_IMAGINE[0].get("response_format") or {}).get("aspect_ratio") == "3:2",
    "formatul cerut in panou ajunge la Nano Banana ca proportie",
    CERERI_IMAGINE[0].get("response_format"))
cer(d12["model_text"] == "gpt-5.6-luna" and d12["model_imagine"] == "gemini-3.1-flash-image",
    "panoul afla exact ce modele au fost folosite, ca sa iasa costul",
    [d12.get("model_text"), d12.get("model_imagine")])
cer(d12["tokens_in"] == 1100 and d12["tokens_out"] == 700,
    "consumul de la ChatGPT se numara la fel ca cel de la Gemini",
    [d12.get("tokens_in"), d12.get("tokens_out")])

config.aplica(PANOU["clienti"][1])
cer(config.lipsuri_generare() == ["cheia Gemini", "cheia OpenAI"],
    "se cer amandoua cheile cand modelele vin din case diferite", config.lipsuri_generare())
PANOU["clienti"][1]["config"].update({"model_text": "gemini-3.6-flash",
                                      "model_imagine": "gemini-3.1-flash-image"})
config.aplica(PANOU["clienti"][1])
cer(config.lipsuri_generare() == ["cheia Gemini"],
    "cu totul pe Gemini, cheia OpenAI nu mai e ceruta degeaba", config.lipsuri_generare())

print("\n" + (f"{len(PICA)} TESTE PICA" if PICA else "toate trec"))
sys.exit(1 if PICA else 0)
