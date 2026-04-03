import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/services/api.service';

@Component({
  selector: 'app-entity-tree',
  imports: [RouterLink],
  template: `
    <div class="hero">
      <h1><span>Silver Shield</span> Entity Hierarchy</h1>
      <p class="subtitle">Subsidiarity -- every chain terminates at a human</p>
    </div>

    <div class="grid-4" style="margin-bottom:1rem;">
      <div class="stat-card"><div class="num">{{ totalEntities() }}</div><div class="label">Entities</div></div>
      <div class="stat-card"><div class="num">{{ totalAccounts() }}</div><div class="label">Accounts</div></div>
      <div class="stat-card"><div class="num">{{ entityTypes().person }}</div><div class="label">Persons</div></div>
      <div class="stat-card"><div class="num">{{ entityTypes().project + entityTypes().agent }}</div><div class="label">Projects + Agents</div></div>
    </div>

    @if (loading()) {
      <div class="loading">Loading entity hierarchy...</div>
    } @else if (rootEntities().length === 0) {
      <div class="card">
        <h2>No Entities Yet</h2>
        <p class="muted">The accounting engine has no entities registered. Create a root person to begin.</p>
        <button class="btn" (click)="showCreateForm.set(!showCreateForm())">Create Root Person</button>
        @if (showCreateForm()) {
          <div class="create-form">
            <input #nameInput placeholder="Name (e.g. Eric)" class="input" />
            <input #slugInput placeholder="Slug (e.g. eric)" class="input" />
            <button class="btn btn-green" (click)="createRoot(nameInput.value, slugInput.value)">Create</button>
          </div>
        }
      </div>
    } @else {
      <div class="tree">
        @for (root of rootEntities(); track root.id) {
          <div class="entity-card root-card">
            <div class="entity-header">
              <span class="type-icon">{{ typeIcon(root.type) }}</span>
              <div class="entity-title">
                <a [routerLink]="['/accounts', root.slug]" class="entity-name">{{ root.name }}</a>
                <span class="badge" [class]="'badge-' + typeColor(root.type)">{{ root.type }}</span>
                <span class="muted acct-count">{{ root.accounts.length }} accounts</span>
              </div>
              <button class="btn-sm" (click)="toggleExpand(root.id)">
                {{ expanded().has(root.id) ? 'Collapse' : 'Expand' }}
              </button>
            </div>

            @if (expanded().has(root.id)) {
              @if (root.accounts.length > 0) {
                <div class="account-grid">
                  @for (acct of root.accounts; track acct.id) {
                    <div class="account-chip" [class]="'chip-' + acct.type">
                      <span class="acct-name">{{ acct.name }}</span>
                      <span class="acct-balance">{{ acct.balance }} {{ acct.currency }}</span>
                    </div>
                  }
                </div>
              }

              @for (child of childrenOf(root.id); track child.id) {
                <div class="entity-card child-card" style="margin-left:1.5rem;">
                  <div class="entity-header">
                    <span class="type-icon">{{ typeIcon(child.type) }}</span>
                    <div class="entity-title">
                      <a [routerLink]="['/accounts', child.slug]" class="entity-name">{{ child.name }}</a>
                      <span class="badge" [class]="'badge-' + typeColor(child.type)">{{ child.type }}</span>
                      <span class="muted acct-count">{{ child.accounts.length }} accounts</span>
                    </div>
                  </div>

                  @if (child.accounts.length > 0) {
                    <div class="account-grid">
                      @for (acct of child.accounts; track acct.id) {
                        <div class="account-chip" [class]="'chip-' + acct.type">
                          <span class="acct-name">{{ acct.name }}</span>
                          <span class="acct-balance">{{ acct.balance }} {{ acct.currency }}</span>
                        </div>
                      }
                    </div>
                  }

                  @for (grandchild of childrenOf(child.id); track grandchild.id) {
                    <div class="entity-card grandchild-card" style="margin-left:1.5rem;">
                      <div class="entity-header">
                        <span class="type-icon">{{ typeIcon(grandchild.type) }}</span>
                        <div class="entity-title">
                          <a [routerLink]="['/accounts', grandchild.slug]" class="entity-name">{{ grandchild.name }}</a>
                          <span class="badge" [class]="'badge-' + typeColor(grandchild.type)">{{ grandchild.type }}</span>
                        </div>
                      </div>
                    </div>
                  }
                </div>
              }
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

    .tree { display: flex; flex-direction: column; gap: .75rem; }

    .entity-card { background: var(--card); border: 1px solid var(--border);
                   border-radius: 10px; padding: 1rem; }
    .root-card { border-left: 3px solid var(--blue); }
    .child-card { border-left: 3px solid var(--silver-dim); margin-top: .5rem; }
    .grandchild-card { border-left: 3px solid var(--teal); margin-top: .5rem; }

    .entity-header { display: flex; align-items: center; gap: .75rem; }
    .type-icon { font-size: 1.3rem; min-width: 1.5rem; text-align: center; }
    .entity-title { display: flex; align-items: center; gap: .5rem; flex: 1; }
    .entity-name { color: var(--silver-bright); text-decoration: none; font-weight: 600; font-size: .9rem; }
    .entity-name:hover { text-decoration: underline; }
    .acct-count { font-size: .72rem; }

    .account-grid { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .6rem; padding-left: 2.25rem; }
    .account-chip { display: flex; justify-content: space-between; gap: .5rem;
                    padding: .3rem .6rem; border-radius: 6px; font-size: .75rem;
                    background: rgba(255,255,255,.04); border: 1px solid var(--border); min-width: 180px; }
    .chip-asset { border-left: 2px solid var(--green); }
    .chip-liability { border-left: 2px solid var(--red); }
    .chip-income { border-left: 2px solid var(--blue); }
    .chip-expense { border-left: 2px solid var(--yellow); }
    .chip-equity { border-left: 2px solid var(--silver); }
    .acct-name { color: var(--text); }
    .acct-balance { color: var(--silver); font-family: monospace; }

    .btn { padding: .5rem 1rem; border: 1px solid var(--silver-dim); border-radius: 6px;
           background: transparent; color: var(--silver); cursor: pointer; font-size: .82rem; }
    .btn:hover { background: rgba(192,192,192,.1); }
    .btn-green { border-color: var(--green); color: var(--green); }
    .btn-sm { padding: .25rem .6rem; border: 1px solid var(--border); border-radius: 4px;
              background: transparent; color: var(--muted); cursor: pointer; font-size: .72rem; }
    .btn-sm:hover { color: var(--text); border-color: var(--silver-dim); }

    .create-form { display: flex; gap: .5rem; margin-top: .75rem; align-items: center; }
    .input { padding: .4rem .6rem; background: var(--bg); border: 1px solid var(--border);
             border-radius: 6px; color: var(--text); font-size: .82rem; }

    .loading { color: var(--muted); font-style: italic; font-size: .82rem; padding: 1rem 0; text-align: center; }
  `],
})
export class EntityTreeComponent implements OnInit {
  private api = inject(ApiService);
  entities = signal<any[]>([]);
  loading = signal(true);
  expanded = signal(new Set<string>());
  showCreateForm = signal(false);

  totalEntities = computed(() => this.entities().length);
  totalAccounts = computed(() => this.entities().reduce((s: number, e: any) => s + e.accounts.length, 0));
  entityTypes = computed(() => {
    const types = { person: 0, business: 0, project: 0, agent: 0 };
    for (const e of this.entities()) (types as any)[e.type] = ((types as any)[e.type] || 0) + 1;
    return types;
  });

  rootEntities = computed(() => this.entities().filter(e => !e.parent_id));

  ngOnInit() {
    this.api.engineEntities().subscribe({
      next: d => {
        this.entities.set(d.entities || []);
        this.loading.set(false);
        // Auto-expand roots
        const exp = new Set<string>();
        for (const e of this.rootEntities()) exp.add(e.id);
        this.expanded.set(exp);
      },
      error: () => this.loading.set(false),
    });
  }

  childrenOf(parentId: string) {
    return this.entities().filter(e => e.parent_id === parentId);
  }

  toggleExpand(id: string) {
    const next = new Set(this.expanded());
    if (next.has(id)) next.delete(id); else next.add(id);
    this.expanded.set(next);
  }

  typeIcon(type: string) {
    return { person: '\u{1F464}', business: '\u{1F3E2}', project: '\u{1F6E1}', agent: '\u{1F916}' }[type] || '\u{2753}';
  }

  typeColor(type: string) {
    return { person: 'blue', business: 'silver', project: 'green', agent: 'yellow' }[type] || 'silver';
  }

  createRoot(name: string, slug: string) {
    if (!name || !slug) return;
    this.api.createEntity({ name, slug, type: 'person' }).subscribe({
      next: () => {
        this.showCreateForm.set(false);
        this.ngOnInit();
      },
    });
  }
}
