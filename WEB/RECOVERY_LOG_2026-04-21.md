# Recovery Log - 2026-04-21

## Incident Summary
- Backend auth and iOS login failures were observed while the DB container was unhealthy.
- Postgres entered a crash loop with `No space left on device` errors.
- Registration was also broken by a missing Rust extension function (`alafia_crypto.generate_sid`).

## Root Causes
1. Docker disk exhaustion from repeated image rebuilds and build cache growth.
2. Backend Dockerfile had Rust crypto build steps commented out, so `alafia_crypto` was installed without expected symbol exports.

## Corrective Actions Performed
1. Confirmed DB failure from logs (`No space left on device` / `postmaster.pid`).
2. Freed Docker space by pruning build cache.
3. Restarted DB and verified readiness/health.
4. Restored Rust extension build in backend image using wheel build/install:
   - `maturin build --release`
   - `pip install target/wheels/*.whl`
5. Rebuilt backend image and restarted backend container.
6. Verified `alafia_crypto` now exposes `generate_sid` in running container.

## Validation Results
- Services: backend, db, chain all healthy.
- Auth flow: register `201`, login `200`.
- AI chat endpoint: returns `200` but can be slow locally (~59-123 seconds observed).

## Remaining Notes
- Local AI latency can exceed short curl timeouts; use >=120s timeout for non-streaming chat tests in this environment.
- Compose warning about obsolete `version` key is non-blocking but should be cleaned up later.
