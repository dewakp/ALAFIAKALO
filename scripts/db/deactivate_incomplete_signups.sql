-- Retire accounts left behind by the BROKEN one-step signup — REVERSIBLE.
--
-- Why these rows exist: `POST /auth/register` created a loginable account
-- immediately, while the web form showed no result at all. So a person could
-- press "Create", be charged nothing, receive no email, and be told nothing —
-- and their address was then permanently taken by an account they could not
-- get into. `woleakpose@outlook.com` is the case this was found from.
--
-- Deliberately NOT a DELETE, for the reason `deactivate_test_accounts.sql`
-- already documents: 65 of the 101 foreign keys pointing at `users` are
-- NO ACTION, so a delete FAILS rather than cascades. Deactivating keeps
-- referential integrity and the audit trail, and scrambling the address to a
-- reserved `.invalid` domain is what actually frees the real address for the
-- person to sign up again properly.
--
-- Selection is by STATE, never by a list of ids. An id list has to be edited
-- for every recurrence, and one typo retires a patient. Every clause must hold:
--
--   * DORMANT — either no sign-in for 30 days, or the ONLY sign-in ever
--     recorded is the automatic one the registration itself performed
--   * no subscription row at all — never even reached a payment attempt
--   * holds NO clinical data whatsoever
--   * older than 7 days, so a signup happening right now is untouched
--   * not a superuser
--
-- ⚠️ `last_login IS NULL` was the first version of the dormancy clause and it
-- was PROVABLY WRONG here: the one-step form calls register() and then login()
-- immediately, so every account it created has a `last_login` stamped at
-- creation. The clause excluded exactly the accounts it was written to catch,
-- and the script reported "0 targets" — which reads as "nothing to clean"
-- rather than "these criteria can never match". §3aa, in a cleanup script:
-- an empty result is not proof of a clean database.
--
-- Dormancy is therefore measured as a WINDOW, not as absence. But a window
-- alone is still too blunt: because the auto-login stamps `last_login` at
-- creation, an account that has NEVER been used looks freshly active for its
-- first 30 days — so the address of someone who could not get in stays locked
-- up for a month.
--
-- `last_login <= created_at + 5 minutes` is the precise signature of that: the
-- only sign-in on record is the one the registration performed. Anyone who has
-- come back, even once, fails it and is left alone. The 7-day clause still
-- applies on top, so a signup happening right now is never touched.
--
-- A row failing ANY clause is left alone. An account with one meal in it is a
-- patient record, not residue.
--
-- Usage (dry run first — it prints the target list and rolls back):
--   psql … -v dry_run=1 -f deactivate_incomplete_signups.sql
--   psql … -v dry_run=0 -f deactivate_incomplete_signups.sql

\set ON_ERROR_STOP on

BEGIN;

-- Same ledger the test-account cleanup writes to, so one rollback path serves
-- both and an operator has a single place to look for "what was retired".
CREATE TABLE IF NOT EXISTS deactivated_accounts (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL,
    original_email  VARCHAR(255) NOT NULL,
    identity_email  VARCHAR(255),
    reason          VARCHAR(100) NOT NULL,
    deactivated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id)
);

CREATE TEMP TABLE _targets ON COMMIT DROP AS
SELECT u.id, u.email, u.full_name, u.created_at
FROM users u
WHERE u.is_active = true
  AND u.is_superuser = false
  AND (
        u.last_login IS NULL
     OR u.last_login < now() - interval '30 days'
     -- The only sign-in on record is the automatic one at registration.
     OR u.last_login <= u.created_at + interval '5 minutes'
      )
  AND u.created_at < now() - interval '7 days'
  AND NOT EXISTS (SELECT 1 FROM subscriptions         s  WHERE s.user_id  = u.id)
  AND NOT EXISTS (SELECT 1 FROM nutrition_logs        n  WHERE n.user_id  = u.id)
  AND NOT EXISTS (SELECT 1 FROM medication_dose_logs  m  WHERE m.user_id  = u.id)
  AND NOT EXISTS (SELECT 1 FROM medications           md WHERE md.user_id = u.id)
  AND NOT EXISTS (SELECT 1 FROM vitals_logs           v  WHERE v.user_id  = u.id)
  AND NOT EXISTS (SELECT 1 FROM lab_results           l  WHERE l.user_id  = u.id)
  AND NOT EXISTS (SELECT 1 FROM chronic_conditions    c  WHERE c.user_id  = u.id)
  AND NOT EXISTS (SELECT 1 FROM therapy_sessions      t  WHERE t.user_id  = u.id);

\echo ''
\echo '── accounts to retire (unused since signup, never paid, no clinical data) ──'
SELECT count(*) AS target_count FROM _targets;
SELECT id, email, full_name, created_at FROM _targets ORDER BY id LIMIT 25;
\echo '(showing at most 25)'
\echo ''

-- Reported, not withheld: an operator must SEE anything unexpected in the set
-- before applying. A recent signup here means the 7-day window is too short.
\echo '── newest account in the target set (sanity check on the window) ──'
SELECT max(created_at) AS newest_target FROM _targets;
\echo ''

-- 1. Preserve the originals so this is reversible.
INSERT INTO deactivated_accounts (user_id, original_email, reason)
SELECT t.id, t.email, 'incomplete signup (one-step form)'
FROM _targets t
ON CONFLICT (user_id) DO NOTHING;

-- 2 + 3. Deactivate and neutralise the address. `.invalid` is reserved by
--     RFC 2606 and can never resolve, so the scrambled address cannot reach a
--     real mailbox — and the REAL address becomes free to sign up with again,
--     which is the whole point for the person this was found from.
UPDATE users u
SET is_active = false,
    email = 'incomplete.' || u.id || '@invalid'
FROM _targets t
WHERE u.id = t.id;

-- 4. Same accounts in the identity store (the primary credential store).
--    Skipping this leaves the credential live: the login path provisions an
--    ALAFIA user on first successful identity auth, so a disabled public row
--    alone does not stop the account coming back.
UPDATE identity.users i
SET account_status = 'disabled',
    updated_at = now()
FROM _targets t
WHERE lower(i.email) = lower(t.email);

UPDATE deactivated_accounts d
SET identity_email = t.email
FROM _targets t
WHERE d.user_id = t.id AND d.identity_email IS NULL;

\echo '── after ──'
SELECT count(*) AS still_active_with_that_shape
FROM users u
WHERE u.is_active = true
  AND u.id IN (SELECT id FROM _targets);

\if :dry_run
  \echo 'DRY RUN — rolling back. Nothing was written.'
  ROLLBACK;
\else
  \echo 'APPLIED.'
  COMMIT;
\endif
