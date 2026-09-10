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
import time
import os
import sys

os.environ["PANEL_URL"] = "https://post.exemplu.ro"
os.environ["CRON_KEY"] = "cheie-test"

import requests
from PIL import Image

PICA = []
MARIMI_CERUTE: list = []
FB_POZE: list = []
IG_POZE: list = []


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
        eIg = (kw.get("params") or {}).get("fel") == "ig"
        PANOU["imagini"][did + ("-ig" if eIg else "")] = kw.get("data")
        PANOU["drafts"].setdefault(did, {}).update(
            {"are_imagine_ig": True, "imagine_ig_key": did + "-ig.jpg"} if eIg
            else {"are_imagine": True, "imagine_key": did + ".jpg"})
        cheie = did + ("-ig" if eIg else "")
        return Raspuns({"ok": True, "url": f"https://post.exemplu.ro/img/{cheie}.jpg"})
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

    # cererea separata pentru promptul de imagine (are articolul in fata)
    if "generativelanguage" in url and "fotoeditor" in str((kw.get("json") or {})):
        CERERI_IMAGINE_PROMPT.append((kw.get("json") or {}))
        return Raspuns({"candidates": [{"content": {"parts": [{"text": IMAGINE_RASPUNS[0]}]}}],
                        "usageMetadata": {"promptTokenCount": 1200, "candidatesTokenCount": 150}})

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
        if "fotoeditor" in str(corp_o):
            CERERI_IMAGINE_PROMPT.append(corp_o)
            return Raspuns({"output": [{"type": "message", "role": "assistant",
                                        "content": [{"type": "output_text", "text": IMAGINE_RASPUNS[0]}]}],
                            "usage": {"input_tokens": 1100, "output_tokens": 700}})
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
        MARIMI_CERUTE.append(corp.get("size"))
        assert corp.get("size") in ("1536x1024", "1024x1024", "1024x1536"), \
            f"marime necunoscuta ceruta de la OpenAI: {corp.get('size')}"
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
            FB_POZE.append(str((kw.get("data") or kw.get("json") or {}).get("url") or ""))
            return Raspuns({"id": "1", "post_id": "p1"})
        if url.endswith("/feed"):
            return Raspuns({"id": "p2"})
        if url.endswith("/media"):
            IG_TEXTE.append(str((kw.get("data") or kw.get("json") or {}).get("caption") or ""))
            IG_POZE.append(str((kw.get("data") or kw.get("json") or {}).get("image_url") or ""))
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
CERERI_IMAGINE_PROMPT: list = []
# raspunsul dat de model la cererea de prompt de imagine; testele il schimba
IMAGINE_RASPUNS = [
    "Close-up of a shop owner's hands counting printed order slips on a scratched wooden "
    "counter at closing time, a cooling cup of coffee and a phone face-down beside them, "
    "shot on 35mm at waist level with shallow depth of field, late afternoon light coming "
    "in sideways through a window, warm browns and muted greens, quiet and a little tired."
]
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
# 1200+800 articolul, 1200+150 cererea separata pentru promptul de imagine
cer(d4.get("tokens_in") == 2400 and d4.get("tokens_out") == 950,
    "consumul ajunge in panou, INCLUSIV apelul pentru promptul de imagine",
    [d4.get("tokens_in"), d4.get("tokens_out")])
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

# 6b. afisul de Instagram: a doua imagine, facuta doar daca omul a bifat-o
image_gen._LOGO_CACHE.clear()
PANOU["clienti"][0]["config"]["logo_url"] = "https://post.exemplu.ro/img/logo-1.png"
PANOU["clienti"][0]["canale"] = ["wp", "fb", "ig"]
PANOU["drafts"].clear(); PANOU["imagini"].clear(); APELURI.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
dIG = list(PANOU["drafts"].values())[0]
cer(not dIG.get("are_imagine_ig"),
    "fara bifa, nu se face a doua imagine si nu se plateste o generare in plus")

PANOU["clienti"][0]["config"].update({
    "ig_separata": True, "ig_sablon": "lista", "ig_format": "4:5",
    "ig_banda": True, "ig_handle": "@moon · themoonagency.ro"})
image_gen._LOGO_CACHE.clear()
PANOU["drafts"].clear(); PANOU["imagini"].clear(); APELURI.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
dIG = list(PANOU["drafts"].values())[0]
did = dIG["id"]
cer(dIG.get("are_imagine") is True and dIG.get("are_imagine_ig") is True,
    "cu bifa pusa, ciorna are AMANDOUA imaginile", [dIG.get("are_imagine"), dIG.get("are_imagine_ig")])
cer(dIG.get("imagini") == 2, "si se factureaza doua generari, nu una", dIG.get("imagini"))
cer("GRAPHIC DESIGN" in (dIG.get("image_prompt_ig") or ""),
    "promptul afisului se salveaza pe ciorna, ca sa se vada in panou")
_ig = Image.open(io.BytesIO(PANOU["imagini"][did + "-ig"]))
cer(abs(_ig.size[0] / _ig.size[1] - 0.8) < 0.03,
    "afisul chiar iese in 4:5, nu lat ca poza de blog", _ig.size)
_bl = Image.open(io.BytesIO(PANOU["imagini"][did]))
cer(_bl.size != _ig.size, "poza de blog ramane a ei, in formatul ei", [_bl.size, _ig.size])

# la publicare, Instagram ia afisul, nu poza de blog
dIG["stare"] = "aprobat"
APELURI.clear()
check_approvals.main()
cer(IG_POZE and IG_POZE[-1].endswith("-ig.jpg"),
    "Instagram primeste afisul (-ig.jpg), nu poza de blog", IG_POZE[-2:])
cer(FB_POZE and not FB_POZE[-1].endswith("-ig.jpg"),
    "Facebook ramane pe poza de blog", FB_POZE[-2:])
cer("1024x1536" in MARIMI_CERUTE, "afisul se cere in marimea portret", MARIMI_CERUTE[-3:])

PANOU["clienti"][0]["config"].update({"ig_separata": False, "ig_banda": False})

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
cer(len(config.lipsuri_publicare(["wp"])) == 1 and "blog" in config.lipsuri_publicare(["wp"])[0].lower(),
    "fara WordPress si fara API propriu, publicarea se opreste cu mesaj clar",
    config.lipsuri_publicare(["wp"]))

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
cer(config.lipsuri_publicare(["wp"]) == [], "pe manual nu se cer date de blog", config.lipsuri_publicare(["wp"]))
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
# textul vine de la ChatGPT (1100/700), promptul de imagine tot de acolo (1100/700)
cer(d12["tokens_in"] == 2200 and d12["tokens_out"] == 1400,
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

# 14b. publicare: canale, esecuri partiale, linkuri
import publishers.blog_api as _bapi
from config import config as _cfg

_cfg.aplica(PANOU["clienti"][0])
_cfg.BLOG_API_URL = "https://client.ro/wp-json/moon/v1/articole"
cer(_bapi._radacina() == "https://client.ro",
    "linkul articolului se face din domeniu, nu prin taiere dupa „/api/”", _bapi._radacina())
_cfg.BLOG_API_URL = "https://themoonagency.ro/api/blog"
cer(_bapi._radacina() == "https://themoonagency.ro", "si pe adresa obisnuita iese la fel")

# blogul nu se mai publica pe un slot care nu-l cere
PANOU["clienti"][0]["config"].update({"blog_tip": "api",
    "blog_api_url": "https://themoonagency.ro/api/blog", "blog_api_token": "token-de-test"})
PANOU["clienti"][0]["canale"] = ["fb"]
PANOU["drafts"].clear(); BLOG_API.clear(); APELURI.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
dS = list(PANOU["drafts"].values())[0]
dS["stare"] = "aprobat"
dS["canale"] = "fb"
check_approvals.main()
cer(not BLOG_API, "un slot doar de Facebook NU mai publica articolul pe blog", BLOG_API)
cer(any(u.endswith("/photos") for _, u in APELURI), "dar Facebook merge normal")

# un canal cazut nu mai inchide ciorna ca „publicata"
PANOU["clienti"][0]["canale"] = ["wp", "fb", "ig"]
PANOU["drafts"].clear(); BLOG_API.clear(); APELURI.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
dP = list(PANOU["drafts"].values())[0]
dP["stare"] = "aprobat"
dP["canale"] = "wp,fb,ig"
IMAGINE_PICA = False
_meta_vechi = meta_mod.publish_instagram_photo if (meta_mod := __import__("publishers.meta", fromlist=["meta"])) else None
def _ig_pica(*a, **k):
    raise RuntimeError("Instagram a refuzat imaginea")
meta_mod.publish_instagram_photo = _ig_pica
check_approvals.main()
meta_mod.publish_instagram_photo = _meta_vechi
cer(dP["stare"] == "eroare",
    "daca pica un canal cerut, ciorna NU se inchide ca publicata", dP.get("stare"))
cer("Instagram" in (dP.get("eroare") or ""), "si scrie ce anume a picat", dP.get("eroare"))
cer(dP["rezultat"].get("wp_link") and dP["rezultat"].get("fb_link"),
    "ce a reusit ramane inregistrat", dP.get("rezultat"))

# la reincercare nu se republica ce a mers deja
BLOG_API.clear(); APELURI.clear()
dP["stare"] = "aprobat"
check_approvals.main()
cer(not BLOG_API, "la reincercare, articolul NU se publica a doua oara pe blog", BLOG_API)
cer(not any(u.endswith("/photos") for _, u in APELURI),
    "si nici pe Facebook", [u for _, u in APELURI])
cer(dP["stare"] == "publicat", "dupa ce trece si Instagram, ciorna se inchide", dP.get("stare"))

# 15. SEO si GEO: forma articolului, datele structurate, verificarile
import seo
from content_gen import SCHELETE, curata_linkurile, _system_prompt

config.aplica(PANOU["clienti"][0])
config.CLIENT_DOMAIN = "themoonagency.ro"
config.AUTOR_NUME = "Felix Ionescu"
config.AUTOR_ROL = "fondator"
config.ORG_CUI = "RO12345678"
config.ORG_ORAS = "Bucuresti"

CIORNA_SEO = {
    "seo_title": "Cat costa reclamele pe TikTok in 2026",
    "meta_description": "Un buget de start pentru TikTok Ads porneste de la 20 de euro pe zi.",
    "topic_title": "Buget TikTok Ads",
    "intrebare": "Cat costa reclamele pe TikTok?",
    "raspuns_scurt": "Reclamele pe TikTok pornesc de la 20 de euro pe zi pentru un set de anunturi.",
    "article_html": "<h1>T</h1><p>Text de " + ("cuvant " * 700) + "</p><h2>A</h2><h2>B</h2>"
                    "<p>In 2026 pretul e 20 euro. <a href='https://themoonagency.ro/servicii'>servicii</a> "
                    "<a href='https://themoonagency.ro/contact'>contact</a> "
                    "<a href='https://ins.ro/date'>INS</a></p>",
}
jsonld = seo.date_structurate(CIORNA_SEO, "https://themoonagency.ro/blog/tiktok-ads", "https://x/y.jpg")
cer(jsonld.startswith("<script type=\"application/ld+json\">"), "articolul pleaca cu date structurate")
import json as _j
graf = _j.loads(jsonld.split(">", 1)[1].rsplit("<", 1)[0])["@graph"]
tipuri = [x["@type"] for x in graf]
cer("BlogPosting" in tipuri and "Organization" in tipuri and "BreadcrumbList" in tipuri,
    "graful are articolul, firma si firimiturile", tipuri)
cer("FAQPage" not in tipuri and "HowTo" not in tipuri and "Speakable" not in tipuri,
    "nu mai emitem tipuri care nu mai produc nimic din mai 2026", tipuri)
art = [x for x in graf if x["@type"] == "BlogPosting"][0]
cer(art["datePublished"] == art["dateModified"],
    "la publicare, data modificarii e egala cu data publicarii", art["dateModified"])
cer(art["inLanguage"] == "ro-RO" and art["abstract"].startswith("Reclamele"),
    "articolul isi duce limba si raspunsul scurt in datele structurate")
pers = [x for x in graf if x["@type"] == "Person"]
cer(pers and pers[0]["name"] == "Felix Ionescu", "autorul real ajunge in datele structurate")
org = [x for x in graf if x["@type"] == "Organization"][0]
cer(org.get("vatID") == "RO12345678", "CUI-ul intra in datele structurate (se verifica la ANAF)")

config.AUTOR_NUME = ""
graf2 = _j.loads(seo.date_structurate(CIORNA_SEO, "https://themoonagency.ro/blog/x").split(">", 1)[1].rsplit("<", 1)[0])["@graph"]
cer(not [x for x in graf2 if x["@type"] == "Person"],
    "fara autor real, semneaza firma — nu inventam un nume")
config.AUTOR_NUME = "Felix Ionescu"

# un articol bun are linkuri interne REALE, iar site-ul e citit
config.SITE = [{"url": "https://themoonagency.ro/servicii", "titlu": "Servicii"},
               {"url": "https://themoonagency.ro/meta-ads", "titlu": "Meta Ads"},
               {"url": "https://themoonagency.ro/despre", "titlu": "Despre"}]
config.CLIENT_CTA_LINK = "https://themoonagency.ro/contact"
CIORNA_SEO["article_html"] = CIORNA_SEO["article_html"].replace(
    "<a href='https://themoonagency.ro/contact'>contact</a>",
    "<a href='https://themoonagency.ro/meta-ads'>Meta Ads</a>")
cer(seo.controale(CIORNA_SEO) == [], "un articol bun trece toate verificarile", seo.controale(CIORNA_SEO))

# indemnul e pus de NOI dupa generare — nu se pune la socoteala ca link intern
doar_cta = dict(CIORNA_SEO, article_html=CIORNA_SEO["article_html"]
                .replace("https://themoonagency.ro/servicii", "https://themoonagency.ro/contact")
                .replace("https://themoonagency.ro/meta-ads", "https://themoonagency.ro/contact"))
cer(any("link" in x for x in seo.controale(doar_cta)),
    "un articol care are DOAR indemnul nu trece drept articol cu linkuri interne",
    seo.controale(doar_cta))

# fara site citit, mesajul spune CAUZA, nu simptomul
_site_vechi = config.SITE
config.SITE = []
mesaje = seo.controale(doar_cta)
cer(any("n-a fost citit" in x for x in mesaje),
    "fara pagini citite, mesajul zice sa citesti site-ul, nu „vrem 3-5 linkuri”", mesaje)
config.SITE = [{"url": "https://themoonagency.ro/servicii"}]
cer(any("stim doar 1 pagini" in x for x in seo.controale(doar_cta)),
    "cu prea putine pagini stiute, mesajul spune si asta", seo.controale(doar_cta))
config.SITE = _site_vechi
rau = dict(CIORNA_SEO, article_html="<h1>a</h1><h1>b</h1><p>In lumea de azi, totul se schimba.</p>",
           seo_title="T" * 80, meta_description="")
p_rau = seo.controale(rau)
cer(any("H1" in x for x in p_rau) and any("65" in x for x in p_rau) and
    any("meta description" in x for x in p_rau) and any("cliseu" in x for x in p_rau) and
    any("scurt" in x for x in p_rau),
    "un articol prost e semnalat pe fiecare problema in parte", p_rau)

cer("<script" not in seo.curata_html('<p>ok</p><script>alert(1)</script>') and
    "onerror" not in seo.curata_html('<img src=x onerror="alert(1)">') and
    "javascript:" not in seo.curata_html('<a href="javascript:alert(1)">x</a>'),
    "scripturile si atributele periculoase nu ajung pe site-ul clientului",
    seo.curata_html('<img src=x onerror="alert(1)">'))

# datele structurate nu pot fi „iesite" cu </script>
rau_titlu = dict(CIORNA_SEO, seo_title="Cum alegem </script><script>alert(1)</script> corect")
bloc = seo.date_structurate(rau_titlu, "https://themoonagency.ro/blog/x")
cer("</script>" not in bloc[:-len("</script>")],
    "un titlu care contine marcaj de inchidere nu mai iese din datele structurate", bloc[:120])
cer(_j.loads(bloc.split(">", 1)[1].rsplit("<", 1)[0]), "si blocul ramane JSON valid")

# curatarea HTML prinde si formele fara spatiu / fara ghilimele
for periculos in ['<img/onerror=alert(1) src=x>', '<svg/onload=alert(1)>',
                  '<a href=javascript:alert(1)>x</a>', '<a href="jav\tascript:alert(1)">y</a>']:
    curat = seo.curata_html(periculos)
    cer("onerror" not in curat and "onload" not in curat and "javascript:" not in curat.replace(" ", ""),
        "e curatat: " + periculos[:32], curat)
cer("<b>bold</b>" in seo.curata_html("<p>text <b>bold</b></p>"),
    "dar marcajul normal ramane neatins")

# raspunsul taiat la limita de tokeni nu mai e carpit si publicat
import content_gen as _cg
try:
    _cg._verifica_intreg_gemini({"candidates": [{"finishReason": "MAX_TOKENS"}]})
    cer(False, "un raspuns taiat trebuie sa opreasca generarea")
except RuntimeError as e:
    cer("jumatati" in str(e), "un raspuns taiat opreste generarea, nu se carpeste", str(e)[:70])
_cg._verifica_intreg_gemini({"candidates": [{"finishReason": "STOP"}]})
cer(True, "un raspuns intreg trece mai departe")

# regexul de linkuri nu mai poate bloca rularea
_req_v2 = requests.request
requests.request = lambda m2, u2, **k2: Raspuns({}, 200)
_t0 = time.time()
_cg.curata_linkurile("<a " + " ".join(f'data-x{i}="v{i}"' for i in range(22)) + ">fara href</a>")
requests.request = _req_v2
cer(time.time() - _t0 < 1.0,
    "un tag cu multe atribute si fara href nu mai blocheaza rularea",
    f"{(time.time() - _t0):.2f}s")

# --- promptul de imagine: scris separat, cu articolul in fata ---
import imagine_prompt

config.aplica(PANOU["clienti"][0])
config.CLIENT_NICHE = "marketing digital"
CIORNA_IMG = {"seo_title": "Cat costa reclamele pe TikTok in 2026",
              "raspuns_scurt": "Pornesc de la 20 de euro pe zi pentru un set de anunturi.",
              "article_html": "<p>Bugetul minim s-a schimbat in 2026.</p>"}
cerere_img = imagine_prompt.cere(CIORNA_IMG)
cer("Cat costa reclamele pe TikTok" in cerere_img and "20 de euro" in cerere_img,
    "cererea de imagine chiar contine articolul, nu doar subiectul")
cer("TENSIUNEA" in cerere_img, "i se cere sa ilustreze tensiunea articolului, nu tema in general")
for cliseu in ["dashboards", "holograms", "circuit boards", "robots", "handshakes", "lightbulb"]:
    cer(cliseu in cerere_img, "cliseul e interzis pe nume: " + cliseu)
cer("s-ar putea fotografia AZI" in cerere_img, "scena trebuie sa poata fi fotografiata cu un aparat")

# paleta agentiei NU se mai da tuturor clientilor
config.IMAGINE_PALETA = ""
cer("roșu" not in cerere_img and "coral" not in cerere_img.lower(),
    "paleta THE MOON nu se mai lipeste pe toti clientii")
config.IMAGINE_PALETA = "verde salvie si lemn deschis"
cer("verde salvie" in imagine_prompt.cere(CIORNA_IMG), "paleta clientului ajunge in cerere")
config.IMAGINE_STIL = "ilustratie"
cer("NU randare 3D" in imagine_prompt.cere(CIORNA_IMG),
    "pe ilustratie se cere desen, nu randare 3D — de acolo venea aerul de reclama la software")
config.IMAGINE_EVITA = "oameni in costum"
cer("oameni in costum" in imagine_prompt.cere(CIORNA_IMG), "ce nu vrea clientul ajunge in cerere")
config.IMAGINE_STIL, config.IMAGINE_PALETA, config.IMAGINE_EVITA = "foto", "", ""

# --- setarile noi de imagine: lumina, format, text pe poza, cerintele omului ---
config.IMAGINE_STIL = "editorial"
cer("ca în reviste" in imagine_prompt.cere(CIORNA_IMG),
    "felul „editorial\" are textul lui, nu cade pe fotografia implicita")
config.IMAGINE_STIL = "minimal"
cer("UN singur obiect" in imagine_prompt.cere(CIORNA_IMG), "si felul „minimal\"")
config.IMAGINE_LUMINA = "calda"
cer("de apus" in imagine_prompt.cere(CIORNA_IMG), "lumina aleasa ajunge in cerere")
config.IMAGINE_LUMINA = ""
cer("Lumina:" not in imagine_prompt.cere(CIORNA_IMG),
    "fara lumina aleasa, nu inventam una")

# textul pe poza de blog e implicit OPRIT — pe blog titlul e deja langa imagine
cer("Fără text, litere" in imagine_prompt.cere(CIORNA_IMG), "implicit, fara text pe poza de blog")
config.IMAGINE_TEXT_PE_POZA = "titlu"
c2 = imagine_prompt.cere(CIORNA_IMG)
cer("SINGUR rând de text" in c2 and "Fără text, litere" not in c2,
    "daca omul cere titlu pe poza, regula se schimba, nu se adauga peste")
config.IMAGINE_TEXT_PE_POZA = "nu"

# cerintele scrise de client stau LA FINAL si bat listele bifate
config.IMAGINE_CERINTE = "Masina pe elevator, in atelier, nu in showroom."
c3 = imagine_prompt.cere(CIORNA_IMG)
cer("Masina pe elevator" in c3, "cerintele clientului ajung in prompt")
cer(c3.index("Masina pe elevator") > c3.index("STILUL CLIENTULUI"),
    "si stau DUPA stil, ca sa fie ultimul lucru citit")
cer("bate tot ce scrie mai sus" in c3, "si i se spune ca bat restul")
config.IMAGINE_CERINTE = ""
config.IMAGINE_STIL = "foto"

# --- ca sa nu iasa a cincea oara acelasi carnet pe un birou de lemn ---
# Calea nu se mai alege de model (alegea mereu cea mai sigura), o alegem noi si
# se roteste. Fara asta, patru poze la rand aratau la fel pe grid.
cer(len(imagine_prompt.CAI) >= 6, "avem cel putin sase cai de imagine", len(imagine_prompt.CAI))
_cid = config.CLIENT_ID
_cai = set()
for _i in range(1, 40):
    config.CLIENT_ID = _i
    _cai.add(imagine_prompt._cale()[0])
config.CLIENT_ID = _cid
cer(len(_cai) == len(imagine_prompt.CAI), "calea se roteste intre clienti", sorted(_cai))
_c4 = imagine_prompt.cere(CIORNA_IMG)
cer("CALEA DE AZI E ALEASĂ" in _c4 and _c4.count("MOMENT dintr-o zi") + _c4.count("NATURĂ STATICĂ")
    + _c4.count("METAFORĂ FIZICĂ") + _c4.count("DETALIU foarte") + _c4.count("LOCUL în care")
    + _c4.count("SCENA VĂZUTĂ") + _c4.count("CEVA ÎN MIȘCARE") == 1,
    "si in prompt intra o SINGURA cale, nu lista de patru din care alege el")

# scenele pozelor anterioare intra in cerere, ca sa nu se repete
config.IMAGINI_RECENTE = ["A worn notebook with a handwritten list and a pen on a wooden desk"]
_c5 = imagine_prompt.cere(CIORNA_IMG)
cer("POZELE ANTERIOARE" in _c5 and "handwritten list" in _c5,
    "ultimele poze ale clientului intra in cerere, ca sa nu le repete")
config.IMAGINI_RECENTE = []
cer("POZELE ANTERIOARE" not in imagine_prompt.cere(CIORNA_IMG),
    "iar la primul articol nu inventam un istoric")

# carnetul pe birou e acum el insusi cliseu si se prinde inainte sa se deseneze
cer("carnet pe birou (deja folosit)" in imagine_prompt._pare_slab(
    "A worn notebook with a handwritten list, a pen and a cup of coffee on a scratched "
    "wooden desk, warm afternoon light coming in sideways, shot on 35mm, shallow depth."),
    "carnetul pe birou e prins ca cliseu, desi n-are niciun cuvant interzis")
cer(not imagine_prompt._pare_slab(
    "A loading ramp at the back of a small warehouse at dusk, one pallet still wrapped and "
    "three already opened, tyre marks on the wet concrete, shot on 35mm from waist level, "
    "low sideways light, muted greys and a single orange strap."),
    "dar o scena chiar diferita trece",
    imagine_prompt._pare_slab("A loading ramp at the back of a small warehouse at dusk, one "
    "pallet still wrapped and three already opened, tyre marks on the wet concrete, shot on "
    "35mm from waist level, low sideways light, muted greys and a single orange strap."))

# --- formatul si taierea ---
import image_gen
cer(image_gen.forma("4:5")[0] == "1024x1536", "4:5 cere de la OpenAI marimea portret")
cer(image_gen.forma("16:9")[1] == "16:9", "iar de la Gemini proportia ceruta, ca atare")
cer(image_gen.forma("aiurea")[1] == "3:2", "un format necunoscut cade pe 3:2, nu crapa")
_lat = Image.new("RGB", (1536, 1024), (10, 10, 10))
cer(abs(image_gen._taie_la(_lat, 4 / 5).size[0] / image_gen._taie_la(_lat, 4 / 5).size[1] - 0.8) < 0.02,
    "poza lata se taie pe centru la 4:5, nu ajunge cu benzi pe Instagram",
    image_gen._taie_la(_lat, 4 / 5).size)
cer(image_gen._taie_la(_lat, None).size == (1536, 1024), "fara proportie ceruta, poza ramane cum e")

# --- logoul: coltul si marimea vin din panou ---
config.LOGO_URL = ""
cer(image_gen._apply_logo(_lat).size == (1536, 1024), "fara logo pus, poza ramane neatinsa")
config.IMAGINE_LOGO_LOC = "fara"
cer(image_gen._apply_logo(_lat) is _lat, "„fara logo\" nici nu incearca sa-l ia")
config.IMAGINE_LOGO_LOC = "dreapta-jos"

# --- afisul de Instagram ---
import imagine_ig
config.IG_SABLON, config.IG_TEXT_CAT, config.IG_FUNDAL = "lista", "mediu", "inchis"
config.IG_ACCENT, config.IG_BANDA, config.IG_HANDLE = "#ff2f4d", True, "@atelier · exemplu.ro"
CIORNA_IG = {"seo_title": "Cat costa reclamele pe TikTok in 2026",
             "article_html": "<h2>Bugetul minim</h2><p>x</p><h2>Cine plateste mai mult</h2>"
                             "<p>y</p><h2>Ce se schimba in 2026</h2><p>z</p>"}
cig = imagine_ig.cere(CIORNA_IG)
cer("GRAPHIC DESIGN task, not a photograph" in cig,
    "afisul cere design, nu fotografie — altfel iese tot o poza")
cer("Cat costa reclamele pe TikTok in 2026" in cig, "titlul articolului se scrie PE imagine")
cer("Bugetul minim" in cig and "Ce se schimba in 2026" in cig,
    "punctele se scot din H2-urile articolului, nu le scrie omul")
cer("@atelier · exemplu.ro" in cig, "banda de brand poarta ce a scris clientul")
cer("#ff2f4d" in cig, "culoarea de accent ajunge in cerere")
cer("diacritics" in cig, "i se cere sa pastreze diacriticele — altfel iese „Cat costa\" fara ele")

config.IG_TEXT_CAT = "putin"
cer("Point 1" not in imagine_ig.cere(CIORNA_IG), "pe „putin text\" ramane doar titlul")
config.IG_TEXT_CAT = "mult"
cer(imagine_ig.cere(CIORNA_IG).count("Point ") >= 3,
    "pe „mult text\" se cer mai multe puncte")
config.IG_TEXT_CAT = "mediu"
config.IG_BANDA = False
cer("brand band" not in imagine_ig.cere(CIORNA_IG), "fara bifa, nu punem banda de brand")
config.IG_BANDA = True
config.IG_CERINTE = "Fara preturi pe poza."
cig2 = imagine_ig.cere(CIORNA_IG)
cer("Fara preturi pe poza." in cig2 and cig2.index("Fara preturi") > cig2.index("STYLE"),
    "cerintele pentru Instagram stau tot la final")
config.IG_CERINTE = ""

# un prompt cu clisee e respins si se mai cere o data
apeluri = []
def _fals(payload, raspunsuri=["A laptop on a desk showing glowing dashboards and charts.",
                               IMAGINE_RASPUNS[0]]):
    apeluri.append(payload)
    return {"candidates": [{"content": {"parts": [{"text": raspunsuri[min(len(apeluri) - 1, 1)]}]}}]}
iesit = imagine_prompt.scrie(CIORNA_IMG, _fals)
cer(len(apeluri) == 2, "un prompt cu dashboard-uri si grafice e respins si se cere altul", len(apeluri))
cer("ÎNCERCAREA ANTERIOARĂ A FOST RESPINSĂ" in str(apeluri[1]),
    "a doua cerere ii spune modelului exact ce a gresit")
cer("counting printed order slips" in iesit, "iese promptul bun, nu cel cu clisee", iesit[:60])

# daca modelul pica de tot, nu se opreste postarea
def _crapa(payload):
    raise RuntimeError("model cazut")
cer(imagine_prompt.scrie(CIORNA_IMG, _crapa) == "",
    "daca apelul pica, intoarce gol si ramane promptul din generarea mare")

# si chiar ajunge pe ciorna
cer(bool(CERERI_IMAGINE_PROMPT), "cererea separata chiar se face la fiecare generare")
PANOU["drafts"].clear(); CERERI_IMAGINE_PROMPT.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
d_img = list(PANOU["drafts"].values())[0]
cer("order slips" in (d_img.get("image_prompt") or ""),
    "promptul scris separat il inlocuieste pe cel din generarea mare si ajunge in panou",
    (d_img.get("image_prompt") or "")[:70])
cer("Titlu SEO de test" in str(CERERI_IMAGINE_PROMPT[0]),
    "cererea de imagine primeste articolul deja scris, nu doar tema")

# la catalog, cand punem in scena poza REALA a produsului, promptul nou NU se
# scrie: acolo se descrie ce e in jurul produsului, nu o scena cu totul noua
_cl_vechi = PANOU["clienti"][0]["flux"]
PANOU["clienti"][0]["flux"] = "catalog"
PANOU["clienti"][0]["produs"] = dict(PRODUS, mod_imagine="wow")
PANOU["drafts"].clear(); CERERI_IMAGINE_PROMPT.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
cer(not CERERI_IMAGINE_PROMPT,
    "la compunerea din poza produsului NU se rescrie promptul — ar strica produsul",
    len(CERERI_IMAGINE_PROMPT))
PANOU["clienti"][0]["produs"] = dict(PRODUS, mod_imagine="generata")
PANOU["drafts"].clear(); CERERI_IMAGINE_PROMPT.clear()
try:
    generate_draft.main()
except SystemExit:
    pass
cer(bool(CERERI_IMAGINE_PROMPT),
    "dar cand poza se deseneaza de la zero, promptul se scrie separat",
    len(CERERI_IMAGINE_PROMPT))
PANOU["clienti"][0]["flux"] = _cl_vechi
PANOU["clienti"][0].pop("produs", None)

# cate linkuri interne cerem depinde de cate pagini stim ca exista
from content_gen import _pagini_site
import re as _re
def _cate(n):
    config.SITE = [{"url": f"https://x.ro/p{i}", "titlu": f"P{i}"} for i in range(n)]
    m = _re.search(r"Vreau (\S+) linkuri", _pagini_site())
    return m.group(1) if m else None
cer(_cate(6) == "3-5" and _cate(2) == "1-2" and _cate(1) == "un",
    "nu cerem mai multe linkuri decat pagini stim — altfel modelul le inventeaza",
    [_cate(6), _cate(2), _cate(1)])
config.SITE = []
cer(_pagini_site() == "", "fara pagini citite nu cerem deloc linkuri interne")

cer(len(SCHELETE) >= 6, "avem cel putin sase forme de articol", len(SCHELETE))
config.SCHELETE_RECENTE = [SCHELETE[0][0], SCHELETE[1][0], SCHELETE[2][0]]
forme = set()
for cid in range(1, 40):
    config.CLIENT_ID = cid
    forme.add(_system_prompt().split("FORMA ARTICOLULUI DE AZI: ")[1].split(" ")[0])
cer(not (forme & set(config.SCHELETE_RECENTE)),
    "forma articolului o ocoleste pe cea a ultimelor trei", sorted(forme))
cer(len(forme) > 1, "forma chiar se roteste intre clienti", sorted(forme))
config.SCHELETE_RECENTE = []

pr = _system_prompt()
cer("primele 40-60 de cuvinte" in pr.lower(), "promptul cere raspunsul sus de tot")  # .lower(): in prompt scrie „Primele", cu majuscula
cer("se ține singură" in pr or "se ține singur" in pr or "SE ȚINE SINGURĂ" in pr,
    "promptul cere sectiuni care se inteleg scoase din pagina")
cer("In lumea de azi" in pr, "promptul interzice deschiderile-cliseu pe nume")
cer("nu le-ai văzut" in pr, "promptul interzice cifrele si sursele inventate")

# reteaua care cade o secunda nu mai inseamna zero ciorne in ziua aia
import retea
retea.PAUZA_PORNIRE = 0
_vechi_post = requests.post
_cazuri = {"n": 0}
def _post_care_cade(url, **kw):
    _cazuri["n"] += 1
    if _cazuri["n"] == 1:
        raise requests.ConnectionError("Remote end closed connection without response")
    return _vechi_post(url, **kw)
requests.post = _post_care_cade
try:
    r = retea.post("https://generativelanguage.googleapis.com/x", json={})
    a_reusit = r is not None
except Exception:
    a_reusit = False
requests.post = _vechi_post
cer(a_reusit and _cazuri["n"] == 2,
    "o conexiune cazuta se reincearca, nu opreste generarea", _cazuri["n"])

_cazuri["n"] = 0
def _post_mereu_cade(url, **kw):
    _cazuri["n"] += 1
    raise requests.ConnectionError("cade mereu")
requests.post = _post_mereu_cade
try:
    retea.post("https://x/y", json={})
    a_ridicat = False
except requests.ConnectionError:
    a_ridicat = True
requests.post = _vechi_post
cer(a_ridicat and _cazuri["n"] == retea.INCERCARI,
    "dar nu incercam la nesfarsit dupa un furnizor chiar cazut", _cazuri["n"])

print("\n" + (f"{len(PICA)} TESTE PICA" if PICA else "toate trec"))
sys.exit(1 if PICA else 0)
