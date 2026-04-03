import { Component } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { VoiceFeedbackComponent } from './shared/components/voice-feedback/voice-feedback.component';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, VoiceFeedbackComponent],
  template: `
    <nav>
      <a routerLink="/" class="brand"><span>Silver Shield</span></a>
      <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{exact: true}" class="nav-link">Dashboard</a>
      <a routerLink="/entities" routerLinkActive="active" class="nav-link">Entities</a>
      <a routerLink="/resources" routerLinkActive="active" class="nav-link">Resources</a>
      <a routerLink="/compliance" routerLinkActive="active" class="nav-link">Compliance</a>
      <a routerLink="/deficiency" routerLinkActive="active" class="nav-link">Deficiency</a>
      <a routerLink="/discovery" routerLinkActive="active" class="nav-link">Discovery</a>
      <a routerLink="/feedback" routerLinkActive="active" class="nav-link">Feedback</a>
      <div class="spacer"></div>
      <span class="port-badge">:5003</span>
    </nav>
    <main>
      <router-outlet />
    </main>
    <app-voice-feedback endpointUrl="http://localhost:5000/api/feedback" source="silver-shield" />
  `,
  styles: [`
    :host { display: block; min-height: 100vh; background: var(--bg); color: var(--text); }
    nav { background: linear-gradient(135deg, #12151f 0%, #1a1f2e 100%);
          padding: .8rem 1.5rem; display: flex; align-items: center; gap: 1.2rem;
          border-bottom: 2px solid var(--silver-dim); flex-wrap: wrap; }
    .brand { font-size: 1.15rem; font-weight: 600; color: #fff; text-decoration: none; }
    .brand span { color: var(--silver); }
    .nav-link { color: var(--muted); text-decoration: none; font-size: .82rem;
                padding: .25rem .5rem; border-radius: 4px; transition: all .2s; }
    .nav-link:hover, .nav-link.active { color: #fff; background: rgba(255,255,255,.06); }
    .spacer { flex: 1; }
    .port-badge { font-size: .7rem; color: var(--silver-dim); padding: .2rem .5rem;
                  border: 1px solid var(--border); border-radius: 12px; font-family: monospace; }
    main { max-width: 1200px; margin: 0 auto; padding: 1.25rem; }
  `],
})
export class App {}
