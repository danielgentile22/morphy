<script lang="ts">
  import { app } from '../lib/stores.svelte';
  import { entitySchema, infrastructureItems, scoreComponents, carriers, type Props } from '../lib/schema';
  import CarrierList from './CarrierList.svelte';
  import Icon from './Icon.svelte';

  const sel = $derived(app.selection);
  const schema = $derived(sel ? entitySchema(sel.kind) : undefined);
  const props = $derived((sel?.props ?? {}) as Props);

  // Rich breakouts for parcels — nested structures the flat schema rows
  // can't show: the per-feature infrastructure list and the score factors.
  const infra = $derived(sel?.kind === 'parcel' ? infrastructureItems(props) : []);
  const components = $derived(sel?.kind === 'parcel' ? scoreComponents(props) : []);
  // Carriers (ULS licensees) on a tower — a list-of-struct rendered with
  // confidence badges (Slice A / #28), so the flat schema row can't show it.
  const towerCarriers = $derived(sel?.kind === 'tower' ? carriers(props) : []);

  function humanize(s: string): string {
    return s.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
  }
</script>

{#if sel}
  <aside class="details" data-testid="details-panel">
    <header>
      <div class="head-text">
        <span class="kind">{sel.kind.replace(/_/g, ' ')}</span>
        <h2>{schema ? schema.title(props) : 'Details'}</h2>
      </div>
      <button class="close" onclick={() => app.clearSelection()} aria-label="Close details">
        <Icon name="x" />
      </button>
    </header>

    {#if schema}
      {@const tags = schema.tags(props)}
      {#if tags.length > 0}
        <div class="tags">
          {#each tags as t (t.label)}
            <span class="tag tag-{t.tone}">{t.label}</span>
          {/each}
        </div>
      {/if}

      <div class="body">
        <!-- The Carriers section is a list-of-struct, rendered as badges
             below — exclude it from the flat key/value loop. -->
        {#each schema.sections.filter((s) => s.title !== 'Carriers') as section (section.title)}
          {@const rows = section.fields.map((f) => ({ label: f.label, value: f.value(props) }))}
          {#if rows.some((r) => r.value !== null)}
            <div class="section">
              <h3>{section.title}</h3>
              {#each rows as row (row.label)}
                <div class="kv" data-field={row.label}>
                  <span class="k">{row.label}</span>
                  <span class="v" class:empty={row.value === null}>{row.value ?? '—'}</span>
                </div>
              {/each}
            </div>
          {/if}
        {/each}

        {#if sel.kind === 'tower'}
          <div class="section">
            <h3>Carriers</h3>
            <CarrierList carriers={towerCarriers} />
          </div>
        {/if}

        {#if infra.length > 0}
          <div class="section">
            <h3>Infrastructure on this parcel</h3>
            {#each infra as item, i (i)}
              <div class="kv">
                <span class="k">{humanize(item.type)}</span>
                <span class="v">#{item.id}{item.owner ? ` · ${item.owner}` : ''}</span>
              </div>
            {/each}
          </div>
        {/if}

        {#if components.length > 0}
          <div class="section">
            <h3>Score factors</h3>
            {#each components as c (c.factor)}
              <div class="factor">
                <span class="fk">{humanize(c.factor)}</span>
                <span class="bar">
                  <span class="fill" style:width="{Math.min(100, c.weight * 250)}%"></span>
                </span>
                <span class="fw">{c.weight.toFixed(2)}</span>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {:else}
      <p class="muted">No detail view for this entity type.</p>
    {/if}
  </aside>
{/if}

<style>
  .details {
    position: absolute;
    top: 12px;
    right: 12px;
    width: 332px;
    max-height: calc(100% - 24px);
    display: flex;
    flex-direction: column;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    box-shadow: var(--shadow-lg);
    z-index: 30;
    overflow: hidden;
  }

  header {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 12px 14px;
    border-bottom: 1px solid var(--border);
  }
  .kind {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
  }
  header h2 {
    font-size: 15px;
    margin-top: 2px;
    word-break: break-word;
  }
  .close {
    margin-left: auto;
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text-2);
  }

  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    padding: 10px 14px 0;
  }
  .tag {
    font-size: 11px;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 999px;
  }
  .tag-oz {
    background: rgba(0, 114, 178, 0.13);
    color: #04519a;
  }
  .tag-distress {
    background: rgba(213, 94, 0, 0.14);
    color: #9c4500;
  }
  .tag-infra {
    background: rgba(0, 158, 115, 0.15);
    color: #006146;
  }
  .tag-neutral {
    background: var(--panel-2);
    color: var(--text-2);
  }

  .body {
    overflow-y: auto;
    padding: 6px 14px 14px;
  }
  .section {
    margin-top: 12px;
  }
  .section h3 {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 3px;
  }
  .kv {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 3px 0;
    border-bottom: 1px dotted var(--border);
    font-size: 12.5px;
  }
  .kv:last-child {
    border-bottom: none;
  }
  .k {
    color: var(--muted);
    flex-shrink: 0;
  }
  .v {
    text-align: right;
    word-break: break-word;
  }
  .v.empty {
    color: var(--muted);
  }

  .factor {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 0;
    font-size: 12px;
  }
  .fk {
    width: 110px;
    flex-shrink: 0;
    color: var(--text-2);
  }
  .bar {
    flex: 1;
    height: 7px;
    background: var(--panel-2);
    border-radius: 999px;
    overflow: hidden;
  }
  .fill {
    display: block;
    height: 100%;
    background: var(--accent);
  }
  .fw {
    width: 32px;
    text-align: right;
    font-variant-numeric: tabular-nums;
    color: var(--muted);
  }

  .muted {
    padding: 14px;
    font-size: 13px;
    color: var(--muted);
  }
</style>
