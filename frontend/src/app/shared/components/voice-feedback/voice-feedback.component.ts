import { Component, Input, signal, computed, OnDestroy } from '@angular/core';

type FeedbackState = 'idle' | 'expanded' | 'recording' | 'uploading' | 'done' | 'error';

/**
 * Reusable voice feedback widget.
 *
 * Usage:
 *   <app-voice-feedback endpointUrl="http://localhost:5000/api/feedback" source="silver-shield" />
 *
 * Works on both internal dashboards (localhost, files on disk) and
 * dash.ericzosso.com (Supabase-backed). Same component, configurable endpoint.
 */
@Component({
  selector: 'app-voice-feedback',
  template: `
    <!-- Floating trigger button -->
    @if (state() === 'idle') {
      <button class="vf-trigger" (click)="expand()">
        <span class="vf-icon">&#x1F399;</span>
        <span>Feedback</span>
      </button>
    }

    <!-- Expanded panel -->
    @if (state() !== 'idle') {
      <div class="vf-panel">
        <button class="vf-close" (click)="reset()">&times;</button>

        @switch (state()) {
          @case ('expanded') {
            <p class="vf-prompt">Record a quick voice note about this page.</p>
            <button class="vf-record-btn" (click)="startRecording()">
              <span class="vf-rec-dot"></span> Record
            </button>
          }
          @case ('recording') {
            <div class="vf-timer">{{ formattedTime() }} / 1:00</div>
            <div class="vf-pulse"></div>
            <button class="vf-stop-btn" (click)="stopRecording()">Stop & Send</button>
          }
          @case ('uploading') {
            <p class="vf-uploading">Uploading...</p>
          }
          @case ('done') {
            <p class="vf-success">Thanks for the feedback!</p>
          }
          @case ('error') {
            <p class="vf-error">{{ errorMsg() }}</p>
            <button class="vf-retry-btn" (click)="expand()">Retry</button>
          }
        }
      </div>
    }
  `,
  styles: [`
    :host { position: fixed; bottom: 1.5rem; left: 1.5rem; z-index: 9999;
            font-family: 'Segoe UI', system-ui, sans-serif; }

    .vf-trigger { display: flex; align-items: center; gap: .4rem;
                  background: var(--silver-dim, #8a8a9a); color: #fff; border: none;
                  padding: .5rem .9rem; border-radius: 999px; cursor: pointer;
                  font-size: .82rem; font-weight: 500;
                  box-shadow: 0 2px 12px rgba(0,0,0,.3);
                  transition: transform .15s, box-shadow .15s; }
    .vf-trigger:hover { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(0,0,0,.4); }
    .vf-icon { font-size: 1rem; }

    .vf-panel { width: 260px; background: var(--card, #181d28); border: 1px solid var(--border, #2a3040);
                border-radius: 12px; padding: 1.25rem; position: relative;
                box-shadow: 0 4px 24px rgba(0,0,0,.4); }

    .vf-close { position: absolute; top: .5rem; right: .6rem; background: none; border: none;
                color: var(--muted, #7a8498); font-size: 1.2rem; cursor: pointer; line-height: 1; }
    .vf-close:hover { color: var(--text, #e0e4ec); }

    .vf-prompt { color: var(--text, #e0e4ec); font-size: .82rem; margin-bottom: .75rem; line-height: 1.4; }

    .vf-record-btn { display: flex; align-items: center; gap: .5rem; width: 100%;
                     background: var(--green, #22c55e); color: #fff; border: none;
                     padding: .55rem; border-radius: 8px; cursor: pointer;
                     font-size: .82rem; font-weight: 600; justify-content: center; }
    .vf-rec-dot { width: 10px; height: 10px; border-radius: 50%; background: #fff; }

    .vf-timer { text-align: center; font-family: 'Cascadia Code', monospace;
                font-size: 1.4rem; color: var(--text, #e0e4ec); margin-bottom: .5rem; }

    .vf-pulse { width: 12px; height: 12px; border-radius: 50%; background: var(--red, #ef4444);
                margin: 0 auto .75rem; animation: vf-pulse 1s ease-in-out infinite; }
    @keyframes vf-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }

    .vf-stop-btn { width: 100%; background: var(--red, #ef4444); color: #fff; border: none;
                   padding: .55rem; border-radius: 8px; cursor: pointer;
                   font-size: .82rem; font-weight: 600; }

    .vf-uploading { text-align: center; color: var(--muted, #7a8498); font-size: .82rem;
                    font-style: italic; }

    .vf-success { text-align: center; color: var(--green, #22c55e); font-size: .85rem;
                  font-weight: 500; }

    .vf-error { text-align: center; color: var(--red, #ef4444); font-size: .82rem;
                margin-bottom: .5rem; }

    .vf-retry-btn { width: 100%; background: var(--silver-dim, #8a8a9a); color: #fff;
                    border: none; padding: .45rem; border-radius: 8px; cursor: pointer;
                    font-size: .78rem; }
  `],
})
export class VoiceFeedbackComponent implements OnDestroy {
  @Input() endpointUrl = 'http://localhost:5000/api/feedback';
  @Input() source = 'silver-shield';

  state = signal<FeedbackState>('idle');
  seconds = signal(0);
  errorMsg = signal('');

  formattedTime = computed(() => {
    const s = this.seconds();
    const min = Math.floor(s / 60);
    const sec = s % 60;
    return `${min}:${sec.toString().padStart(2, '0')}`;
  });

  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private mimeType = 'audio/webm';

  expand() {
    this.state.set('expanded');
    this.errorMsg.set('');
  }

  reset() {
    this.stopTimer();
    if (this.recorder && this.recorder.state !== 'inactive') {
      this.recorder.stop();
    }
    if (this.stream) {
      this.stream.getTracks().forEach(t => t.stop());
      this.stream = null;
    }
    this.recorder = null;
    this.chunks = [];
    this.seconds.set(0);
    this.state.set('idle');
  }

  async startRecording() {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      this.errorMsg.set('Microphone access denied.');
      this.state.set('error');
      return;
    }

    // Detect supported MIME type
    for (const mime of ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']) {
      if (MediaRecorder.isTypeSupported(mime)) {
        this.mimeType = mime;
        break;
      }
    }

    this.chunks = [];
    this.recorder = new MediaRecorder(this.stream, { mimeType: this.mimeType });

    this.recorder.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };

    this.recorder.onstop = () => this.upload();

    this.recorder.start(1000);
    this.seconds.set(0);
    this.state.set('recording');
    this.startTimer();
  }

  stopRecording() {
    this.stopTimer();
    if (this.recorder && this.recorder.state !== 'inactive') {
      this.recorder.stop();
    }
    if (this.stream) {
      this.stream.getTracks().forEach(t => t.stop());
      this.stream = null;
    }
  }

  private async upload() {
    this.state.set('uploading');

    const ext = this.mimeType.includes('mp4') ? 'm4a' : 'webm';
    const blob = new Blob(this.chunks, { type: this.mimeType });
    const form = new FormData();
    form.append('audio', blob, `feedback.${ext}`);
    form.append('source', this.source);
    form.append('page_url', window.location.href);
    form.append('duration', this.seconds().toString());

    try {
      const res = await fetch(this.endpointUrl, { method: 'POST', body: form });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this.state.set('done');
      setTimeout(() => this.reset(), 3000);
    } catch (e: any) {
      this.errorMsg.set(e.message || 'Upload failed');
      this.state.set('error');
    }
  }

  private startTimer() {
    this.timer = setInterval(() => {
      const s = this.seconds() + 1;
      this.seconds.set(s);
      if (s >= 60) this.stopRecording();
    }, 1000);
  }

  private stopTimer() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  ngOnDestroy() {
    this.reset();
  }
}
