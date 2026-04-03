import { Component, OnInit, signal } from '@angular/core';

@Component({
  selector: 'app-feedback-list',
  template: `
    <div class="hero">
      <h1><span>Silver Shield</span> Feedback</h1>
      <p class="subtitle">Voice feedback from internal dashboards</p>
    </div>
    <div class="card">
      <h2>Submissions <span class="subtitle">{{ entries().length }} total</span></h2>
      @if (entries().length === 0) {
        <div class="loading">No feedback yet. Use the microphone button to record.</div>
      } @else {
        @for (entry of entries(); track entry.id) {
          <div class="feedback-row">
            <div class="feedback-meta">
              <span class="badge badge-silver">{{ entry.source }}</span>
              <span class="muted">{{ entry.created_at }}</span>
              <span class="muted">{{ entry.duration_seconds }}s</span>
            </div>
            @if (entry.transcript) {
              <p class="transcript">{{ entry.transcript }}</p>
            }
            <audio [src]="audioUrl(entry.id)" controls preload="none" style="width:100%;margin-top:.3rem;height:32px;"></audio>
          </div>
        }
      }
    </div>
  `,
  styles: [`
    .hero h1 { font-size: 1.5rem; margin-bottom: .2rem; }
    .hero h1 span { color: var(--silver); }
    .subtitle { color: var(--muted); font-size: .85rem; margin-bottom: 1.25rem; }
    .muted { color: var(--muted); font-size: .75rem; }
    .feedback-row { padding: .75rem 0; border-bottom: 1px solid var(--border); }
    .feedback-meta { display: flex; align-items: center; gap: .5rem; margin-bottom: .3rem; }
    .transcript { color: var(--text); font-size: .82rem; line-height: 1.4; margin-top: .3rem; }
    audio { filter: invert(.85) hue-rotate(180deg); }
  `],
})
export class FeedbackListComponent implements OnInit {
  entries = signal<any[]>([]);

  ngOnInit() {
    fetch('http://localhost:5000/api/feedback')
      .then(r => r.json())
      .then(d => this.entries.set(d.entries || []))
      .catch(() => {});
  }

  audioUrl(id: string) {
    return `http://localhost:5000/api/feedback/audio/${id}`;
  }
}
