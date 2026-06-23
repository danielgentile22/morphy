<script lang="ts">
  // Minimal Lucide-style icons (MIT path data, inlined). The handful of chrome
  // icons we actually use don't justify the @lucide/svelte dependency; add a
  // path here when a new one is needed. 24×24 grid, currentColor stroke.
  let {
    name,
    size = 16,
  }: { name: 'x' | 'chevron-down'; size?: number } = $props();

  const PATHS: Record<typeof name, string> = {
    x: 'M18 6 6 18M6 6l12 12',
    'chevron-down': 'm6 9 6 6 6-6',
  };
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d={PATHS[name]} />
</svg>
