import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-compliance-view',
  template: `
    <div class="hero">
      <h1><span>Silver Shield</span> Compliance</h1>
      <p class="subtitle">CI 42 Series -- automated audit checks</p>
    </div>

    @if (loading()) {
      <div class="loading">Running compliance checks...</div>
    } @else if (error()) {
      <div class="card"><p class="muted">{{ error() }}</p></div>
    } @else {
      <div class="grid-4" style="margin-bottom:1rem;">
        <div class="stat-card"><div class="num" style="color:var(--green)">{{ passed() }}</div><div class="label">Passed</div></div>
        <div class="stat-card"><div class="num" style="color:var(--red)">{{ failed() }}</div><div class="label">Failed</div></div>
        <div class="stat-card"><div class="num">{{ total() }}</div><div class="label">Total Checks</div></div>
        <div class="stat-card"><div class="num" [style.color]="passRate() === 100 ? 'var(--green)' : 'var(--yellow)'">{{ passRate() }}%</div><div class="label">Pass Rate</div></div>
      </div>

      <div class="card">
        <h2>Check Results</h2>
        @for (r of results(); track r.check_id) {
          <div class="check-row" [class]="r.passed ? 'check-pass' : 'check-fail'">
            <div class="check-header">
              <span class="check-icon">{{ r.passed ? '\u2705' : '\u274C' }}</span>
              <span class="check-id mono">{{ r.check_id }}</span>
              <span class="check-name">{{ r.name }}</span>
              <span class="badge" [class]="severityBadge(r.severity)">{{ r.severity }}</span>
            </div>
            @if (r.details) {
              <div class="check-details">{{ r.details }}</div>
            }
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

    .check-row { padding: .6rem .8rem; border-radius: 8px; margin-bottom: .4rem;
                 border: 1px solid var(--border); }
    .check-pass { border-left: 3px solid var(--green); }
    .check-fail { border-left: 3px solid var(--red); background: rgba(239,68,68,.05); }
    .check-header { display: flex; align-items: center; gap: .6rem; }
    .check-icon { font-size: 1rem; }
    .check-id { color: var(--silver-dim); }
    .check-name { font-weight: 500; font-size: .85rem; flex: 1; }
    .check-details { color: var(--muted); font-size: .75rem; margin-top: .3rem; padding-left: 1.6rem; }

    .loading { color: var(--muted); font-style: italic; font-size: .82rem; padding: 1rem 0; text-align: center; }
  `],
})
export class ComplianceViewComponent implements OnInit {
  private api = inject(ApiService);
  results = signal<any[]>([]);
  loading = signal(true);
  error = signal('');

  passed = computed(() => this.results().filter(r => r.passed).length);
  failed = computed(() => this.results().filter(r => !r.passed).length);
  total = computed(() => this.results().length);
  passRate = computed(() => this.total() ? Math.round(this.passed() / this.total() * 100) : 0);

  ngOnInit() {
    this.api.compliance().subscribe({
      next: d => {
        if (d.available && !d.error) {
          this.results.set(d.results || []);
        } else {
          this.error.set(d.error || 'Compliance checks not available');
        }
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Failed to reach dashboard API');
        this.loading.set(false);
      },
    });
  }

  severityBadge(severity: string) {
    return { critical: 'badge-red', high: 'badge-yellow', medium: 'badge-silver', low: 'badge-blue' }[severity] || 'badge-silver';
  }
}
