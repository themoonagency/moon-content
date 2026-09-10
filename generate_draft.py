"""
Rulare ORARĂ (cron): panoul spune ce clienți au o postare scadentă în ora asta,
după programul fiecăruia (zilnic / la N zile / mai multe pe zi). Pentru fiecare
generează articolul + postările sociale + imaginea, urcă imaginea și lasă ciorna
în panou, la aprobare.

Nu publică nimic. Nu scrie nimic în repo — toată starea stă în panou.

Pornire manuală din panou: CLIENT_ID + FORTEAZA (workflow_dispatch).
"""

from __future__ import annotations
import os
import sys
import traceback

import panel
from config import config
from content_gen import CONSUM, generate_authority_draft
from content_gen_catalog import genereaza_pentru_produs
from image_gen import compune_din_produs, generate_image, image_from_url
import telegram_bot as tg


def genereaza_imagine(prompt: str) -> tuple[bytes | None, str]:
    """O reîncercare, apoi renunțăm — dar spunem clar că lipsește.
    Înainte, un eșec de imagine trecea tăcut și abia la publicare se vedea
    că Facebook și Instagram au fost sărite."""
    ultima = ""
    for incercare in (1, 2):
        try:
            return generate_image(prompt), ""
        except Exception as e:  # noqa: BLE001 — orice eșec de imagine e recuperabil
            ultima = str(e)[:300]
            print(f"  imaginea a eșuat (încercarea {incercare}): {ultima}")
    return None, ultima


def pentru_client(client: dict) -> None:
    config.aplica(client)
    nume = config.CLIENT_NAME
    print(f"\n=== {nume} (id {config.CLIENT_ID}) ===")

    lipsa = config.lipsuri_generare()
    if lipsa:
        print(f"  sărit: lipsește {', '.join(lipsa)}")
        return
    print(f"  slot {config.SLOT}, canale: {', '.join(config.CANALE)}")

    # panoul alege produsul pentru clienții pe flux „catalog"; motorul doar scrie
    produs = client.get("produs")
    if config.FLUX == "catalog" and not produs:
        print("  sărit: catalog gol sau toate produsele au fost postate recent")
        return

    try:
        continut = genereaza_pentru_produs(produs) if produs else generate_authority_draft()
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        tg.anunta(f"⚠️ *MOON Post* — generarea de text a eșuat pentru {nume}:\n`{str(e)[:300]}`")
        print(f"  EȘEC la generare: {e}")
        return

    imagine, eroare_img = None, ""
    poza_costa = True          # dacă a trecut pe la OpenAI, se pune la socoteală

    if produs and produs.get("imagine"):
        mod = produs.get("mod_imagine") or "wow"
        try:
            bruta = image_from_url(produs["imagine"], cu_logo=(mod == "catalog"))
            if mod == "catalog":
                imagine, poza_costa = bruta, False
                print("  imaginea e poza din catalog, neatinsă")
            elif mod == "wow":
                # poza reală devine punctul de plecare: produsul rămâne el, dar intră într-o scenă
                try:
                    imagine = compune_din_produs(bruta, continut["image_prompt"])
                    print("  imaginea: poza produsului, pusă în scenă")
                except Exception as e:  # noqa: BLE001
                    print(f"  compunerea a eșuat ({str(e)[:120]}), rămân la poza din catalog")
                    imagine, poza_costa = bruta, False
        except Exception as e:  # noqa: BLE001
            print(f"  poza produsului nu s-a putut lua ({str(e)[:120]})")

    if not imagine:
        imagine, eroare_img = genereaza_imagine(continut["image_prompt"])

    draft_id = panel.creeaza_ciorna(config.CLIENT_ID, {
        "topic_title": continut["topic_title"],
        "angle": continut["angle"],
        "seo_title": continut["seo_title"],
        "meta_description": continut["meta_description"],
        "article_html": continut["article_html"],
        "facebook_text": continut["facebook_text"],
        "instagram_text": continut["instagram_text"],
        "are_imagine": bool(imagine),
        "produs_ext_id": (produs or {}).get("ext_id"),
        "idee_id": (config.IDEE or {}).get("id"),
        "canale": config.CANALE,
        "slot": config.SLOT,
        # consumul, ca panoul să poată arăta costul și profitul pe client
        "model_text": config.GEMINI_MODEL,
        "model_imagine": config.OPENAI_IMAGE_MODEL,
        "tokens_in": CONSUM["tokens_in"],
        "tokens_out": CONSUM["tokens_out"],
        # poza luată ca atare din catalog nu costă nimic; cea pusă în scenă, da
        "imagini": 1 if (imagine and poza_costa) else 0,
    })

    if imagine:
        try:
            panel.urca_imagine(draft_id, imagine)
        except Exception as e:  # noqa: BLE001
            print(f"  imaginea nu a putut fi urcată în panou: {e}")
            panel.actualizeaza(draft_id, are_imagine=False,
                               eroare=f"Imaginea nu a putut fi urcată: {str(e)[:200]}")
            imagine = None
            eroare_img = str(e)[:300]

    avertisment = ""
    if not imagine and ("ig" in config.CANALE or "fb" in config.CANALE):
        avertisment = ("Ciorna nu are imagine — Instagram se sare, iar pe Facebook se postează "
                       "link către articol. Motiv: " + (eroare_img or "necunoscut"))
        panel.actualizeaza(draft_id, eroare=avertisment)

    tg.anunta_ciorna(draft_id, continut["seo_title"], continut["facebook_text"],
                     continut["instagram_text"], imagine, avertisment)
    print(f"  ciorna {draft_id}: {continut['topic_title']}" + ("  [FĂRĂ IMAGINE]" if not imagine else ""))


def main() -> None:
    unul = os.environ.get("CLIENT_ID", "").strip()
    forteaza = os.environ.get("FORTEAZA", "").strip().lower() in ("1", "da", "true", "yes")
    # DOAR_COADA=1: rulat din fluxul de publicare (la 5 minute), ia numai clientii
    # apasati din butonul „Genereaza acum". Asa pornirea manuala nu mai depinde
    # de cronul de generare, care poate intarzia mult.
    doar_coada = os.environ.get("DOAR_COADA", "").strip().lower() in ("1", "da", "true", "yes")
    clienti = panel.clienti(scadenti=not doar_coada, coada=doar_coada,
                            client_id=int(unul) if unul.isdigit() else None,
                            forteaza=forteaza)
    if not clienti:
        print("Nimeni la rand." if doar_coada else "Niciun client cu postare scadentă în ora asta.")
        return
    print(f"{len(clienti)} client(i) de rulat acum.")
    esecuri = 0
    for client in clienti:
        try:
            pentru_client(client)
        except Exception as e:  # noqa: BLE001 — un client căzut nu oprește restul
            esecuri += 1
            traceback.print_exc()
            print(f"  EȘEC pe {client.get('nume')}: {e}")
    sys.exit(1 if esecuri and esecuri == len(clienti) else 0)


if __name__ == "__main__":
    main()
