import { describe, it, expect, vi, afterEach } from 'vitest';
import { mergeCluster, splitCluster } from '../../src/lib/leads-api';

// The merge/split trigger (Slice 7 / #53) must map to the right backend call:
// POST /api/leads/{id}/{merge|split} with a {source_cluster_id} body. We stub
// fetch and assert the request the client builds (the same seam the LeadPage
// buttons drive through the leads store).

function stubFetch(body: unknown) {
  const spy = vi.fn((_url: string, _init?: RequestInit) =>
    Promise.resolve({ ok: true, json: async () => body } as unknown as Response),
  );
  vi.stubGlobal('fetch', spy);
  return spy;
}

afterEach(() => vi.unstubAllGlobals());

describe('mergeCluster', () => {
  it('POSTs source_cluster_id to the merge endpoint and returns the merged lead', async () => {
    const detail = {
      owner: { display_cluster_id: 'aaa' },
      merged_members: [{ display_cluster_id: 'bbb', owner_name: 'X' }],
    };
    const spy = stubFetch(detail);

    const res = await mergeCluster('aaa', 'bbb');

    expect(spy).toHaveBeenCalledTimes(1);
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe('/api/leads/aaa/merge');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({ source_cluster_id: 'bbb' });
    expect(res).toEqual(detail);
  });
});

describe('splitCluster', () => {
  it('POSTs source_cluster_id to the split endpoint', async () => {
    const spy = stubFetch({ merged_members: [] });

    await splitCluster('aaa', 'bbb');

    const [url, init] = spy.mock.calls[0];
    expect(url).toBe('/api/leads/aaa/split');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({ source_cluster_id: 'bbb' });
  });

  it('URL-encodes the cluster id in the path', async () => {
    const spy = stubFetch({});
    await mergeCluster('a/b', 'c');
    expect(spy.mock.calls[0][0]).toBe('/api/leads/a%2Fb/merge');
  });
});
