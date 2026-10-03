"""
MOON Post — cele 4 site-uri ale noastre (2 oct 2026, dupa auditul SEO).
Portat din moon-post/src/motor/siteuri-moon.js — tine-le identice.

Pe themoonagency.ro, moonpost.ro, moonchat.ro si moonsite.ro MOON Post scrie pentru noi, deci:
- datele structurate NU mai aduc o organizatie proprie: `publisher` trimite la @id-ul organizatiei
  pe care o descrie chiar site-ul (fiecare site are alt @id);
- autorul e mereu Felix Dumitru, cu acelasi obiect Person peste tot;
- BreadcrumbList doar unde pagina de articol nu-l face singura (moonsite.ro il face);
- preturile produselor MOON nu intra in texte: „abonament lunar, în funcție de …" + pagina de preturi.
Sumele de mai jos sunt doar ca sa RECUNOASTEM un pret MOON scris fara numele produsului.
Modulul nu importa config: il folosesc si config.py, si poarta.py, si seo.py.
"""

from __future__ import annotations
import re
from urllib.parse import urlsplit

PERSOANA_FELIX = {
    "@type": "Person", "@id": "https://themoonagency.ro/echipa#felix-dumitru", "name": "Felix Dumitru",
    "url": "https://themoonagency.ro/echipa", "sameAs": ["https://www.linkedin.com/in/felix-dumitru"],
}

# „\b" din JS e pe ASCII; in Python ar fi pe Unicode, deci il scriem de mana
_B0, _B1 = r"(?<![A-Za-z0-9_])", r"(?![A-Za-z0-9_])"

PRODUSE_MOON = {
    "post": {"nume": "MOON Post", "re": re.compile(_B0 + r"moon\s*post" + _B1, re.I),
             "preturi": "https://moonpost.ro/preturi", "axa": "cât de des publici",
             "sume": [99, 199, 249, 399, 499, 899, 1199]},
    "chat": {"nume": "MOON Chat", "re": re.compile(_B0 + r"moon\s*chat" + _B1, re.I),
             "preturi": "https://moonchat.ro/preturi", "axa": "numărul de conversații",
             "sume": [20, 25, 29, 30, 39, 59, 79, 119, 149, 229]},
    "site": {"nume": "MOON Site", "re": re.compile(_B0 + r"moon\s*site" + _B1, re.I),
             "preturi": "https://moonsite.ro/#preturi", "axa": "pachetul ales",
             "sume": [2, 4, 6, 9, 19, 25, 29, 35, 119]},
}

# org = @id-ul organizatiei din schema site-ului; breadcrumb = il pune MOON Post
SITE_MOON = {
    "themoonagency.ro": {"org": "https://themoonagency.ro/#organization", "breadcrumb": True, "produs": ""},
    "moonpost.ro": {"org": "https://moonpost.ro/#organizatie", "breadcrumb": True, "produs": "post"},
    "moonchat.ro": {"org": "https://moonchat.ro/#organizatie", "breadcrumb": True, "produs": "chat"},
    "moonsite.ro": {"org": "https://moonsite.ro/#org", "breadcrumb": False, "produs": "site"},
}


def gazda(adresa) -> str:
    """„https://www.MoonPost.ro/blog" / „moonpost.ro" -> „moonpost.ro"."""
    a = str(adresa or "").strip().lower()
    if not a:
        return ""
    if not re.match(r"^[a-z]+://", a):
        a = "https://" + a
    try:
        h = urlsplit(a).hostname or ""
    except ValueError:
        return ""
    return re.sub(r"\.$", "", re.sub(r"^www\.", "", h))


def site_moon(adresa) -> dict | None:
    """Setarile site-ului nostru pentru un domeniu/o adresa, ori None pentru un client oarecare.
    Subdomeniile clientilor (brutaria-ion.moonsite.ro) NU sunt site-urile noastre."""
    g = gazda(adresa)
    if not g or g not in SITE_MOON:
        return None
    return {"gazda": g, "baza": "https://" + g, **SITE_MOON[g]}


def nume_autor(nume) -> str:
    """„Dumitru Felix" (cum era trecut in panou) -> „Felix Dumitru". Restul numelor raman cum sunt."""
    n = str(nume or "").strip()
    return "Felix Dumitru" if re.sub(r"\s+", " ", n.lower()) == "dumitru felix" else n
