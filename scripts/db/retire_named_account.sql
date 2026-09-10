-- Retire ONE account the operator names — REVERSIBLE.
--
-- The bulk script (`deactivate_incomplete_signups.sql`) selects by state and
-- deliberately refuses anything younger than 7 days, so an account created
-- today is out of its reach even when it is plainly residue. This is the
-- operator-directed counterpart: the address is named on the command line
-- rather than matched, because the judgement that it should go is a person's.
--
-- Naming it does NOT switch the safety off. The account must still hold no
-- clinical data and no subscription; if it does, this REFUSES rather than
-- retiring it. An operator naming an address is stating intent, not asserting
-- the row is empty — and "I meant that one" is exactly how a patient record
-- gets deleted.
--
-- Mechanism is identical to the bulk script, so one rollback path serves both:
-- deactivate, scramble the address to a reserved `.invalid` domain (which is
-- what FREES the real address), disable the identity credential, and record
-- the original in `deactivated_accounts`.
--
-- Usage:
--   psql … -v dry_run=1 -v target_email="'someone@example.com'" -f retire_named_account.sql
--   psql … -v dry_run=0 -v target_email="'someone@example.com'" -f retire_named_account.sql

\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS deactivated_accounts (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL,
    original_email  VARCHAR(255) NOT NULL,
    identity_email  VARCHAR(255),
    reason          VARCHAR(100) NOT NULL,
    deactivated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id)
);

CREATE TEMP TABLE _target ON COMMIT DROP AS
SELECT u.id, u.email, u.full_name, u.created_at
FROM users u
WHERE lower(u.email) = lower(:target_email)
  AND u.is_active = true;

\echo ''
\echo '── the named account ──'
SELECT id, email, full_name, created_at FROM _target;

-- The guard. Counted BEFORE anything is written, and reported, so an operator
-- sees why a refusal happened rather than just that it did.
\echo ''
\echo '── what it holds (all must be 0 to proceed) ──'
SELECT
  (SELECT count(*) FROM subscriptions        s  JOIN _target t ON s.user_id  = t.id) AS subscriptions,
  (SELECT count(*) FROM nutrition_logs       n  JOIN _target t ON n.user_id  = t.id) AS meals,
  (SELECT count(*) FROM medication_dose_logs m  JOIN _target t ON m.user_id  = t.id) AS dose_logs,
  (SELECT count(*) FROM medications          md JOIN _target t ON md.user_id = t.id) AS prescriptions,
  (SELECT count(*) FROM vitals_logs          v  JOIN _target t ON v.user_id  = t.id) AS vitals,
  (SELECT count(*) FROM lab_results          l  JOIN _target t ON l.user_id  = t.id) AS labs,
  (SELECT count(*) FROM chronic_conditions   c  JOIN _target t ON c.user_id  = t.id) AS conditions,
  (SELECT count(*) FROM therapy_sessions     th JOIN _target t ON th.user_id = t.id) AS therapy_sessions;

DO $$
DECLARE
    n_target integer;
    n_data   integer;
BEGIN
    SELECT count(*) INTO n_target FROM _target;
    IF n_target = 0 THEN
        RAISE EXCEPTION 'No ACTIVE account with that address. Nothing to retire.';
    END IF;
    IF n_target > 1 THEN
        RAISE EXCEPTION 'More than one active account matched — refusing.';
    END IF;

    SELECT
        (SELECT count(*) FROM subscriptions        s  JOIN _target t ON s.user_id  = t.id)
      + (SELECT count(*) FROM nutrition_logs       n  JOIN _target t ON n.user_id  = t.id)
      + (SELECT count(*) FROM medication_dose_logs m  JOIN _target t ON m.user_id  = t.id)
      + (SELECT count(*) FROM medications          md JOIN _target t ON md.user_id = t.id)
      + (SELECT count(*) FROM vitals_logs          v  JOIN _target t ON v.user_id  = t.id)
      + (SELECT count(*) FROM lab_results          l  JOIN _target t ON l.user_id  = t.id)
      + (SELECT count(*) FROM chronic_conditions   c  JOIN _target t ON c.user_id  = t.id)
      + (SELECT count(*) FROM therapy_sessions     th JOIN _target t ON th.user_id = t.id)
      INTO n_data;

    IF n_data > 0 THEN
        RAISE EXCEPTION
            'REFUSED: that account holds % clinical or billing rows. Naming an '
            'address is not a statement that it is empty.', n_data;
    END IF;
END $$;

INSERT INTO deactivated_accounts (user_id, original_email, reason)
SELECT t.id, t.email, 'incomplete signup (operator-named)'
FROM _target t
ON CONFLICT (user_id) DO NOTHING;

UPDATE users u
SET is_active = false,
    email = 'incomplete.' || u.id || '@invalid'
FROM _target t
WHERE u.id = t.id;

-- The identity store is the primary credential store. Leaving it enabled means
-- the login path can provision a fresh ALAFIA user on the next successful auth.
UPDATE identity.users i
SET account_status = 'disabled',
    updated_at = now()
FROM _target t
WHERE lower(i.email) = lower(t.email);

UPDATE deactivated_accounts d
SET identity_email = t.email
FROM _target t
WHERE d.user_id = t.id AND d.identity_email IS NULL;

\echo ''
\echo '── after: the address should now be free ──'
SELECT count(*) AS still_using_that_address
FROM users WHERE lower(email) = lower(:target_email);

\if :dry_run
  \echo 'DRY RUN — rolling back. Nothing was written.'
  ROLLBACK;
\else
  \echo 'APPLIED.'
  COMMIT;
\endif
