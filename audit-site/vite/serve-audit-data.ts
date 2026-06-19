import type { Plugin, Connect } from 'vite';
import { createReadStream, statSync } from 'node:fs';
import { join, normalize, resolve, sep } from 'node:path';

/**
 * Serve the audit artifacts (`docs/research/data-audit/*`) at `<base>data/*`
 * in both `vite dev` and `vite preview`, reading from disk on every request so
 * a re-run that rewrites `index.json` / the dossier `.md` shows up on a plain
 * refresh — the "auto-populate on rerun" contract, with no rebuild.
 *
 * Production parity: the deployed Caddy serves the same `<base>data/*` path
 * from a baked snapshot of the same folder, so the SPA's fetch path is
 * identical in dev, preview, and prod (no environment branching in the app).
 */
const CONTENT_TYPES: Record<string, string> = {
  '.json': 'application/json; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
};

export function serveAuditData(opts: { dir: string; segment?: string }): Plugin {
  const segment = opts.segment ?? 'data';
  const rootDir = resolve(opts.dir);
  // Resolved in configResolved once `base` is known (e.g. `/audit/data/`).
  let prefix = `/${segment}/`;

  const middleware: Connect.NextHandleFunction = (req, res, next) => {
    const url = (req.url ?? '').split('?')[0];
    const at = url.indexOf(prefix);
    if (at === -1) return next();

    const rel = decodeURIComponent(url.slice(at + prefix.length));
    const filePath = normalize(join(rootDir, rel));
    // Path-traversal guard: the resolved file must stay inside the audit dir.
    if (filePath !== rootDir && !filePath.startsWith(rootDir + sep)) {
      res.statusCode = 403;
      res.end('forbidden');
      return;
    }
    try {
      if (!statSync(filePath).isFile()) return next();
    } catch {
      return next();
    }
    const ext = filePath.slice(filePath.lastIndexOf('.'));
    res.setHeader('Content-Type', CONTENT_TYPES[ext] ?? 'application/octet-stream');
    // Never cache — each request re-reads disk so re-runs are live.
    res.setHeader('Cache-Control', 'no-store');
    createReadStream(filePath).pipe(res);
  };

  return {
    name: 'serve-audit-data',
    configResolved(config) {
      prefix = `${config.base}${segment}/`.replace(/\/{2,}/g, '/');
    },
    configureServer(server) {
      server.middlewares.use(middleware);
    },
    configurePreviewServer(server) {
      server.middlewares.use(middleware);
    },
  };
}
