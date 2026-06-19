<script lang="ts">
  import { tagMeta, DIMENSION_LABELS } from '../lib/tags';

  let { dimension, value, sm = false }: { dimension: string; value: string; sm?: boolean } = $props();

  const meta = $derived(tagMeta(dimension, value));
  const title = $derived(`${DIMENSION_LABELS[dimension] ?? dimension}: ${value} — ${meta.title}`);
</script>

<span class="chip chip--{meta.tone}" class:chip--sm={sm} {title}>{meta.label}</span>
