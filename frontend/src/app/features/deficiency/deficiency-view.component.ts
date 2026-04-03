import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-deficiency-view',
  template: `
    <div class="hero">
      <h1><span>Silver Shield</span> Deficiency Tracker</h1>
      <p class="subtitle">Rule 121 response items -- {{ total() }} tracked</p>
    </div>

    @if (loading()) {
      <div class="loading">Loading deficiency items...</div>
    } @else if (!available()) {
      <div class="card"><p class="muted">Deficiency tracker not configured. Check config.yaml.</p></div>
    } @else {
      <div class="grid-4" style="margin-bottom:1rem;">
        <div class="stat-card"><div class="num" style="color:var(--green)">{{ complete() }}</div><div class="label">Complete</div></div>
        <div class="stat-card"><div class="num" style="color:var(--yellow)">{{ partial() }}</div><div class="label">Partial</div></div>
        <div class="stat-card"><div class="num" style="color:var(--red)">{{ missing() }}</div><div class="label">Missing</div></div>
        <div class="stat-card"><div class="num">{{ overallPercent() }}%</div><div class="label">Overall</div></div>
      </div>

      <div class="progress-bar">
        <div class="progress-fill" [style.width.%]="overallPercent()"></div>
      </div>

      <div class="card">
        <h2>Items</h2>
        @for (item of items(); track item.id) {
          <div class="deficiency-row" [class]="'status-' + item.status">
            <div class="item-header">
              <span class="item-id mono">{{ item.id }}</span>
              <span class="item-name">{{ item.name }}</span>
              <span class="badge" [class]="statusBadge(item.status)">{{ item.status }}</span>
              <span class="pct mono">{{ item.percent }}%</span>
            </div>
            @if (item.description) {
              <div class="item-desc">{{ item.description }}</div>
            }
            <div class="item-progress">
              <div class="item-fill" [style.width.%]="item.percent"></div>
            </div>
          </div>
        }
      </div>
    }
  `,
  styles: [`
    .hero h1 { font-size: 1.5rem; margin-bottom: .2rem; }
    .hero h1 span { color: var(--silver); }
    .subtitle { color: var(--muted); font-size: .85rem; margin-bottom: 1.25rem; }
    .muted { color: var(--muted); }
    .mono { font-family: monospace; font-size: .82rem; }

    .progress-bar { height: 6px; background: var(--border); border-radius: 3px; margin-bottom: 1rem; overflow: hidden; }
    .progress-fill { height: 100%; background: linear-gradient(90deg, var(--green), var(--teal)); border-radius: 3px;
                     transition: width .3s; }

    .deficiency-row { padding: .6rem .8rem; border-radius: 8px; margin-bottom: .4rem;
                      border: 1px solid var(--border); }
    .status-complete { border-left: 3px solid var(--green); }
    .status-partial { border-left: 3px solid var(--yellow); }
    .status-missing { border-left: 3px solid var(--red); }
    .item-header { display: flex; align-items: center; gap: .6rem; }
    .item-id { color: var(--silver-dim); min-width: 3rem; }
    .item-name { font-weight: 500; font-size: .85rem; flex: 1; }
    .pct { color: var(--silver); }
    .item-desc { color: var(--muted); font-size: .75rem; margin: .3rem 0 .3rem 3.6rem; }
    .item-progress { height: 3px; background: var(--border); border-radius: 2px; margin-top: .4rem; }
    .item-fill { height: 100%; background: var(--silver-dim); border-radius: 2px; transition: width .3s; }

    .loading { color: var(--muted); font-style: italic; font-size: .82rem; padding: 1rem 0; text-align: center; }
  `],
})
export class DeficiencyViewComponent implements OnInit {
  private api = inject(ApiService);
  items = signal<any[]>([]);
  loading = signal(true);
  available = signal(false);

  complete = signal(0);
  partial = signal(0);
  missing = signal(0);
  total = computed(() => this.items().length);
  overallPercent = computed(() => {
    const items = this.items();
    if (!items.length) return 0;
    return Math.round(items.reduce((s: number, i: any) => s + (i.percent || 0), 0) / items.length);
  });

  ngOnInit() {
    this.api.deficiency().subscribe({
      next: d => {
        this.available.set(d.available);
        this.items.set(d.items || []);
        this.complete.set(d.complete || 0);
        this.partial.set(d.partial || 0);
        this.missing.set(d.missing || 0);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  statusBadge(status: string) {
    return { complete: 'badge-green', partial: 'badge-yellow', missing: 'badge-red' }[status] || 'badge-silver';
  }
}
