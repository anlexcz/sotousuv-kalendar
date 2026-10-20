from __future__ import annotations

import html
import json
import os
from pathlib import Path

from event_registry import build_registry


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def badge(text: str, cls: str = "") -> str:
    return f'<span class="badge {cls}">{esc(text)}</span>'


def format_term(term: dict | None) -> str:
    if not term:
        return "—"
    df = term.get("date_from") or ""
    dt = term.get("date_to") or df
    return esc(df if df == dt else f"{df} – {dt}")


def build_html(payload: dict) -> str:
    summary = payload["summary"]
    rows = []
    details = []

    for event in payload["events"]:
        states = event["states"]
        terms = event["terms_summary"]
        categories = " ".join(badge(c, "cat") for c in event.get("categories", [])) or "—"
        attention = " ".join(badge(a, "warn") for a in event.get("attention", [])) or "—"
        review_cls = "ok" if states.get("review_state") == "ZKONTROLOVANO" else "warn"
        editorial_cls = "ok" if states.get("editorial_state") == "READY" else "warn"
        publish_cls = "ok" if states.get("publish") == "ANO" else "muted"
        event_id = int(event["event_id"])

        rows.append(f"""
        <tr data-event-id="{event_id}" data-search="{esc((event['title'] + ' ' + ' '.join(event.get('categories', []))).lower())}" data-review="{esc(states.get('review_state'))}" data-editorial="{esc(states.get('editorial_state'))}" data-publish="{esc(states.get('publish'))}">
          <td class="mono">{event_id}</td>
          <td><button class="link-button" onclick="toggleDetail({event_id})">{esc(event['title'])}</button></td>
          <td>{format_term(terms.get('next_or_current_term'))}</td>
          <td class="num">{esc(terms.get('active_count'))}</td>
          <td>{categories}</td>
          <td>{badge(states.get('review_state'), review_cls)}</td>
          <td>{badge(states.get('editorial_state'), editorial_cls)}</td>
          <td>{badge(states.get('publish'), publish_cls)}</td>
          <td>{attention}</td>
        </tr>
        <tr id="detail-row-{event_id}" class="detail-row" hidden>
          <td colspan="9"><div id="detail-{event_id}" class="detail"></div></td>
        </tr>
        """)

        source_items = []
        for source in event.get("sources", []):
            url = source.get("url") or ""
            label = source.get("label") or source.get("source_id") or url
            source_items.append(f'<li><a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)}</a> <span class="muted-text">({esc(source.get("source_role"))})</span></li>')

        term_items = []
        for term in event.get("terms", []):
            active = term.get("is_active") == "ANO"
            cls = "" if active else "inactive"
            term_items.append(
                f'<li class="{cls}"><span class="mono">{esc(term.get("term_id"))}</span> — {format_term(term)} — {esc(term.get("term_state"))} — {esc(term.get("is_active"))}</li>'
            )

        findings = event.get("origin", {}).get("findings", [])
        finding_items = [
            f'<li><span class="mono">{esc(f.get("finding_id"))}</span> — {esc(f.get("status"))} — {esc(f.get("resolution"))}</li>'
            for f in findings
        ]

        loc = event.get("location", {})
        details.append(
            f'<template id="template-{event_id}">'
            f'<div class="detail-grid">'
            f'<section><h3>Základní údaje</h3><dl>'
            f'<dt>Popis</dt><dd>{esc(event.get("description")) or "—"}</dd>'
            f'<dt>Místo</dt><dd>{esc(loc.get("municipality"))} {esc(loc.get("place"))}</dd>'
            f'<dt>Region / země</dt><dd>{esc(loc.get("region"))} {esc(loc.get("country"))}</dd>'
            f'<dt>Trasa</dt><dd>{esc(event.get("route")) or "—"}</dd>'
            f'<dt>Organizátor</dt><dd>{esc(event.get("organizer")) or "—"}</dd>'
            f'<dt>Celodenní</dt><dd>{esc(event.get("all_day"))}</dd>'
            f'</dl></section>'
            f'<section><h3>Editorial</h3><dl>'
            f'<dt>Overrides</dt><dd>{esc(event.get("editorial", {}).get("active_overrides"))}</dd>'
            f'<dt>Alerty</dt><dd>{esc(event.get("editorial", {}).get("open_alerts"))}</dd>'
            f'<dt>Historie</dt><dd>{esc(event.get("editorial", {}).get("history_entries"))}</dd>'
            f'<dt>Verze řádku</dt><dd>{esc(event.get("editorial", {}).get("row_version"))}</dd>'
            f'</dl></section>'
            f'</div>'
            f'<div class="detail-grid">'
            f'<section><h3>Zdroje</h3><ul>{"".join(source_items) or "<li>—</li>"}</ul></section>'
            f'<section><h3>Původ</h3><ul>{"".join(finding_items) or "<li>—</li>"}</ul></section>'
            f'</div>'
            f'<section><h3>Termíny ({esc(terms.get("active_count"))} aktivních, {esc(terms.get("inactive_count"))} neaktivních)</h3><ul class="terms">{"".join(term_items)}</ul></section>'
            f'</template>'
        )

    generated_at = esc(payload.get("generated_at"))
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!doctype html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Šotoušův kalendář – evidence událostí</title>
<style>
:root {{ color-scheme: light dark; font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
body {{ margin: 0; background: Canvas; color: CanvasText; }}
header {{ padding: 24px 28px 12px; border-bottom: 1px solid color-mix(in srgb, CanvasText 16%, transparent); }}
h1 {{ margin: 0 0 6px; font-size: 24px; }}
.sub {{ opacity: .65; font-size: 13px; }}
main {{ padding: 20px 28px 40px; }}
.cards {{ display: grid; grid-template-columns: repeat(5,minmax(120px,1fr)); gap: 10px; margin-bottom: 18px; }}
.card {{ border: 1px solid color-mix(in srgb, CanvasText 16%, transparent); border-radius: 10px; padding: 12px 14px; }}
.card strong {{ display:block; font-size:22px; margin-top:4px; }}
.controls {{ display:flex; gap:10px; flex-wrap:wrap; margin:14px 0; }}
input, select {{ padding:8px 10px; border-radius:8px; border:1px solid color-mix(in srgb, CanvasText 22%, transparent); background:Canvas; color:CanvasText; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th, td {{ text-align:left; padding:9px 8px; border-bottom:1px solid color-mix(in srgb, CanvasText 13%, transparent); vertical-align:top; }}
th {{ position:sticky; top:0; background:Canvas; z-index:1; }}
.num {{ text-align:right; }}
.mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
.badge {{ display:inline-block; padding:2px 7px; border-radius:999px; font-size:11px; margin:1px 2px 1px 0; border:1px solid color-mix(in srgb, CanvasText 20%, transparent); }}
.badge.ok {{ font-weight:600; }} .badge.warn {{ font-weight:600; }} .badge.muted {{ opacity:.65; }} .badge.cat {{ opacity:.85; }}
.link-button {{ all:unset; cursor:pointer; text-decoration:underline; text-decoration-style:dotted; font-weight:600; }}
.detail-row td {{ padding:0 8px 16px; }}
.detail {{ border:1px solid color-mix(in srgb, CanvasText 16%, transparent); border-radius:10px; padding:16px; margin-top:4px; background:color-mix(in srgb, Canvas 96%, CanvasText 4%); }}
.detail-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
h3 {{ margin:4px 0 10px; font-size:15px; }}
dl {{ display:grid; grid-template-columns:140px 1fr; gap:6px 12px; margin:0; }} dt {{ opacity:.6; }} dd {{ margin:0; }}
ul {{ margin:6px 0 0; padding-left:20px; }} .terms {{ max-height:300px; overflow:auto; }} .inactive {{ opacity:.45; text-decoration:line-through; }}
.muted-text {{ opacity:.6; }}
@media (max-width:900px) {{ .cards {{ grid-template-columns:repeat(2,1fr); }} .detail-grid {{ grid-template-columns:1fr; }} table {{ min-width:1000px; }} .table-wrap {{ overflow:auto; }} }}
</style>
</head>
<body>
<header>
  <h1>Evidence událostí</h1>
  <div class="sub">Read-only pracovní pohled • vygenerováno {generated_at}</div>
</header>
<main>
  <div class="cards">
    <div class="card">Události<strong>{summary['event_count']}</strong></div>
    <div class="card">Ke kontrole<strong>{summary['needs_review']}</strong></div>
    <div class="card">Ready<strong>{summary['ready']}</strong></div>
    <div class="card">Publikované<strong>{summary['published']}</strong></div>
    <div class="card">Aktivní termíny<strong>{summary['active_terms']}</strong></div>
  </div>
  <div class="controls">
    <input id="search" type="search" placeholder="Hledat název nebo kategorii…" oninput="applyFilters()">
    <select id="review" onchange="applyFilters()"><option value="">Všechny kontroly</option><option>NEZKONTROLOVANO</option><option>ZKONTROLOVANO</option><option>KE_KONTROLE</option></select>
    <select id="editorial" onchange="applyFilters()"><option value="">Všechny editorial stavy</option><option>DRAFT</option><option>READY</option></select>
    <select id="publish" onchange="applyFilters()"><option value="">Publikace: vše</option><option>NE</option><option>ANO</option></select>
  </div>
  <div class="table-wrap">
  <table id="events"><thead><tr><th>ID</th><th>Název</th><th>Nejbližší termín</th><th>Akt.</th><th>Kategorie</th><th>Kontrola</th><th>Editorial</th><th>Publ.</th><th>Pozornost</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
  </div>
  {''.join(details)}
</main>
<script>
const registry = {data_json};
function toggleDetail(id) {{
  const row = document.getElementById('detail-row-' + id);
  const box = document.getElementById('detail-' + id);
  if (row.hidden) {{
    if (!box.hasChildNodes()) {{ box.appendChild(document.getElementById('template-' + id).content.cloneNode(true)); }}
    row.hidden = false;
  }} else row.hidden = true;
}}
function applyFilters() {{
  const q = document.getElementById('search').value.trim().toLowerCase();
  const review = document.getElementById('review').value;
  const editorial = document.getElementById('editorial').value;
  const publish = document.getElementById('publish').value;
  document.querySelectorAll('#events tbody tr[data-event-id]').forEach(row => {{
    const show = (!q || row.dataset.search.includes(q)) && (!review || row.dataset.review === review) && (!editorial || row.dataset.editorial === editorial) && (!publish || row.dataset.publish === publish);
    row.hidden = !show;
    const detail = document.getElementById('detail-row-' + row.dataset.eventId);
    if (!show) detail.hidden = true;
  }});
}}
</script>
</body>
</html>
"""


def main() -> int:
    output_path = Path(os.environ.get("EVENT_REGISTRY_HTML_PATH", "../../data/event_registry.html"))
    payload = build_registry()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_html(payload), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "mode": "EVENT_REGISTRY_HTML_READ_ONLY",
        "read_only": True,
        "output_path": str(output_path),
        "event_count": payload["summary"]["event_count"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
