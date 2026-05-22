import { mount } from 'svelte';
import 'maplibre-gl/dist/maplibre-gl.css';
import './app.css';
import App from './App.svelte';

const target = document.getElementById('app');
if (!target) throw new Error('mount target #app not found');

export default mount(App, { target });
