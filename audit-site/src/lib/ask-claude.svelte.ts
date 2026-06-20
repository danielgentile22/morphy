/**
 * The "Ask Claude" client (PRD #187 / #188 / #189) — the thin browser seam over
 * the backend's `POST /api/audit/ask` SSE route.
 *
 * Slice 1 (the walking skeleton) was question-only. Slice 2 (#189) grounds the
 * conversation in the page: a highlighted selection scopes the question, the
 * on-screen signals + visible text ride along, and follow-ups keep a short
 * in-memory thread. Nothing is persisted client-side — closing the panel or
 * asking about a new selection starts a fresh thread.
 *
 * The request is a POST (so it carries a JSON body), which means `EventSource`
 * (GET-only) can't be used; instead we read the streamed response body and parse
 * SSE frames by hand. The session `pilot_session` cookie rides along on the
 * same-origin fetch, so the route authorizes exactly like the rest of the app.
 */

import { buildAskContext, onScreenSignals, routeLabel } from './ask-context';
import { store } from './audit-store.svelte';
import { renderAnswer } from './markdown';
import { router } from './router.svelte';

// The API lives at the site root (`/api/*`), reverse-proxied by Caddy — it is
// NOT under the `/audit/` base path the SPA is served from. Same-origin, so the
// `pilot_session` cookie rides along and authorizes the request.
const ASK_URL = '/api/audit/ask';

export interface AskMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface SSEEvent {
  event: string;
  data: string;
}

/**
 * Split an accumulated stream buffer into complete SSE events plus the leftover
 * partial frame. Pure + incremental: feed it the running buffer, apply the
 * returned events, and carry `rest` into the next chunk. Events are delimited by
 * a blank line; `event:`/`data:` lines are parsed, multi-line `data` is rejoined
 * with newlines (mirrors the SSE spec).
 */
export function parseSSE(buffer: string): { events: SSEEvent[]; rest: string } {
  const events: SSEEvent[] = [];
  let rest = buffer;
  let sep = rest.indexOf('\n\n');
  while (sep !== -1) {
    const frame = rest.slice(0, sep);
    rest = rest.slice(sep + 2);
    let event = 'message';
    const data: string[] = [];
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
    }
    if (data.length > 0) events.push({ event, data: data.join('\n') });
    sep = rest.indexOf('\n\n');
  }
  return { events, rest };
}

function messageFor(status: number): string {
  if (status === 503) return "Ask Claude isn't configured right now.";
  if (status === 429) return "You're asking a bit quickly — give it a moment.";
  if (status === 401) return 'Your session expired — reload the page to sign in again.';
  return 'Something went wrong reaching Ask Claude. Try again.';
}

// The default question when the panel is opened from a selection and the reader
// just hits send without typing one — "explain this" (#189).
const EXPLAIN_SELECTION = 'Explain the selected text.';

/** The visible page text, read from the main content region (excludes the nav,
 *  footer, and the Ask Claude panel itself). Bounded again by buildAskContext. */
function readVisibleText(): string {
  if (typeof document === 'undefined') return '';
  const main = document.querySelector('main');
  return (main?.innerText ?? document.body?.innerText ?? '').trim();
}

class AskClaudeStore {
  open = $state(false);
  question = $state('');
  messages = $state<AskMessage[]>([]);
  streaming = $state(false);
  error = $state<string | null>(null);
  // The highlighted text the conversation is scoped to (#189), or null for a
  // free-typed question. Set via askAboutSelection; cleared on close / new
  // selection / clearSelection.
  selection = $state<string | null>(null);

  #controller: AbortController | null = null;

  /** Rendered HTML for an assistant message (markdown → safe HTML). */
  render(content: string): string {
    return renderAnswer(content);
  }

  toggle(): void {
    this.open ? this.close() : this.openPanel();
  }

  openPanel(): void {
    this.open = true;
  }

  /** Open the panel scoped to a fresh selection (#189). A new selection always
   *  starts a clean thread — prior turns about a different thing would mislead. */
  askAboutSelection(text: string): void {
    this.#abort();
    this.messages = [];
    this.question = '';
    this.error = null;
    this.selection = text;
    this.open = true;
  }

  /** Drop the selection scope without losing the thread (the reader wants to ask
   *  about the page generally instead). */
  clearSelection(): void {
    this.selection = null;
  }

  close(): void {
    this.open = false;
    this.#abort();
    // Closing ends the conversation — nothing is persisted (#189).
    this.messages = [];
    this.question = '';
    this.selection = null;
    this.error = null;
  }

  #abort(): void {
    this.#controller?.abort();
    this.#controller = null;
    this.streaming = false;
  }

  async send(): Promise<void> {
    // With a selection in scope, an empty box still asks — "explain this" (#189).
    const q = this.question.trim() || (this.selection ? EXPLAIN_SELECTION : '');
    if (!q || this.streaming) return;

    this.error = null;
    // The thread is the prior turns, captured before this question is appended;
    // it rides along so the stateless backend keeps context across follow-ups.
    const thread = this.messages.map((m) => ({ role: m.role, content: m.content }));
    this.messages = [
      ...this.messages,
      { role: 'user', content: q },
      { role: 'assistant', content: '' },
    ];
    const answerAt = this.messages.length - 1;
    this.question = '';
    this.streaming = true;
    this.#controller = new AbortController();

    // Snapshot the page grounding now (route + on-screen signals + visible text).
    const payload = buildAskContext({
      question: q,
      route: routeLabel(router.route),
      selection: this.selection,
      visibleText: readVisibleText(),
      signals: onScreenSignals(router.route, store.signals, store.signalById),
      thread,
    });

    try {
      const res = await fetch(ASK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: this.#controller.signal,
      });

      if (!res.ok || !res.body) {
        this.error = messageFor(res.status);
        // Drop the unanswered question + empty answer; the error banner stands in.
        this.messages = this.messages.slice(0, answerAt - 1);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { events, rest } = parseSSE(buffer);
        buffer = rest;
        for (const ev of events) this.#apply(ev, answerAt);
      }
    } catch (err) {
      // An intentional abort (panel close / re-ask) isn't an error.
      if (!(err instanceof DOMException && err.name === 'AbortError')) {
        this.error = messageFor(0);
        this.messages = this.messages.slice(0, answerAt - 1);
      }
    } finally {
      this.streaming = false;
      this.#controller = null;
    }
  }

  #apply(ev: SSEEvent, answerAt: number): void {
    if (ev.event === 'delta') {
      const text = (JSON.parse(ev.data) as { text?: string }).text ?? '';
      this.messages[answerAt].content += text; // deep $state proxy → reactive
    } else if (ev.event === 'error') {
      this.error = (JSON.parse(ev.data) as { message?: string }).message ?? messageFor(0);
    }
    // 'done' carries no payload — the stream simply ends.
  }
}

export const askClaude = new AskClaudeStore();
