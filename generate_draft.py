"""
Rulare ORARĂ (cron): panoul spune ce clienți au o postare scadentă în ora asta,
după programul fiecăruia (zilnic / la N zile / mai multe pe zi). Pentru fiecare
generează articolul + postările sociale + imaginea, urcă imaginea și lasă ciorna
în panou, la aprobare.

Nu publică nimic. Nu scrie nimic în repo — toată starea stă în panou.

Pornire manuală din panou: CLIENT_ID + FORTEAZA (workflow_dispatch).
"""

from __future__ import annotations
import html as html_lib
import os
import re
import sys
import traceback

import panel
from config import config
import imagine_prompt
import imagine_ig as imagine_ig_mod
import seo
import cta
from content_gen import CONSUM, curata_linkurile, generate_authority_draft
from content_gen_catalog import genereaza_pentru_produs
from image_gen import afis_instagram, compune_coperta, compune_din_produs, generate_image, image_from_url
import telegram_bot as tg


# Scena de rezerva cand poza reala a produsului nu vine: se vede atmosfera
# articolului, nu un produs inventat.
FARA_PRODUS = (" Do not show the product itself or any packaging, bottle, box, label, brand "
               "name, logo or text of it — the scene must work without the product.")


def genereaza_imagine(prompt: str, cu_logo: bool = True) -> tuple[bytes | None, str]:
    """O reîncercare, apoi renunțăm — dar spunem clar că lipsește.
    Înainte, un eșec de imagine trecea tăcut și abia la publicare se vedea
    că Facebook și Instagram au fost sărite."""
    ultima = ""
    for incercare in (1, 2):
        try:
            return generate_image(prompt, cu_logo=cu_logo), ""
        except Exception as e:  # noqa: BLE001 — orice eșec de imagine e recuperabil
            ultima = str(e)[:300]
            print(f"  imaginea a eșuat (încercarea {incercare}): {ultima}")
    return None, ultima


def _imagini(continut: dict, produs: dict | None, probleme_seo: list,
             prompt_deja_scris: bool = False) -> dict:
    """Poza principala si afisul de Instagram pentru un continut deja scris. O folosesc si
    generarea completa, si modul DRAFT_ID (mp12: textul l-a scris motorul din worker).
    `config.FEL_AZI` trebuie ales inainte. Scrie in `continut["image_prompt"]` si adauga in
    `probleme_seo` ce afla pe drum (poza produsului lipsa, prompt generic)."""
    # Poza REALA a produsului se aduce inainte de orice: de ea depinde daca punem
    # produsul in scena, il lasam ca atare sau — daca nu vine — facem o scena FARA el.
    # Produsul nu se deseneaza niciodata dupa nume: pe 11 sept poza lui La Favorite
    # n-a venit de pe evero.ro, motorul a cerut „Fotografie de produs: Jean Paul
    # Gaultier La Favorite", iar modelul si-a imaginat alt flacon.
    # Felul pozei principale (foto, ilustratie, coperta…) se alege O DATA pe ciorna: pe
    # „rulaj" e aleator, iar promptul si compunerea trebuie sa vada acelasi fel.
    if config.FEL_AZI != "foto" or (config.IMAGINE_STIL or "").strip().lower() == "rulaj":
        print(f"  felul pozei: {config.FEL_AZI}" + (" (rulaj)" if config.IMAGINE_STIL == "rulaj" else ""))

    mod = (produs.get("mod_imagine") or "wow") if produs else ""
    poza_reala, motiv_poza = None, ""
    if produs and mod in ("wow", "catalog"):
        if produs.get("imagine"):
            try:
                poza_reala = image_from_url(produs["imagine"], cu_logo=(mod == "catalog"),
                                            referer=produs.get("url") or None)
            except Exception as e:  # noqa: BLE001
                motiv_poza = str(e)[:160]
                print(f"  poza produsului nu s-a putut lua ({motiv_poza})")
        else:
            motiv_poza = "produsul n-are poză în catalog"
    fara_produs = bool(produs) and mod in ("wow", "catalog") and poza_reala is None
    if fara_produs:
        probleme_seo.append("poza produsului nu s-a putut lua de pe site (" + motiv_poza +
                            ") — imaginea e o scenă FĂRĂ produs; pune poza reală înainte de aprobare")

    # Promptul de imagine se scrie ACUM, cu articolul terminat in fata — nu in
    # aceeasi cerere cu articolul, unde primea cea mai putina atentie si iesea
    # „laptop cu grafice", fara legatura cu ce scrisese modelul.
    #
    # NU si la catalog cand punem in scena poza reala a produsului: acolo
    # promptul descrie ce e IN JURUL produsului, iar produsul ramane neatins.
    # Un prompt scris pentru o scena cu totul noua ar strica exact compunerea.
    pune_in_scena = poza_reala is not None and mod == "wow"
    if not pune_in_scena and not prompt_deja_scris:
        from content_gen import cheama_modelul
        prompt_nou = imagine_prompt.scrie(continut, cheama_modelul)
        if prompt_nou:
            continut["image_prompt"] = prompt_nou
            print(f"  imaginea: {prompt_nou[:90]}…")
            slabe = imagine_prompt._pare_slab(prompt_nou)
            if slabe:
                probleme_seo.append("poza risca sa iasa generica (" + ", ".join(slabe) + ")")

    imagine, eroare_img = None, ""
    poza_costa = True          # dacă a trecut pe la OpenAI, se pune la socoteală

    if poza_reala is not None:
        if mod == "catalog":
            imagine, poza_costa = poza_reala, False
            print("  imaginea e poza din catalog, neatinsă")
        else:
            # poza reală devine punctul de plecare: produsul rămâne el, dar intră într-o scenă
            try:
                imagine = compune_din_produs(poza_reala, continut["image_prompt"])
                print("  imaginea: poza produsului, pusă în scenă")
            except Exception as e:  # noqa: BLE001
                print(f"  compunerea a eșuat ({str(e)[:120]}), rămân la poza din catalog")
                imagine, poza_costa = poza_reala, False

    if not imagine:
        prompt_img = continut.get("image_prompt") or ""
        # Numele produsului intra in prompt DOAR cand omul a cerut dinadins poza
        # desenata („generata"). Altfel modelul inventeaza un produs care nu e al lui.
        if produs and prompt_img and mod == "generata":
            prompt_img = (
                f"Fotografie editoriala de produs: {produs.get('nume') or 'produsul'}. "
                + prompt_img
            )
        if not prompt_img.strip():
            prompt_img = (f"Fotografie editoriala, lumina naturala, pentru un articol despre "
                          f"{continut.get('topic_title') or config.CLIENT_NICHE or 'subiectul articolului'}.")
        if fara_produs:
            prompt_img = prompt_img.rstrip() + FARA_PRODUS
        prompt_img = prompt_img.rstrip() + imagine_prompt.fara_text_la_generare()
        coperta = config.FEL_AZI == "coperta"
        imagine, eroare_img = genereaza_imagine(prompt_img, cu_logo=not coperta)
        if imagine and coperta:
            titlu_coperta = continut.get("seo_title") or continut.get("topic_title") or ""
            try:
                imagine = compune_coperta(imagine, titlu_coperta)
                print("  coperta: titlul pus pe poza")
            except Exception as e:  # noqa: BLE001 — fara titlu, poza ramane buna de folosit
                print(f"  coperta nu s-a putut compune ({str(e)[:120]}) — rămâne poza simplă")

    # Afișul de Instagram: a doua imagine, cu text mare pe ea. Se face doar dacă
    # omul a bifat-o ȘI dacă Instagram e chiar în canalele slotului — altfel am
    # plăti o generare în plus pentru o poză pe care n-o vede nimeni.
    imagine_ig, prompt_ig = None, ""
    if config.IG_SEPARATA and "ig" in config.CANALE:
        prompt_ig = imagine_ig_mod.scrie(continut)
        try:
            imagine_ig = afis_instagram(prompt_ig)
            print("  imaginea de Instagram: afiș " + (config.IG_SABLON or "lista"))
        except Exception as e:  # noqa: BLE001 — afișul nu merită să oprească postarea
            print(f"  afișul de Instagram nu a ieșit ({str(e)[:120]}) — rămâne poza de blog")
            imagine_ig = None

    return {"imagine": imagine, "poza_costa": poza_costa, "eroare_img": eroare_img,
            "imagine_ig": imagine_ig, "prompt_ig": prompt_ig}


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

    # Intai scoatem linkurile inventate de model, apoi punem indemnul — altfel
    # am verifica si linkul ales de om, care e bun prin definitie.
    ale_noastre = {str(p.get("url") or "").rstrip("/") for p in (config.SITE or []) if p.get("url")}
    continut["article_html"], linkuri_scoase = curata_linkurile(continut.get("article_html") or "", ale_noastre)
    if linkuri_scoase:
        print(f"  {linkuri_scoase} link(uri) inventate scoase din articol")
    # HTML-ul vine de la un model care a citit paginile clientului: il tratam ca
    # text din afara si scoatem script/style/on… inainte sa ajunga pe site
    continut["article_html"] = seo.curata_html(continut["article_html"])
    # indemnul: stilul, culoarea, textele si pozitia vin din panou (cta.py)
    continut["article_html"] = cta.pune(continut["article_html"])

    # verificarile de SEO/GEO nu opresc nimic — se scriu pe ciorna, ca omul sa
    # vada la ce sa se uite inainte de aprobare
    probleme_seo = seo.controale(continut)
    if probleme_seo:
        print("  de verificat: " + "; ".join(probleme_seo))
    # semnatura vizibila a autorului, sub titlu — dupa controale, ca linkul spre pagina
    # autorului sa nu treaca drept link intern pus de model
    continut["article_html"] = seo.cu_semnatura(continut["article_html"])

    # Poza REALA a produsului, felul pozei, promptul separat, poza si afisul: vezi _imagini()
    config.FEL_AZI = imagine_prompt.alege_fel()
    rez = _imagini(continut, produs, probleme_seo)
    imagine, poza_costa, eroare_img = rez["imagine"], rez["poza_costa"], rez["eroare_img"]
    imagine_ig, prompt_ig = rez["imagine_ig"], rez["prompt_ig"]

    draft_id = panel.creeaza_ciorna(config.CLIENT_ID, {
        "topic_title": continut["topic_title"],
        "angle": continut["angle"],
        "seo_title": continut["seo_title"],
        "meta_description": continut["meta_description"],
        "article_html": continut["article_html"],
        "facebook_text": continut["facebook_text"],
        "instagram_text": continut["instagram_text"],
        "are_imagine": bool(imagine),
        "intrebare": continut.get("intrebare") or "",
        "raspuns_scurt": continut.get("raspuns_scurt") or "",
        "schelet": continut.get("_schelet") or "",
        "seo_probleme": probleme_seo,
        # promptul se vede in panou: altfel nu poti judeca DE CE a iesit poza asa
        "image_prompt": continut.get("image_prompt") or "",
        # felul pozei principale; panoul il tine ca rulajul sa nu repete acelasi fel
        "imagine_fel": config.FEL_AZI or "",
        "image_prompt_ig": prompt_ig if imagine_ig else "",
        "produs_ext_id": (produs or {}).get("ext_id"),
        "idee_id": (config.IDEE or {}).get("id"),
        "canale": config.CANALE,
        "slot": config.SLOT,
        # consumul, ca panoul să poată arăta costul și profitul pe client
        "model_text": config.MODEL_TEXT,
        "model_imagine": config.MODEL_IMAGINE,
        "calitate_imagine": config.OPENAI_IMAGE_QUALITY,
        "tokens_in": CONSUM["tokens_in"],
        "tokens_out": CONSUM["tokens_out"],
        # poza luată ca atare din catalog nu costă nimic; cea pusă în scenă, da.
        # Afișul de Instagram e o generare în plus, deci se numără separat.
        "imagini": (1 if (imagine and poza_costa) else 0) + (1 if imagine_ig else 0),
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

    if imagine_ig:
        try:
            panel.urca_imagine(draft_id, imagine_ig, fel="ig")
        except Exception as e:  # noqa: BLE001 — Instagram cade înapoi pe poza de blog
            print(f"  afișul de Instagram nu a putut fi urcat: {str(e)[:150]}")

    avertisment = ""
    if not imagine and ("ig" in config.CANALE or "fb" in config.CANALE):
        avertisment = ("Ciorna nu are imagine — Instagram se sare, iar pe Facebook se postează "
                       "link către articol. Motiv: " + (eroare_img or "necunoscut"))
        panel.actualizeaza(draft_id, eroare=avertisment)

    tg.anunta_ciorna(draft_id, continut["seo_title"], continut["facebook_text"],
                     continut["instagram_text"], imagine, avertisment)
    print(f"  ciorna {draft_id}: {continut['topic_title']}" + ("  [FĂRĂ IMAGINE]" if not imagine else ""))


def _ciorna_disparuta(e: Exception) -> bool:
    """Panoul a raspuns 404: ciorna nu mai exista (stearsa din panou). Nu e o eroare de reincercat."""
    return isinstance(e, panel.PanouIndisponibil) and str(e).startswith("404 ")


def doar_imagini(draft_id: str) -> None:
    """mp12: textul ciornei l-a scris motorul din worker (MOTOR_TEXT = "js"). Aici se fac DOAR
    pozele ei, apoi panoul afla ca e gata (`imagine_gata`) si aduna costul lor peste cel al
    textului (`consum_adauga`). Lesa img-<ciorna> din panou opreste o a doua rulare."""
    try:
        date = panel.imagine_de_facut(draft_id)
    except panel.PanouIndisponibil as e:
        if not _ciorna_disparuta(e):
            raise
        print(f"Nimic de facut pe {draft_id}: ciorna a fost stearsa intre timp")
        return
    ciorna = date.get("ciorna")
    if not ciorna:
        print(f"Nimic de facut pe {draft_id}: {date.get('motiv') or 'ciorna nu asteapta imagini'}")
        return
    client = date.get("client") or {}
    CONSUM["tokens_in"] = CONSUM["tokens_out"] = 0
    try:
        # in try: un config care crapa tot trebuie sa elibereze ciorna („in lucru") din panou
        config.aplica(client)
        print(f"\n=== {config.CLIENT_NAME} (id {config.CLIENT_ID}) — doar imaginile ciornei {draft_id} ===")
        lipsa = config.lipsuri_generare()
        if lipsa:
            panel.actualizeaza(draft_id, imagine_gata=True,
                               eroare="Imaginile nu s-au facut: lipsește " + ", ".join(lipsa))
            return
        continut = dict(ciorna)
        produs = client.get("produs")
        config.FEL_AZI = (ciorna.get("imagine_fel") or "").strip() or imagine_prompt.alege_fel()
        probleme: list = []
        rez = _imagini(continut, produs, probleme, prompt_deja_scris=bool(ciorna.get("prompt_scris")))
        imagine, imagine_ig, eroare_img = rez["imagine"], rez["imagine_ig"], rez["eroare_img"]

        if imagine:
            try:
                panel.urca_imagine(draft_id, imagine)
            except Exception as e:  # noqa: BLE001
                if _ciorna_disparuta(e):
                    print(f"  ciorna {draft_id} a fost stearsa cat se faceau pozele — nu mai anunt nimic")
                    return
                print(f"  imaginea nu a putut fi urcată în panou: {e}")
                imagine, eroare_img = None, str(e)[:300]
        if imagine_ig:
            try:
                panel.urca_imagine(draft_id, imagine_ig, fel="ig")
            except Exception as e:  # noqa: BLE001 — Instagram cade înapoi pe poza de blog
                if _ciorna_disparuta(e):
                    print(f"  ciorna {draft_id} a fost stearsa cat se faceau pozele — nu mai anunt nimic")
                    return
                print(f"  afișul de Instagram nu a putut fi urcat: {str(e)[:150]}")
                imagine_ig = None

        avertisment = ""
        if not imagine and ("ig" in config.CANALE or "fb" in config.CANALE):
            avertisment = ("Ciorna nu are imagine — Instagram se sare, iar pe Facebook se postează "
                           "link către articol. Motiv: " + (eroare_img or "necunoscut"))
        campuri = {
            "imagine_gata": True, "consum_adauga": True, "are_imagine": bool(imagine),
            "image_prompt": continut.get("image_prompt") or "",
            "image_prompt_ig": rez["prompt_ig"] if imagine_ig else "",
            "seo_probleme_adauga": probleme,
            "model_imagine": config.MODEL_IMAGINE, "calitate_imagine": config.OPENAI_IMAGE_QUALITY,
            "tokens_in": CONSUM["tokens_in"], "tokens_out": CONSUM["tokens_out"],
            "imagini": (1 if (imagine and rez["poza_costa"]) else 0) + (1 if imagine_ig else 0),
        }
        if avertisment:
            campuri["eroare"] = avertisment
        panel.actualizeaza(draft_id, **campuri)
    except Exception as e:  # noqa: BLE001 — ciorna nu ramane blocata „in lucru"
        traceback.print_exc()
        try:
            panel.actualizeaza(draft_id, imagine_gata=True, eroare=f"Imaginile au picat: {str(e)[:300]}")
        finally:
            raise
    tg.anunta_ciorna(draft_id, continut.get("seo_title") or "", continut.get("facebook_text") or "",
                     continut.get("instagram_text") or "", imagine, avertisment)
    print(f"  ciorna {draft_id}: imaginile gata" + ("" if imagine else "  [FĂRĂ IMAGINE]"))


def main() -> None:
    # mp12: pornit din coada Cloudflare doar pentru pozele unei ciorne scrise in worker
    ciorna = os.environ.get("DRAFT_ID", "").strip()
    if ciorna:
        try:
            doar_imagini(ciorna)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            print(f"  EȘEC la imaginile ciornei {ciorna}: {e}")
            sys.exit(1)
        return
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
    # inainte iesea verde daca macar un client reusea; acum orice esec se vede
    sys.exit(1 if esecuri else 0)


if __name__ == "__main__":
    main()
