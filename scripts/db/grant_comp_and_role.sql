-- Grant a complimentary membership (and optionally a professional role) to
-- named accounts — IDEMPOTENT, and safe to re-run.
--
-- Why this is SQL and not an API call: there is no admin write surface. The
-- admin console (`/api/v1/admin/*`) is deliberately read-only, `/subscription`
-- only accepts *verified provider purchases*, and role assignment goes through
-- `POST /users/roles`, which needs the target user's own bearer token. Comping a
-- user you cannot log in as therefore has to happen in the database.
--
-- What it does, in one transaction:
--   1. resolves each email to a users row — an email that matches nothing ABORTS
--      the run, because a comp that silently reached no one is exactly the
--      failure worth being loud about
--   2. optionally grants a role assignment (idempotent; reactivates a revoked one)
--   3. upserts the subscription to an `active` complimentary period
--   4. writes a SubscriptionEvent audit row, so the grant sits on the record
--      next to every real provider event
--
-- The subscription is written as status='active', provider='none', price 0,
-- cancel_at_period_end=true. Nothing renews a provider='none' row, so that flag
-- is the truth — and the web UI reads it to print "Access ends on <date>"
-- instead of the wrong "Renews on <date>".
--
-- Refuses to overwrite a subscription belonging to a real billing rail
-- (stripe/paypal/google_play/apple) unless -v allow_overwrite=1: clobbering one
-- strips the reconciliation ids that tie the row to the provider, and the next
-- webhook would have nothing to match.
--
-- Parameters (all required — the wrapper script supplies them):
--   -v emails='a@x.com,b@y.com'   targets, comma-separated
--   -v grant_role=1|0             whether to assign a role at all
--   -v role='physician'           role value (must exist in the UserRole enum)
--   -v make_primary=1|0           make it the user's primary role
--   -v months=12                  length of the complimentary period
--   -v allow_overwrite=0|1        permit replacing a paid subscription
--   -v dry_run=1|0                1 = print everything, then ROLLBACK
--
-- Usage (dry run first — it prints the plan and rolls back):
--   psql … -v dry_run=1 -f grant_comp_and_role.sql
--   psql … -v dry_run=0 -f grant_comp_and_role.sql

\set ON_ERROR_STOP on

BEGIN;

-- Pin the session's text rendering for the same reason fingerprint.sql does:
-- so the timestamps this prints mean the same thing on every machine.
SET LOCAL TimeZone = 'UTC';

-- ── Parameters ───────────────────────────────────────────────────────────
-- psql does NOT interpolate variables inside dollar-quoted strings, so the
-- PL/pgSQL guards below cannot read :vars directly. Materialise them once here,
-- where interpolation does happen, and have every step read this table.
CREATE TEMP TABLE _params ON COMMIT DROP AS
SELECT :'emails'::text          AS emails,
       (:grant_role = 1)        AS grant_role,
       :'role'::text            AS role,
       (:make_primary = 1)      AS make_primary,
       (:'months')::int         AS months,
       (:allow_overwrite = 1)   AS allow_overwrite;

-- ── 1. Resolve targets ───────────────────────────────────────────────────
-- One `now()` serves the whole run: it is transaction-stable, so the period
-- start, the audit row and the printed report cannot disagree.
CREATE TEMP TABLE _targets ON COMMIT DROP AS
SELECT u.id, u.email, u.full_name, u.is_active
FROM users u
JOIN _params p ON true
JOIN unnest(string_to_array(p.emails, ',')) AS t(email)
  ON lower(u.email) = lower(btrim(t.email));

DO $$
DECLARE missing text;
BEGIN
    SELECT string_agg(btrim(t.email), ', ')
      INTO missing
      FROM _params p, unnest(string_to_array(p.emails, ',')) AS t(email)
     WHERE NOT EXISTS (
         SELECT 1 FROM users u WHERE lower(u.email) = lower(btrim(t.email))
     );
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'no users row for: %', missing
              USING HINT = 'create the account first (POST /api/v1/auth/register)';
    END IF;
END $$;

\echo '── targets ──'
SELECT id, email, full_name, is_active FROM _targets ORDER BY id;

-- Inactive accounts are reported, not blocked: comping one is legitimate
-- (reactivation is a separate decision), but the operator should see it.
\echo ''
\echo '── heads-up: targets that are NOT active ──'
SELECT id, email FROM _targets WHERE NOT is_active ORDER BY id;

\echo ''
\echo '── existing subscriptions on these accounts ──'
SELECT s.user_id, t.email, s.status, s.provider, s.plan, s.current_period_end
FROM subscriptions s JOIN _targets t ON t.id = s.user_id
ORDER BY s.user_id;

DO $$
DECLARE paid text;
BEGIN
    SELECT string_agg(t.email || ' (' || s.provider || ')', ', ')
      INTO paid
      FROM subscriptions s JOIN _targets t ON t.id = s.user_id
     WHERE s.provider NOT IN ('none', '');
    IF paid IS NOT NULL AND NOT (SELECT allow_overwrite FROM _params) THEN
        RAISE EXCEPTION 'these targets already hold a provider subscription: %', paid
              USING HINT = 'overwriting drops the provider reconciliation ids; '
                           're-run with -v allow_overwrite=1 only if that is intended';
    END IF;
END $$;

-- ── 2. Role assignment ───────────────────────────────────────────────────
\if :grant_role

-- A user has at most one primary role, so clear the old one before claiming it.
\if :make_primary
UPDATE user_role_assignments ra
SET is_primary = false
FROM _targets t, _params p
WHERE ra.user_id = t.id AND ra.is_primary AND ra.role <> p.role;
\endif

-- `patient` is implicit for every account (users.py always prepends it to
-- active_roles), so only the professional role needs a row of its own.
INSERT INTO user_role_assignments (user_id, role, is_primary, is_active, granted_at)
SELECT t.id, p.role, p.make_primary, true, now()
FROM _targets t, _params p
ON CONFLICT (user_id, role) DO UPDATE
SET is_active  = true,
    revoked_at = NULL,
    is_primary = user_role_assignments.is_primary OR EXCLUDED.is_primary;

\echo ''
\echo '── role assignments after grant ──'
SELECT ra.user_id, t.email, ra.role, ra.is_primary, ra.is_active
FROM user_role_assignments ra JOIN _targets t ON t.id = ra.user_id
ORDER BY ra.user_id, ra.role;

\endif

-- ── 3. Complimentary subscription ────────────────────────────────────────
INSERT INTO subscriptions (
    user_id, status, provider, plan, price_usd,
    current_period_start, current_period_end,
    cancel_at_period_end, created_at, updated_at
)
SELECT t.id, 'active', 'none', 'plus_annual', 0,
       now(), now() + make_interval(months => p.months),
       true, now(), now()
FROM _targets t, _params p
ON CONFLICT (user_id) DO UPDATE
SET status               = 'active',
    provider             = 'none',
    plan                 = 'plus_annual',
    price_usd            = 0,
    current_period_start = EXCLUDED.current_period_start,
    current_period_end   = EXCLUDED.current_period_end,
    cancel_at_period_end = true,
    canceled_at          = NULL,
    updated_at           = now();

-- ── 4. Audit row, alongside every real provider event ────────────────────
INSERT INTO subscription_events (user_id, provider, event_id, event_type, payload, created_at)
SELECT t.id,
       'none',
       'comp:' || t.id || ':' || to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
       'complimentary_grant',
       json_build_object(
           'granted_by', 'scripts/db/grant_comp_and_role.sql',
           'months',     p.months,
           'role',       CASE WHEN p.grant_role THEN p.role ELSE NULL END,
           'email',      t.email
       )::text,
       now()
FROM _targets t, _params p
ON CONFLICT (provider, event_id) DO NOTHING;

\echo ''
\echo '── result ──'
SELECT s.user_id, t.email, s.status, s.provider, s.plan, s.price_usd,
       s.current_period_start, s.current_period_end, s.cancel_at_period_end
FROM subscriptions s JOIN _targets t ON t.id = s.user_id
ORDER BY s.user_id;

\if :dry_run
  \echo ''
  \echo '*** DRY RUN — rolling back. Re-run with -v dry_run=0 to apply. ***'
  ROLLBACK;
\else
  COMMIT;
  \echo ''
  \echo '*** APPLIED. ***'
\endif
