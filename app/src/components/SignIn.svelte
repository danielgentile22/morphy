<script lang="ts">
  import { auth } from '../lib/auth-store.svelte';

  // Single-step username + password sign-in (Slice 1 / #76). The backend
  // checks the credentials and mints the same session JWT the app already
  // uses; tenant + identity are derived from that token downstream.
  let username = $state('');
  let password = $state('');
  let error = $state<string | null>(null);
  let busy = $state(false);

  async function submit(e: Event): Promise<void> {
    e.preventDefault();
    error = null;
    busy = true;
    try {
      await auth.login(username, password);
    } catch (err) {
      // The backend returns a specific message (unknown user vs wrong password).
      error = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }
</script>

<div class="signin" data-testid="signin">
  <div class="card">
    <div class="brand">
      <img class="logo" src="/favicon.png" alt="" width="44" height="44" />
      <span class="name">Morphy Consulting</span>
    </div>

    <form onsubmit={submit}>
      <label for="username">Username</label>
      <input
        id="username"
        type="text"
        data-testid="signin-username"
        bind:value={username}
        autocomplete="username"
        required
      />
      <label for="password">Password</label>
      <input
        id="password"
        type="password"
        data-testid="signin-password"
        bind:value={password}
        autocomplete="current-password"
        required
      />
      <button type="submit" data-testid="signin-submit" disabled={busy}>
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
    </form>

    {#if error}
      <p class="err" data-testid="signin-error">{error}</p>
    {/if}
  </div>
</div>

<style>
  .signin {
    display: flex;
    justify-content: center;
    padding: 24px 22px;
  }
  .card {
    width: 100%;
    max-width: 360px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 30px 28px;
    box-shadow: var(--shadow);
  }
  .brand {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    margin-bottom: 24px;
  }
  .logo {
    border-radius: 10px;
  }
  .name {
    font-size: 19px;
    font-weight: 600;
    letter-spacing: 0.01em;
  }
  form {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
  input {
    padding: 9px 11px;
    font-size: 13px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
  }
  button[type='submit'] {
    margin-top: 14px;
    padding: 10px 14px;
    font-size: 13px;
    font-weight: 600;
    border: 1px solid var(--accent);
    background: var(--accent);
    color: #fff;
    border-radius: var(--radius);
    cursor: pointer;
  }
  button[type='submit']:disabled {
    opacity: 0.6;
  }
  .err {
    margin-top: 12px;
    font-size: 12.5px;
    color: var(--danger);
  }
</style>
