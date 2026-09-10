"""
Plasa de siguranta pentru apelurile catre furnizorii de AI.

De ce exista fisierul asta: pe 9 septembrie o generare a picat cu
`RemoteDisconnected: Remote end closed connection without response` — Google
a inchis conexiunea fara sa raspunda. Nu e o eroare a modelului si nu e nimic
de reparat in prompt: e o pana de retea de o secunda. Dar cum `requests.post`
era chemat gol, exceptia urca pana sus si clientul ramanea in ziua aia fara
ciorna, fara ca cineva sa afle de ce.

Aici incercam din nou, de cateva ori, cu pauza tot mai mare. Doar la erorile
de retea (conexiune cazuta, timeout) — un 4xx sau 5xx tot ajunge la apelant,
fiindca alea se trateaza altfel (429 = cota, 400 = cerere gresita).
"""

from __future__ import annotations
import time
import requests

# 3 incercari cu 4s, apoi 8s intre ele: acopera sughitul de retea de cateva
# secunde fara sa tina jobul in loc daca furnizorul chiar e cazut.
INCERCARI = 3
PAUZA_PORNIRE = 4


def post(url: str, **kw):
    """requests.post care nu se da batut la prima pana de retea."""
    return _cu_rabdare("POST", url, **kw)


def get(url: str, **kw):
    """requests.get care nu se da batut la prima pana de retea."""
    return _cu_rabdare("GET", url, **kw)


def _cu_rabdare(metoda: str, url: str, **kw):
    pauza = PAUZA_PORNIRE
    for i in range(INCERCARI):
        try:
            # chemam prin modul, nu prin referinta salvata la import, ca testele
            # sa poata inlocui requests.post cu unul fals
            return requests.post(url, **kw) if metoda == "POST" else requests.get(url, **kw)
        except (requests.ConnectionError, requests.Timeout) as e:
            if i == INCERCARI - 1:
                raise
            print(f"  reteaua a cazut ({type(e).__name__}) — mai incerc peste {pauza}s")
            time.sleep(pauza)
            pauza *= 2
