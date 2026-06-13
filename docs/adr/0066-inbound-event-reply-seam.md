# ADR-066: Replies are provider-agnostic inbound activity events

**Status:** Accepted
**Date:** 2026-06-06
**Pairs with:** ADR-065, ADR-061
**Plan:** the UI-overhaul plan (decisions D6, D12) — shipped; the plan doc was retired, recover from git history if needed.

## Context

The redesigned Dashboard's two headline items — "replies we received" (the
Attention feed) and the auto follow-up rule ("ignore the ones that replied") — both
require the app to know whether a landowner **responded**. Today there is no such
concept: `ContactAttempt` records only outbound touches plus auto-logged status
changes, and there is no email integration. The obvious-looking move is to wire the
Dashboard directly to Gmail, but most outreach is calls + mailed letters (no email
to match), and an inbox integration is a heavy, privacy-sensitive dependency to put
under a core surface.

## Decision

Model a reply as a **first-class inbound event** in the existing activity log,
**decoupled from any email provider**: add a **`direction` (outbound | inbound)**
column to `ContactAttempt`. A "reply" is simply any **inbound** entry. For now
inbound events are **logged manually** ("Log reply"), exactly like logging a call.
The Dashboard, Attention feed, and auto follow-up rule read **inbound events** —
never Gmail. A later **Gmail integration becomes a pure auto-filler** of the same
inbound events (matching incoming mail to a lead by `contact_email`), with zero
rework to anything downstream.

## Consequences

- **Minimal schema change** (one column) unlocks the whole Dashboard; the calendar/
  history views are then just the activity stream on a timeline.
- The **auto follow-up rule** keys on presence/absence of an inbound event, not on
  status — a reply can arrive with no status change ("who is this?").
- The Gmail integration (a later phase) is isolated and optional; the app is fully
  usable, manual-first, without it.

## Alternatives considered

- **Status implies reply** (moving to Interested/Uninterested = they replied).
  Rejected — conflates "they replied" with "I judged them interested," loses the
  reply date the calendar needs, and leaves neutral replies homeless.
- **Gmail integration as the source of truth now.** Rejected — heavy auth/privacy
  scope, and it can't see call/mail replies; better as a later auto-filler of the
  manual events this ADR defines.
