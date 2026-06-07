<script lang="ts">
  // Settings → Account (PRD #121): read-only identity, editable display name,
  // and self-service password change.
  import { auth } from '../lib/auth-store.svelte';
  import { updateDisplayName, changeMyPassword, ApiError } from '../lib/leads-api';

  // ── display name ──────────────────────────────────────────────────────────
  let displayName = $state(auth.displayName ?? '');
  let nameStatus = $state<'idle' | 'saving' | 'saved' | 'error'>('idle');
  let nameError = $state('');

  async function saveName(): Promise<void> {
    nameStatus = 'saving';
    nameError = '';
    try {
      const me = await updateDisplayName(displayName.trim());
      auth.displayName = me.display_name ?? null;
      displayName = me.display_name ?? '';
      nameStatus = 'saved';
    } catch (e) {
      nameStatus = 'error';
      nameError = e instanceof Error ? e.message : String(e);
    }
  }

  // ── password change ───────────────────────────────────────────────────────
  let current = $state('');
  let next = $state('');
  let confirm = $state('');
  let pwStatus = $state<'idle' | 'saving' | 'saved' | 'error'>('idle');
  let pwError = $state('');

  async function changePassword(e: SubmitEvent): Promise<void> {
    e.preventDefault();
    pwError = '';
    if (!next) {
      pwStatus = 'error';
      pwError = 'New password must not be empty.';
      return;
    }
    if (next !== confirm) {
      pwStatus = 'error';
      pwError = 'New passwords do not match.';
      return;
    }
    pwStatus = 'saving';
    try {
      await changeMyPassword(current, next);
      pwStatus = 'saved';
      current = next = confirm = '';
    } catch (err) {
      pwStatus = 'error';
      pwError =
        err instanceof ApiError && err.status === 401
          ? 'Current password is incorrect.'
          : err instanceof Error
            ? err.message
            : String(err);
    }
  }
</script>

<section class="set-section" data-testid="settings-account">
  <h2>Account</h2>
  <p class="hint">Your identity and sign-in credential.</p>

  <div class="set-group">
    <h3>Identity</h3>
    <div class="set-row">
      <span class="set-label">Email</span>
      <span class="set-readonly" data-testid="account-email">{auth.email}</span>
    </div>
    <div class="set-row">
      <span class="set-label">Team</span>
      <span class="set-readonly" data-testid="account-team">{auth.team ?? '—'}</span>
    </div>
    <p class="hint">Email and team are managed by an administrator.</p>
  </div>

  <div class="set-group">
    <h3>Display name</h3>
    <div class="set-row">
      <input
        class="set-input"
        data-testid="display-name"
        bind:value={displayName}
        placeholder={auth.email ?? 'Your name'}
        aria-label="Display name"
      />
      <button
        class="set-btn"
        data-testid="display-name-save"
        disabled={nameStatus === 'saving'}
        onclick={saveName}
      >
        Save
      </button>
      {#if nameStatus === 'saved'}<span class="set-status ok">Saved ✓</span>{/if}
      {#if nameStatus === 'error'}<span class="set-status err">{nameError}</span>{/if}
    </div>
    <p class="hint">Shown on history, stats, and task assignment. Blank falls back to your email.</p>
  </div>

  <form class="set-group" onsubmit={changePassword} data-testid="password-form">
    <h3>Change password</h3>
    <div class="set-row">
      <span class="set-label">Current</span>
      <input
        class="set-input"
        type="password"
        data-testid="pw-current"
        bind:value={current}
        autocomplete="current-password"
        aria-label="Current password"
      />
    </div>
    <div class="set-row">
      <span class="set-label">New</span>
      <input
        class="set-input"
        type="password"
        data-testid="pw-new"
        bind:value={next}
        autocomplete="new-password"
        aria-label="New password"
      />
    </div>
    <div class="set-row">
      <span class="set-label">Confirm new</span>
      <input
        class="set-input"
        type="password"
        data-testid="pw-confirm"
        bind:value={confirm}
        autocomplete="new-password"
        aria-label="Confirm new password"
      />
    </div>
    <div class="set-row">
      <button
        class="set-btn"
        type="submit"
        data-testid="pw-save"
        disabled={pwStatus === 'saving' || !current || !next}
      >
        Update password
      </button>
      {#if pwStatus === 'saved'}<span class="set-status ok" data-testid="pw-ok">Password updated ✓</span>{/if}
      {#if pwStatus === 'error'}<span class="set-status err" data-testid="pw-error">{pwError}</span>{/if}
    </div>
  </form>
</section>
