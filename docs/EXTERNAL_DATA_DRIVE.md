# Data on an external drive (Samsung T9)

The `data/` tree (~108 GB raw + processed composites) lives on an external
**Samsung T9** (exfat), not on the internal disk. In the repo, `data` is a
**symlink** to it:

```
data -> /Volumes/T9/pilot-data
```

Every code path resolves data as `PROJECT_ROOT / "data" / …` (see
`scripts/fetch/__init__.py`, `scripts/preprocess/__init__.py`,
`backend/app/config.py`), so the symlink is transparent — **no code knows or
cares** that the bytes are on the drive.

## Working rules

| Task | Drive needed? |
|---|---|
| Editing code, running most tests, frontend dev | **No** |
| Preprocess / reprocess (`scripts/preprocess.py`, data TUI) | **Yes** |
| Running the backend locally against real composites | **Yes** |
| Deploy (`./deploy.sh …`, data TUI deploy) | **Yes** |

With the drive **unplugged**, `data` is a dangling symlink. That is fine: it's
git-ignored, and code work never reads it. Anything that touches `data/` will
fail loudly (file-not-found) rather than silently — plug the drive back in.

## How it was set up (2026-07-04)

Non-destructive: copy → verify → symlink → keep a backup.

```bash
rsync -rt data/ /Volumes/T9/pilot-data/     # copy (macOS ships openrsync; no --info=progress2)
mv data data.local-bak                        # safety net on internal disk
ln -s /Volumes/T9/pilot-data data             # repo now points at the drive
```

Verified: real-file counts matched (2279 = 2279), sizes matched (108G), and a
one-state reprocess (`--state 05`) succeeded writing back through the symlink.
`data.local-bak/` was then deleted.

`.gitignore` was updated: the old `data/` pattern (trailing slash matches
**directories only**) did not match a symlink, so it's now bare `data` plus
`data.local-bak/`.

## Redoing this on a fresh machine / new drive

1. Plug in the drive, note its mount (`ls /Volumes`).
2. `rsync -rt <source-data>/ /Volumes/<DRIVE>/pilot-data/`
3. In the repo: `rm -rf data && ln -s /Volumes/<DRIVE>/pilot-data data`
   (or `mv data data.local-bak` first if `data` still holds the real bytes).
4. Confirm: `python3 -c "from pathlib import Path; print(Path('data/manifest.json').exists())"` → `True`.

## Bugs to watch for

### 1. "database is locked" (exfat + SQLite)
exfat has weak POSIX file locking. The **local dev** SQLite DB
(`data/processed/lead_state.sqlite3`) can throw `database is locked` when
served from the drive. Prod is unaffected (Fly + Litestream → R2, a separate
DB).

**Fix — keep just that one file on the internal disk:**
```bash
# move the DB off the drive, symlink it back into place
mv data/processed/lead_state.sqlite3 ~/pilot-lead_state.sqlite3
ln -s ~/pilot-lead_state.sqlite3 /Volumes/T9/pilot-data/processed/lead_state.sqlite3
```
(Symlinking the target *inside* the drive tree keeps the repo-side `data`
symlink untouched.)

### 2. `._*` sidecar files (exfat AppleDouble) — the big gotcha
macOS stamps every process-written file with a `com.apple.provenance`
extended attribute. exfat can't store xattrs inline, so the OS spills them to
an AppleDouble `._<name>` sidecar next to each file. This happens on **every
pipeline write**, not just the initial copy — you can't turn it off (it's the
kernel, not `cp`). `COPYFILE_DISABLE=1` only suppresses them for `cp`/`rsync`,
not for pyarrow/tippecanoe writes, so the pipeline recreates them constantly.

Why it bites: `Path.glob("*.parquet")` **matches dotfiles**, and `sorted()`
puts `._foo.parquet` (a 4 KB stub) *before* the real `foo.parquet` — so a
naive `paths[0]` grabs the stub → `Parquet magic bytes not found in footer`.
This broke facets + tile generation on the first drive-backed reprocess.

**Fixed** in `scripts/preprocess/app_assets.py` (`resolve_parcel_paths` +
`state_has_parcels`) by globbing `"[!.]*.parquet"` — the `[!.]` excludes any
dot-prefixed file. Real parquet shards never start with a dot.

If you add a **new** parquet consumer that hands a glob straight to DuckDB or
tippecanoe, use `"[!.]*.parquet"`, not `"*.parquet"`. (Read paths that wrap
each shard in try/except already skip the stubs — they just log a warning per
sidecar.)

The `._*` files themselves are otherwise harmless (~0 bytes). Sweep them any
time with `find /Volumes/T9/pilot-data -name '._*' -delete`; they'll come back
on the next write, which is fine.

### 3. Dangling symlink = confusing errors when drive is absent
If a preprocess/deploy fails with "No such file or directory" on a `data/…`
path, first check the drive is mounted: `ls -la data` should show
`data -> /Volumes/T9/pilot-data`, and `ls data/` should list contents.

### 4. Drive not at `/Volumes/T9`
macOS appends a suffix (`/Volumes/T9 1`) if the name collides. If the symlink
breaks after a remount, recreate it pointing at the actual mount path.

### 5. exfat has no permissions/ownership
The drive mounts `noowners`, so file modes shown are cosmetic. Don't rely on
`chmod` there. Not a problem for the pipeline, but don't put anything needing
real Unix perms on it.
