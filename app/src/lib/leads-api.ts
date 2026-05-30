// Thin client for the Lead write-layer backend (backend/app/main.py).
//
// In dev, Vite proxies `/api/*` to the FastAPI server on :8000 (see
// vite.config.ts) so the browser only ever talks to the Vite origin.
// Override the base for other setups with `VITE_API_BASE`.

import type { LeadStatus } from './lead-status';
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
}

export interface ContactAttempt {
  id: number;
  occurred_on: string;
  channel: string;
  outcome: string;
  note: string;
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

export interface LeadDetail extends ContactFields {
  owner: OwnerSummary;
  status: LeadStatus;
  notes: string;
  updated_at: string | null;
  attempts: ContactAttempt[];
  mailing_address: MailingAddress | null;
  tallest_tower_height_m: number | null;
  holdings: Holding[];
}

/** The body POSTed to log a manual contact attempt. */
export interface AttemptPayload {
  channel: string;
  outcome: string;
  note: string;
  occurred_on: string | null;
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

export interface RequestLinkResponse {
  ok: boolean;
  // Present only in dev (AUTH_EXPOSE_TOKEN on) so the SPA can finish the
  // exchange without a real inbox; null in prod.
  dev_token: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface MeResponse {
  tenant_id: number;
  email: string;
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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

// ── auth (Slice 2 / #48) ────────────────────────────────────────────────────
export function requestLink(email: string): Promise<RequestLinkResponse> {
  return request<RequestLinkResponse>('/auth/request-link', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

export function exchangeToken(token: string): Promise<TokenResponse> {
  return request<TokenResponse>('/auth/exchange', {
    method: 'POST',
    body: JSON.stringify({ token }),
  });
}

export function fetchMe(): Promise<MeResponse> {
  return request<MeResponse>('/auth/me');
}
