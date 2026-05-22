import { describe, it, expect } from 'vitest';
import {
  TOWER_SCHEMA,
  PARCEL_SCHEMA,
  SOLAR_SCHEMA,
  DISTRESS_SCHEMA,
  COUNTY_SCHEMA,
  entitySchema,
  infrastructureItems,
  scoreComponents,
  type EntitySchema,
  type Props,
} from '../../src/lib/schema';

// Sample props mirroring real AR composite features (see inspect.py output).
const AR_TOWER: Props = {
  asr_number: '080946',
  city: 'EUDORA',
  height_m: 79.248,
  lat: 33.00588,
  lon: -91.31267,
  status: 'O',
  status_desc: 'Other',
  structure_type: 'TOWER',
  structure_type_desc: 'TOWER',
  is_active: true,
  in_oz: false,
  in_qct: true,
  distress_tier: '',
  distress_overlays: ['qct'],
  owner_name: '',
  parcel_owner: 'MITCHELL VICKI',
  parcel_id_full: '017-010-04119-000',
  parcel_acreage: 10.0,
  parcel_value: 5950.0,
  parcel_use_code: 'AI',
  persistent_poverty: 'False',
  date_built: null,
  street: null,
  zip: null,
};

const AR_PARCEL: Props = {
  parcel_id: '0001-05431-0000',
  parcel_id_full: '123-0001-05431-0000',
  owner_name: 'BURCH, LAN CO TRUSTEE OF BURCH FAMILY FARM TRUST &',
  owner_name_2: '',
  owner_kind: 'trust',
  mailing_addr: '123 FARM RD',
  mailing_city: 'STAR CITY',
  mailing_state: 'AR',
  mailing_zip: '71667',
  situs_addr: '',
  situs_city: '',
  county_fips: '05123',
  acreage: 285.790008545,
  land_use_desc: 'AV',
  land_use_code: 'AV',
  year_built: null,
  assessed_value: 299935.0,
  land_value: 299935.0,
  improvement_value: 0.0,
  owner_cluster_size: 3,
  owner_cluster_value_total: 791935.0,
  tower_count: 2,
  solar_count: 1,
  billboard_count: 0,
  distress_tier: 'distressed',
  in_oz: false,
  in_qct: true,
  persistent_poverty: true,
  distress_overlays: ['qct'],
  interestingness_score: 0.9,
  interestingness_components: {
    infrastructure: 0.4,
    distress_overlays: 0.2,
    county_tier: 0.15,
    owner_kind: 0.1,
  },
  infrastructure_summary: [
    { type: 'tower', id: '115833', owner: '' },
    { type: 'tower', id: '1329672', owner: '' },
  ],
};

/** Find a field's rendered value by its label. */
function renderField(schema: EntitySchema, label: string, props: Props): string | null {
  for (const section of schema.sections) {
    for (const f of section.fields) {
      if (f.label === label) return f.value(props);
    }
  }
  throw new Error(`no field labelled "${label}" in the ${schema.kind} schema`);
}

describe('entitySchema registry', () => {
  it('resolves every entity kind the map can render', () => {
    expect(entitySchema('tower')).toBe(TOWER_SCHEMA);
    expect(entitySchema('parcel')).toBe(PARCEL_SCHEMA);
    expect(entitySchema('solar')).toBe(SOLAR_SCHEMA);
    expect(entitySchema('distress_overlay')).toBe(DISTRESS_SCHEMA);
    expect(entitySchema('county')).toBe(COUNTY_SCHEMA);
  });
});

describe('schema structure', () => {
  for (const schema of [
    TOWER_SCHEMA,
    PARCEL_SCHEMA,
    SOLAR_SCHEMA,
    DISTRESS_SCHEMA,
    COUNTY_SCHEMA,
  ]) {
    it(`${schema.kind}: every field is well-formed`, () => {
      expect(schema.sections.length).toBeGreaterThan(0);
      for (const section of schema.sections) {
        expect(section.title).toBeTruthy();
        expect(section.fields.length).toBeGreaterThan(0);
        for (const f of section.fields) {
          expect(f.label).toBeTruthy();
          expect(Array.isArray(f.keys)).toBe(true);
          expect(f.keys.length).toBeGreaterThan(0);
          expect(typeof f.value).toBe('function');
        }
      }
    });
  }
});

describe('TOWER_SCHEMA against a real AR tower', () => {
  it('titles by ASR number', () => {
    expect(TOWER_SCHEMA.title(AR_TOWER)).toBe('Tower 080946');
  });

  it('tags QCT and an identified landowner, but not OZ', () => {
    const labels = TOWER_SCHEMA.tags(AR_TOWER).map((t) => t.label);
    expect(labels).toContain('QCT');
    expect(labels).toContain('Landowner identified');
    expect(labels).not.toContain('Opportunity Zone');
  });

  it('shows the denormalised landowner — the pitch-critical fields', () => {
    expect(renderField(TOWER_SCHEMA, 'Owner', AR_TOWER)).toBe('MITCHELL VICKI');
    expect(renderField(TOWER_SCHEMA, 'Parcel value', AR_TOWER)).toBe('$5,950');
    expect(renderField(TOWER_SCHEMA, 'Parcel acreage', AR_TOWER)).toBe('10.00 ac');
  });

  it('renders the tower facts with v3 field names', () => {
    expect(renderField(TOWER_SCHEMA, 'Height', AR_TOWER)).toBe('79.2 m (260 ft)');
    expect(renderField(TOWER_SCHEMA, 'Status', AR_TOWER)).toBe('Other');
    expect(renderField(TOWER_SCHEMA, 'Coordinates', AR_TOWER)).toBe('33.00588, -91.31267');
    expect(renderField(TOWER_SCHEMA, 'Active', AR_TOWER)).toBe('Yes');
  });

  it('returns null (not a crash) for genuinely-empty fields', () => {
    // owner_name is empty on most towers; distress_tier is blank.
    expect(renderField(TOWER_SCHEMA, 'FAA registrant', AR_TOWER)).toBeNull();
    expect(renderField(TOWER_SCHEMA, 'County economic tier', AR_TOWER)).toBeNull();
  });

  it('joins the distress_overlays array into labels', () => {
    expect(renderField(TOWER_SCHEMA, 'Distress overlays', AR_TOWER)).toBe(
      'Qualified Census Tract',
    );
  });
});

describe('PARCEL_SCHEMA against a real AR parcel', () => {
  it('titles by parcel id', () => {
    expect(PARCEL_SCHEMA.title(AR_PARCEL)).toBe('Parcel 0001-05431-0000');
  });

  it('tags the distress tier and hosted infrastructure', () => {
    const labels = PARCEL_SCHEMA.tags(AR_PARCEL).map((t) => t.label);
    expect(labels).toContain('Distressed');
    expect(labels).toContain('2 towers');
    expect(labels).toContain('1 solar facility');
    expect(labels).toContain('QCT');
  });

  it('shows owner, valuation and score — the pitch-critical fields', () => {
    expect(renderField(PARCEL_SCHEMA, 'Owner', AR_PARCEL)).toContain('BURCH');
    expect(renderField(PARCEL_SCHEMA, 'Owner type', AR_PARCEL)).toBe('Trust');
    expect(renderField(PARCEL_SCHEMA, 'Assessed value', AR_PARCEL)).toBe('$299,935');
    expect(renderField(PARCEL_SCHEMA, 'Score', AR_PARCEL)).toBe('0.90');
  });

  it('composes the mailing address from its four parts', () => {
    expect(renderField(PARCEL_SCHEMA, 'Mailing address', AR_PARCEL)).toBe(
      '123 FARM RD, STAR CITY, AR, 71667',
    );
  });

  it('renders infrastructure counts', () => {
    expect(renderField(PARCEL_SCHEMA, 'Towers', AR_PARCEL)).toBe('2');
    expect(renderField(PARCEL_SCHEMA, 'Solar facilities', AR_PARCEL)).toBe('1');
    expect(renderField(PARCEL_SCHEMA, 'Billboards', AR_PARCEL)).toBe('0');
  });
});

const AR_SOLAR: Props = {
  name: 'Carpenter',
  operator: 'Entergy Arkansas LLC',
  technology: '',
  capacity_mw: null,
  is_operational: true,
  tracking_type: 'fixed',
  online_date: null,
  facility_id: '166',
  parcel_owner: 'ENTERGY ARKANSAS INC',
  parcel_id_full: '051-100-08774-000U',
};

const AR_DISTRESS: Props = {
  overlay_type: 'opportunity_zone',
  geoid: '05107480600',
  tract: '480600',
  county_fips: '05107',
  rural_flag: 'True',
};

describe('SOLAR_SCHEMA against a real AR solar facility', () => {
  it('titles by facility name', () => {
    expect(SOLAR_SCHEMA.title(AR_SOLAR)).toBe('Carpenter');
  });
  it('shows the operator, status and landowner', () => {
    expect(renderField(SOLAR_SCHEMA, 'Operator', AR_SOLAR)).toBe('Entergy Arkansas LLC');
    expect(renderField(SOLAR_SCHEMA, 'Status', AR_SOLAR)).toBe('Operational');
    expect(renderField(SOLAR_SCHEMA, 'Owner', AR_SOLAR)).toBe('ENTERGY ARKANSAS INC');
  });
});

describe('DISTRESS_SCHEMA against a real AR distress overlay', () => {
  it('titles by overlay type', () => {
    expect(DISTRESS_SCHEMA.title(AR_DISTRESS)).toBe('Opportunity Zone');
  });
  it('tags the overlay type', () => {
    expect(DISTRESS_SCHEMA.tags(AR_DISTRESS).map((t) => t.label)).toContain('Opportunity Zone');
  });
  it('shows the tract identifiers', () => {
    expect(renderField(DISTRESS_SCHEMA, 'GEOID', AR_DISTRESS)).toBe('05107480600');
    expect(renderField(DISTRESS_SCHEMA, 'Tract', AR_DISTRESS)).toBe('480600');
    // rural_flag arrives as the string 'True'.
    expect(renderField(DISTRESS_SCHEMA, 'Rural', AR_DISTRESS)).toBe('Yes');
  });
});

const AR_COUNTY: Props = {
  county_fips: '05001',
  county_name: 'Arkansas',
  tier: 'transitional',
  arc_distressed: false,
  arc_at_risk: false,
  persistent_poverty: false,
};

describe('COUNTY_SCHEMA against a real AR county', () => {
  it('titles by county name', () => {
    expect(COUNTY_SCHEMA.title(AR_COUNTY)).toBe('Arkansas County');
  });
  it('tags the ARC economic tier', () => {
    expect(COUNTY_SCHEMA.tags(AR_COUNTY).map((t) => t.label)).toContain('Transitional');
  });
  it('renders the tier and ARC flags', () => {
    expect(renderField(COUNTY_SCHEMA, 'County FIPS', AR_COUNTY)).toBe('05001');
    expect(renderField(COUNTY_SCHEMA, 'ARC economic tier', AR_COUNTY)).toBe('Transitional');
    expect(renderField(COUNTY_SCHEMA, 'ARC distressed', AR_COUNTY)).toBe('No');
    expect(renderField(COUNTY_SCHEMA, 'Persistent poverty', AR_COUNTY)).toBe('No');
  });
});

describe('nested-structure parsers', () => {
  it('infrastructureItems parses the summary list', () => {
    const items = infrastructureItems(AR_PARCEL);
    expect(items).toHaveLength(2);
    expect(items[0]).toEqual({ type: 'tower', id: '115833', owner: '' });
  });
  it('infrastructureItems is empty for a parcel with no summary', () => {
    expect(infrastructureItems({})).toEqual([]);
  });
  it('scoreComponents parses and sorts components descending', () => {
    const comps = scoreComponents(AR_PARCEL);
    expect(comps[0]).toEqual({ factor: 'infrastructure', weight: 0.4 });
    expect(comps.map((c) => c.weight)).toEqual([...comps.map((c) => c.weight)].sort((a, b) => b - a));
  });
  it('scoreComponents is empty when absent', () => {
    expect(scoreComponents({})).toEqual([]);
  });

  // A DuckDB parquet row delivers the nested columns as JSON strings,
  // not arrays/objects — the parsers must accept either.
  it('infrastructureItems accepts a JSON-string column (DuckDB row)', () => {
    const items = infrastructureItems({
      infrastructure_summary: '[{"type":"tower","id":"42","owner":"ACME"}]',
    });
    expect(items).toEqual([{ type: 'tower', id: '42', owner: 'ACME' }]);
  });
  it('scoreComponents accepts a JSON-string column (DuckDB row)', () => {
    const comps = scoreComponents({
      interestingness_components: '{"infrastructure":0.6,"distress":0.2}',
    });
    expect(comps).toEqual([
      { factor: 'infrastructure', weight: 0.6 },
      { factor: 'distress', weight: 0.2 },
    ]);
  });
});
