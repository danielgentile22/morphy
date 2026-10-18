// One calm, transient notice for the whole app (ADR-077). The read-only demo
// is its first user: a write the backend refuses with 403 surfaces here
// instead of as a broken panel. Plain module state, so leads-api.ts can raise
// it without importing any component.

class NoticeStore {
  message = $state<string | null>(null);
  #timer: ReturnType<typeof setTimeout> | undefined;

  show(message: string, ms = 4000): void {
    this.message = message;
    clearTimeout(this.#timer);
    this.#timer = setTimeout(() => (this.message = null), ms);
  }

  dismiss(): void {
    clearTimeout(this.#timer);
    this.message = null;
  }
}

export const notice = new NoticeStore();
