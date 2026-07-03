import { describe, it, expect } from 'vitest';
import {
  parseCarriers,
  confidenceMeta,
  isInactiveLicense,
  inactiveLicenseLabel,
  CONFIDENCE_ORDER,
} from '../../src/lib/carrier';
import { carriers } from '../../src/lib/schema';

// A real AR composite carrier entry shape (see composite/05/towers.geojson).
const RAW = [
  { carrier_name: 'AT&T', callsign: 'KNKN566', license_expiry: '2031-10-01', confidence_tag: 'verified' },
  { carrier_name: 'ALLTEL Corporation', callsign: 'WPOI253', license_expiry: '2009-01-25', confidence_tag: 'likely' },
];

describe('parseCarriers', () => {
  it('parses the GeoJSON array form, preserving order + fields', () => {
    const out = parseCarriers(RAW);
    expect(out).toHaveLength(2);
    expect(out[0]).toEqual({
      carrier_name: 'AT&T',
      callsign: 'KNKN566',
      license_expiry: '2031-10-01',
      license_status: '',
      license_status_desc: '',
      confidence_tag: 'verified',
    });
    expect(out[1].confidence_tag).toBe('likely');
  });

  it('carries the license status code + label when present (M-l / #216)', () => {
    const out = parseCarriers([
      { carrier_name: 'ALLTEL', callsign: 'WPOI253', license_status: 'C', license_status_desc: 'Cancelled', confidence_tag: 'likely' },
    ]);
    expect(out[0].license_status).toBe('C');
    expect(out[0].license_status_desc).toBe('Cancelled');
  });

  it('parses the DuckDB JSON-string form (parquet row)', () => {
    expect(parseCarriers(JSON.stringify(RAW))).toEqual(parseCarriers(RAW));
  });

  it('treats empty / null / blank / malformed as no carriers', () => {
    expect(parseCarriers([])).toEqual([]);
    expect(parseCarriers('[]')).toEqual([]);
    expect(parseCarriers('')).toEqual([]);
    expect(parseCarriers(null)).toEqual([]);
    expect(parseCarriers(undefined)).toEqual([]);
    expect(parseCarriers('{not json')).toEqual([]);
  });

  it('normalises a missing/blank license_expiry to null and keeps only the known fields', () => {
    const out = parseCarriers([
      { carrier_name: 'Verizon', callsign: 'WQGA123', confidence_tag: 'possible', extra: 'drop me' },
      { carrier_name: 'T-Mobile', callsign: 'KNKA000', license_expiry: '', confidence_tag: 'possible' },
    ]);
    expect(out[0]).toEqual({
      carrier_name: 'Verizon',
      callsign: 'WQGA123',
      license_expiry: null,
      license_status: '',
      license_status_desc: '',
      confidence_tag: 'possible',
    });
    expect(out[1].license_expiry).toBeNull();
    expect(Object.keys(out[0])).not.toContain('extra');
  });

  it('keeps an unmapped carrier visible with its raw licensee name', () => {
    const out = parseCarriers([
      { carrier_name: 'SOME RURAL TELEPHONE CO-OP', callsign: 'WXYZ999', confidence_tag: 'likely' },
    ]);
    expect(out[0].carrier_name).toBe('SOME RURAL TELEPHONE CO-OP');
  });
});

describe('isInactiveLicense / inactiveLicenseLabel (M-l / #216)', () => {
  it('flags cancelled / expired / terminated / term-pending codes', () => {
    for (const code of ['C', 'E', 'T', 'X']) {
      expect(isInactiveLicense({ license_status: code })).toBe(true);
    }
  });

  it('does NOT flag active, blank (pre-#216 data) or unknown codes', () => {
    expect(isInactiveLicense({ license_status: 'A' })).toBe(false);
    expect(isInactiveLicense({ license_status: '' })).toBe(false);
    expect(isInactiveLicense({ license_status: 'P' })).toBe(false);
  });

  it('labels with the status word when carried, else a generic Inactive', () => {
    expect(
      inactiveLicenseLabel({ license_status: 'C', license_status_desc: 'Cancelled' }),
    ).toBe('Cancelled');
    expect(inactiveLicenseLabel({ license_status: 'E', license_status_desc: '' })).toBe(
      'Inactive',
    );
  });
});

describe('confidenceMeta', () => {
  it('maps verified/likely/possible to label + tone + a grounded tooltip', () => {
    const v = confidenceMeta('verified');
    expect(v.label).toBe('Verified');
    expect(v.tone).toBe('verified');
    expect(v.tooltip).toMatch(/ASR-number/i);

    const l = confidenceMeta('likely');
    expect(l.label).toBe('Likely');
    expect(l.tooltip).toMatch(/100 m/);

    const p = confidenceMeta('possible');
    expect(p.label).toBe('Possible');
    expect(p.tooltip).toMatch(/100.*500 m/);
  });

  it('degrades an unknown tag to a neutral badge that still names it', () => {
    const m = confidenceMeta('experimental');
    expect(m.tone).toBe('unknown');
    expect(m.label).toBe('Experimental');
    expect(m.tooltip).toMatch(/not recorded/i);
  });

  it('orders confidence best-first', () => {
    expect(CONFIDENCE_ORDER).toEqual(['verified', 'likely', 'possible']);
  });
});

describe('carriers(p) schema accessor', () => {
  it('reads a tower props object in the GeoJSON array form', () => {
    expect(carriers({ carriers: RAW })).toHaveLength(2);
  });
  it('reads the DuckDB JSON-string form', () => {
    expect(carriers({ carriers: JSON.stringify(RAW) })[0].carrier_name).toBe('AT&T');
  });
  it('is empty for a tower with no carriers (the common case)', () => {
    expect(carriers({})).toEqual([]);
    expect(carriers({ carriers: [] })).toEqual([]);
  });
});
