# ADR-066: Replies are provider-agnostic inbound activity events

**Status:** Accepted
**Date:** 2026-06-06
**Pairs with:** ADR-065, ADR-061
**Plan:** the UI-overhaul plan (decisions D6, D12). It shipped, and the plan doc was retired; git history has it.

## Context

The redesigned Dashboard's two headline items, "replies we received" (the
Attention feed) and the auto follow-up rule ("ignore the ones that replied"), both
require the app to know whether a landowner **responded**. Before this change there was no such
concept. `ContactAttempt` recorded only outbound touches plus auto-logged status
changes, and there was no email integration. The obvious-looking move is to wire the
Dashboard directly to Gmail. But most contact happens by phone and mailed letter (no email
to match), and an inbox integration is a heavy, privacy-sensitive dependency to put
under a core surface.

## Decision

Model a reply as a **first-class inbound event** in the existing activity log,
**decoupled from any email provider**. Add a **`direction` (outbound | inbound)**
column to `ContactAttempt`. A "reply" is any **inbound** entry. Inbound events are
**logged manually** ("Log reply"), exactly like logging a call.
The Dashboard, Attention feed, and auto follow-up rule read **inbound events**,
never Gmail. A Gmail integration would be a **pure auto-filler** of the same
inbound events (matching incoming mail to a lead by `contact_email`), with zero
rework to anything downstream.

## Consequences

- A **minimal schema change** (one column) unlocks the whole Dashboard. The calendar and
  history views are then the activity stream on a timeline.
- The **auto follow-up rule** keys on presence or absence of an inbound event, not on
  status, because a reply can arrive with no status change ("who is this?").
- The Gmail integration was planned but never built. It stays isolated and optional; the app is fully
  usable, manual-first, without it.

## Alternatives considered

- **Status implies reply** (moving to Interested/Uninterested = they replied).
  Rejected. It conflates "they replied" with "I judged them interested," loses the
  reply date the calendar needs, and leaves neutral replies homeless.
- **Gmail integration as the source of truth.** Rejected. The auth and privacy
  scope is heavy, and it can't see phone or mail replies. It fits better as an auto-filler of the
  manual events this ADR defines.
