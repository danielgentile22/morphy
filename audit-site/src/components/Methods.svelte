<script lang="ts">
  // The three audit methods (PLAN §6): A = read code/docs, B = query the real
  // data, C = web-research the source. A lit letter means that method was run.
  let { methods }: { methods: { A: boolean; B: boolean; C: boolean } } = $props();

  const items: Array<[string, boolean, string]> = $derived([
    ['A', methods.A, 'A — read the code/docs'],
    ['B', methods.B, 'B — query the real data'],
    ['C', methods.C, 'C — web-research the source'],
  ]);
</script>

<span class="methods">
  {#each items as [letter, done, title] (letter)}
    <span class="m" class:done {title}>{letter}</span>
  {/each}
</span>

<style>
  .methods {
    display: inline-flex;
    gap: 3px;
  }
  .m {
    width: 18px;
    height: 18px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    font-family: var(--mono);
    background: var(--muted-bg);
    color: var(--muted-fg);
    border: 1px solid var(--muted-bd);
  }
  .m.done {
    background: var(--good-bg);
    color: var(--good-fg);
    border-color: var(--good-bd);
  }
</style>
