import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-ledger-browser',
  imports: [RouterLink],
  template: `
    <div class="hero">
      <a routerLink="/entities" class="back-link">&larr; Entity Tree</a>
      <h1><span>Silver Shield</span> Ledger</h1>
      <p class="subtitle">Account {{ accountId.slice(0, 8) }}... -- {{ entries().length }} entries (append-only)</p>
    </div>

    @if (loading()) {
      <div class="loading">Loading ledger entries...</div>
    } @else if (entries().length === 0) {
      <div class="card"><p class="muted">No entries recorded for this account yet.</p></div>
    } @else {
      <div class="card">
        <h2>Entries <span class="subtitle">most recent first</span></h2>
        <table class="ledger-table">
          <thead>
            <tr>
              <th>Date</th><th>Description</th><th>Type</th><th>Amount</th><th>Balance</th><th>Source</th>
            </tr>
          </thead>
          <tbody>
            @for (e of entries(); track e.id) {
              <tr>
                <td class="mono date-col">{{ e.entry_date }}</td>
                <td class="desc-col">{{ e.description }}</td>
                <td>
                  <span class="badge" [class]="e.entry_type === 'debit' ? 'badge-green' : 'badge-red'">
                    {{ e.entry_type }}
                  </span>
                </td>
                <td class="mono amount-col">{{ e.amount }}</td>
                <td class="mono balance-col">{{ e.balance_after }}</td>
                <td class="source-col">{{ e.source_system || '--' }}</td>
              </tr>
            }
          </tbody>
        </table>
      </div>

      @if (entries().length >= limit) {
        <div style="text-align:center;margin-top:.5rem;">
          <button class="btn" (click)="loadMore()">Load more</button>
        </div>
      }
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

    .ledger-table { width: 100%; border-collapse: collapse; font-size: .82rem; }
    .ledger-table th { text-align: left; color: var(--muted); font-weight: 500; font-size: .72rem;
                       text-transform: uppercase; letter-spacing: .04em; padding: .4rem .5rem;
                       border-bottom: 1px solid var(--border); }
    .ledger-table td { padding: .5rem; border-bottom: 1px solid rgba(255,255,255,.04); }
    .date-col { white-space: nowrap; color: var(--silver-dim); }
    .desc-col { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .amount-col { font-weight: 600; color: var(--silver); }
    .balance-col { color: var(--text); }
    .source-col { color: var(--muted); font-size: .72rem; }

    .btn { padding: .4rem .8rem; border: 1px solid var(--silver-dim); border-radius: 6px;
           background: transparent; color: var(--silver); cursor: pointer; font-size: .78rem; }
    .btn:hover { background: rgba(192,192,192,.1); }

    .loading { color: var(--muted); font-style: italic; font-size: .82rem; padding: 1rem 0; text-align: center; }
  `],
})
export class LedgerBrowserComponent implements OnInit {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  accountId = '';
  entries = signal<any[]>([]);
  loading = signal(true);
  limit = 50;

  ngOnInit() {
    this.accountId = this.route.snapshot.paramMap.get('accountId') || '';
    this.load();
  }

  load() {
    this.api.engineLedger(this.accountId, this.limit).subscribe({
      next: d => {
        this.entries.set(d.entries || []);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  loadMore() {
    this.limit += 50;
    this.load();
  }
}
