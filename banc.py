"""
Bancul de probă pentru modele — MOON Post.

Rulează ACELAȘI brief prin mai multe modele de text și mai multe modele de
imagine, măsoară tokenii și costul REAL, și scoate o pagină locală unde le vezi
cap la cap. Nu creează ciorne în panou și nu publică nimic: singurul lucru pe
care îl cere de la panou e configurația clientului (chei, nișă, pagini de site,
produs), exact ca motorul.

De ce separat de motor: alegerea modelului o faci tu, o dată, pentru toți
clienții. Ca s-o faci în cunoștință de cauză trebuie să vezi ieșirile una lângă
alta, nu să apeși „Generează acum" de zece ori și să ții minte.

    python banc.py --client 1 --text gemini-3.6-flash,gemini-3-pro \
                   --imagine gpt-image-2,gemini-3.1-flash-image --calitate medie,mare

    python banc.py --uscat        # probă seacă: nu cheamă nimic, nu costă nimic

Cere în mediu PANEL_URL și CRON_KEY (aceleași ca la motor).
"""

from __future__ import annotations
import argparse
import base64
import html as H
import io
import json
import os
import pathlib
import sys
import time
import traceback

from config import config
import panel
import content_gen
import content_gen_catalog
import image_gen

# --------------------------------------------------------------- prețurile reale
#
# NU sunt cele din panou. Tabelul din `src/ai.js` a rămas în urmă (gemini-3.6-flash
# e trecut acolo cu 0,30/2,50, dar Google cere 0,75/3,75), iar bancul n-are voie
# să mintă exact la lucrul pentru care există. Verificate în septembrie 2026;
# `sursa` spune cât de sigur e prețul.
PRET_TEXT = {
    # model: (USD / 1M intrare, USD / 1M ieșire, sursa)
    "gemini-3.6-flash":        (0.75, 3.75, "ai.google.dev, promoție până la 31.12.2026"),
    "gemini-3.5-flash":        (0.75, 3.75, "presupus egal cu 3.6"),
    "gemini-3.5-flash-lite":   (0.30, 2.50, "ai.google.dev"),
    "gemini-3.1-pro":          (2.00, 12.00, "ai.google.dev, prompt sub 200k"),
    "gemini-3-pro":            (2.00, 12.00, "ai.google.dev, prompt sub 200k"),
    "gpt-5.6-luna":            (0.20, 1.20, "tabelul din panou, NEVERIFICAT"),
    "gpt-5.4-nano":            (0.20, 1.25, "tabelul din panou, NEVERIFICAT"),
    "gpt-5.4-mini":            (0.75, 4.50, "tabelul din panou, NEVERIFICAT"),
    "gpt-5.6-terra":           (2.00, 12.00, "tabelul din panou, NEVERIFICAT"),
    "gpt-5.4":                 (2.50, 15.00, "tabelul din panou, NEVERIFICAT"),
}

# per imagine, pe calitatea din panou (mica / medie / mare).
# La Gemini calitatea se traduce în 512px / 1K / 2K (vezi image_gen._MARIME_G),
# la OpenAI în low / medium / high.
PRET_IMAGINE = {
    "gpt-image-2":                  {"mica": 0.006, "medie": 0.053, "mare": 0.211},
    "gpt-image-1.5":                {"mica": 0.009, "medie": 0.050, "mare": 0.200},
    "gpt-image-1-mini":             {"mica": 0.005, "medie": 0.011, "mare": 0.052},
    "gpt-image-2.5-flare":          {"mica": 0.006, "medie": 0.053, "mare": 0.211},
    "gpt-image-2.5-sunburst":       {"mica": 0.006, "medie": 0.053, "mare": 0.211},
    "gemini-3-pro-image":           {"mica": 0.067, "medie": 0.134, "mare": 0.134},
    "gemini-3.1-flash-image":       {"mica": 0.045, "medie": 0.067, "mare": 0.101},
    "gemini-3.1-flash-lite-image":  {"mica": 0.034, "medie": 0.034, "mare": 0.034},
    "gemini-2.5-flash-image":       {"mica": 0.039, "medie": 0.039, "mare": 0.039},
}

# Grounding cu Google Search: 5.000 cereri gratis pe LUNĂ, pe tot proiectul, apoi
# 14 USD la mie. Nu apare nicăieri în panou — aici îl vezi separat, ca să știi ce
# te așteaptă când crește numărul de clienți.
GROUNDING_USD = 0.014

CURS_IMPLICIT = 4.6


def pret_text(model: str):
    for k in sorted(PRET_TEXT, key=len, reverse=True):
        if model.startswith(k):
            return PRET_TEXT[k]
    return (0.0, 0.0, "PREȚ NECUNOSCUT")


def pret_imagine(model: str, calitate: str) -> float:
    for k in sorted(PRET_IMAGINE, key=len, reverse=True):
        if model.startswith(k):
            return PRET_IMAGINE[k].get(calitate, 0.0)
    return 0.0


# --------------------------------------------------------------- proba propriu-zisă

def _pune_model_text(model: str) -> None:
    """`_gemini_url()` se uită la GEMINI_MODEL, rutarea la MODEL_TEXT. Le punem
    pe amândouă, altfel proba rulează cu modelul clientului, nu cu cel cerut."""
    config.MODEL_TEXT = model
    config.GEMINI_MODEL = model


def _pune_model_imagine(model: str, calitate: str, marime: str) -> None:
    config.MODEL_IMAGINE = model
    config.OPENAI_IMAGE_MODEL = model
    config.OPENAI_IMAGE_QUALITY = calitate
    config.OPENAI_IMAGE_SIZE = marime


def proba_text(model: str, flux: str, produs: dict | None) -> dict:
    """O generare de text. Întoarce ce a ieșit + cât a costat, fără să arunce:
    un model care pică e un rezultat, nu o oprire a probei."""
    _pune_model_text(model)
    r = {"model": model, "flux": flux, "furnizor": config.FURNIZOR_TEXT}
    t0 = time.time()
    try:
        if flux == "catalog":
            date = content_gen_catalog.genereaza_pentru_produs(produs or {})
        else:
            date = content_gen.generate_authority_draft()
        r["ok"] = True
        r.update({k: date.get(k, "") for k in (
            "topic_title", "angle", "seo_title", "meta_description",
            "article_html", "facebook_text", "instagram_text", "image_prompt")})
    except Exception as e:  # noqa: BLE001 — orice eșec e un rezultat de comparat
        r["ok"] = False
        r["eroare"] = f"{type(e).__name__}: {str(e)[:400]}"
    r["secunde"] = round(time.time() - t0, 1)
    r["tokens_in"] = content_gen.CONSUM["tokens_in"]
    r["tokens_out"] = content_gen.CONSUM["tokens_out"]

    p_in, p_out, sursa = pret_text(model)
    r["sursa_pret"] = sursa
    r["usd_tokeni"] = round(r["tokens_in"] / 1e6 * p_in + r["tokens_out"] / 1e6 * p_out, 6)
    # fluxul de autoritate caută pe net înainte să scrie; catalogul nu
    r["usd_cautare"] = GROUNDING_USD if flux == "autoritate" else 0.0
    r["usd"] = round(r["usd_tokeni"] + r["usd_cautare"], 6)
    r["cuvinte"] = len((r.get("article_html") or "").split())
    return r


def proba_imagine(model: str, calitate: str, marime: str, prompt: str,
                  produs: dict | None, mod: str) -> dict:
    """O imagine. `mod` = 'generata' (de la zero) sau 'wow' (poza produsului
    pusă în scenă) — a doua e ce vând pachetele de magazin, deci se probează."""
    _pune_model_imagine(model, calitate, marime)
    r = {"model": model, "calitate": calitate, "marime": marime, "mod": mod,
         "furnizor": config.FURNIZOR_IMAGINE}
    t0 = time.time()
    try:
        if mod == "wow" and produs and produs.get("imagine"):
            bruta = image_gen.image_from_url(produs["imagine"], cu_logo=False)
            r["octeti"] = image_gen.compune_din_produs(bruta, prompt)
        else:
            r["octeti"] = image_gen.generate_image(prompt)
        r["ok"] = True
    except Exception as e:  # noqa: BLE001
        r["ok"] = False
        r["eroare"] = f"{type(e).__name__}: {str(e)[:400]}"
        r["octeti"] = b""
    r["secunde"] = round(time.time() - t0, 1)
    r["usd"] = pret_imagine(model, calitate) if r["ok"] else 0.0
    return r


# --------------------------------------------------------------- proba seacă

def _uscat_pornit() -> None:
    """Înlocuiește apelurile plătite cu răspunsuri false. Serviciul: verifici că
    bancul și pagina merg cap la cap fără să dai un dolar."""
    from PIL import Image, ImageDraw

    def text_fals(payload, max_retries=4):
        model = config.MODEL_TEXT
        content_gen.CONSUM["tokens_in"] += 7000 + len(model) * 100
        content_gen.CONSUM["tokens_out"] += 3000 + len(model) * 50
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({
            "topic_title": f"Subiect de probă seacă ({model})",
            "angle": "unghi de probă",
            "seo_title": f"Titlu scris de {model}",
            "meta_description": "descriere de probă",
            "article_html": f"<h1>Titlu scris de {model}</h1><p>" + ("cuvânt " * 120) + "</p>",
            "facebook_text": f"postare Facebook de la {model}",
            "instagram_text": f"postare Instagram de la {model} #test",
            "image_prompt": "A cracked hourglass on a dark desk, coral rim light, editorial photography.",
        })}]}}]}

    def imagine_falsa(prompt, size=None):
        img = Image.new("RGB", (768, 512), (18, 18, 22))
        d = ImageDraw.Draw(img)
        d.rectangle([24, 24, 744, 488], outline=(255, 47, 77), width=3)
        d.text((44, 44), f"{config.MODEL_IMAGINE}\n{config.OPENAI_IMAGE_QUALITY}\nprobă seacă",
               fill=(240, 240, 240))
        b = io.BytesIO(); img.save(b, format="JPEG", quality=88)
        return b.getvalue()

    content_gen.cheama_modelul = text_fals
    content_gen_catalog.cheama_modelul = text_fals
    image_gen.generate_image = imagine_falsa
    image_gen.compune_din_produs = lambda poza, prompt, size=None: imagine_falsa(prompt)
    image_gen.image_from_url = lambda url, cu_logo=True: b"x"

    def clienti_falsi(**kw):
        return [{"id": 1, "slug": "proba", "nume": "Client de probă",
                 "domeniu": "exemplu.ro", "flux": "autoritate", "canale": ["wp"],
                 "site": [{"url": "https://exemplu.ro/servicii", "titlu": "Servicii",
                           "rezumat": "ce facem"}],
                 "produs": {"ext_id": "1", "nume": "Produs de probă",
                            "url": "https://exemplu.ro/p/1", "pret": "99",
                            "moneda": "RON", "descriere": "un produs",
                            "imagine": "https://exemplu.ro/poza-produs.jpg",
                            "mod_imagine": "wow", "conexe": []},
                 "config": {"nisa": "probă", "gemini_key": "fals", "openai_key": "fals"}}]

    panel.clienti = clienti_falsi
    panel.subiecte_recente = lambda client_id, zile=45: []


# --------------------------------------------------------------- pagina

STIL = """
*{box-sizing:border-box}body{margin:0;background:#0b0b0d;color:#e8e8ea;
font:15px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;padding:32px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:38px 0 14px;display:flex;
align-items:center;gap:9px}h2::before{content:'';width:9px;height:9px;border-radius:50%;
background:#ff2f4d;flex:none}.sub{color:#8b8b93;margin:0 0 26px}
table{width:100%;border-collapse:collapse;margin:0 0 10px;font-size:14px}
th,td{padding:9px 11px;text-align:left;border-bottom:1px solid #24242a}
th{color:#8b8b93;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
td.n{text-align:right;font-variant-numeric:tabular-nums}
tr.rau td{color:#ff6b81}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:18px}
.card{background:#141419;border:1px solid #24242a;border-radius:14px;padding:18px;overflow:hidden}
.card h3{margin:0 0 3px;font-size:15px}
.card .meta{color:#8b8b93;font-size:12.5px;margin:0 0 12px}
.card img{width:100%;border-radius:9px;display:block;background:#000}
.art{max-height:430px;overflow:auto;font-size:14px;border-top:1px solid #24242a;
padding-top:12px;margin-top:12px}
.art h1{font-size:17px}.art h2{font-size:15px;margin:16px 0 7px}.art h2::before{display:none}
.soc{background:#0f0f13;border-radius:9px;padding:10px 12px;margin-top:10px;font-size:13.5px;
white-space:pre-wrap;color:#c9c9d1}
.eroare{color:#ff6b81;font-size:13.5px;white-space:pre-wrap}
.pastila{display:inline-block;background:#1d1d24;border-radius:999px;padding:2px 9px;
font-size:11.5px;color:#a9a9b3;margin-right:6px}
.tot{font-size:14px;color:#8b8b93;margin-top:8px}
b.rosu{color:#ff2f4d}
"""


def _lei(usd: float, curs: float) -> str:
    return f"{usd * curs:.2f} lei"


def scrie_pagina(cale: pathlib.Path, texte: list, imagini: list, info: dict) -> None:
    curs = info["curs"]
    p = [f"<!doctype html><meta charset='utf-8'><title>Banc de modele — MOON Post</title>",
         f"<style>{STIL}</style>",
         f"<h1>Banc de modele — MOON Post</h1>",
         f"<p class='sub'>{H.escape(info['cand'])} · client <b>{H.escape(str(info['client']))}</b>"
         f" · curs {curs} lei/USD{' · <b class=rosu>PROBĂ SEACĂ (nimic real)</b>' if info['uscat'] else ''}</p>"]

    tot = sum(t["usd"] for t in texte) + sum(i["usd"] for i in imagini)
    p.append(f"<p class='tot'>Proba asta a costat <b class='rosu'>{tot:.4f} USD ({_lei(tot, curs)})</b>.</p>")

    # ---- text
    p.append("<h2>Text</h2><table><tr><th>model</th><th>flux</th><th>furnizor</th>"
             "<th class=n>in</th><th class=n>out</th><th class=n>cuvinte</th><th class=n>sec</th>"
             "<th class=n>tokeni USD</th><th class=n>căutare</th><th class=n>total USD</th>"
             "<th class=n>lei/postare</th><th>preț luat din</th></tr>")
    for t in sorted(texte, key=lambda x: x["usd"]):
        clasa = "" if t["ok"] else " class=rau"
        p.append(f"<tr{clasa}><td>{H.escape(t['model'])}</td><td>{t['flux']}</td>"
                 f"<td>{t['furnizor']}</td><td class=n>{t['tokens_in']}</td>"
                 f"<td class=n>{t['tokens_out']}</td><td class=n>{t.get('cuvinte',0)}</td>"
                 f"<td class=n>{t['secunde']}</td><td class=n>{t['usd_tokeni']:.4f}</td>"
                 f"<td class=n>{t['usd_cautare']:.3f}</td><td class=n>{t['usd']:.4f}</td>"
                 f"<td class=n>{t['usd']*curs:.3f}</td><td>{H.escape(t['sursa_pret'])}</td></tr>")
    p.append("</table>")

    p.append("<div class='grid'>")
    for t in texte:
        p.append("<div class='card'>")
        p.append(f"<h3>{H.escape(t['model'])}</h3>")
        p.append(f"<p class='meta'><span class='pastila'>{t['flux']}</span>"
                 f"<span class='pastila'>{t['usd']:.4f} USD</span>"
                 f"<span class='pastila'>{t['secunde']}s</span></p>")
        if not t["ok"]:
            p.append(f"<p class='eroare'>{H.escape(t.get('eroare',''))}</p></div>")
            continue
        p.append(f"<p class='meta'><b>{H.escape(t.get('seo_title',''))}</b><br>"
                 f"{H.escape(t.get('meta_description',''))}</p>")
        p.append(f"<div class='art'>{t.get('article_html','')}</div>")
        p.append(f"<div class='soc'>FB · {H.escape(t.get('facebook_text',''))}</div>")
        p.append(f"<div class='soc'>IG · {H.escape(t.get('instagram_text',''))}</div>")
        p.append(f"<div class='soc'>prompt imagine · {H.escape(t.get('image_prompt',''))}</div>")
        p.append("</div>")
    p.append("</div>")

    # ---- imagini
    p.append("<h2>Imagine</h2><table><tr><th>model</th><th>calitate</th><th>mod</th>"
             "<th>furnizor</th><th class=n>sec</th><th class=n>USD</th><th class=n>lei</th>"
             "<th class=n>lei la 31 postări</th><th class=n>lei la 186</th></tr>")
    for i in sorted(imagini, key=lambda x: x["usd"]):
        clasa = "" if i["ok"] else " class=rau"
        p.append(f"<tr{clasa}><td>{H.escape(i['model'])}</td><td>{i['calitate']}</td>"
                 f"<td>{i['mod']}</td><td>{i['furnizor']}</td><td class=n>{i['secunde']}</td>"
                 f"<td class=n>{i['usd']:.4f}</td><td class=n>{i['usd']*curs:.3f}</td>"
                 f"<td class=n>{i['usd']*curs*31:.0f}</td><td class=n>{i['usd']*curs*186:.0f}</td></tr>")
    p.append("</table>")

    p.append("<div class='grid'>")
    for i in imagini:
        p.append("<div class='card'>")
        p.append(f"<h3>{H.escape(i['model'])}</h3>")
        p.append(f"<p class='meta'><span class='pastila'>{i['calitate']}</span>"
                 f"<span class='pastila'>{i['mod']}</span>"
                 f"<span class='pastila'>{i['usd']:.4f} USD</span>"
                 f"<span class='pastila'>{i['secunde']}s</span></p>")
        if i["ok"]:
            b64 = base64.b64encode(i["octeti"]).decode()
            p.append(f"<img src='data:image/jpeg;base64,{b64}' alt=''>")
        else:
            p.append(f"<p class='eroare'>{H.escape(i.get('eroare',''))}</p>")
        p.append("</div>")
    p.append("</div>")

    p.append("<h2>De citit cu ochii pe cifre</h2><p class='sub'>"
             "Costul de text de aici e cel REAL, nu cel din tabelul panoului (`src/ai.js`), "
             "care a rămas în urmă. Căutarea pe net (grounding) e 14 USD la mie după primele "
             "5.000 de cereri pe lună, pe tot proiectul — nu pe client — și nu e înregistrată "
             "nicăieri în panou.</p>")

    cale.write_text("\n".join(p), encoding="utf-8")


# --------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="Banc de probă pentru modelele MOON Post")
    ap.add_argument("--client", type=int, default=0, help="id-ul clientului din panou")
    ap.add_argument("--text", default="gemini-3.6-flash",
                    help="modele de text, separate prin virgulă")
    ap.add_argument("--imagine", default="gpt-image-2",
                    help="modele de imagine, separate prin virgulă")
    ap.add_argument("--calitate", default="mare", help="mica,medie,mare")
    ap.add_argument("--marime", default="1536x1024")
    ap.add_argument("--flux", default="autoritate", choices=["autoritate", "catalog", "ambele"])
    ap.add_argument("--curs", type=float, default=CURS_IMPLICIT)
    ap.add_argument("--iesire", default=os.path.expanduser("~/Moon Bot/banc-modele"),
                    help="unde se scriu rezultatele; implicit LÂNGĂ repo, nu în el —\nmotorul e repo public, iar aici ies articole și poze de client")
    ap.add_argument("--uscat", action="store_true", help="probă seacă: nu cheamă nimic, nu costă nimic")
    a = ap.parse_args()

    if a.uscat:
        _uscat_pornit()

    lista = panel.clienti(client_id=a.client or None, forteaza=True)
    if not lista:
        print("Niciun client. Dă --client cu un id din panou.")
        return 1
    client = lista[0]
    config.aplica(client)
    produs = client.get("produs")

    fluxuri = ["autoritate", "catalog"] if a.flux == "ambele" else [a.flux]
    if "catalog" in fluxuri and not produs:
        print("  clientul n-are produs la rând — sar peste fluxul de catalog")
        fluxuri = [f for f in fluxuri if f != "catalog"]

    texte, imagini = [], []
    for flux in fluxuri:
        for model in [m.strip() for m in a.text.split(",") if m.strip()]:
            print(f"  text · {flux} · {model} …", flush=True)
            r = proba_text(model, flux, produs)
            print(f"    {'ok' if r['ok'] else 'PICAT'} · {r['tokens_in']}/{r['tokens_out']} tokeni"
                  f" · {r['usd']:.4f} USD")
            texte.append(r)

    # toate modelele de imagine primesc ACELAȘI prompt, altfel compari și prompturi,
    # nu doar modele. Îl luăm din prima generare reușită.
    prompt = next((t.get("image_prompt") for t in texte if t.get("ok") and t.get("image_prompt")), "")
    if not prompt:
        prompt = ("A cracked hourglass on a dark desk, coral rim light, shallow depth of field, "
                  "editorial photography.")
        print("  niciun prompt de imagine din text — folosesc unul de rezervă")

    moduri = ["generata"]
    if produs and produs.get("imagine") and "catalog" in fluxuri:
        moduri.append("wow")

    for mod in moduri:
        for model in [m.strip() for m in a.imagine.split(",") if m.strip()]:
            for cal in [c.strip() for c in a.calitate.split(",") if c.strip()]:
                print(f"  imagine · {mod} · {model} · {cal} …", flush=True)
                r = proba_imagine(model, cal, a.marime, prompt, produs, mod)
                print(f"    {'ok' if r['ok'] else 'PICAT'} · {r['usd']:.4f} USD")
                imagini.append(r)

    dosar = pathlib.Path(a.iesire) / time.strftime("%Y-%m-%d-%H%M")
    dosar.mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(imagini):
        if r["ok"]:
            (dosar / f"{i+1:02d}-{r['model']}-{r['calitate']}-{r['mod']}.jpg").write_bytes(r["octeti"])
    (dosar / "date.json").write_text(json.dumps(
        {"texte": texte, "imagini": [{k: v for k, v in r.items() if k != "octeti"} for r in imagini]},
        ensure_ascii=False, indent=2), encoding="utf-8")

    pagina = dosar / "index.html"
    scrie_pagina(pagina, texte, imagini, {
        "cand": time.strftime("%d.%m.%Y %H:%M"),
        "client": f"{client.get('nume')} (id {client.get('id')})",
        "curs": a.curs, "uscat": a.uscat})

    tot = sum(t["usd"] for t in texte) + sum(i["usd"] for i in imagini)
    print(f"\nGata. Proba a costat {tot:.4f} USD ({tot*a.curs:.2f} lei).")
    print(f"Pagina: {pagina.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
