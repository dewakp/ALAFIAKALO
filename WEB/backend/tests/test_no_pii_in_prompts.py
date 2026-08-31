"""No direct identifier may be interpolated into a string. Fails the build.

Canon §3al says the patient's IDENTITY never leaves — the clinical detail does.
That was enforced in two places at once: `_fetch_patient_context` sent an HMAC
`subject_token`, and `scrub_pii` redacted anything that slipped past it at the
single egress point.

Neither held. Four prompt builders opened with `PATIENT: {user.full_name}` and
shipped the patient's real name to a model provider:

    app/api/planners.py   meal plan, meal suggestions, exercise plan
    app/api/image_ai.py   drug-drug interaction check

The egress scrubber is a backstop, not the control:
  - it only runs on the HOSTED path. `try_hosted()` is where redaction lives,
    so every one of these prompts reached Ollama with the name intact, and in
    dev Ollama is the PREFERRED provider (§3ak).
  - it depends on recognising the value. §3al already records, as a passing
    test, that a bare name in passing is NOT detectable by pattern.

So the rule this file enforces is the stronger one, and the one §3al actually
states: do not assemble the identifier in the first place.

To add a legitimate use, put it in ALLOWED with a comment saying why — the same
contract as `tests/test_clinical_sources.py`.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

# Direct identifiers (HIPAA's 18) as they are named on our models. `gender`,
# `age`, `height_cm`, `current_weight_kg` and the clinical fields are NOT here:
# a dietitian model needs them, and they do not identify anyone on their own.
FORBIDDEN_ATTRS = frozenset({
    "full_name",
    "email",
    "phone_number",
    "date_of_birth",
    "insurance_id",
    "profile_picture_url",
    "firebase_uid",
    "identity_uid",
    "system_id",
})

# Objects that hold a patient. A local `row.email` on some unrelated model is
# not what this test is about.
SUBJECTS = frozenset({"user", "current_user", "patient", "u", "usr", "owner", "member"})

# (path relative to app/, attribute) -> why it is allowed.
ALLOWED: dict[tuple[str, str], str] = {
    # The admin console renders the operator's own audit line; never a prompt.
    ("core/admin_auth.py", "email"): "admin audit log line, not a model prompt",
    # Account recovery and sign-in must address a real mailbox.
    ("api/auth.py", "email"): "password reset / sign-in address the real user",
    ("api/signup.py", "email"): "verification mail addresses the real user",
    ("core/entitlement.py", "email"): "paywall exemption allowlist is by email",
    ("api/data_sharing.py", "email"): "invitations are matched by recipient email",
    # Clinician- and patient-facing OUTPUT. These render to a human who is
    # already entitled to the record; they do not go to a model provider.
    ("api/clinician_dashboard.py", "full_name"): "clinician UI shows their own patient",
    ("api/clinician_dashboard.py", "email"): "clinician UI shows their own patient",
    ("api/admin.py", "full_name"): "admin console user list",
    ("api/admin.py", "email"): "admin console user list",
    ("api/admin.py", "phone_number"): "admin console user detail",
    ("api/pharmacy.py", "full_name"): "a prescription is a legal document naming the patient",
    ("api/physicians.py", "full_name"): "review byline, shown to other users",
    ("api/user_roles.py", "full_name"): "role directory entry",
    ("api/user_roles.py", "email"): "role directory entry",
    ("api/pdf_tools.py", "full_name"): "exported PDF header for the patient's own record",
    ("api/pdf_tools.py", "email"): "exported PDF header for the patient's own record",
    # DOB -> age conversions. The DATE is never sent; these call sites hand it
    # to a parser that returns whole years (see nutrient_goals_service._calc_age).
    ("api/ai.py", "date_of_birth"): "converted to age before it enters context",
    ("api/nutrition.py", "date_of_birth"): "converted to age for goal computation",
    ("api/personalization.py", "date_of_birth"): "converted to age for goal computation",
    ("api/wellness.py", "date_of_birth"): "converted to age for goal computation",
    ("api/planners.py", "date_of_birth"): "converted to age for goal computation",
}


def _iter_python_files():
    for path in sorted(APP.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _violations() -> list[str]:
    found: list[str] = []
    for path in _iter_python_files():
        rel = str(path.relative_to(APP))
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            # An f-string is how a prompt gets built. A plain `user.email`
            # passed to a mailer is not this test's business.
            if not isinstance(node, ast.JoinedStr):
                continue
            for part in ast.walk(node):
                if not isinstance(part, ast.Attribute):
                    continue
                if part.attr not in FORBIDDEN_ATTRS:
                    continue
                base = part.value
                base_name = (
                    base.id if isinstance(base, ast.Name)
                    else getattr(base, "attr", None)
                )
                if base_name not in SUBJECTS:
                    continue
                if (rel, part.attr) in ALLOWED:
                    continue
                found.append(f"{rel}:{part.lineno}  f-string interpolates {base_name}.{part.attr}")
    return found


def test_no_direct_identifier_is_interpolated_into_a_string():
    violations = _violations()
    assert not violations, (
        "A direct identifier is being formatted into a string. If it reaches a "
        "model provider this is a PHI disclosure — the egress scrubber runs only "
        "on the hosted path and only on values it recognises.\n\n"
        "Send app.services.prompt_identity.subject_reference(user) instead, or "
        "add an entry to ALLOWED with the reason.\n\n  "
        + "\n  ".join(violations)
    )


def test_the_four_prompts_that_leaked_are_still_clean():
    """Pins the specific regression rather than trusting the sweep alone."""
    for rel in ("api/planners.py", "api/image_ai.py"):
        src = (APP / rel).read_text()
        # The exact shape that shipped — as an f-string, not as the docstring
        # in planners.py that records why it is gone.
        assert 'f"PATIENT: {user.full_name' not in src, rel
        assert 'f"PATIENT: {current_user.full_name' not in src, rel


def test_allowed_entries_all_point_at_a_real_file():
    """A stale allow-list quietly stops enforcing anything."""
    missing = [rel for (rel, _attr) in ALLOWED if not (APP / rel).exists()]
    assert not missing, f"ALLOWED names files that no longer exist: {missing}"
