// Thin client for the Lead write-layer backend (backend/app/main.py).
//
// In dev, Vite proxies `/api/*` to the FastAPI server on :8000 (see
// vite.config.ts) so the browser only ever talks to the Vite origin.
// Override the base for other setups with `VITE_API_BASE`.

import type { LeadStatus } from './lead-status';
import type { FilterableOwner } from './filter-model';
import type { Carrier } from './carrier';
import { authHeader } from './auth-token';

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api';

export interface OwnerSummary {
  display_cluster_id: string;
  owner_name: string;
  owner_kind: string;
  states: string[];
  n_states: number;
  cross_state: boolean;
  parcel_count: number;
  tower_count: number;
  solar_count: number;
  total_assessed_value: number;
  max_parcel_score: number;
  score: number;
  distress_tier: string;
  in_oz: boolean;
  in_qct: boolean;
  persistent_poverty: boolean;
  status: LeadStatus;
  // Owner-level filter rollups (Slice 6 / #52) — let the shared FilterModel
  // narrow the Candidates list with the same predicate the map uses. Optional
  // so an older backend/index still parses (the filters they back no-op then).
  counties?: string[];
  structure_count?: number;
  structure_types?: string[];
  active_tower_count?: number;
  tallest_tower_height_m?: number | null;
  // The antenna that sparked pursuit (#109, ADR-067/D2) — '' until pursued.
  trigger_asr?: string;
}

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
  };
}

export type ActivityDirection = 'outbound' | 'inbound';

export interface ContactAttempt {
  id: number;
  occurred_on: string;
  channel: string;
  outcome: string;
  note: string;
  // outbound touch | inbound reply (#106, ADR-066). Optional so a row from an
  // older backend (pre-direction) still parses — treat a missing value as
  // outbound (the only kind before replies existed).
  direction?: ActivityDirection;
}

export interface Structure {
  type: 'tower' | 'solar';
  asr?: string | null;
  id?: string | null;
  height_m?: number | null;
  lat?: number | null;
  lon?: number | null;
  active?: boolean | null;
  structure_kind?: string | null;
  owner?: string | null;
  // ULS spectrum licensee(s) on this tower (Slice A / #28). Absent on solar
  // entries, and on a pre-carriers index (older backend) — treat as []. Empty
  // is the common case (most ASR towers carry no matched ULS per-site license).
  carriers?: Carrier[] | null;
  // Per-tower interestingness score (UI overhaul P1 / #105) — the tower's
  // underlying parcel's score. Absent on solar entries and on a pre-v5 index.
  score?: number | null;
}

export interface Holding {
  parcel_id: string;
  state: string;
  county_fips: string;
  land_use: string;
  assessed_value: number;
  acreage: number | null;
  tower_count: number;
  solar_count: number;
  // [minlng, minlat, maxlng, maxlat] and [lng, lat], EPSG:4326.
  bbox: [number, number, number, number] | null;
  point: [number, number] | null;
  structures: Structure[];
}

export interface MailingAddress {
  addr: string;
  city: string;
  state: string;
  zip: string;
}

/** Fields the co-founder edits on a Lead (kept in lockstep with the
 *  backend `LeadUpdate` contact fields). */
export interface ContactFields {
  contact_name: string;
  contact_phone: string;
  contact_email: string;
  best_channel: string;
}

/** A raw owner-cluster merged into this Lead (Slice 7 / #53). */
export interface MergedMember {
  display_cluster_id: string;
  owner_name: string;
}

export interface LeadDetail extends ContactFields {
  owner: OwnerSummary;
  status: LeadStatus;
  notes: string;
  updated_at: string | null;
  attempts: ContactAttempt[];
  mailing_address: MailingAddress | null;
  tallest_tower_height_m: number | null;
  holdings: Holding[];
  // Owner-clusters merged into this Lead via a manual override; empty when none.
  merged_members: MergedMember[];
}

/** The body POSTed to log a manual activity event. ``direction='inbound'``
 *  logs a reply; omitted (or 'outbound') logs a touch (#106). */
export interface AttemptPayload {
  channel: string;
  outcome: string;
  note: string;
  occurred_on: string | null;
  direction?: ActivityDirection;
}

export interface CandidatesResponse {
  count: number;
  candidates: OwnerSummary[];
}

/** The My-Leads worklist — owners advanced off New (Slice 5 / #51). */
export interface MyLeadsResponse {
  count: number;
  leads: OwnerSummary[];
}

/** Live nav counts for the two list surfaces. */
export interface CountsResponse {
  candidates: number;
  my_leads: number;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface MeResponse {
  tenant_id: number;
  email: string;
  // The signed-in user's team name (#86). Optional so an older backend
  // (pre-teams) still parses; the nav just omits the team then.
  team?: string;
  // The friendly name set in Settings (PRD #121); '' falls back to the email.
  display_name?: string;
}

/** Per-user preferences (PRD #121). `home_view` / `filter_default` are opaque
 *  JSON strings this client owns; the backend stores + serves them verbatim. */
export interface UserSettings {
  theme: 'light' | 'dark' | 'system';
  colorblind: boolean;
  basemap: 'light' | 'voyager' | 'dark';
  view_mode: 'home' | 'last';
  home_view: string;
  filter_default: string;
  filter_default_apply: boolean;
}

/** Error carrying the HTTP status so callers can branch (e.g. 409 illegal). */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** The shared fetch wrapper: attaches the Bearer JWT, maps non-2xx to an
 *  ApiError carrying the status. Reused by the tasks client (tasks-api.ts) so
 *  every backend call shares one auth + error path. */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      // Attach the Bearer JWT to every call; an explicit init.headers wins.
      headers: {
        'Content-Type': 'application/json',
        ...authHeader(),
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

export function updateLead(
  displayClusterId: string,
  patch: { status?: LeadStatus; notes?: string } & Partial<ContactFields>,
): Promise<LeadDetail> {
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
 *  couldn't auto-resolve. Mirrors the backend `AntennaState`. */
export interface AntennaState {
  asr: string;
  archived: boolean;
  address: string;
  owner_name: string;
  owner_phone: string;
  owner_email: string;
  notes: string;
}

/** A partial antenna update — omit a field to leave it unchanged. */
export type AntennaUpdate = Partial<Omit<AntennaState, 'asr'>>;

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

// ── auth (Slice 1 / #76) ────────────────────────────────────────────────────
export function login(username: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
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
