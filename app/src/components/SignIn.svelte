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
    <h2>Sign in</h2>
    <p class="sub">
      Lead state is private to your team (tenant-isolated, ADR-055). Enter your username and
      password.
    </p>

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
    padding: 48px 22px;
  }
  .card {
    width: 100%;
    max-width: 420px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 22px 24px;
    box-shadow: var(--shadow);
  }
  h2 {
    font-size: 18px;
    margin-bottom: 6px;
  }
  .sub {
    font-size: 12.5px;
    color: var(--text-2);
    margin-bottom: 16px;
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
    padding: 8px 10px;
    font-size: 13px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
  }
  button[type='submit'] {
    margin-top: 8px;
    padding: 8px 14px;
    font-size: 13px;
    border: 1px solid var(--accent);
    background: var(--accent);
    color: #fff;
    border-radius: var(--radius);
  }
  button[type='submit']:disabled {
    opacity: 0.6;
  }
  .err {
    margin-top: 10px;
    font-size: 12.5px;
    color: var(--danger);
  }
</style>
