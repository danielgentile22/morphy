import { mount } from 'svelte';
import './app.css';
import App from './App.svelte';
import { applyBootTheme } from './lib/theme.svelte';

// Apply the theme class before the app paints so there's no flash of the wrong
// surface (mirrors the map app's boot-appearance step).
applyBootTheme();

const target = document.getElementById('app');
if (!target) throw new Error('mount target #app not found');

export default mount(App, { target });
