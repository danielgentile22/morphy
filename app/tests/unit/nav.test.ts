import { describe, it, expect } from 'vitest';
import {
  parseRoute,
  sectionOf,
  dashboardHash,
  leadHash,
  towerHash,
  settingsHash,
  isUnowned,
  NO_OWNER,
  SECTION_HASH,
  type Route,
} from '../../src/lib/nav';

describe('nav routing (UI overhaul P1 / #104)', () => {
  it('opens on the Dashboard for an empty hash', () => {
    expect(parseRoute('')).toEqual({ name: 'dashboard', sub: 'home' });
    expect(parseRoute('#/')).toEqual({ name: 'dashboard', sub: 'home' });
    expect(parseRoute('#/dashboard')).toEqual({ name: 'dashboard', sub: 'home' });
  });

  it('parses each top-level section', () => {
    expect(parseRoute('#/explore')).toEqual({ name: 'explore' });
    expect(parseRoute('#/leads')).toEqual({ name: 'leads' });
  });

  it('parses each Dashboard sub-page', () => {
    for (const sub of ['tasks', 'calendar', 'history', 'stats'] as const) {
      expect(parseRoute(`#/dashboard/${sub}`)).toEqual({ name: 'dashboard', sub });
    }
  });

  it('falls back to the digest hub for an unknown Dashboard sub-page', () => {
    expect(parseRoute('#/dashboard/bogus')).toEqual({ name: 'dashboard', sub: 'home' });
  });

  it('parses a lead/owner page and decodes its key', () => {
    expect(parseRoute('#/lead/abc123')).toEqual({ name: 'lead', key: 'abc123' });
    expect(parseRoute('#/lead/a%2Fb')).toEqual({ name: 'lead', key: 'a/b' });
  });

  it('falls back to Dashboard for an unknown route', () => {
    expect(parseRoute('#/nonsense')).toEqual({ name: 'dashboard', sub: 'home' });
  });

  it('parses the settings route and round-trips its hash (PRD #121)', () => {
    expect(parseRoute('#/settings')).toEqual({ name: 'settings' });
    expect(settingsHash()).toBe('#/settings');
    expect(parseRoute(settingsHash())).toEqual({ name: 'settings' });
    // a stray sub-segment is ignored — settings has no sub-routes
    expect(parseRoute('#/settings/account')).toEqual({ name: 'settings' });
    // a near-miss still falls back to the Dashboard (no regression)
    expect(parseRoute('#/settingz')).toEqual({ name: 'dashboard', sub: 'home' });
  });

  it('parses a tower detail page (cid + asr, decoded) under Explore', () => {
    expect(parseRoute('#/tower/cid123/1287345')).toEqual({
      name: 'tower',
      cid: 'cid123',
      asr: '1287345',
    });
    // a tower route missing the asr falls back (not a valid tower)
    expect(parseRoute('#/tower/cid123')).toEqual({ name: 'dashboard', sub: 'home' });
  });

  it('gives an unowned tower an openable page via the NO_OWNER sentinel', () => {
    // An empty cid would make `#/tower//asr` unparseable; towerHash substitutes
    // the sentinel so the page still opens. (UI overhaul round 2.)
    const hash = towerHash('', '1287345');
    expect(hash).toBe(`#/tower/${NO_OWNER}/1287345`);
    expect(parseRoute(hash)).toEqual({ name: 'tower', cid: NO_OWNER, asr: '1287345' });
    expect(isUnowned(NO_OWNER)).toBe(true);
    expect(isUnowned('')).toBe(true);
    expect(isUnowned('cid123')).toBe(false);
  });

  it('maps a route to its active nav section (a lead page → Leads)', () => {
    expect(sectionOf({ name: 'explore' })).toBe('explore');
    expect(sectionOf({ name: 'leads' })).toBe('leads');
    expect(sectionOf({ name: 'lead', key: 'x' })).toBe('leads');
    expect(sectionOf({ name: 'tower', cid: 'c', asr: 'a' })).toBe('explore');
    expect(sectionOf({ name: 'dashboard', sub: 'stats' })).toBe('dashboard');
  });

  it('builds canonical hashes that round-trip through parseRoute', () => {
    expect(parseRoute(SECTION_HASH.explore)).toEqual({ name: 'explore' });
    expect(parseRoute(SECTION_HASH.leads)).toEqual({ name: 'leads' });
    expect(parseRoute(dashboardHash('home'))).toEqual({ name: 'dashboard', sub: 'home' });
    expect(parseRoute(dashboardHash('tasks'))).toEqual({ name: 'dashboard', sub: 'tasks' });
    const r: Route = parseRoute(leadHash('cid/with/slash'));
    expect(r).toEqual({ name: 'lead', key: 'cid/with/slash' });
    expect(parseRoute(towerHash('cid1', '1287345'))).toEqual({
      name: 'tower',
      cid: 'cid1',
      asr: '1287345',
    });
  });
});
