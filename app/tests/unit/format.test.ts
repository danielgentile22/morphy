import { describe, it, expect } from 'vitest';
import {
  fmtMoney,
  fmtAcres,
  fmtMeters,
  fmtLatLng,
  formatPhone,
  fmtInt,
  fmtYear,
  fmtScore,
  fmtMw,
  fmtBool,
  fmtText,
  joinNonEmpty,
  hasValue,
  escapeHtml,
} from '../../src/lib/format';

describe('fmtMoney', () => {
  it('formats whole dollars with separators', () => {
    expect(fmtMoney(299935)).toBe('$299,935');
    expect(fmtMoney(5950)).toBe('$5,950');
  });
  it('handles zero and rounds floats', () => {
    expect(fmtMoney(0)).toBe('$0');
    expect(fmtMoney(299935.0)).toBe('$299,935');
    expect(fmtMoney(12.6)).toBe('$13');
  });
  it('accepts numeric strings (int64 vs float64 drift across states)', () => {
    expect(fmtMoney('113948')).toBe('$113,948');
  });
  it('returns null for absent / non-numeric input', () => {
    expect(fmtMoney(null)).toBeNull();
    expect(fmtMoney(undefined)).toBeNull();
    expect(fmtMoney('')).toBeNull();
    expect(fmtMoney('n/a')).toBeNull();
    expect(fmtMoney(NaN)).toBeNull();
  });
});

describe('fmtAcres', () => {
  it('formats to two decimals', () => {
    expect(fmtAcres(285.790008545)).toBe('285.79 ac');
    expect(fmtAcres(10)).toBe('10.00 ac');
    expect(fmtAcres(0)).toBe('0.00 ac');
  });
  it('returns null for absent input', () => {
    expect(fmtAcres(null)).toBeNull();
    expect(fmtAcres('')).toBeNull();
  });
});

describe('fmtMeters', () => {
  it('formats metres with a feet conversion', () => {
    expect(fmtMeters(79.248)).toBe('79.2 m (260 ft)');
    expect(fmtMeters(100)).toBe('100.0 m (328 ft)');
  });
  it('returns null for absent input', () => {
    expect(fmtMeters(null)).toBeNull();
    expect(fmtMeters('')).toBeNull();
  });
});

describe('fmtLatLng', () => {
  it('formats a coordinate pair to five decimals', () => {
    expect(fmtLatLng(33.00588055, -91.31267222)).toBe('33.00588, -91.31267');
  });
  it('returns null unless both are numeric', () => {
    expect(fmtLatLng(33, null)).toBeNull();
    expect(fmtLatLng(null, -91)).toBeNull();
    expect(fmtLatLng(null, null)).toBeNull();
  });
});

describe('formatPhone', () => {
  it('formats a 10-digit number', () => {
    expect(formatPhone('5015551234')).toBe('(501) 555-1234');
    expect(formatPhone('(501) 555-1234')).toBe('(501) 555-1234');
  });
  it('returns non-10-digit input unchanged', () => {
    expect(formatPhone('123')).toBe('123');
  });
  it('returns null for absent input', () => {
    expect(formatPhone(null)).toBeNull();
    expect(formatPhone('')).toBeNull();
  });
});

describe('fmtInt', () => {
  it('formats integers with separators', () => {
    expect(fmtInt(2116976)).toBe('2,116,976');
    expect(fmtInt(0)).toBe('0');
  });
  it('returns null for absent input', () => {
    expect(fmtInt(null)).toBeNull();
  });
});

describe('fmtYear', () => {
  it('drops the float decimal', () => {
    expect(fmtYear(1998)).toBe('1998');
    expect(fmtYear(1998.0)).toBe('1998');
  });
  it('treats zero / negative / absent as no data', () => {
    expect(fmtYear(0)).toBeNull();
    expect(fmtYear(-1)).toBeNull();
    expect(fmtYear(null)).toBeNull();
  });
});

describe('fmtScore', () => {
  it('formats a 0-1 score to two decimals', () => {
    expect(fmtScore(0.9)).toBe('0.90');
    expect(fmtScore(0.95)).toBe('0.95');
    expect(fmtScore(0)).toBe('0.00');
  });
  it('returns null for absent input', () => {
    expect(fmtScore(null)).toBeNull();
  });
});

describe('fmtMw', () => {
  it('formats generating capacity', () => {
    expect(fmtMw(4.5)).toBe('4.5 MW');
    expect(fmtMw(100)).toBe('100.0 MW');
  });
  it('returns null for absent input', () => {
    expect(fmtMw(null)).toBeNull();
    expect(fmtMw('')).toBeNull();
  });
});

describe('fmtBool', () => {
  it('formats real booleans', () => {
    expect(fmtBool(true)).toBe('Yes');
    expect(fmtBool(false)).toBe('No');
  });
  it('formats stringified booleans (towers carry persistent_poverty as a string)', () => {
    expect(fmtBool('True')).toBe('Yes');
    expect(fmtBool('false')).toBe('No');
    expect(fmtBool('False')).toBe('No');
  });
  it('returns null for non-boolean input', () => {
    expect(fmtBool(null)).toBeNull();
    expect(fmtBool('maybe')).toBeNull();
    expect(fmtBool(1)).toBeNull();
  });
});

describe('fmtText', () => {
  it('trims and passes through non-empty text', () => {
    expect(fmtText('  hello ')).toBe('hello');
    expect(fmtText(5)).toBe('5');
  });
  it('returns null for empty / blank / absent', () => {
    expect(fmtText('')).toBeNull();
    expect(fmtText('   ')).toBeNull();
    expect(fmtText(null)).toBeNull();
    expect(fmtText(undefined)).toBeNull();
  });
});

describe('joinNonEmpty', () => {
  it('joins non-empty parts', () => {
    expect(joinNonEmpty(['123 Main', '', 'Eudora', 'AR'])).toBe('123 Main, Eudora, AR');
  });
  it('honours a custom separator', () => {
    expect(joinNonEmpty(['a', 'b'], ' / ')).toBe('a / b');
  });
  it('returns null when every part is empty', () => {
    expect(joinNonEmpty([null, undefined, '', '  '])).toBeNull();
  });
});

describe('hasValue', () => {
  it('is true for real values', () => {
    expect(hasValue('x')).toBe(true);
    expect(hasValue(0)).toBe(true);
    expect(hasValue(false)).toBe(true);
    expect(hasValue(['a'])).toBe(true);
    expect(hasValue({ k: 1 })).toBe(true);
  });
  it('is false for empty / absent values', () => {
    expect(hasValue(null)).toBe(false);
    expect(hasValue(undefined)).toBe(false);
    expect(hasValue('')).toBe(false);
    expect(hasValue('   ')).toBe(false);
    expect(hasValue(NaN)).toBe(false);
    expect(hasValue([])).toBe(false);
    expect(hasValue({})).toBe(false);
  });
});

describe('escapeHtml', () => {
  it('escapes HTML-significant characters', () => {
    expect(escapeHtml('<a href="x">&\'')).toBe('&lt;a href=&quot;x&quot;&gt;&amp;&#39;');
  });
  it('leaves plain text untouched', () => {
    expect(escapeHtml('BURCH FAMILY FARM TRUST')).toBe('BURCH FAMILY FARM TRUST');
  });
});
