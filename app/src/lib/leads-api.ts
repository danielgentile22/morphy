// Thin client for the Lead write-layer backend (backend/app/main.py).
//
// In dev, Vite proxies `/api/*` to the FastAPI server on :8000 (see
// vite.config.ts) so the browser only ever talks to the Vite origin.
// Override the base for other setups with `VITE_API_BASE`.

import type { LeadStatus } from './lead-status';

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

export interface LeadDetail {
  owner: OwnerSummary;
  status: LeadStatus;
  notes: string;
  updated_at: string | null;
  attempts: ContactAttempt[];
}

export interface CandidatesResponse {
  count: number;
  candidates: OwnerSummary[];
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
      headers: { 'Content-Type': 'application/json' },
      ...init,
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

export function fetchLead(displayClusterId: string): Promise<LeadDetail> {
  return request<LeadDetail>(`/leads/${encodeURIComponent(displayClusterId)}`);
}

export function updateLead(
  displayClusterId: string,
  patch: { status?: LeadStatus; notes?: string },
): Promise<LeadDetail> {
  return request<LeadDetail>(`/leads/${encodeURIComponent(displayClusterId)}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}
