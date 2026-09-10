"""
Rulare la 5 minute: ia din panou ciornele APROBATE (de om, din panou) și le
publică pe WordPress + Facebook + Instagram, apoi scrie rezultatul înapoi în
panou.

Nu mai citește Telegram și nu mai ține offset — aprobarea se face în panou.
Publicarea forțată nu mai are nevoie de un input de workflow: se apasă
„Aprobă" pe ciorna respectivă.
"""

from __future__ import annotations
import traceback

import requests

import time

import panel
import seo
from config import config
from publishers import blog_api, gbp, meta, wordpress
import telegram_bot as tg


def _imagine_ciorna(ciorna: dict) -> bytes | None:
    """Imaginea stă în panou (R2). O luăm de acolo, nu o regenerăm — ar costa
    din nou și ar ieși altceva decât ce a aprobat omul."""
    cheie = ciorna.get("imagine_key")
    if not ciorna.get("are_imagine") or not cheie or not config.PANEL_URL:
        return None
    # „n-am putut lua imaginea" NU e acelasi lucru cu „ciorna n-are imagine":
    # inainte, o pana de retea facea Facebook sa posteze fara poza si Instagram
    # sa fie sarit cu motivul gresit. Acum incercam de trei ori si, daca tot nu
    # merge, ridicam — publicarea se reia la urmatoarea trecere.
    ultima = ""
    for incercare in range(3):
        try:
            r = requests.get(f"{config.PANEL_URL}/img/{cheie}", timeout=60)
            if r.status_code < 400 and len(r.content) > 100:
                return r.content
            ultima = f"panoul a raspuns {r.status_code}"
        except requests.RequestException as e:
            ultima = str(e)[:150]
        if incercare < 2:
            time.sleep(3 * (incercare + 1))
    raise RuntimeError(f"Ciorna are imagine, dar nu am putut-o lua din panou: {ultima}")


def _adresa_imagine(ciorna: dict) -> str | None:
    """Adresa publica a imaginii din panou — Meta si Google o descarca de acolo."""
    cheie = ciorna.get("imagine_key")
    if not (ciorna.get("are_imagine") and cheie and config.PANEL_URL):
        return None
    return f"{config.PANEL_URL}/img/{cheie}"


def _adresa_imagine_ig(ciorna: dict) -> str | None:
    """Afisul de Instagram, daca ciorna are unul. Daca nu, Instagram foloseste
    poza de blog, ca pana acum — nicio postare nu se pierde pentru ca lipseste
    afisul."""
    cheie = ciorna.get("imagine_ig_key")
    if not (ciorna.get("are_imagine_ig") and cheie and config.PANEL_URL):
        return None
    return f"{config.PANEL_URL}/img/{cheie}"


def publica(ciorna: dict) -> None:
    draft_id = ciorna["id"]
    print(f"  public {draft_id}: {ciorna.get('seo_title')}")

    lipsa = config.lipsuri_publicare([c for c in str(ciorna.get("canale") or "wp").split(",") if c])
    if lipsa:
        panel.actualizeaza(draft_id, stare="eroare", eroare="Lipsesc " + ", ".join(lipsa))
        return

    imagine = _imagine_ciorna(ciorna)
    canale = [c for c in str(ciorna.get("canale") or "wp").split(",") if c]
    # ce a reusit deja la o incercare anterioara nu se mai face o data
    facut = ciorna.get("rezultat") if isinstance(ciorna.get("rezultat"), dict) else {}

    if facut.get("wp_link"):
        _publica_social(ciorna, draft_id,
                        {"id": None, "link": facut["wp_link"], "image_url": _adresa_imagine(ciorna)},
                        ["articolul era deja publicat — am reluat doar restul canalelor"])
        return

    # Slotul poate fi doar Facebook+Instagram. Inainte publicam articolul pe
    # blog oricum, adica pe un canal pe care omul il scosese dinadins.
    if "wp" not in canale:
        _publica_social(ciorna, draft_id, {"id": None, "link": "", "image_url": _adresa_imagine(ciorna)},
                        ["blogul nu e in programul slotului asta"])
        return

    # blogul se pune de mana: nu-l atingem, dar restul canalelor merg
    if config.BLOG_MANUAL:
        wp = {"id": None, "link": "", "image_url": _adresa_imagine(ciorna)}
        _publica_social(ciorna, draft_id, wp, ["articolul se copiaza de mana in platforma clientului"])
        return

    # blogul e fie pe API propriu, fie pe WordPress
    unde = "API propriu" if config.BLOG_PE_API else "WordPress"
    try:
        if config.BLOG_PE_API:
            # imaginea e deja publica in panou (R2) — API-ul primeste adresa, nu octetii
            adresa_img = _adresa_imagine(ciorna)
            wp = blog_api.publish_article(
                title=ciorna["seo_title"],
                html_content=ciorna["article_html"],
                meta_description=ciorna.get("meta_description") or "",
                image_url=adresa_img,
                tags=[t for t in str(ciorna.get("tags") or "").split(",") if t.strip()],
            )
        else:
            wp = wordpress.publish_article(
                title=ciorna["seo_title"],
                html_content=ciorna["article_html"],
                meta_description=ciorna.get("meta_description") or "",
                image_bytes=imagine,
            )
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        panel.actualizeaza(draft_id, stare="eroare", eroare=f"Blog ({unde}): {str(e)[:400]}")
        tg.anunta(f"❌ *MOON Post* — publicare blog ({unde}) eșuată ({config.CLIENT_NAME}):\n`{str(e)[:300]}`")
        return

    # Datele structurate au nevoie de adresa finala a articolului, deci se pun
    # abia acum, printr-o a doua trecere. Daca blogul nu accepta actualizarea,
    # nu e o tragedie: articolul e deja publicat.
    _pune_date_structurate(ciorna, wp)

    _publica_social(ciorna, draft_id, wp)


def _pune_date_structurate(ciorna: dict, wp: dict) -> None:
    adresa = (wp.get("link") or "").strip()
    if not adresa:
        return
    try:
        bloc = seo.date_structurate(ciorna, adresa, wp.get("image_url"))
        if not bloc:
            return
        html_nou = (ciorna.get("article_html") or "") + bloc
        if config.BLOG_PE_API:
            blog_api.actualizeaza_articol(wp.get("id"), html_nou)
        elif wp.get("id"):
            wordpress.actualizeaza_articol(wp["id"], html_nou)
    except Exception as e:  # noqa: BLE001
        print(f"  datele structurate n-au putut fi puse: {str(e)[:150]}")


def _cu_link(text: str, link: str, sablon: str) -> str:
    """Pune adresa articolului la finalul textului de social, o singura data.
    Fara asta, postarile trimit oamenii nicaieri — iar articolul e tot ce avem."""
    text = (text or "").strip()
    if not link or link in text:
        return text
    return (text + "\n\n" + sablon.format(link=link)).strip()


def _publica_social(ciorna: dict, draft_id: str, wp: dict, note_initiale: list[str] | None = None) -> None:
    """Facebook / Instagram / Profil Google, dupa ce blogul e rezolvat (sau sarit)."""
    rezultat = {"wp_link": wp.get("link")}
    note = list(note_initiale or [])
    image_url = wp.get("image_url")
    # canalele care CHIAR au picat (nu cele sarite dinadins) — decid daca ciorna
    # ramane de reincercat sau se inchide
    cazute: list[str] = []
    facut = ciorna.get("rezultat") if isinstance(ciorna.get("rezultat"), dict) else {}

    # canalele alese în programul clientului pentru slotul ăsta
    canale = [c for c in str(ciorna.get("canale") or "wp").split(",") if c]

    # --- Facebook ---
    # „a mers deja" NU se deduce din prezenta linkului: Google si Meta pot
    # publica cu succes si sa nu intoarca niciun permalink. De-aia marcam
    # separat reusita, altfel canalul s-ar publica a doua oara la reincercare.
    if facut.get("fb_ok") or facut.get("fb_link"):
        rezultat["fb_ok"] = True
        if facut.get("fb_link"):
            rezultat["fb_link"] = facut["fb_link"]
    elif "fb" in canale:
        try:
            if image_url:
                # postarea cu poza nu are camp de link, deci il punem in text
                fb = meta.publish_facebook_photo(
                    image_url,
                    _cu_link(ciorna.get("facebook_text") or "", wp.get("link"), "Articolul complet: {link}"),
                )
                rezultat["fb_link"] = fb.get("permalink_url")
                rezultat["fb_ok"] = True
            elif wp.get("link"):
                # fără imagine, postăm link către articol — înainte, Facebook se sărea tăcut
                fb = meta.publish_facebook_link(wp.get("link"), ciorna.get("facebook_text") or "")
                note.append("Facebook: postare cu link, fără imagine.")
                rezultat["fb_link"] = fb.get("permalink_url")
                rezultat["fb_ok"] = True
            else:
                note.append("Facebook sărit: nu există nici imagine, nici link de articol.")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            note.append(f"Facebook a eșuat: {str(e)[:200]}")
            cazute.append("Facebook")

    # --- Instagram (are nevoie obligatoriu de o imagine publică) ---
    if facut.get("ig_ok") or facut.get("ig_link"):
        rezultat["ig_ok"] = True
        if facut.get("ig_link"):
            rezultat["ig_link"] = facut["ig_link"]
    elif "ig" in canale:
        # afisul facut pentru Instagram bate poza de blog; daca nu exista, tot poza
        adresa_ig = _adresa_imagine_ig(ciorna) or image_url
        if not adresa_ig:
            note.append("Instagram sărit: nu există imagine, iar Instagram nu acceptă postări fără imagine.")
        else:
            try:
                # pe Instagram adresele nu sunt clicabile in descriere, dar oamenii
                # le copiaza; le punem intregi, cu „https://", ca sa mearga la copiere
                adresa = (wp.get("link") or "").rstrip("/")
                ig = meta.publish_instagram_photo(
                    adresa_ig,
                    _cu_link(ciorna.get("instagram_text") or "", adresa, "Articolul complet: {link}"),
                )
                rezultat["ig_link"] = ig.get("permalink_url")
                rezultat["ig_ok"] = True
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                note.append(f"Instagram a eșuat: {str(e)[:200]}")
                cazute.append("Instagram")

    # --- Profilul Google ---
    if facut.get("gbp_ok") or facut.get("gbp_link"):
        rezultat["gbp_ok"] = True
        if facut.get("gbp_link"):
            rezultat["gbp_link"] = facut["gbp_link"]
    elif "gbp" in canale:
        try:
            g = gbp.publish_local_post(
                text=ciorna.get("facebook_text") or ciorna.get("seo_title") or "",
                link=wp.get("link") or None,
                image_url=image_url,
            )
            rezultat["gbp_link"] = g.get("permalink_url")
            rezultat["gbp_ok"] = True
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            note.append(f"Profilul Google a eșuat: {str(e)[:200]}")
            cazute.append("Profilul Google")

    # Daca un canal cerut a picat, ciorna NU se inchide ca „publicat": ar
    # disparea din coada si nimeni n-ar mai reincerca vreodata. Ce s-a publicat
    # deja e in `rezultat`, iar publicatorii sar peste canalele care au reusit.
    stare = "eroare" if cazute else "publicat"
    # Articolul e DEJA publicat aici. Daca scrisul starii pica, nu aruncam mai
    # departe: main() ar incerca sa scrie „eroare" pe acelasi panou mort, ar
    # crapa rularea, si la urmatoarea trecere s-ar publica totul din nou.
    scris = False
    for i in range(4):
        try:
            panel.actualizeaza(draft_id, stare=stare, rezultat=rezultat,
                               eroare="; ".join(note) if note else None)
            scris = True
            break
        except Exception as e:  # noqa: BLE001
            ultima_eroare = str(e)[:150]
            if i < 3:
                time.sleep(4 * (i + 1))
    if not scris:
        print(f"  ATENTIE: {draft_id} e publicat, dar panoul nu a putut fi anuntat ({ultima_eroare})")
        tg.anunta(f"⚠️ *MOON Post* — {config.CLIENT_NAME}: articolul e publicat, dar panoul nu a "
                  f"putut fi anuntat. Verifica sa nu se republice.")
        return

    semn = "✅ *Publicat" if not cazute else "⚠️ *Publicat pe jumatate"
    tg.anunta(
        f"{semn} — {config.CLIENT_NAME}*\n*{ciorna.get('seo_title')}*\n"
        f"Articol: {rezultat.get('wp_link') or '—'}\n"
        f"Facebook: {rezultat.get('fb_link') or 'lipsă'}\n"
        f"Instagram: {rezultat.get('ig_link') or 'lipsă'}"
        + (f"\nProfil Google: {rezultat.get('gbp_link') or 'lipsă'}" if "gbp" in canale else "")
        + (("\n⚠️ " + "; ".join(note)) if note else "")
    )


def main() -> None:
    aprobate = panel.ciorne(stare="aprobat")
    if not aprobate:
        print("Nicio ciornă aprobată.")
        return

    # cheile sunt ale clientului -> le încărcăm o dată per client
    dupa_id = {c["id"]: c for c in panel.clienti()}
    print(f"{len(aprobate)} ciornă/ciorne de publicat.")

    for ciorna in aprobate:
        client = dupa_id.get(ciorna["client_id"])
        if not client:
            panel.actualizeaza(ciorna["id"], stare="eroare",
                               eroare="Clientul e oprit sau suspendat — nu se publică.")
            continue
        config.aplica(client)
        try:
            publica(ciorna)
        except Exception as e:  # noqa: BLE001 — o ciornă căzută nu oprește restul
            traceback.print_exc()
            try:
                panel.actualizeaza(ciorna["id"], stare="eroare", eroare=str(e)[:400])
            except Exception:  # noqa: BLE001 — panoul e cazut; restul ciornelor merg mai departe
                print(f"  panoul nu raspunde; {ciorna['id']} ramane asa cum e")


if __name__ == "__main__":
    main()
