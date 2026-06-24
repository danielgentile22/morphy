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

<!-- Halo design-system anatomy: .card surface, .field/.input form rows, an
     .eyebrow brand label, and a primary .btn. Logic + testids unchanged. -->
<div class="signin" data-testid="signin">
  <div class="card signin-card">
    <div class="brand">
      <div class="brand-mark" aria-hidden="true"></div>
      <div class="brand-text">
        <span class="eyebrow">Morphy Consulting</span>
        <span class="t-headline-md">Sign in</span>
      </div>
    </div>

    <form onsubmit={submit} class="stack">
      <div class="field">
        <label class="field-label" for="username">Username</label>
        <input
          class="input"
          id="username"
          type="text"
          data-testid="signin-username"
          bind:value={username}
          autocomplete="username"
          required
        />
      </div>
      <div class="field">
        <label class="field-label" for="password">Password</label>
        <input
          class="input"
          id="password"
          type="password"
          data-testid="signin-password"
          bind:value={password}
          autocomplete="current-password"
          required
        />
      </div>
      <button class="btn btn-primary btn-lg" type="submit" data-testid="signin-submit" disabled={busy}>
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
    </form>

    {#if error}
      <p class="field-help is-error" data-testid="signin-error">{error}</p>
    {/if}
  </div>
</div>

<style>
  .signin {
    display: flex;
    justify-content: center;
    padding: 48px 22px;
  }
  .signin-card {
    width: 100%;
    max-width: 380px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .brand-mark {
    width: 36px;
    height: 36px;
    flex-shrink: 0;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border-strong);
    background: conic-gradient(
      from 220deg at 50% 50%,
      var(--color-primary),
      #1e2029,
      var(--color-primary)
    );
  }
  .brand-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  /* Full-width primary action for the form. */
  .signin .btn {
    width: 100%;
    margin-top: 4px;
  }
</style>
