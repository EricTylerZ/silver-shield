import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-resources-view',
  imports: [RouterLink],
  template: `
    <div class="hero">
      <h1><span>Silver Shield</span> Resource Tracking</h1>
      <p class="subtitle">Per-entity budgets, merit balances, and spending</p>
    </div>

    @if (loading()) {
      <div class="loading">Loading resource data...</div>
    } @else {
      <div class="grid-2">
        <div class="card">
          <h2>Merit Costs <span class="subtitle">CI 40-703.7</span></h2>
          @if (costs()) {
            <table class="cost-table">
              <thead><tr><th>Action</th><th>Cost (MP)</th></tr></thead>
              <tbody>
                @for (entry of costEntries(); track entry.action) {
                  <tr>
                    <td>{{ formatAction(entry.action) }}</td>
                    <td class="mono">{{ entry.cost }}</td>
                  </tr>
                }
              </tbody>
            </table>
          }
        </div>

        <div class="card">
          <h2>Currencies <span class="subtitle">registered</span></h2>
          @for (c of currencies(); track c.code) {
            <div class="currency-row">
              <span class="mono currency-code">{{ c.code }}</span>
              <span class="currency-name">{{ c.name }}</span>
              <span class="mono currency-sym">{{ c.symbol }}</span>
              @if (!c.convertible) {
                <span class="badge badge-silver">non-convertible</span>
              }
            </div>
          }
        </div>
      </div>

      <div class="card">
        <h2>Entity Balances</h2>
        @if (entities().length === 0) {
          <p class="muted">No entities with accounts. <a routerLink="/entities" class="link">Create entities first.</a></p>
        } @else {
          <table class="balance-table">
            <thead>
              <tr><th>Entity</th><th>Type</th><th>Accounts</th><th>Balances</th></tr>
            </thead>
            <tbody>
              @for (e of entities(); track e.id) {
                <tr>
                  <td><a [routerLink]="['/accounts', e.slug]" class="entity-link">{{ e.name }}</a></td>
                  <td><span class="badge" [class]="'badge-' + typeColor(e.type)">{{ e.type }}</span></td>
                  <td class="mono">{{ e.accounts.length }}</td>
                  <td>
                    @for (acct of e.accounts; track acct.id) {
                      @if (acct.type === 'asset' && acct.balance !== '0') {
                        <span class="balance-chip">{{ acct.balance }} {{ acct.currency }}</span>
                      }
                    }
                    @if (!hasAssets(e)) {
                      <span class="muted">--</span>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        }
      </div>
    }
  `,
  styles: [`
    .hero h1 { font-size: 1.5rem; margin-bottom: .2rem; }
    .hero h1 span { color: var(--silver); }
    .subtitle { color: var(--muted); font-size: .85rem; margin-bottom: 1.25rem; }
    .muted { color: var(--muted); font-size: .82rem; }
    .mono { font-family: monospace; font-size: .82rem; }
    .link { color: var(--silver); text-decoration: none; }
    .link:hover { text-decoration: underline; }

    .cost-table, .balance-table { width: 100%; border-collapse: collapse; font-size: .82rem; }
    .cost-table th, .balance-table th { text-align: left; color: var(--muted); font-weight: 500;
                     font-size: .72rem; text-transform: uppercase; letter-spacing: .04em;
                     padding: .4rem .5rem; border-bottom: 1px solid var(--border); }
    .cost-table td, .balance-table td { padding: .5rem; border-bottom: 1px solid rgba(255,255,255,.04); }

    .currency-row { display: flex; align-items: center; gap: .75rem; padding: .35rem 0;
                    border-bottom: 1px solid rgba(255,255,255,.04); font-size: .82rem; }
    .currency-code { color: var(--silver); font-weight: 600; min-width: 3.5rem; }
    .currency-name { flex: 1; }
    .currency-sym { color: var(--muted); }

    .entity-link { color: var(--silver-bright); text-decoration: none; font-weight: 500; }
    .entity-link:hover { text-decoration: underline; }

    .balance-chip { display: inline-block; padding: .15rem .4rem; margin: .1rem .2rem;
                    background: rgba(34,197,94,.1); border: 1px solid rgba(34,197,94,.2);
                    border-radius: 4px; font-family: monospace; font-size: .75rem; color: var(--green); }

    .loading { color: var(--muted); font-style: italic; font-size: .82rem; padding: 1rem 0; text-align: center; }
  `],
})
export class ResourcesViewComponent implements OnInit {
  private api = inject(ApiService);
  entities = signal<any[]>([]);
  currencies = signal<any[]>([]);
  costs = signal<any>(null);
  loading = signal(true);

  costEntries = computed(() => {
    const c = this.costs();
    return c ? Object.entries(c).map(([action, cost]) => ({ action, cost })) : [];
  });

  ngOnInit() {
    this.api.engineEntities().subscribe({
      next: d => {
        this.entities.set(d.entities || []);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
    this.api.engineCurrencies().subscribe({
      next: d => this.currencies.set(d.currencies || []),
    });
    this.api.meritCosts().subscribe({
      next: d => this.costs.set(d),
    });
  }

  typeColor(type: string) {
    return { person: 'blue', business: 'silver', project: 'green', agent: 'yellow' }[type] || 'silver';
  }

  formatAction(action: string) {
    return action.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  hasAssets(entity: any) {
    return entity.accounts.some((a: any) => a.type === 'asset' && a.balance !== '0');
  }
}
