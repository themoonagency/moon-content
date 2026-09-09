# MOON Post — motorul

Scrie și publică zilnic articol + postare de Facebook + postare de Instagram,
pentru **fiecare client activ** din panoul MOON Post.

Rulează în GitHub Actions. Nu mai ține nicio stare în repo: clienții, cheile,
ciornele, aprobările și subiectele deja tratate stau în panou (Cloudflare Worker
+ D1 + R2). Codul panoului: `~/Moon Bot/moon-post`.

## Cum merge

**`generate_draft.py`** (din oră în oră)
cere panoului **cine are o postare scadentă acum** — panoul face calculul, după
programul fiecărui client (zilnic / la N zile / mai multe postări pe zi, cu ore,
zile și platforme alese). Pentru fiecare: scrie articolul cu Gemini (cu grounding
pe Google Search), face imaginea cu OpenAI, o urcă în panou (R2) și lasă ciorna la
aprobare, cu canalele slotului pe ea. Trimite și un anunț pe Telegram, dacă acel
client are bot.

Pornire manuală din panou (butonul „Generează acum") = `workflow_dispatch` cu
`client_id` și `forteaza`.

**`check_approvals.py`** (la 5 minute)
ia ciornele pe care le-a aprobat un om **în panou** și le publică pe canalele
scrise pe ciornă (blog → Facebook → Instagram), apoi scrie linkurile înapoi în panou.

Aprobarea se face în panou, nu pe Telegram. Telegram doar anunță, cu un buton
care duce în panou — un singur bot nu poate ține butoane de aprobare pentru
mai mulți clienți fără o stare partajată fragilă.

## Configurare

În GitHub → Settings → Secrets rămân **doar două**:

| Secret | Ce e |
|---|---|
| `PANEL_URL` | adresa panoului, ex. `https://moon-post.themoonagency.workers.dev` |
| `CRON_KEY` | aceeași valoare ca secretul `CRON_KEY` din worker |

Per client, în panou: WordPress, Meta, Telegram, ton, nișă, CTA — fiecare bloc cu
buton „Testează". Cât de des și unde se postează se alege la „Programul de postare".

**Cheile de Gemini și OpenAI sunt ale noastre**, puse o singură dată în contul MOON
(Setări → AI). Clientului i se atribuie doar ce model folosește. Motorul primește
cheile prin `/api/cron/clients` și raportează înapoi tokenii consumați și imaginile
generate, ca panoul să arate costul și profitul pe fiecare client.

**Logoul suprapus pe imagini e al clientului** (încărcat sau luat de pe pagina lui
de Facebook/Instagram). Fără logo pus în panou, imaginea iese curată — nu punem
logoul agenției peste postările altcuiva.

## Capcane deja rezolvate

- **WordPress cere „Parolă de aplicație"**, nu parola de login (Users → Profile →
  Application Passwords). Aici a fost cauza reală a eșecurilor de publicare.
- **Firewallul hostingului blochează user-agent-ul `python-requests`** — trimitem
  user-agent de browser.
- **Instagram respinge PNG** — imaginea OpenAI se convertește în JPEG.
- **Logoul** THE MOON Agency (`assets/logo.png`) se suprapune automat dreapta-jos
  pe fiecare imagine.
- **Fără imagine nu se mai sare tăcut**: generarea imaginii se reîncearcă o dată,
  ciorna e marcată explicit în panou cu motivul, Facebook primește o postare cu
  link către articol, iar Instagram e sărit cu explicație (Instagram nu acceptă
  postări fără imagine).
- Retry automat la 429 pe Gemini + reparare de JSON invalid printr-un al doilea apel.

## Teste

`python test_motor.py` — înlocuiește `requests` cu un fals și trece motorul prin
tot fluxul, pe doi clienți, inclusiv cazul „fără imagine". Nu atinge nicio rețea.
