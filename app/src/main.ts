import { mount } from 'svelte';
// maplibre-gl.css is imported by MapView (the lazy map chunk), not here, so its
// ~72 KB doesn't block first paint on the Dashboard landing (PERF-036).
import './app.css';
import App from './App.svelte';
import { applyBootAppearance } from './lib/user-settings-store.svelte';

// Apply the cached theme/colorblind class before the app paints (PRD #121) so
// there's no flash of the wrong theme; the backend value reconciles after the
// per-user settings load.
applyBootAppearance();

const target = document.getElementById('app');
if (!target) throw new Error('mount target #app not found');

export default mount(App, { target });
