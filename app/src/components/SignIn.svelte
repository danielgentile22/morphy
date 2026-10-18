<script lang="ts">
  import { onMount } from 'svelte';
  import { auth } from '../lib/auth-store.svelte';

  // Single-step username + password sign-in (Slice 1 / #76). The backend
  // checks the credentials and mints the same session JWT the app already
  // uses; tenant + identity are derived from that token downstream.
  let username = $state('');
  let password = $state('');
  let error = $state<string | null>(null);
  let busy = $state(false);

  onMount(() => {
    void auth.loadConfig();
  });

  // The public read-only demo (ADR-077): one click, no password.
  async function exploreDemo(): Promise<void> {
    error = null;
    busy = true;
    try {
      await auth.loginDemo();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }

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
        <span class="eyebrow">morphy</span>
        <span class="t-headline-md">Sign in</span>
      </div>
    </div>

    {#if auth.demoMode}
      <div class="demo stack">
        <button
          class="btn btn-primary btn-lg"
          type="button"
          data-testid="signin-demo"
          disabled={busy}
          onclick={exploreDemo}
        >
          {busy ? 'Opening the demo…' : 'Explore the demo'}
        </button>
        <p class="field-help" data-testid="signin-demo-help">
          Read-only, with sample leads. No account needed.
        </p>
      </div>
      <p class="or t-label-sm" aria-hidden="true">or sign in</p>
    {/if}

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
      <button
        class="btn btn-lg {auth.demoMode ? 'btn-secondary' : 'btn-primary'}"
        type="submit"
        data-testid="signin-submit"
        disabled={busy}
      >
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
  .demo {
    margin-top: 16px;
  }
  .or {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 16px 0 4px;
    color: var(--color-text-muted);
  }
  .or::before,
  .or::after {
    content: '';
    flex: 1;
    border-top: 1px solid var(--color-border);
  }
  /* Full-width primary action for the form. */
  .signin .btn {
    width: 100%;
    margin-top: 4px;
  }
</style>
