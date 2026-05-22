/**
 * schema.ts — the linchpin.
 *
 * Every v3 composite field name the detail panels read lives here, in
 * one typed module. The v1 app broke because the v3 compose renamed
 * nearly every field and the panels still read the old names, rendering
 * rows of "—". Pinning the names here means a future rename is caught by
 * a failing type-check or the schema-completeness test — not by a blank
 * panel in front of a user.
 *
 * Field *names* are stable across states; numeric *types* are not —
 * `assessed_value` / `land_value` / `improvement_value` are float64 on
 * AR but int64 on MT. Every formatter in ./format tolerates both.
 */

import {
  fmtAcres,
  fmtBool,
  fmtInt,
  fmtLatLng,
  fmtMeters,
  fmtMoney,
  fmtMw,
  fmtScore,
  fmtText,
  fmtYear,
  joinNonEmpty,
} from './format';
import { distressTierLabel, overlayTypeLabel, ownerKindLabel } from './palette';

export type Props = Record<string, unknown>;

export type EntityKind = 'tower' | 'parcel' | 'solar' | 'distress_overlay' | 'county';

/** A single row in a detail panel. */
export interface FieldDef {
  label: string;
  /** v3 property keys this row reads — drives the schema-completeness test. */
  keys: string[];
  /** Render the row's display value, or null when there is nothing to show. */
  value: (p: Props) => string | null;
}

export interface FieldSection {
  title: string;
  fields: FieldDef[];
}

export type TagTone = 'oz' | 'distress' | 'infra' | 'neutral';
export interface Tag {
  label: string;
  tone: TagTone;
}

export interface EntitySchema {
  kind: EntityKind;
  /** Panel header line. */
  title: (p: Props) => string;
  /** Chips shown under the header. */
  tags: (p: Props) => Tag[];
  sections: FieldSection[];
}

// ── shared value helpers ─────────────────────────────────────────────────

/** distress_tier as a label, or null when the tier is blank (common on towers). */
function tierValue(p: Props): string | null {
  return fmtText(p.distress_tier) ? distressTierLabel(p.distress_tier) : null;
}

/**
 * The nested columns (distress_overlays, infrastructure_summary,
 * interestingness_components) arrive as real arrays/objects from a
 * GeoJSON feature but as JSON strings from a DuckDB parquet row — accept
 * either.
 */
function coerceJson(value: unknown): unknown {
  if (typeof value !== 'string') return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

/** distress_overlays — an array of overlay-type strings. */
function overlaysValue(p: Props): string | null {
  const v = coerceJson(p.distress_overlays);
  if (!Array.isArray(v) || v.length === 0) return null;
  return v.map(overlayTypeLabel).join(', ');
}

/** One entry of a parcel's infrastructure_summary list. */
export interface InfraItem {
  type: string;
  id: string;
  owner: string;
}

/** Parse `infrastructure_summary` (a list of {type,id,owner}) defensively. */
export function infrastructureItems(p: Props): InfraItem[] {
  const v = coerceJson(p.infrastructure_summary);
  if (!Array.isArray(v)) return [];
  return v
    .filter((x): x is Record<string, unknown> => typeof x === 'object' && x !== null)
    .map((x) => ({
      type: String(x.type ?? ''),
      id: String(x.id ?? ''),
      owner: String(x.owner ?? ''),
    }));
}

/** Parse `interestingness_components` (a {factor: weight} map) into sorted pairs. */
export function scoreComponents(p: Props): Array<{ factor: string; weight: number }> {
  const v = coerceJson(p.interestingness_components);
  if (typeof v !== 'object' || v === null || Array.isArray(v)) return [];
  return Object.entries(v as Record<string, unknown>)
    .map(([factor, weight]) => ({ factor, weight: Number(weight) }))
    .filter((c) => Number.isFinite(c.weight))
    .sort((a, b) => b.weight - a.weight);
}

// ── tower ────────────────────────────────────────────────────────────────

export const TOWER_SCHEMA: EntitySchema = {
  kind: 'tower',
  title: (p) => {
    const asr = fmtText(p.asr_number);
    return asr ? `Tower ${asr}` : 'Tower';
  },
  tags: (p) => {
    const tags: Tag[] = [];
    if (p.in_oz === true) tags.push({ label: 'Opportunity Zone', tone: 'oz' });
    if (p.in_qct === true) tags.push({ label: 'QCT', tone: 'oz' });
    if (fmtText(p.parcel_owner)) tags.push({ label: 'Landowner identified', tone: 'infra' });
    return tags;
  },
  sections: [
    {
      // The pitch-critical block: the v3 tower carries the landowner
      // denormalized onto it — no cross-layer join needed.
      title: 'Landowner',
      fields: [
        { label: 'Owner', keys: ['parcel_owner'], value: (p) => fmtText(p.parcel_owner) },
        {
          label: 'Parcel ID',
          keys: ['parcel_id_full'],
          value: (p) => fmtText(p.parcel_id_full),
        },
        {
          label: 'Parcel value',
          keys: ['parcel_value'],
          value: (p) => fmtMoney(p.parcel_value),
        },
        {
          label: 'Parcel acreage',
          keys: ['parcel_acreage'],
          value: (p) => fmtAcres(p.parcel_acreage),
        },
        {
          label: 'Land use',
          keys: ['parcel_use_code'],
          value: (p) => fmtText(p.parcel_use_code),
        },
      ],
    },
    {
      title: 'Tower (FCC ASR / FAA)',
      fields: [
        { label: 'ASR number', keys: ['asr_number'], value: (p) => fmtText(p.asr_number) },
        {
          label: 'Status',
          keys: ['status_desc', 'status'],
          value: (p) => fmtText(p.status_desc) ?? fmtText(p.status),
        },
        {
          label: 'Structure',
          keys: ['structure_type_desc', 'structure_type'],
          value: (p) => fmtText(p.structure_type_desc) ?? fmtText(p.structure_type),
        },
        { label: 'Height', keys: ['height_m'], value: (p) => fmtMeters(p.height_m) },
        { label: 'Active', keys: ['is_active'], value: (p) => fmtBool(p.is_active) },
        { label: 'Built', keys: ['date_built'], value: (p) => fmtText(p.date_built) },
        {
          label: 'Coordinates',
          keys: ['lat', 'lon'],
          value: (p) => fmtLatLng(p.lat, p.lon),
        },
        {
          label: 'Location',
          keys: ['street', 'city', 'state', 'zip'],
          value: (p) => joinNonEmpty([p.street, p.city, p.state, p.zip]),
        },
        {
          label: 'FAA registrant',
          keys: ['owner_name'],
          value: (p) => fmtText(p.owner_name),
        },
      ],
    },
    {
      title: 'Distress context',
      fields: [
        { label: 'Opportunity Zone', keys: ['in_oz'], value: (p) => fmtBool(p.in_oz) },
        { label: 'Qualified Census Tract', keys: ['in_qct'], value: (p) => fmtBool(p.in_qct) },
        {
          label: 'Persistent poverty',
          keys: ['persistent_poverty'],
          value: (p) => fmtBool(p.persistent_poverty),
        },
        { label: 'County economic tier', keys: ['distress_tier'], value: tierValue },
        { label: 'Distress overlays', keys: ['distress_overlays'], value: overlaysValue },
      ],
    },
  ],
};

// ── parcel ───────────────────────────────────────────────────────────────

export const PARCEL_SCHEMA: EntitySchema = {
  kind: 'parcel',
  title: (p) => {
    const id = fmtText(p.parcel_id) ?? fmtText(p.parcel_id_full);
    return id ? `Parcel ${id}` : 'Parcel';
  },
  tags: (p) => {
    const tags: Tag[] = [];
    if (fmtText(p.distress_tier)) {
      tags.push({ label: distressTierLabel(p.distress_tier), tone: 'distress' });
    }
    // PMTiles parcels carry has_tower/has_solar booleans, not counts —
    // fall back to those so a tile-clicked parcel still tags its infra.
    const towers = Number(p.tower_count) || 0;
    if (towers > 0) {
      tags.push({ label: `${towers} tower${towers === 1 ? '' : 's'}`, tone: 'infra' });
    } else if (p.has_tower === true) {
      tags.push({ label: 'Hosts a tower', tone: 'infra' });
    }
    const solar = Number(p.solar_count) || 0;
    if (solar > 0) {
      tags.push({
        label: `${solar} solar facilit${solar === 1 ? 'y' : 'ies'}`,
        tone: 'infra',
      });
    } else if (p.has_solar === true) {
      tags.push({ label: 'Hosts solar', tone: 'infra' });
    }
    if (p.in_oz === true) tags.push({ label: 'Opportunity Zone', tone: 'oz' });
    if (p.in_qct === true) tags.push({ label: 'QCT', tone: 'oz' });
    return tags;
  },
  sections: [
    {
      title: 'Ownership',
      fields: [
        { label: 'Owner', keys: ['owner_name'], value: (p) => fmtText(p.owner_name) },
        { label: 'Co-owner', keys: ['owner_name_2'], value: (p) => fmtText(p.owner_name_2) },
        {
          label: 'Owner type',
          keys: ['owner_kind'],
          value: (p) => (fmtText(p.owner_kind) ? ownerKindLabel(p.owner_kind) : null),
        },
        {
          label: 'Mailing address',
          keys: ['mailing_addr', 'mailing_city', 'mailing_state', 'mailing_zip'],
          value: (p) =>
            joinNonEmpty([p.mailing_addr, p.mailing_city, p.mailing_state, p.mailing_zip]),
        },
      ],
    },
    {
      title: 'Property',
      fields: [
        {
          label: 'Situs address',
          keys: ['situs_addr', 'situs_city'],
          value: (p) => joinNonEmpty([p.situs_addr, p.situs_city]),
        },
        { label: 'County FIPS', keys: ['county_fips'], value: (p) => fmtText(p.county_fips) },
        { label: 'Acreage', keys: ['acreage'], value: (p) => fmtAcres(p.acreage) },
        {
          label: 'Land use',
          keys: ['land_use_desc', 'land_use_code'],
          value: (p) => fmtText(p.land_use_desc) ?? fmtText(p.land_use_code),
        },
        { label: 'Year built', keys: ['year_built'], value: (p) => fmtYear(p.year_built) },
      ],
    },
    {
      title: 'Valuation',
      fields: [
        {
          label: 'Assessed value',
          keys: ['assessed_value'],
          value: (p) => fmtMoney(p.assessed_value),
        },
        { label: 'Land value', keys: ['land_value'], value: (p) => fmtMoney(p.land_value) },
        {
          label: 'Improvement value',
          keys: ['improvement_value'],
          value: (p) => fmtMoney(p.improvement_value),
        },
      ],
    },
    {
      title: 'Owner portfolio',
      fields: [
        {
          label: 'Parcels by this owner',
          keys: ['owner_cluster_size'],
          value: (p) => fmtInt(p.owner_cluster_size),
        },
        {
          label: 'Portfolio value',
          keys: ['owner_cluster_value_total'],
          value: (p) => fmtMoney(p.owner_cluster_value_total),
        },
      ],
    },
    {
      title: 'Infrastructure',
      fields: [
        { label: 'Towers', keys: ['tower_count'], value: (p) => fmtInt(p.tower_count) },
        {
          label: 'Solar facilities',
          keys: ['solar_count'],
          value: (p) => fmtInt(p.solar_count),
        },
        {
          label: 'Billboards',
          keys: ['billboard_count'],
          value: (p) => fmtInt(p.billboard_count),
        },
      ],
    },
    {
      title: 'Distress context',
      fields: [
        { label: 'County economic tier', keys: ['distress_tier'], value: tierValue },
        { label: 'Opportunity Zone', keys: ['in_oz'], value: (p) => fmtBool(p.in_oz) },
        { label: 'Qualified Census Tract', keys: ['in_qct'], value: (p) => fmtBool(p.in_qct) },
        {
          label: 'Persistent poverty',
          keys: ['persistent_poverty'],
          value: (p) => fmtBool(p.persistent_poverty),
        },
        { label: 'Distress overlays', keys: ['distress_overlays'], value: overlaysValue },
      ],
    },
    {
      title: 'Interestingness',
      fields: [
        {
          label: 'Score',
          keys: ['interestingness_score'],
          value: (p) => fmtScore(p.interestingness_score),
        },
      ],
    },
  ],
};

// ── solar facility ───────────────────────────────────────────────────────

export const SOLAR_SCHEMA: EntitySchema = {
  kind: 'solar',
  title: (p) => {
    const name = fmtText(p.name);
    if (name) return name;
    const id = fmtText(p.facility_id);
    return id ? `Solar facility ${id}` : 'Solar facility';
  },
  tags: (p) => {
    const tags: Tag[] = [];
    if (p.is_operational === true) tags.push({ label: 'Operational', tone: 'infra' });
    else if (p.is_operational === false) tags.push({ label: 'Retired', tone: 'neutral' });
    if (fmtText(p.parcel_owner)) tags.push({ label: 'Landowner identified', tone: 'infra' });
    return tags;
  },
  sections: [
    {
      title: 'Facility',
      fields: [
        { label: 'Name', keys: ['name'], value: (p) => fmtText(p.name) },
        { label: 'Operator', keys: ['operator'], value: (p) => fmtText(p.operator) },
        { label: 'Technology', keys: ['technology'], value: (p) => fmtText(p.technology) },
        { label: 'Capacity', keys: ['capacity_mw'], value: (p) => fmtMw(p.capacity_mw) },
        { label: 'Tracking', keys: ['tracking_type'], value: (p) => fmtText(p.tracking_type) },
        {
          label: 'Status',
          keys: ['is_operational'],
          value: (p) =>
            p.is_operational === true
              ? 'Operational'
              : p.is_operational === false
                ? 'Retired'
                : null,
        },
        { label: 'Online date', keys: ['online_date'], value: (p) => fmtText(p.online_date) },
      ],
    },
    {
      title: 'Landowner',
      fields: [
        { label: 'Owner', keys: ['parcel_owner'], value: (p) => fmtText(p.parcel_owner) },
        {
          label: 'Parcel ID',
          keys: ['parcel_id_full'],
          value: (p) => fmtText(p.parcel_id_full),
        },
      ],
    },
  ],
};

// ── distress overlay (census tract) ──────────────────────────────────────

export const DISTRESS_SCHEMA: EntitySchema = {
  kind: 'distress_overlay',
  title: (p) => overlayTypeLabel(p.overlay_type),
  tags: (p) => {
    const tags: Tag[] = [];
    if (fmtText(p.overlay_type)) {
      tags.push({ label: overlayTypeLabel(p.overlay_type), tone: 'oz' });
    }
    if (fmtBool(p.rural_flag) === 'Yes') tags.push({ label: 'Rural', tone: 'neutral' });
    return tags;
  },
  sections: [
    {
      title: 'Census tract',
      fields: [
        {
          label: 'Overlay type',
          keys: ['overlay_type'],
          value: (p) => (fmtText(p.overlay_type) ? overlayTypeLabel(p.overlay_type) : null),
        },
        { label: 'GEOID', keys: ['geoid'], value: (p) => fmtText(p.geoid) },
        { label: 'Tract', keys: ['tract'], value: (p) => fmtText(p.tract) },
        { label: 'County FIPS', keys: ['county_fips'], value: (p) => fmtText(p.county_fips) },
        { label: 'Rural', keys: ['rural_flag'], value: (p) => fmtBool(p.rural_flag) },
      ],
    },
  ],
};

// ── county (choropleth) ──────────────────────────────────────────────────

export const COUNTY_SCHEMA: EntitySchema = {
  kind: 'county',
  title: (p) => {
    const name = fmtText(p.county_name);
    return name ? `${name} County` : 'County';
  },
  tags: (p) => {
    const tags: Tag[] = [];
    if (fmtText(p.tier)) {
      tags.push({ label: distressTierLabel(p.tier), tone: 'distress' });
    }
    if (fmtBool(p.persistent_poverty) === 'Yes') {
      tags.push({ label: 'Persistent poverty', tone: 'distress' });
    }
    return tags;
  },
  sections: [
    {
      title: 'County',
      fields: [
        { label: 'County FIPS', keys: ['county_fips'], value: (p) => fmtText(p.county_fips) },
        {
          label: 'ARC economic tier',
          keys: ['tier'],
          value: (p) => (fmtText(p.tier) ? distressTierLabel(p.tier) : null),
        },
        {
          label: 'ARC distressed',
          keys: ['arc_distressed'],
          value: (p) => fmtBool(p.arc_distressed),
        },
        { label: 'ARC at-risk', keys: ['arc_at_risk'], value: (p) => fmtBool(p.arc_at_risk) },
        {
          label: 'Persistent poverty',
          keys: ['persistent_poverty'],
          value: (p) => fmtBool(p.persistent_poverty),
        },
      ],
    },
  ],
};

// ── registry ─────────────────────────────────────────────────────────────

export const ENTITY_SCHEMAS: Partial<Record<EntityKind, EntitySchema>> = {
  tower: TOWER_SCHEMA,
  parcel: PARCEL_SCHEMA,
  solar: SOLAR_SCHEMA,
  distress_overlay: DISTRESS_SCHEMA,
  county: COUNTY_SCHEMA,
};

export function entitySchema(kind: EntityKind): EntitySchema | undefined {
  return ENTITY_SCHEMAS[kind];
}
