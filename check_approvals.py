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

import panel
from config import config
from publishers import blog_api, gbp, meta, wordpress
import telegram_bot as tg


def _imagine_ciorna(ciorna: dict) -> bytes | None:
    """Imaginea stă în panou (R2). O luăm de acolo, nu o regenerăm — ar costa
    din nou și ar ieși altceva decât ce a aprobat omul."""
    cheie = ciorna.get("imagine_key")
    if not ciorna.get("are_imagine") or not cheie or not config.PANEL_URL:
        return None
    try:
        r = requests.get(f"{config.PANEL_URL}/img/{cheie}", timeout=60)
        if r.status_code < 400 and len(r.content) > 100:
            return r.content
    except requests.RequestException:
        pass
    return None


def publica(ciorna: dict) -> None:
    draft_id = ciorna["id"]
    print(f"  public {draft_id}: {ciorna.get('seo_title')}")

    lipsa = config.lipsuri_publicare()
    if lipsa:
        panel.actualizeaza(draft_id, stare="eroare", eroare="Lipsesc " + ", ".join(lipsa))
        return

    imagine = _imagine_ciorna(ciorna)

    # blogul se pune de mana: nu-l atingem, dar restul canalelor merg
    if config.BLOG_MANUAL:
        adresa_img = (
            f"{config.PANEL_URL}/img/{ciorna.get('imagine_key')}"
            if (ciorna.get("are_imagine") and ciorna.get("imagine_key") and config.PANEL_URL)
            else None
        )
        wp = {"id": None, "link": "", "image_url": adresa_img}
        _publica_social(ciorna, draft_id, wp, ["articolul se copiaza de mana in platforma clientului"])
        return

    # blogul e fie pe API propriu, fie pe WordPress
    unde = "API propriu" if config.BLOG_PE_API else "WordPress"
    try:
        if config.BLOG_PE_API:
            # imaginea e deja publica in panou (R2) — API-ul primeste adresa, nu octetii
            cheie = ciorna.get("imagine_key")
            adresa_img = (
                f"{config.PANEL_URL}/img/{cheie}"
                if (ciorna.get("are_imagine") and cheie and config.PANEL_URL)
                else None
            )
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

    _publica_social(ciorna, draft_id, wp)


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

    # canalele alese în programul clientului pentru slotul ăsta
    canale = [c for c in str(ciorna.get("canale") or "wp").split(",") if c]

    # --- Facebook ---
    if "fb" in canale:
        try:
            if image_url:
                # postarea cu poza nu are camp de link, deci il punem in text
                fb = meta.publish_facebook_photo(
                    image_url,
                    _cu_link(ciorna.get("facebook_text") or "", wp.get("link"), "Articolul complet: {link}"),
                )
                rezultat["fb_link"] = fb.get("permalink_url")
            elif wp.get("link"):
                # fără imagine, postăm link către articol — înainte, Facebook se sărea tăcut
                fb = meta.publish_facebook_link(wp.get("link"), ciorna.get("facebook_text") or "")
                note.append("Facebook: postare cu link, fără imagine.")
                rezultat["fb_link"] = fb.get("permalink_url")
            else:
                note.append("Facebook sărit: nu există nici imagine, nici link de articol.")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            note.append(f"Facebook a eșuat: {str(e)[:200]}")

    # --- Instagram (are nevoie obligatoriu de o imagine publică) ---
    if "ig" in canale:
        if not image_url:
            note.append("Instagram sărit: nu există imagine, iar Instagram nu acceptă postări fără imagine.")
        else:
            try:
                # pe Instagram adresele nu sunt clicabile in descriere, dar oamenii
                # le copiaza; le punem intregi, cu „https://", ca sa mearga la copiere
                adresa = (wp.get("link") or "").rstrip("/")
                ig = meta.publish_instagram_photo(
                    image_url,
                    _cu_link(ciorna.get("instagram_text") or "", adresa, "Articolul complet: {link}"),
                )
                rezultat["ig_link"] = ig.get("permalink_url")
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                note.append(f"Instagram a eșuat: {str(e)[:200]}")

    # --- Profilul Google ---
    if "gbp" in canale:
        try:
            g = gbp.publish_local_post(
                text=ciorna.get("facebook_text") or ciorna.get("seo_title") or "",
                link=wp.get("link") or None,
                image_url=image_url,
            )
            rezultat["gbp_link"] = g.get("permalink_url")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            note.append(f"Profilul Google a eșuat: {str(e)[:200]}")

    panel.actualizeaza(draft_id, stare="publicat", rezultat=rezultat,
                       eroare="; ".join(note) if note else None)

    tg.anunta(
        f"✅ *Publicat — {config.CLIENT_NAME}*\n*{ciorna.get('seo_title')}*\n"
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
            panel.actualizeaza(ciorna["id"], stare="eroare", eroare=str(e)[:400])


if __name__ == "__main__":
    main()
