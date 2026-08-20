"""SRS 변경 리포트 생성 (HTML + Markdown)."""
from __future__ import annotations

import html as html_lib
from pathlib import Path
from typing import Any

from .diff import SrsDiff


def _summary_counts(diffs: list[SrsDiff]) -> dict[str, int]:
    counts = {"new": 0, "deleted": 0, "changed": 0, "unchanged": 0}
    for d in diffs:
        counts[d.change_type] = counts.get(d.change_type, 0) + 1
    return counts


def render_markdown(
    diffs: list[SrsDiff],
    *,
    execution_date: str,
    previous_date: str | None,
    current_date: str,
    pdf_sanity: list[dict[str, Any]],
) -> str:
    counts = _summary_counts(diffs)
    lines = [
        f"# SRS Change Report ({execution_date})",
        "",
        f"- Execution Date: {execution_date}",
        f"- Previous Snapshot: {previous_date or '(none - first run)'}",
        f"- Current Snapshot: {current_date}",
        f"- Total SRS: {len(diffs)}",
        f"- New: {counts['new']}",
        f"- Deleted: {counts['deleted']}",
        f"- Changed: {counts['changed']}",
        f"- Unchanged: {counts['unchanged']}",
        "",
        "## PDF Sanity Check",
        "",
    ]
    for p in pdf_sanity:
        lines.append(f"- {p['file']}: {p['status']} ({p.get('detail', '')})")

    lines.append("")
    lines.append("## Changed / New / Deleted SRS")
    lines.append("")
    for d in diffs:
        if d.change_type == "unchanged":
            continue
        lines.append(f"### {d.id} - {d.title or d.title_after or ''}")
        lines.append("")
        lines.append(f"Change Type: **{d.change_type}**")
        if d.field_changes:
            lines.append("")
            lines.append("Detected changes:")
            for c in d.field_changes:
                lines.append(f"- {c}")
        if d.status_before != d.status_after:
            lines.append("")
            lines.append(f"Status: `{d.status_before}` -> `{d.status_after}`")
        if d.text_diff_lines:
            lines.append("")
            lines.append("```diff")
            lines.extend(d.text_diff_lines[:200])
            lines.append("```")
        lines.append("")
    return "\n".join(lines)


_HTML_CSS = """
body{font-family:'Segoe UI',sans-serif;font-size:13px;color:#111;max-width:1000px;margin:24px auto;}
.summary{background:#f5f5f5;border:1px solid #ddd;padding:12px 16px;border-radius:6px;}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;color:#fff;margin-right:4px;}
.badge.new{background:#2e7d32;} .badge.deleted{background:#c62828;} .badge.changed{background:#ef6c00;} .badge.unchanged{background:#9e9e9e;}
.srs{border:1px solid #ddd;border-radius:6px;padding:10px 14px;margin:12px 0;}
.diff{background:#1e1e1e;color:#ddd;padding:10px;border-radius:4px;overflow-x:auto;font-family:Consolas,monospace;font-size:12px;white-space:pre;}
.diff .add{color:#4caf50;} .diff .del{color:#ef5350;}
table.sanity{border-collapse:collapse;} table.sanity td, table.sanity th{border:1px solid #ccc;padding:4px 10px;}
"""


def _diff_html(lines: list[str]) -> str:
    out = []
    for line in lines[:200]:
        esc = html_lib.escape(line)
        if line.startswith("+") and not line.startswith("+++"):
            out.append(f'<span class="add">{esc}</span>')
        elif line.startswith("-") and not line.startswith("---"):
            out.append(f'<span class="del">{esc}</span>')
        else:
            out.append(esc)
    return "\n".join(out)


def render_html(
    diffs: list[SrsDiff],
    *,
    execution_date: str,
    previous_date: str | None,
    current_date: str,
    pdf_sanity: list[dict[str, Any]],
) -> str:
    counts = _summary_counts(diffs)
    rows = []
    for d in diffs:
        if d.change_type == "unchanged":
            continue
        changes_html = ", ".join(html_lib.escape(c) for c in d.field_changes) or "-"
        diff_block = f'<div class="diff">{_diff_html(d.text_diff_lines)}</div>' if d.text_diff_lines else ""
        rows.append(
            f'<div class="srs"><h3><span class="badge {d.change_type}">{d.change_type}</span> '
            f'{html_lib.escape(d.id)} - {html_lib.escape(d.title or d.title_after or "")}</h3>'
            f"<p>Detected changes: {changes_html}</p>{diff_block}</div>"
        )

    sanity_rows = "".join(
        f"<tr><td>{html_lib.escape(p['file'])}</td><td>{html_lib.escape(p['status'])}</td>"
        f"<td>{html_lib.escape(p.get('detail', ''))}</td></tr>"
        for p in pdf_sanity
    )

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>SRS Change Report {execution_date}</title><style>{_HTML_CSS}</style></head>
<body>
<h1>SRS Change Report</h1>
<div class="summary">
<b>Execution Date:</b> {execution_date}<br/>
<b>Previous Snapshot:</b> {previous_date or '(none - first run)'}<br/>
<b>Current Snapshot:</b> {current_date}<br/><br/>
<b>Total SRS:</b> {len(diffs)} &nbsp;
<span class="badge new">New {counts['new']}</span>
<span class="badge deleted">Deleted {counts['deleted']}</span>
<span class="badge changed">Changed {counts['changed']}</span>
<span class="badge unchanged">Unchanged {counts['unchanged']}</span>
</div>
<h2>PDF Sanity Check</h2>
<table class="sanity"><tr><th>File</th><th>Status</th><th>Detail</th></tr>{sanity_rows}</table>
<h2>Changed / New / Deleted SRS</h2>
{''.join(rows) if rows else '<p>No changes detected.</p>'}
</body></html>"""


def save_reports(
    reports_dir: Path,
    date_str: str,
    diffs: list[SrsDiff],
    *,
    previous_date: str | None,
    current_date: str,
    pdf_sanity: list[dict[str, Any]],
) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    md_path = reports_dir / f"SRS_Change_Report_{date_str}.md"
    html_path = reports_dir / f"SRS_Change_Report_{date_str}.html"
    md_path.write_text(
        render_markdown(
            diffs, execution_date=date_str, previous_date=previous_date, current_date=current_date, pdf_sanity=pdf_sanity
        ),
        encoding="utf-8",
    )
    html_path.write_text(
        render_html(
            diffs, execution_date=date_str, previous_date=previous_date, current_date=current_date, pdf_sanity=pdf_sanity
        ),
        encoding="utf-8",
    )
    return md_path, html_path
