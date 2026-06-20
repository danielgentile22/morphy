/**
 * M3 · Catalog config (curated data). The *only* curated layer in the catalog:
 * group definitions + a plain-English meaning for each known base-signal-id. Every
 * other per-point fact (trust, provenance, freshness, verdict) is read live from
 * `index.json` by the builder (catalog.ts) — so a re-run that rewrites the audit
 * auto-populates the catalog, and only a genuinely *new* data point needs a
 * one-line addition here. A base id the config doesn't recognise is never dropped;
 * the builder routes it into the synthetic "Newly added" group with its raw verdict.
 *
 * Keys are stable base-signal-ids (the `@NN` state suffix stripped — see
 * `baseSignalId` in signals.ts), so the four per-state copies of a parcel field
 * share one entry.
 */

/** A catalog group: a human bucket "by what the data tells you about a deal". */
export interface GroupDef {
  /** Stable slug — also the deep-link anchor (`#/catalog/<id>`). */
  id: string;
  emoji: string;
  title: string;
  blurb: string;
  /** Render order; lower first. The Newly-added group sorts ahead of all of these. */
  order: number;
}

/** Per-base-id curation: which group it belongs to + its one-line plain meaning. */
export interface ConfigEntry {
  group: string;
  meaning: string;
}

export interface CatalogConfig {
  groups: GroupDef[];
  /** The synthetic bucket for base ids absent from {@link entries}. */
  newlyAdded: GroupDef;
  entries: Record<string, ConfigEntry>;
}

/** The seven curated groups, in display order (PRD M3). */
export const GROUPS: GroupDef[] = [
  {
    id: 'tower',
    emoji: '🗼',
    title: 'The Tower',
    blurb: 'The physical structure and its FCC registration.',
    order: 1,
  },
  {
    id: 'carrier',
    emoji: '📡',
    title: 'The Carrier',
    blurb: 'Which wireless operators are on the tower.',
    order: 2,
  },
  {
    id: 'landowner',
    emoji: '👤',
    title: 'The Landowner',
    blurb: 'Who owns the land, and what else they control.',
    order: 3,
  },
  {
    id: 'land',
    emoji: '🗺️',
    title: 'The Land / Parcel',
    blurb: 'The parcel itself — where it is, how big, what it’s worth.',
    order: 4,
  },
  {
    id: 'distress',
    emoji: '📉',
    title: 'Motivation & Distress',
    blurb: 'Economic-distress signals that hint a landowner may want to deal.',
    order: 5,
  },
  {
    id: 'derived',
    emoji: '🧮',
    title: 'Derived Scores & Joins',
    blurb: 'Values we compute or join together — not fetched raw.',
    order: 6,
  },
  {
    id: 'exploratory',
    emoji: '🧪',
    title: 'Exploratory',
    blurb: 'Captured, not yet used in production.',
    order: 7,
  },
];

/** The fallback bucket: anything the config doesn't recognise lands here (never
 *  dropped), shown with its raw audit verdict. Sorts ahead of the curated groups. */
export const NEWLY_ADDED_GROUP: GroupDef = {
  id: 'newly-added',
  emoji: '✨',
  title: 'Newly added',
  blurb: 'Data points the catalog doesn’t recognise yet — shown with their raw audit verdict so nothing is ever silently hidden.',
  order: -1,
};

/** base-signal-id → { group, plain meaning }. Keyed by stable ids so re-runs
 *  don't disturb it; per-state parcel fields key on the suffix-stripped base id. */
export const SIGNAL_ENTRIES: Record<string, ConfigEntry> = {
  // ── The Tower (FCC ASR + FAA corroboration) ──────────────────────────────
  tower_coords: { group: 'tower', meaning: 'Where the tower physically stands (latitude / longitude).' },
  asr_number: { group: 'tower', meaning: 'The tower’s unique FCC registration number — the canonical key.' },
  structure_type: { group: 'tower', meaning: 'What kind of structure it is (lattice, guyed, monopole…).' },
  tower_height: { group: 'tower', meaning: 'How tall the tower is.' },
  tower_status: { group: 'tower', meaning: 'Whether the FCC registration is active, granted, or cancelled.' },
  tower_date_built: { group: 'tower', meaning: 'When the tower was registered / built.' },
  tower_owner: { group: 'tower', meaning: 'The company that registered the tower with the FCC.' },
  faa_tower_corroboration: {
    group: 'tower',
    meaning: 'Whether the FAA’s obstacle database independently confirms the tower exists.',
  },

  // ── The Carrier ──────────────────────────────────────────────────────────
  carriers: { group: 'carrier', meaning: 'Which wireless carriers operate on the tower.' },

  // ── The Landowner (deed owner + clustering + owner type) ──────────────────
  owner_name: { group: 'landowner', meaning: 'The name on the parcel deed — who owns the land.' },
  mailing_address: { group: 'landowner', meaning: 'Where to reach the landowner by mail.' },
  owner_kind: { group: 'landowner', meaning: 'Whether the owner is a person, a company, or a government body.' },
  owner_cluster_id: { group: 'landowner', meaning: 'Links parcels that appear to share the same owner.' },
  display_cluster_id: { group: 'landowner', meaning: 'The owner-group shown in the app after any manual merge / split.' },
  owner_cluster_size: { group: 'landowner', meaning: 'How many parcels that same owner controls.' },
  owner_cluster_value_total: { group: 'landowner', meaning: 'The combined assessed value of everything that owner controls.' },
  owner_portfolio_rollups: { group: 'landowner', meaning: 'Per-owner totals — parcel count, acreage, value — across their holdings.' },

  // ── The Land / Parcel ─────────────────────────────────────────────────────
  situs_address: { group: 'land', meaning: 'The street address of the land itself.' },
  acreage: { group: 'land', meaning: 'How big the parcel is, in acres.' },
  parcel_value: { group: 'land', meaning: 'The county’s assessed value of the parcel.' },
  land_use: { group: 'land', meaning: 'How the parcel is classified (residential, ag, commercial…).' },
  year_built: { group: 'land', meaning: 'When the structure on the parcel was built, per the assessor.' },
  parcel_geometry: { group: 'land', meaning: 'The mapped shape / boundary of the parcel.' },
  parcel_id: { group: 'land', meaning: 'The county’s parcel identifier (APN).' },

  // ── Motivation & Distress ──────────────────────────────────────────────────
  in_oz: { group: 'distress', meaning: 'Whether the parcel sits in a federal Opportunity Zone.' },
  in_qct: { group: 'distress', meaning: 'Whether the parcel sits in a HUD Qualified Census Tract.' },
  persistent_poverty: { group: 'distress', meaning: 'Whether the county is a persistent-poverty county.' },
  distress_tier: { group: 'distress', meaning: 'An overall economic-distress tier for the location.' },
  county_distress: { group: 'distress', meaning: 'County-level economic-distress indicators.' },

  // ── Derived Scores & Joins ─────────────────────────────────────────────────
  interestingness_score: { group: 'derived', meaning: 'Our lead-priority score for a tower.' },
  interestingness_components: { group: 'derived', meaning: 'The individual factors that make up the priority score.' },
  parcel_tower_join: { group: 'derived', meaning: 'The spatial match that ties a tower to the parcel it sits on.' },
  tower_landowner_attrs: { group: 'derived', meaning: 'Landowner facts carried onto a tower via the parcel join.' },
  infrastructure_summary: { group: 'derived', meaning: 'A roll-up of the infrastructure found on or near a parcel.' },

  // ── Exploratory (captured, not yet used) ───────────────────────────────────
  billboard_dead_columns: { group: 'exploratory', meaning: 'Florida billboard-permit columns captured but not yet used.' },
  solar_facility: { group: 'exploratory', meaning: 'Utility-scale solar facilities — captured, not yet wired into leads.' },
  parcel_solar: { group: 'exploratory', meaning: 'Solar facilities matched to parcels — exploratory.' },
  uls_license_entity_location: { group: 'exploratory', meaning: 'FCC ULS license-holder locations — captured, not yet used.' },
  unused_raw_columns: { group: 'exploratory', meaning: 'Raw source columns we ingest but don’t surface.' },
  misused_raw_columns: { group: 'exploratory', meaning: 'Raw columns whose meaning we flagged as easy to misread.' },
};

/** The default config the catalog builder uses in production. */
export const defaultCatalogConfig: CatalogConfig = {
  groups: GROUPS,
  newlyAdded: NEWLY_ADDED_GROUP,
  entries: SIGNAL_ENTRIES,
};
