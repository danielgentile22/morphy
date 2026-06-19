<script lang="ts">
  import { TAG_DIMENSIONS, type SignalTags } from '../lib/audit-data';
  import Chip from './Chip.svelte';

  let { tags, sm = false }: { tags: SignalTags; sm?: boolean } = $props();
</script>

<span class="tagrow">
  {#each TAG_DIMENSIONS as dim (dim)}
    <Chip dimension={dim} value={tags[dim]} {sm} />
  {/each}
</span>

<style>
  .tagrow {
    display: inline-flex;
    flex-wrap: wrap;
    gap: 5px;
  }
</style>
