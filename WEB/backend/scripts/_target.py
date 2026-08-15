"""Resolve which patient an import script writes to — by EMAIL, never a literal id.

Every import script in this directory once carried `USER_ID = 1` (commented
"demo@alafia.app") or `CONDITION_ID = 14` (commented "ESRD"). Neither row exists
in this database. Two things follow, and both have happened:

  - The script writes clinical rows against a user id that belongs to nobody, or
    to somebody else entirely. Nothing announces this; the insert succeeds.
  - The same constant gets copied into a CLIENT. The web Hemodialysis form
    shipped `condition_id: 14`, so the API's ownership check rejected every
    session save with "Chronic condition not found".

Row ids are per-database and shift with every restore. An email address is
stable and is what a human actually knows. So scripts take `--user-email` and
resolve it here, failing loudly when it does not exist.

Test data belongs to **developer@hntsolutions.com** by convention — do not
invent throwaway accounts in a database that holds real patients.
"""

from __future__ import annotations


def resolve_user(conn, email: str) -> int:
    """users.id for an email, or exit with a message naming what was wrong."""
    cur = conn.cursor()
    cur.execute("SELECT id, is_active FROM users WHERE lower(email) = lower(%s)", (email,))
    row = cur.fetchone()
    if not row:
        raise SystemExit(
            f"no user with email {email!r} in this database.\n"
            "  Check the target: dev is 127.0.0.1:5435, production is reached "
            "through the Cloud SQL proxy on 5436."
        )
    user_id, is_active = row
    if not is_active:
        print(f"  ⚠ {email} is INACTIVE (id {user_id}) — writing to a deactivated account")
    return user_id


def resolve_condition(conn, user_id: int, category: str | None = None,
                      name_like: str | None = None) -> int | None:
    """A chronic condition id belonging to THIS user, or None.

    None is a valid answer: a therapy session without a condition still saves.
    A wrong id does not — the API verifies ownership and 404s.
    """
    cur = conn.cursor()
    if category:
        cur.execute(
            "SELECT id, condition_name FROM chronic_conditions "
            "WHERE user_id = %s AND upper(category::text) = upper(%s) "
            "ORDER BY is_active DESC, id LIMIT 1",
            (user_id, category),
        )
        row = cur.fetchone()
        if row:
            print(f"  condition: {row[1]} (id {row[0]})")
            return row[0]
    if name_like:
        cur.execute(
            "SELECT id, condition_name FROM chronic_conditions "
            "WHERE user_id = %s AND condition_name ILIKE %s "
            "ORDER BY is_active DESC, id LIMIT 1",
            (user_id, f"%{name_like}%"),
        )
        row = cur.fetchone()
        if row:
            print(f"  condition: {row[1]} (id {row[0]})")
            return row[0]
    print(f"  condition: none matched for user {user_id} — sessions will have no condition")
    return None
