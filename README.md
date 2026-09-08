# Moon Content — Faza 1 (THE MOON Agency, flux "autoritate")

Bot care scrie zilnic un articol de blog + postări pentru Facebook și
Instagram, generează o imagine, și le trimite pe Telegram pentru aprobare
înainte de publicare. Nimic nu se publică automat (deocamdată) — vezi
`AUTO_PUBLISH_IF_NO_RESPONSE` mai jos.

## Ce face, pas cu pas

1. **`generate_draft.py`** (rulează 1x/zi, cron GitHub Actions):
   - Gemini caută o noutate recentă din nișa agenției (căutare Google
     integrată direct în API, fără cheie separată)
   - Scrie articolul (SEO+GEO) + text Facebook + text Instagram
   - OpenAI generează o imagine pe baza articolului
   - Trimite totul pe Telegram, cu butoane **Aprobă** / **Respinge**
2. **`check_approvals.py`** (rulează la 15 min, cron separat):
   - Citește răspunsul de pe Telegram
   - Dacă e aprobat: publică articolul pe WordPress, apoi poza + text pe
     Facebook și Instagram (reutilizează imaginea urcată pe WordPress,
     Meta cere un URL public, nu acceptă fișier direct)
   - Dacă e respins: marchează ciorna ca respinsă, nu publică nimic
   - Trimite o confirmare pe Telegram cu linkurile publicate

## Instalare (o singură dată)

### 1. Pune codul pe GitHub
```bash
cd moon-content
git add -A
git commit -m "Moon Content v1"
git remote add origin git@github.com:themoonagency/moon-content.git
git push -u origin main
```

### 2. Adaugă secretele în GitHub
Repo → Settings → Secrets and variables → Actions → **New repository secret**,
câte unul pentru fiecare din astea (valorile le ai deja, din conversația
unde le-am pregătit):

| Secret | Valoare |
|---|---|
| `WP_URL` | `https://themoonagency.ro` |
| `WP_USER` | `MOON` |
| `WP_APP_PASSWORD` | parola de aplicație WordPress pe care mi-ai dat-o |
| `META_SYSTEM_USER_TOKEN` | token-ul System User "Moon Content" de pe Meta |
| `META_PAGE_ID` | `104878805077409` |
| `META_IG_ID` | `17841447599150600` |
| `GEMINI_API_KEY` | cheia Gemini |
| `OPENAI_API_KEY` | cheia OpenAI |
| `TELEGRAM_BOT_TOKEN` | token-ul de la @BotFather (`MoonContent_bot`) |
| `TELEGRAM_CHAT_ID` | `895952654` |

**Important pe termen lung:** token-ul System User de pe Meta expirat sau
revocat trebuie regenerat manual din Business Manager, din când în când
(în funcție de tipul de token ales la generare — cele pe termen lung țin
luni de zile, dar nu sunt eterne).

### 3. (Opțional) Activează publicarea automată după un timp
Repo → Settings → Secrets and variables → Actions → tab **Variables**:
- `AUTO_PUBLISH_IF_NO_RESPONSE` = `true` (implicit e `false` — nimic nu
  se publică fără aprobare explicită)
- `AUTO_PUBLISH_AFTER_HOURS` = `6` (sau ce interval preferi)

Recomandare: lasă pe `false` primele 2-3 săptămâni, până vezi calitatea
constantă a ciornelor.

### 4. Testează manual, fără să aștepți cronul
Repo → tab **Actions** → alege workflow-ul → **Run workflow**. Poți rula
`generate-daily` oricând vrei o ciornă nouă pe loc.

## Testare locală (opțional, înainte de a pune pe GitHub)

```bash
pip install -r requirements.txt
export WP_URL=https://themoonagency.ro
export WP_USER=MOON
export WP_APP_PASSWORD=...
export META_SYSTEM_USER_TOKEN=...
export META_PAGE_ID=104878805077409
export META_IG_ID=17841447599150600
export GEMINI_API_KEY=...
export OPENAI_API_KEY=...
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=895952654

python generate_draft.py     # generează + trimite pe Telegram
# ... aprobă din Telegram ...
python check_approvals.py    # publică ce a fost aprobat
```

## Structura proiectului

```
config.py              — toate setările, citite din variabile de mediu
state.py                — ciorne + subiecte folosite (anti-repetiție), în state/*.json
content_gen.py          — Gemini: căutare + articol + postări sociale
image_gen.py            — OpenAI: generare imagine
publishers/wordpress.py — publicare articol + upload imagine
publishers/meta.py      — publicare Facebook + Instagram
telegram_bot.py         — trimitere spre aprobare + citire răspunsuri
generate_draft.py       — script 1: generare zilnică
check_approvals.py      — script 2: publicare după aprobare
.github/workflows/      — cele două cronuri
state/                  — NU se șterge, e memoria botului (comisă de workflow)
```

## Limitări cunoscute (de rezolvat în valuri următoare)

- **Meta description pe WordPress**: momentan merge în câmpul `excerpt`.
  Dacă site-ul folosește Yoast SEO, meta description-ul real (cel citit de
  Google) e alt câmp (`_yoast_wpseo_metadesc`) — necesită fie un mic plugin/
  endpoint suplimentar pe WordPress, fie completare manuală ocazională.
  Ușor de adăugat quando vrei — spune-mi și rezolv.
- **Threads**: lăsat deocamdată — API-ul e disponibil de curând pe cont,
  se adaugă separat.
- **Google Business Profile**: în așteptarea aprobării Google (case ID
  `9-3978000041181`), se adaugă ca `publishers/gbp.py` quando vine accesul.
- **Token Meta pe termen lung**: nu e gestionat automat — de verificat
  manual din când în când că nu a expirat.
- **Flux "catalog"** (magazine online): neconstruit încă — Faza 1 e doar
  flux "autoritate", fără produse.
