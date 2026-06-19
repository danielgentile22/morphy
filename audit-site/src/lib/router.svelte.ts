/**
 * Hash-based routing (mirrors the map app's approach): a URL is a shareable
 * deep link that survives refresh with no server rewrite, and it composes with
 * the `/audit/` base + Caddy history fallback. Pure parse/build functions are
 * unit-tested; the reactive `router` singleton wraps them for components.
 *
 * Hash grammar: `#/<path>?<query>` — the query carries the Signals browser's
 * filter state (see signals.ts).
 */

export type Route =
  | { name: 'overview' }
  | { name: 'signals'; query: string }
  | { name: 'signal'; id: string }
  | { name: 'cards' }
  | { name: 'card'; id: string }
  | { name: 'doc'; file: string; anchor: string | null };

export function parseHash(hash: string): Route {
  const raw = hash.replace(/^#\/?/, '');
  const [path, query = ''] = raw.split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  switch (parts[0]) {
    case 'signals':
      return parts[1] ? { name: 'signal', id: parts[1] } : { name: 'signals', query };
    case 'cards':
      return parts[1] ? { name: 'card', id: parts[1] } : { name: 'cards' };
    case 'doc':
      return parts[1] ? { name: 'doc', file: parts[1], anchor: parts[2] ?? null } : { name: 'overview' };
    default:
      return { name: 'overview' };
  }
}

export const hrefs = {
  overview: '#/',
  signals: (query = '') => (query ? `#/signals?${query}` : '#/signals'),
  signal: (id: string) => `#/signals/${encodeURIComponent(id)}`,
  cards: '#/cards',
  card: (id: string) => `#/cards/${encodeURIComponent(id)}`,
  doc: (file: string, anchor?: string | null) =>
    `#/doc/${encodeURIComponent(file)}${anchor ? `/${encodeURIComponent(anchor)}` : ''}`,
};

class Router {
  hash = $state(typeof location !== 'undefined' ? location.hash : '');
  route = $derived(parseHash(this.hash));

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('hashchange', () => {
        this.hash = location.hash;
      });
    }
  }

  /** Navigate (updates the hash; the listener refreshes `route`). */
  go(href: string): void {
    if (href.startsWith('#')) location.hash = href.slice(1);
    else location.hash = href;
  }
}

export const router = new Router();
