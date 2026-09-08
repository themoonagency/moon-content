"""
Generează panoul de control — un articol WordPress (draft, vizibil doar
ție logat) cu istoricul tuturor ciornelor: ce s-a generat, ce status are,
și linkuri directe către fiecare publicare (WordPress + Facebook +
Instagram). Rulează la finalul ambelor cronuri, ca panoul să fie mereu
la zi.

Citește toate fișierele state/drafts_*.json (câte unul per client — acum
doar the-moon-agency, dar pregătit pentru mai mulți clienți în viitor).
"""
import glob
import json
import os
from datetime import datetime, timezone

from publishers import wordpress

STATE_DIR = os.path.join(os.path.dirname(__file__), "state")

STATUS_LABELS = {
    "pending": "🕓 În așteptare",
    "approved": "⏳ Aprobată, se publică",
    "published": "✅ Publicată",
    "rejected": "🗑️ Respinsă",
}


def _load_all_drafts() -> list[dict]:
    all_drafts = []
    for path in glob.glob(os.path.join(STATE_DIR, "drafts_*.json")):
        with open(path, "r", encoding="utf-8") as f:
            drafts = json.load(f)
        all_drafts.extend(drafts.values())
    all_drafts.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return all_drafts


def _row_html(draft: dict) -> str:
    status = STATUS_LABELS.get(draft.get("status"), draft.get("status", "?"))
    created = draft.get("created_at", "")[:16].replace("T", " ")
    title = draft.get("seo_title") or draft.get("topic_title") or "(fără titlu)"
    client = draft.get("client_slug", "")

    links = []
    if draft.get("wp_link"):
        links.append(f'<a href="{draft["wp_link"]}">WordPress</a>')
    if draft.get("fb_link"):
        links.append(f'<a href="{draft["fb_link"]}">Facebook</a>')
    if draft.get("ig_link"):
        links.append(f'<a href="{draft["ig_link"]}">Instagram</a>')
    links_html = " · ".join(links) if links else "—"

    return (
        "<tr>"
        f"<td>{created}</td>"
        f"<td>{client}</td>"
        f"<td>{title}</td>"
        f"<td>{status}</td>"
        f"<td>{links_html}</td>"
        "</tr>"
    )


def build_dashboard_html() -> str:
    drafts = _load_all_drafts()
    rows = "\n".join(_row_html(d) for d in drafts) or "<tr><td colspan='5'>Încă nicio ciornă.</td></tr>"

    counts = {}
    for d in drafts:
        s = d.get("status", "?")
        counts[s] = counts.get(s, 0) + 1
    summary = " · ".join(f"{STATUS_LABELS.get(k, k)}: {v}" for k, v in counts.items())

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""
<p><em>Actualizat automat: {now}</em></p>
<p><strong>{summary}</strong></p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%;">
<thead>
<tr><th>Data</th><th>Client</th><th>Titlu</th><th>Status</th><th>Linkuri</th></tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
"""


def main() -> None:
    html = build_dashboard_html()
    result = wordpress.upsert_dashboard_post("🎛️ Moon Content — Panou de control", html)
    preview_link = f"{result.get('link') or ''}"
    print(f"Panou actualizat: articol WordPress #{result['id']}")


if __name__ == "__main__":
    main()
