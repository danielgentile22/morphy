/**
 * Markdown → HTML for the dossiers and boards, with two audit-specific rules:
 *
 *  1. **Signal-id heading anchors.** A `## Signal: \`tower_coords\` · confidence: …`
 *     heading is given `id="tower_coords"` — exactly the anchor `index.json`'s
 *     `signals[].dossier` points at — so signal→dossier deep-links land on the
 *     right section (handoff §5/§9). GitHub's own slug of that heading would be
 *     `signal-tower_coords--confidence-high`, which would NOT match.
 *  2. **In-app link rewriting.** Cross-file `*.md` links and in-page `#anchor`
 *     links are rewritten onto the app's hash router (`#/doc/<file>/<anchor>`)
 *     so the rendered boards navigate inside the SPA; external `http(s)` links
 *     open in a new tab.
 *
 * The audit `.md` is our own trusted repo content, so HTML is rendered without a
 * sanitiser — there is no untrusted input path here.
 */

import { Marked, type Tokens } from 'marked';

function slug(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');
}

/** The signal-id anchor for a `## Signal: \`id\` · …` heading, else null. */
function signalAnchor(token: Tokens.Heading): string | null {
  if (token.depth !== 2 || !/^\s*Signal:/.test(token.text)) return null;
  const code = (token.tokens ?? []).find(
    (t): t is Tokens.Codespan => t.type === 'codespan',
  );
  return code ? code.text : null;
}

function docHash(file: string, anchor?: string): string {
  const base = `#/doc/${encodeURIComponent(file)}`;
  return anchor ? `${base}/${encodeURIComponent(anchor)}` : base;
}

/** Render a markdown file to HTML. `file` is the current file's name, used to
 *  keep its in-page `#anchor` links inside the app's router. */
export function renderMarkdown(markdown: string, file: string): string {
  const used = new Map<string, number>();
  const uniqueSlug = (text: string): string => {
    const base = slug(text) || 'section';
    const n = used.get(base) ?? 0;
    used.set(base, n + 1);
    return n === 0 ? base : `${base}-${n}`;
  };

  const md = new Marked({
    gfm: true,
    breaks: false,
    renderer: {
      heading(token: Tokens.Heading): string {
        const inner = this.parser.parseInline(token.tokens ?? []);
        const id = signalAnchor(token) ?? uniqueSlug(token.text);
        return `<h${token.depth} id="${id}">${inner}</h${token.depth}>\n`;
      },
      link(token: Tokens.Link): string {
        const inner = this.parser.parseInline(token.tokens ?? []);
        const href = token.href ?? '';
        if (/^https?:\/\//.test(href)) {
          return `<a href="${href}" target="_blank" rel="noopener noreferrer">${inner}</a>`;
        }
        let target = href;
        if (href.startsWith('#')) {
          target = docHash(file, href.slice(1));
        } else {
          const m = href.match(/(?:^|\/)([^/]+\.md)(?:#(.*))?$/);
          if (m) target = docHash(m[1], m[2]);
        }
        const title = token.title ? ` title="${token.title}"` : '';
        return `<a href="${target}"${title}>${inner}</a>`;
      },
    },
  });

  return md.parse(markdown, { async: false }) as string;
}

/**
 * Render an "Ask Claude" answer to HTML (PRD #187 / #188).
 *
 * Unlike {@link renderMarkdown}, which renders our own trusted repo dossiers,
 * this is *model output* — a less-trusted path. So as defense-in-depth (even
 * behind the login), raw HTML in the markdown is dropped rather than passed
 * through, and links are forced to safe `http(s)` targets opening in a new tab.
 * `breaks: true` keeps single newlines as line breaks, which reads better for a
 * chat answer.
 */
export function renderAnswer(markdown: string): string {
  const md = new Marked({
    gfm: true,
    breaks: true,
    renderer: {
      // Strip any raw HTML the model emits — neutralises `<script>`/`<img
      // onerror>` style injection without pulling in a sanitiser dependency.
      html(): string {
        return '';
      },
      link(token: Tokens.Link): string {
        const inner = this.parser.parseInline(token.tokens ?? []);
        const href = token.href ?? '';
        const safe = /^https?:\/\//.test(href) ? href : '#';
        return `<a href="${safe}" target="_blank" rel="noopener noreferrer">${inner}</a>`;
      },
    },
  });
  return md.parse(markdown, { async: false }) as string;
}

/**
 * Pull one signal's `## Signal: …` block (heading through just before the next
 * `## ` heading) out of a dossier file, for the per-signal detail view. Returns
 * null when the file has no block for that id (then the detail view falls back
 * to the structured fields + a link to the full dossier).
 */
export function extractSignalSection(markdown: string, signalId: string): string | null {
  const lines = markdown.split('\n');
  const headingRe = /^##\s+Signal:\s+`([^`]+)`/;
  let start = -1;
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(headingRe);
    if (m && m[1] === signalId) {
      start = i;
      break;
    }
  }
  if (start === -1) return null;
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i++) {
    if (/^##\s/.test(lines[i])) {
      end = i;
      break;
    }
  }
  return lines.slice(start, end).join('\n').trim();
}
