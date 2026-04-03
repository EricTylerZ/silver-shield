import { Component } from '@angular/core';

@Component({
  selector: 'app-discovery',
  template: `
    <div class="hero">
      <h1><span>Silver Shield</span> Discovery</h1>
      <p class="subtitle">Rule 121 deficiency response -- statement extraction, categorization, ledger building, compliance tracking</p>
    </div>
    <div class="card">
      <h2>Discovery Module</h2>
      <p class="muted">
        The full discovery dashboard is available at
        <a href="http://localhost:5003/discovery" style="color:var(--silver);">localhost:5003/discovery</a>
        (Flask view) while the Angular port is in progress.
      </p>
    </div>
  `,
  styles: [`
    .hero h1 { font-size: 1.5rem; margin-bottom: .2rem; }
    .hero h1 span { color: var(--silver); }
    .subtitle { color: var(--muted); font-size: .85rem; margin-bottom: 1.25rem; }
    .muted { color: var(--muted); font-size: .85rem; line-height: 1.5; }
  `],
})
export class DiscoveryComponent {}
