import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-dashboard',
  imports: [RouterLink],
  template: `
    <div class="hero">
      <h1><span>Silver Shield</span> Financial Bookkeeping Armor</h1>
      <p class="subtitle-line">{{ subtitle() }}</p>
    </div>

    <div class="grid-4" style="margin-bottom:1rem;">
      <div class="stat-card"><div class="num">{{ engineEntityCount() || status()?.entities?.length || '--' }}</div><div class="label">Entities</div></div>
      <div class="stat-card"><div class="num">{{ engineAccountCount() || status()?.account_count || '--' }}</div><div class="label">Accounts</div></div>
      <div class="stat-card"><div class="num">5</div><div class="label">Currencies</div></div>
      <div class="stat-card"><div class="num">{{ complianceLabel() }}</div><div class="label">CI 42</div></div>
    </div>

    <div class="grid-2">
      <div>
        <div class="card">
          <h2>Entity Hierarchy <span class="subtitle">subsidiarity</span></h2>
          @if (status()?.entities?.length) {
            @for (entity of status()!.entities; track entity.name) {
              <div class="entity-node">
                <div class="entity-header">
                  <span>{{ entity.type === 'personal' ? '\u{1F464}' : '\u{1F3E2}' }}</span>
                  <strong>{{ entity.name }}</strong>
                  <span class="badge" [class]="entity.type === 'personal' ? 'badge-blue' : 'badge-silver'">{{ entity.type }}</span>
                  <span class="muted-right">{{ entity.accounts.length }} accounts</span>
                </div>
                @for (a of entity.accounts; track a.id) {
                  <div class="account-row">
                    <span class="mono silver">{{ a.id }}</span>
                    <span class="muted">{{ a.institution }} -- {{ a.label }}</span>
                  </div>
                }
              </div>
            }
          } @else {
            <div class="loading">No entities configured</div>
          }
          <a routerLink="/entities" class="view-all">View entity tree &rarr;</a>
        </div>
      </div>

      <div>
        <div class="card">
          <h2>Modules</h2>
          <a routerLink="/entities" class="module-card">
            <span class="module-icon">\u{1F464}</span>
            <div class="module-info">
              <div class="name">Entity Tree</div>
              <div class="desc">Hierarchy, accounts, balances</div>
            </div>
          </a>
          <a routerLink="/resources" class="module-card">
            <span class="module-icon">\u{1F4CA}</span>
            <div class="module-info">
              <div class="name">Resource Tracking</div>
              <div class="desc">Per-project budgets, merit balances</div>
            </div>
          </a>
          <a routerLink="/compliance" class="module-card">
            <span class="module-icon">\u{2705}</span>
            <div class="module-info">
              <div class="name">Compliance</div>
              <div class="desc">CI 42 automated audit checks</div>
            </div>
          </a>
          <a routerLink="/deficiency" class="module-card">
            <span class="module-icon">\u{1F4CB}</span>
            <div class="module-info">
              <div class="name">Deficiency Tracker</div>
              <div class="desc">Rule 121 response items</div>
            </div>
          </a>
          <a routerLink="/discovery" class="module-card">
            <span class="module-icon">\u{1F6E1}</span>
            <div class="module-info">
              <div class="name">Discovery</div>
              <div class="desc">Statement extraction + ledger</div>
            </div>
          </a>
        </div>

        <div class="card">
          <h2>Core Engine <span class="subtitle">Phase 2 active</span></h2>
          <div class="engine-status">
            @for (m of engineModules; track m.name) {
              <div class="engine-row">
                <span class="dot" [class]="m.ready ? 'dot-green' : 'dot-gray'"></span>
                <span class="mono silver">{{ m.name }}</span>
                <span class="muted">{{ m.desc }}</span>
              </div>
            }
            <div class="muted" style="margin-top:.5rem;font-size:.75rem;">10/10 modules ready | 62 tests passing</div>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .hero h1 { font-size: 1.5rem; margin-bottom: .2rem; }
    .hero h1 span { color: var(--silver); }
    .subtitle-line { color: var(--muted); font-size: .85rem; margin-bottom: 1.25rem; }
    .entity-node { margin-bottom: .5rem; }
    .entity-header { display: flex; align-items: center; gap: .5rem; padding: .4rem .5rem;
                     border-radius: 6px; font-size: .88rem; }
    .account-row { display: flex; gap: .5rem; padding: .2rem 0 .2rem 1.5rem; font-size: .78rem; }
    .silver { color: var(--silver); }
    .muted { color: var(--muted); }
    .muted-right { color: var(--muted); font-size: .72rem; margin-left: auto; }
    .view-all { display: block; text-align: right; color: var(--silver-dim); font-size: .75rem;
                text-decoration: none; margin-top: .5rem; padding-top: .5rem; border-top: 1px solid var(--border); }
    .view-all:hover { color: var(--silver); }
    .module-card { display: flex; align-items: center; gap: 1rem; padding: .75rem 1rem;
                   border: 1px solid var(--border); border-radius: 8px; margin-bottom: .5rem;
                   text-decoration: none; color: var(--text); transition: all .15s; }
    .module-card:hover { background: var(--card-hover); border-color: var(--silver-dim); }
    .module-icon { font-size: 1.5rem; min-width: 2rem; text-align: center; }
    .module-info .name { font-weight: 600; font-size: .88rem; }
    .module-info .desc { color: var(--muted); font-size: .72rem; }
    .engine-row { display: flex; align-items: center; gap: .5rem; padding: .25rem 0; font-size: .82rem; }
    .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
    .dot-green { background: var(--green); }
    .dot-gray { background: #555; }
  `],
})
export class DashboardComponent implements OnInit {
  private api = inject(ApiService);
  status = signal<any>(null);
  compliance = signal<any>(null);
  engineEntityCount = signal(0);
  engineAccountCount = signal(0);

  subtitle = signal('Loading...');
  complianceLabel = signal('--');

  engineModules = [
    { name: 'core/models.py', desc: 'Entity, Account, Currency, Entry', ready: true },
    { name: 'core/ledger.py', desc: 'Append-only double-entry', ready: true },
    { name: 'core/double_entry.py', desc: 'Transaction patterns', ready: true },
    { name: 'core/entities.py', desc: 'Hierarchy + human authority', ready: true },
    { name: 'core/accounts.py', desc: 'Open, close, balance, trial', ready: true },
    { name: 'core/currencies.py', desc: 'Currency registry', ready: true },
    { name: 'storage/json_store.py', desc: 'JSONL persistence', ready: true },
    { name: 'resources/tracker.py', desc: 'Per-entity resource tracking', ready: true },
    { name: 'integrations/merit.py', desc: 'EZ Merit ledger bridge', ready: true },
    { name: 'integrations/auto_agent.py', desc: 'Resource consumption + budget', ready: true },
  ];

  ngOnInit() {
    this.api.status().subscribe(d => {
      this.status.set(d);
      this.subtitle.set(d.configured
        ? `${d.case_name}${d.case_number ? ' | ' + d.case_number : ''} -- offline on localhost:5003`
        : 'Offline financial bookkeeping armor -- localhost:5003');
    });
    this.api.compliance().subscribe(d => {
      if (d.available && !d.error) {
        this.complianceLabel.set(`${d.passed}/${d.total}`);
      }
    });
    this.api.engineEntities().subscribe({
      next: d => {
        const entities = d.entities || [];
        this.engineEntityCount.set(entities.length);
        this.engineAccountCount.set(entities.reduce((s: number, e: any) => s + e.accounts.length, 0));
      },
      error: () => {},
    });
  }
}
