/**
 * URL → app-state sync. The query string carries the active state, the
 * selected parcel, and whether a filter set is present.
 *
 * `?state=05&selected=<parcel_id>&filters=…` — only the *presence* of a
 * `filters` param matters here (it suppresses the saved filter default);
 * its contents are owned by the live `FilterModel`, not parsed here.
 */

export interface UrlState {
  state: string | null;
  selected: string | null;
  /** True when the URL carries a `filters` param. */
  hasFilters: boolean;
}

export function readUrlState(search: string): UrlState {
  const params = new URLSearchParams(search);
  return {
    state: params.get('state'),
    selected: params.get('selected'),
    hasFilters: params.get('filters') !== null,
  };
}
