<script lang="ts">
  import { auth } from '../lib/auth-store.svelte';

  // Two-step magic-link sign-in: request a link, then exchange the token.
  // In dev the backend echoes the token (auth.devToken) so we prefill it;
  // in prod the user pastes it from their email.
  let email = $state('');
  let token = $state('');

  async function request(e: Event): Promise<void> {
    e.preventDefault();
    await auth.requestLink(email);
    if (auth.devToken) token = auth.devToken;
  }

  async function exchange(e: Event): Promise<void> {
    e.preventDefault();
    await auth.exchange(token);
  }
</script>

<div class="signin" data-testid="signin">
  <div class="card">
    <h2>Sign in</h2>
    <p class="sub">
      Lead state is private to your team (tenant-isolated, ADR-055). Enter your email to get a
      one-time sign-in link.
    </p>

    {#if auth.phase !== 'link-sent' && auth.phase !== 'exchanging'}
      <form onsubmit={request}>
        <label for="email">Email</label>
        <input
          id="email"
          type="email"
          data-testid="signin-email"
          bind:value={email}
          placeholder="you@example.com"
          required
        />
        <button type="submit" data-testid="signin-request" disabled={auth.phase === 'requesting'}>
          {auth.phase === 'requesting' ? 'Sending…' : 'Send magic link'}
        </button>
      </form>
    {:else}
      <form onsubmit={exchange}>
        <p class="sent">
          Link sent to <b>{email}</b>.
          {#if auth.devToken}
            <span class="dev">Dev mode: token prefilled below.</span>
          {:else}
            Paste the token from your email.
          {/if}
        </p>
        <label for="token">Sign-in token</label>
        <input
          id="token"
          type="text"
          data-testid="signin-token"
          bind:value={token}
          placeholder="one-time token"
          required
        />
        <button type="submit" data-testid="signin-exchange">Sign in</button>
        <button type="button" class="link" onclick={() => auth.signOut()}>Use a different email</button>
      </form>
    {/if}

    {#if auth.error}
      <p class="err" data-testid="signin-error">{auth.error}</p>
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
  button.link {
    margin-top: 4px;
    background: none;
    border: none;
    color: var(--accent);
    font-size: 12px;
    align-self: flex-start;
    padding: 0;
  }
  .sent {
    font-size: 12.5px;
    color: var(--text-2);
  }
  .dev {
    color: var(--muted);
  }
  .err {
    margin-top: 10px;
    font-size: 12.5px;
    color: var(--danger);
  }
</style>
