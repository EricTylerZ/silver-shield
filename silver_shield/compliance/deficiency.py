"""
Deficiency response tracker.

Tracks completion status of deficiency letter items
and generates an HTML dashboard for visual reporting.
"""

from dataclasses import dataclass
from typing import Optional

from ..config import Config, DeficiencyItem


@dataclass
class ItemStatus:
    """Status of a single deficiency item."""
    item: DeficiencyItem
    status: str = "missing"  # complete, partial, missing
    percent: int = 0
    notes: str = ""
    subitems: list[dict] = None

    def __post_init__(self):
        if self.subitems is None:
            self.subitems = []


class DeficiencyTracker:
    """Tracks and reports on deficiency letter compliance."""

    def __init__(self, config: Config):
        self.config = config
        self.items: list[ItemStatus] = [
            ItemStatus(item=item) for item in config.deficiency_items
        ]

    def update_item(self, item_id: int, status: str, percent: int = 0,
                    notes: str = "", subitems: Optional[list[dict]] = None):
        """Update status of a deficiency item."""
        for item_status in self.items:
            if item_status.item.id == item_id:
                item_status.status = status
                item_status.percent = percent
                item_status.notes = notes
                if subitems:
                    item_status.subitems = subitems
                return

    @property
    def overall_percent(self) -> int:
        if not self.items:
            return 0
        return sum(i.percent for i in self.items) // len(self.items)

    @property
    def complete_count(self) -> int:
        return sum(1 for i in self.items if i.status == "complete")

    @property
    def partial_count(self) -> int:
        return sum(1 for i in self.items if i.status == "partial")

    @property
    def missing_count(self) -> int:
        return sum(1 for i in self.items if i.status == "missing")

    def generate_html(self) -> str:
        """Generate the HTML deficiency tracker dashboard."""
        total = len(self.items)
        complete = self.complete_count
        partial = self.partial_count
        missing = self.missing_count
        pct = self.overall_percent

        items_html = ""
        for i_status in self.items:
            item = i_status.item
            status_class = {
                "complete": "badge-green",
                "partial": "badge-yellow",
                "missing": "badge-red",
            }.get(i_status.status, "badge-red")
            status_label = i_status.status.upper()
            indicator_class = {
                "complete": "status-complete",
                "partial": "status-partial",
                "missing": "status-missing",
            }.get(i_status.status, "status-missing")

            subitems_html = ""
            for sub in i_status.subitems:
                sub_status = sub.get("status", "missing")
                sub_badge = {"complete": "badge-green", "partial": "badge-yellow"}.get(sub_status, "badge-red")
                subitems_html += f"""
                <div class="subitem">
                  <div class="subitem-header">
                    <span class="subitem-title">{sub.get('name', '')}</span>
                    <span class="badge {sub_badge}">{sub_status.upper()}</span>
                  </div>
                  <div class="subitem-detail">{sub.get('notes', '')}</div>
                </div>"""

            notes_html = f'<div class="notes-box">{i_status.notes}</div>' if i_status.notes else ""

            items_html += f"""
            <div class="section">
              <div class="section-header" onclick="this.parentElement.classList.toggle('open')">
                <h2><span class="status-indicator {indicator_class}"></span>
                    Item {item.id}: {item.name}</h2>
                <div>
                  <span class="badge {status_class}">{status_label}</span>
                  <span class="section-meta">{i_status.percent}%</span>
                  <span class="chevron">&#9660;</span>
                </div>
              </div>
              <div class="section-body">
                <p class="subitem-detail">{item.description}</p>
                {subitems_html}
                {notes_html}
              </div>
            </div>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{self.config.case_name} - Deficiency Response Tracker</title>
<style>
  :root {{
    --green: #22c55e; --yellow: #eab308; --red: #ef4444; --blue: #3b82f6;
    --bg: #0f172a; --card: #1e293b; --border: #334155; --text: #e2e8f0; --muted: #94a3b8;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
         background: var(--bg); color: var(--text); padding: 20px; line-height: 1.5; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 4px; }}
  .subtitle {{ color: var(--muted); margin-bottom: 28px; font-size: 0.95rem; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                   gap: 12px; margin-bottom: 32px; }}
  .summary-card {{ background: var(--card); border-radius: 10px; padding: 16px;
                   border: 1px solid var(--border); text-align: center; }}
  .summary-card .num {{ font-size: 2.2rem; font-weight: 700; }}
  .summary-card .label {{ font-size: 0.75rem; color: var(--muted);
                          text-transform: uppercase; letter-spacing: 0.05em; margin-top: 4px; }}
  .green {{ color: var(--green); }} .yellow {{ color: var(--yellow); }}
  .red {{ color: var(--red); }} .blue {{ color: var(--blue); }}
  .progress-bar {{ width: 100%; height: 8px; background: rgba(255,255,255,0.08);
                   border-radius: 4px; overflow: hidden; margin-top: 10px; }}
  .progress-fill {{ height: 100%; border-radius: 4px; background: var(--green); }}
  .section {{ background: var(--card); border-radius: 10px; border: 1px solid var(--border);
              margin-bottom: 14px; overflow: hidden; }}
  .section-header {{ padding: 16px 20px; cursor: pointer; display: flex;
                     justify-content: space-between; align-items: center; }}
  .section-header:hover {{ background: rgba(255,255,255,0.03); }}
  .section-header h2 {{ font-size: 1.05rem; display: flex; align-items: center; gap: 12px; }}
  .section-meta {{ font-size: 0.8rem; color: var(--muted); margin: 0 8px; }}
  .section-body {{ padding: 0 20px 16px; display: none; }}
  .section.open .section-body {{ display: block; }}
  .section.open .chevron {{ transform: rotate(180deg); }}
  .chevron {{ transition: transform 0.2s; font-size: 1rem; color: var(--muted); }}
  .badge {{ display: inline-block; padding: 3px 11px; border-radius: 999px;
            font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }}
  .badge-green {{ background: rgba(34,197,94,0.15); color: var(--green); }}
  .badge-yellow {{ background: rgba(234,179,8,0.15); color: var(--yellow); }}
  .badge-red {{ background: rgba(239,68,68,0.15); color: var(--red); }}
  .subitem {{ margin-bottom: 14px; }}
  .subitem-header {{ display: flex; gap: 12px; align-items: flex-start; margin-bottom: 8px; }}
  .subitem-title {{ flex: 1; font-weight: 500; }}
  .subitem-detail {{ color: var(--muted); font-size: 0.85rem; line-height: 1.4; margin-bottom: 6px; }}
  .status-indicator {{ width: 12px; height: 12px; border-radius: 50%; display: inline-block;
                       margin-right: 6px; vertical-align: middle; }}
  .status-complete {{ background: var(--green); }}
  .status-partial {{ background: var(--yellow); }}
  .status-missing {{ background: var(--red); }}
  .notes-box {{ background: rgba(255,255,255,0.04); border-left: 3px solid var(--muted);
                padding: 12px 14px; border-radius: 4px; margin-top: 12px;
                font-size: 0.85rem; color: var(--muted); }}
</style>
</head>
<body>
<div class="container">
  <h1>Deficiency Response Tracker</h1>
  <div class="subtitle">{self.config.case_name} | Case No. {self.config.case_number}</div>

  <div class="summary-grid">
    <div class="summary-card">
      <div class="num blue">{total}</div>
      <div class="label">Total Items</div>
    </div>
    <div class="summary-card">
      <div class="num green">{complete}</div>
      <div class="label">Complete</div>
    </div>
    <div class="summary-card">
      <div class="num yellow">{partial}</div>
      <div class="label">Partial</div>
    </div>
    <div class="summary-card">
      <div class="num red">{missing}</div>
      <div class="label">Missing</div>
    </div>
    <div class="summary-card">
      <div class="num blue">{pct}%</div>
      <div class="label">Overall</div>
      <div class="progress-bar"><div class="progress-fill" style="width:{pct}%"></div></div>
    </div>
  </div>

  {items_html}

  <div style="text-align:center; color:var(--muted); font-size:0.8rem; margin-top:32px;">
    Generated by Silver Shield | {self.config.case_name}
  </div>
</div>
</body>
</html>"""
        return html

    def save_html(self, path: Optional[str] = None) -> str:
        """Save tracker HTML to file."""
        output = path or str(self.config.tracker_path)
        html = self.generate_html()
        with open(output, 'w') as f:
            f.write(html)
        return output
