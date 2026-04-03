import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-account-detail',
  imports: [RouterLink],
  template: `
    <div class="hero">
      <a routerLink="/entities" class="back-link">&larr; Entity Tree</a>
      <h1><span>{{ entityName() }}</span> Accounts</h1>
      <p class="subtitle">{{ slug }} -- {{ accounts().length }} accounts across {{ currencyCount() }} currencies</p>
    </div>

    @if (loading()) {
      <div class="loading">Loading accounts...</div>
    } @else if (error()) {
      <div class="card"><p class="muted">{{ error() }}</p></div>
    } @else {
      <div class="grid-4" style="margin-bottom:1rem;">
        @for (curr of currencySummary(); track curr.code) {
          <div class="stat-card">
            <div class="num">{{ curr.net }}</div>
            <div class="label">{{ curr.code }} net</div>
          </div>
        }
      </div>

      <div class="card">
        <h2>All Accounts <span class="subtitle">{{ accounts().length }} total</span></h2>
        <table class="acct-table">
          <thead>
            <tr>
              <th>Account</th><th>Type</th><th>Currency</th><th>Balance</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            @for (acct of accounts(); track acct.id) {
              <tr>
                <td class="name-col">{{ acct.name }}</td>
                <td><span class="badge" [class]="'badge-' + typeColor(acct.type)">{{ acct.type }}</span></td>
                <td class="mono">{{ acct.currency }}</td>
                <td class="mono balance-col" [class]="balanceClass(acct)">{{ acct.balance }}</td>
                <td>
                  <span class="dot" [class]="acct.active ? 'dot-green' : 'dot-gray'"></span>
                  {{ acct.active ? 'Active' : 'Closed' }}
                </td>
                <td><a [routerLink]="['/ledger', acct.id]" class="link">Ledger &rarr;</a></td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    }
  `,
  styles: [`
    .hero h1 { font-size: 1.5rem; margin-bottom: .2rem; }
    .hero h1 span { color: var(--silver); }
    .subtitle { color: var(--muted); font-size: .85rem; margin-bottom: 1.25rem; }
    .muted { color: var(--muted); }
    .back-link { color: var(--silver-dim); font-size: .78rem; text-decoration: none; display: block; margin-bottom: .5rem; }
    .back-link:hover { color: var(--silver); }
    .mono { font-family: monospace; font-size: .82rem; }

    .acct-table { width: 100%; border-collapse: collapse; font-size: .82rem; }
    .acct-table th { text-align: left; color: var(--muted); font-weight: 500; font-size: .72rem;
                     text-transform: uppercase; letter-spacing: .04em; padding: .4rem .5rem;
                     border-bottom: 1px solid var(--border); }
    .acct-table td { padding: .5rem; border-bottom: 1px solid rgba(255,255,255,.04); }
    .name-col { font-weight: 500; }
    .balance-col { font-weight: 600; }
    .positive { color: var(--green); }
    .negative { color: var(--red); }
    .zero { color: var(--muted); }

    .dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; margin-right: .3rem; }
    .dot-green { background: var(--green); }
    .dot-gray { background: #555; }

    .link { color: var(--silver-dim); text-decoration: none; font-size: .75rem; }
    .link:hover { color: var(--silver); }

    .loading { color: var(--muted); font-style: italic; font-size: .82rem; padding: 1rem 0; text-align: center; }
  `],
})
export class AccountDetailComponent implements OnInit {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  slug = '';
  accounts = signal<any[]>([]);
  entityName = signal('');
  loading = signal(true);
  error = signal('');

  currencyCount = computed(() => new Set(this.accounts().map(a => a.currency)).size);
  currencySummary = computed(() => {
    const map = new Map<string, number>();
    for (const a of this.accounts()) {
      const bal = parseFloat(a.balance) || 0;
      map.set(a.currency, (map.get(a.currency) || 0) + (a.type === 'asset' ? bal : a.type === 'liability' ? -bal : 0));
    }
    return Array.from(map.entries()).map(([code, net]) => ({ code, net: net.toFixed(2) }));
  });

  ngOnInit() {
    this.slug = this.route.snapshot.paramMap.get('slug') || '';
    this.api.engineEntity(this.slug).subscribe({
      next: d => this.entityName.set(d.name || this.slug),
      error: () => {},
    });
    this.api.engineAccounts(this.slug).subscribe({
      next: d => {
        this.accounts.set(d.accounts || []);
        this.loading.set(false);
      },
      error: e => {
        this.error.set('Could not load accounts');
        this.loading.set(false);
      },
    });
  }

  typeColor(type: string) {
    return { asset: 'green', liability: 'red', income: 'blue', expense: 'yellow', equity: 'silver' }[type] || 'silver';
  }

  balanceClass(acct: any) {
    const b = parseFloat(acct.balance);
    if (b > 0) return 'positive';
    if (b < 0) return 'negative';
    return 'zero';
  }
}
