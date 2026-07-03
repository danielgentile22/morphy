// Thin client for the Lead write-layer backend (backend/app/main.py).
//
// In dev, Vite proxies `/api/*` to the FastAPI server on :8000 (see
// vite.config.ts) so the browser only ever talks to the Vite origin.
// Override the base for other setups with `VITE_API_BASE`.

import type { LeadStatus } from './lead-status';
import type { FilterableOwner } from './filter-model';
import type { Carrier } from './carrier';
import type { BasemapName } from './basemap';
import type { components } from './api-types';

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api';

// Request/response shapes come from the generated OpenAPI types module
// (api-types.ts, PRD #133) — regenerate with `npm run generate:api` after a
// backend model change; CI fails on drift. The aliases below only NARROW the
// generated shapes with client-side semantics the schema can't express (the
// status ladder, tuple coordinates) or restore the presence of fields the
// schema marks optional-with-default but the server always serializes
// (`Required<…>`). Field presence/absence otherwise flows from the schema.
type Schemas = components['schemas'];

export type OwnerSummary = Omit<Schemas['OwnerSummary'], 'status'> & {
  status: LeadStatus;
};

/** Adapt an OwnerSummary to the shape the shared FilterModel predicate reads,
 *  filling the v3 rollups (which an older backend may omit) from what's
 *  present — so the Candidates list and the map narrow by the same logic. */
export function ownerSummaryToFilterable(o: OwnerSummary): FilterableOwner {
  return {
    states: o.states,
    counties: o.counties ?? [],
    owner_kind: o.owner_kind,
    distress_tier: o.distress_tier,
    in_oz: o.in_oz,
    in_qct: o.in_qct,
    persistent_poverty: o.persistent_poverty,
    score: o.score,
    parcel_count: o.parcel_count,
    total_assessed_value: o.total_assessed_value,
    tower_count: o.tower_count,
    solar_count: o.solar_count,
    structure_count: o.structure_count ?? o.tower_count + o.solar_count,
    structure_types:
      o.structure_types ??
      [...(o.tower_count > 0 ? ['tower'] : []), ...(o.solar_count > 0 ? ['solar'] : [])],
    active_tower_count: o.active_tower_count ?? 0,
    tallest_tower_height_m: o.tallest_tower_height_m ?? null,
    carrier_count: o.carrier_count ?? 0,
  };
}

export type ActivityDirection = 'outbound' | 'inbound';

// outbound touch | inbound reply (#106, ADR-066) — narrowed from the
// schema's plain string.
export type ContactAttempt = Omit<Schemas['ContactAttemptOut'], 'direction'> & {
  direction: ActivityDirection;
};

// `carriers` keeps the frontend Carrier shape (carrier.ts — the typed home
// both surfaces + tests share); a generated CarrierOut is assignable to it.
// Empty/absent is the common case (most ASR towers match no ULS license).
export type Structure = Omit<Schemas['Structure'], 'type' | 'carriers'> & {
  type: 'tower' | 'solar';
  carriers?: Carrier[] | null;
};

export type Holding = Omit<Required<Schemas['Holding']>, 'bbox' | 'point' | 'structures'> & {
  // [minlng, minlat, maxlng, maxlat] and [lng, lat], EPSG:4326.
  bbox: [number, number, number, number] | null;
  point: [number, number] | null;
  structures: Structure[];
};

export type MailingAddress = Schemas['MailingAddress'];

/** Fields the co-founder edits on a Lead (the backend `LeadUpdate` contact
 *  fields, picked from the generated detail shape). */
export type ContactFields = Pick<
  Schemas['LeadDetail'],
  'contact_name' | 'contact_phone' | 'contact_email' | 'best_channel'
>;

/** A raw owner-cluster merged into this Lead (Slice 7 / #53). */
export type MergedMember = Schemas['MergedMember'];

export type LeadDetail = Omit<
  Required<Schemas['LeadDetail']>,
  'owner' | 'status' | 'attempts' | 'holdings'
> & {
  owner: OwnerSummary;
  status: LeadStatus;
  attempts: ContactAttempt[];
  holdings: Holding[];
};

/** The body POSTed to log a manual activity event. ``direction='inbound'``
 *  logs a reply; omitted (or 'outbound') logs a touch (#106). */
export type AttemptPayload = Omit<Schemas['ContactAttemptIn'], 'direction'> & {
  direction?: ActivityDirection;
};

/** A partial Lead update — status and/or notes and/or contact fields. */
export type LeadPatch = Omit<Schemas['LeadUpdate'], 'status'> & {
  status?: LeadStatus | null;
};

export type CandidatesResponse = Omit<Schemas['CandidatesResponse'], 'candidates'> & {
  candidates: OwnerSummary[];
};

/** The My-Leads worklist — owners advanced off New (Slice 5 / #51). */
export type MyLeadsResponse = Omit<Schemas['MyLeadsResponse'], 'leads'> & {
  leads: OwnerSummary[];
};

/** Live nav counts for the two list surfaces. */
export type CountsResponse = Schemas['CountsResponse'];

export type TokenResponse = Schemas['TokenResponse'];

export type MeResponse = Schemas['MeResponse'];

/** Per-user preferences (PRD #121). `home_view` / `filter_default` are opaque
 *  JSON strings this client owns; the backend stores + serves them verbatim. */
export type UserSettings = Omit<
  Schemas['UserSettingsResponse'],
  'theme' | 'basemap' | 'view_mode'
> & {
  theme: 'light' | 'dark' | 'system';
  basemap: BasemapName;
  view_mode: 'home' | 'last';
};

/** Error carrying the HTTP status so callers can branch (e.g. 409 illegal). */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** The shared fetch wrapper: maps non-2xx to an ApiError carrying the status.
 *  Auth rides in the httpOnly session cookie (PRD #130), which the browser
 *  attaches to same-origin requests automatically — no header plumbing here.
 *  Reused by the tasks client (tasks-api.ts) so every backend call shares one
 *  error path. */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers as Record<string, string> | undefined),
      },
    });
  } catch (e) {
    throw new ApiError(
      `Cannot reach the Lead backend at ${API_BASE}. Is it running (uvicorn backend.app.main:app)?`,
      0,
    );
  }
  if (!res.ok) {
    const detail = await res
      .json()
      .then((b) => (b as { detail?: string }).detail)
      .catch(() => null);
    throw new ApiError(detail ?? `${res.status} ${res.statusText}`, res.status);
  }
  // 204 No Content (e.g. DELETE) has no body — resolve to undefined.
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function fetchCandidates(limit = 200): Promise<CandidatesResponse> {
  return request<CandidatesResponse>(`/candidates?limit=${limit}`);
}

export function fetchMyLeads(): Promise<MyLeadsResponse> {
  return request<MyLeadsResponse>('/my-leads');
}

export function fetchCounts(): Promise<CountsResponse> {
  return request<CountsResponse>('/counts');
}

export function fetchLead(displayClusterId: string): Promise<LeadDetail> {
  return request<LeadDetail>(`/leads/${encodeURIComponent(displayClusterId)}`);
}

export function updateLead(displayClusterId: string, patch: LeadPatch): Promise<LeadDetail> {
  return request<LeadDetail>(`/leads/${encodeURIComponent(displayClusterId)}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export function appendAttempt(
  displayClusterId: string,
  payload: AttemptPayload,
): Promise<LeadDetail> {
  return request<LeadDetail>(`/leads/${encodeURIComponent(displayClusterId)}/attempts`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** Pursue an owner from Explore (#109): advance New → Researching and record
 *  the triggering antenna. Returns the (now-worked) Lead. */
export function pursueOwner(displayClusterId: string, triggerAsr: string): Promise<LeadDetail> {
  return request<LeadDetail>(`/leads/${encodeURIComponent(displayClusterId)}/pursue`, {
    method: 'POST',
    body: JSON.stringify({ trigger_asr: triggerAsr }),
  });
}

/** Merge `sourceClusterId` into this Lead (the survivor). Afterward the source
 *  resolves to this Lead everywhere (Slice 7 / #53). Returns the merged Lead. */
export function mergeCluster(
  displayClusterId: string,
  sourceClusterId: string,
): Promise<LeadDetail> {
  return request<LeadDetail>(`/leads/${encodeURIComponent(displayClusterId)}/merge`, {
    method: 'POST',
    body: JSON.stringify({ source_cluster_id: sourceClusterId }),
  });
}

/** Split `sourceClusterId` back out of this Lead — it returns to its own raw
 *  cluster. Reverses a prior merge. Returns the updated (target) Lead. */
export function splitCluster(
  displayClusterId: string,
  sourceClusterId: string,
): Promise<LeadDetail> {
  return request<LeadDetail>(`/leads/${encodeURIComponent(displayClusterId)}/split`, {
    method: 'POST',
    body: JSON.stringify({ source_cluster_id: sourceClusterId }),
  });
}

// ── per-antenna manual state (UI overhaul round 2) ───────────────────────────
/** The team's editable layer over one antenna (by ASR) — an address, an
 *  archived flag, and manual owner details for a tower whose landowner we
 *  couldn't auto-resolve. */
export type AntennaState = Schemas['AntennaState'];

/** A partial antenna update — omit a field to leave it unchanged. */
export type AntennaUpdate = Schemas['AntennaUpdate'];

export function fetchAntenna(asr: string): Promise<AntennaState> {
  return request<AntennaState>(`/antennas/${encodeURIComponent(asr)}`);
}

export function updateAntenna(asr: string, patch: AntennaUpdate): Promise<AntennaState> {
  return request<AntennaState>(`/antennas/${encodeURIComponent(asr)}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

/** The ASRs this tenant has archived — the map + list drop them by default. */
export function fetchArchivedAsrs(): Promise<{ asrs: string[] }> {
  return request<{ asrs: string[] }>('/antennas/archived');
}

// ── auth (Slice 1 / #76; cookie sessions PRD #130) ───────────────────────────
/** Sign in. The response also sets the httpOnly session cookie — the body's
 *  access_token is unused by the SPA (kept for non-browser clients). */
export function login(username: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

/** Sign out: the backend clears the session cookie, ending data access too. */
export function logout(): Promise<void> {
  return request<void>('/auth/logout', { method: 'POST' });
}

export function fetchMe(): Promise<MeResponse> {
  return request<MeResponse>('/auth/me');
}

// ── per-user self-service (PRD #121) ─────────────────────────────────────────
export function fetchMySettings(): Promise<UserSettings> {
  return request<UserSettings>('/me/settings');
}

export function saveMySettings(patch: Partial<UserSettings>): Promise<UserSettings> {
  return request<UserSettings>('/me/settings', {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export function updateDisplayName(displayName: string): Promise<MeResponse> {
  return request<MeResponse>('/me', {
    method: 'PUT',
    body: JSON.stringify({ display_name: displayName }),
  });
}

/** Change my password. Resolves on success; rejects with an ApiError whose
 *  status is 401 when the current password is wrong. */
export function changeMyPassword(currentPassword: string, newPassword: string): Promise<void> {
  return request<void>('/me/password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}
