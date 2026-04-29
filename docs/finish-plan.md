# Milestone 1–6 Finish Plan

## Goal
Move from scaffold to production-ready milestone completion with acceptance coverage.

## Phase A — Core hardening (current implementation pass)
1. Normalize API contracts with typed Pydantic payloads for campaigns and publishing transitions.
2. Add validation guardrails for statuses and source filters.
3. Expand automated API tests beyond dashboard to queues/social/publishing/campaign flows.
4. Add explicit finish criteria mapping in README.

## Phase B — Data/infra hardening
1. Add Alembic migrations for all tables.
2. Add idempotent seed strategy and startup checks.
3. Add structured logging and error envelopes.
4. Add Redis worker for scheduled refresh.

## Phase C — Real integrations
1. Replace mock connectors with provider clients:
   - Google Calendar
   - Jobber
   - Immich / Immich-GPT
   - Paperless / Paperless-GPT
2. Add per-integration credential/settings management and health checks.

## Phase D — Full UX completion
1. Build multi-page frontend:
   - Dashboard
   - Queues
   - AI Social Studio
   - Publishing board/list/calendar
   - Campaigns
2. Add loading/error states and edit forms for all models.

## Phase E — Final acceptance + release
1. End-to-end tests per acceptance criteria.
2. Compose deployment verification on Unraid.
3. Security review (secrets, auth flows, logs).
4. MVP release checklist sign-off.
