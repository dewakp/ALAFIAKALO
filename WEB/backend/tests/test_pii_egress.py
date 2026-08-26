"""What is allowed to reach a third-party model provider.

Prompts carrying clinical material never get here — they are local-only
(`test_provider_order.py`). This pins the rules for the narrow set of calls that
legitimately opt out: the subject is identified by OUR token, and the text is
redacted at the egress point rather than by each call site remembering to.
"""

import pytest

from alafia_model import privacy


class _Adapter:
    def __init__(self, name, calls, seen, fail=False):
        self.name, self.calls, self.seen, self.fail = name, calls, seen, fail
        self.model_name = f"{name}-model"

    async def chat(self, messages, *a, **k):
        self.calls.append(self.name)
        self.seen.append(messages)
        if self.fail:
            raise RuntimeError(f"{self.name} down")
        return {"content": "ok", "tokens_used": 3, "model": self.model_name}

    complete = chat


# ── The subject token ─────────────────────────────────────────────────────────

def test_the_token_is_stable_for_the_same_user():
    assert privacy.subject_token(42) == privacy.subject_token(42)


def test_different_users_get_different_tokens():
    assert privacy.subject_token(42) != privacy.subject_token(43)


def test_the_token_does_not_contain_the_user_id():
    """It is a handle, not an encoding of the row id."""
    token = privacy.subject_token(123456)
    assert "123456" not in token
    assert token.startswith("alafia-")


def test_the_token_is_not_a_bare_hash_of_the_id(monkeypatch):
    """A plain sha256 of a small integer is reversible by enumeration."""
    import hashlib
    monkeypatch.setenv("ALAFIA_PSEUDONYM_SECRET", "a-real-secret")
    token = privacy.subject_token(7)
    assert hashlib.sha256(b"7").hexdigest()[:16] not in token


# ── Redaction ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,gone", [
    ("email me at jane.doe@example.com please", "jane.doe@example.com"),
    ("call +1 (555) 010-9999 after five", "555"),
    ("my ssn is 123-45-6789", "123-45-6789"),
    ("born 04/11/1962", "04/11/1962"),
    ("see https://portal.example.com/r/abc123", "portal.example.com"),
    ("record MRN0012345 attached", "MRN0012345"),
])
def test_direct_identifiers_are_redacted(raw, gone):
    assert gone not in privacy.scrub_pii(raw), privacy.scrub_pii(raw)


def test_clinical_content_survives_redaction():
    """Redaction must not eat the medically meaningful part of the sentence."""
    text = "I take calcitriol 0.5 mcg and my potassium was 5.2 on Tuesday"
    out = privacy.scrub_pii(text)
    assert "calcitriol" in out and "0.5 mcg" in out and "5.2" in out, out


@pytest.mark.parametrize("raw,gone", [
    ("Dr. Sarah Okafor increased my dose", "Okafor"),
    ("Nurse Adeyemi checked my fistula", "Adeyemi"),
    ("I'm Jane Doe and my potassium was 5.2", "Jane Doe"),
    ("my name is Ade Bello, I take calcitriol", "Ade Bello"),
])
def test_names_are_redacted_without_the_caller_supplying_them(raw, gone):
    """Found by capturing a REAL request body, not by a unit test.

    The first version of this module redacted emails, phones, dates and record
    numbers — and sent "I'm Jane Doe" straight to the provider. The unit tests
    passed because they only asserted on the identifiers the author remembered.
    """
    assert gone not in privacy.scrub_pii(raw), privacy.scrub_pii(raw)


def test_a_known_name_is_redacted_when_supplied():
    out = privacy.scrub_pii("Tell Bola I logged my meal", known_values=["Bola"])
    assert "Bola" not in out, out


def test_the_longest_known_value_wins():
    """Redacting "Jane" first would leave "[name] Doe" — still a surname."""
    out = privacy.scrub_pii("Jane Doe called", known_values=["Jane", "Jane Doe"])
    assert "Doe" not in out, out


def test_a_bare_name_in_passing_is_NOT_redacted():
    """The known limit of pattern matching, pinned so nobody assumes otherwise.

    "Bola" is a name, "Mark" is also a verb, "Dialysis" is capitalised
    mid-sentence, and no regex separates them. This is exactly why the real
    guarantee is local-only-by-default rather than redaction: patient free text
    does not reach a third party at all. If this ever starts passing because
    someone added a name model, update the comment — do not weaken the default.
    """
    assert "Bola" in privacy.scrub_pii("Tell Bola I logged my meal")


def test_scrub_payload_handles_a_message_list():
    msgs = [{"role": "user", "content": "reach me at a@b.co"}]
    out = privacy.scrub_payload(msgs)
    assert "a@b.co" not in out[0]["content"]
    assert out[0]["role"] == "user"
    assert msgs[0]["content"] == "reach me at a@b.co", "must not mutate the caller's list"


# ── The boundary itself ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_hosted_provider_never_receives_raw_pii(monkeypatch):
    from alafia_model.capabilities.llm import LLMCapability
    from alafia_model.registry.providers import ProviderSpec

    calls, seen = [], []
    cap = LLMCapability.__new__(LLMCapability)
    spec = ProviderSpec("groq", "https://x/v1", "GROQ_API_KEY", "m", "free", 1.0)
    monkeypatch.setattr("alafia_model.registry.providers.ordered_for_selection", lambda: [spec])
    monkeypatch.setattr(cap, "_adapter_for", lambda s: _Adapter("hosted", calls, seen),
                        raising=False)
    monkeypatch.delenv("OLLAMA_FIRST", raising=False)

    result = await cap.infer({
        "task": "chat", "local_only": False,
        "messages": [{"role": "user", "content": "I'm Jane Doe, jane@example.com, call 555-010-9999"}],
    })

    assert result.success
    sent = str(seen[-1])
    assert "jane@example.com" not in sent, sent
    assert "555-010-9999" not in sent, sent


@pytest.mark.asyncio
async def test_the_local_model_receives_the_text_unredacted(monkeypatch):
    """Redaction is an EGRESS control, not a data-quality one.

    ALAFIA-operated inference is inside the trust boundary and needs the real
    clinical detail; scrubbing there would degrade the answer for no privacy gain.
    """
    from alafia_model.capabilities.llm import LLMCapability

    calls, seen = [], []
    cap = LLMCapability.__new__(LLMCapability)
    monkeypatch.setattr(cap, "_get_adapter", lambda model=None: _Adapter("ollama", calls, seen),
                        raising=False)

    text = "I'm Jane Doe and my potassium was 5.2"
    result = await cap.infer({"task": "chat", "messages": [{"role": "user", "content": text}]})

    assert result.success
    assert calls == ["ollama"]
    assert "Jane Doe" in str(seen[-1]), "the local model must get the real text"


# ── Identity comes from the request, not from the caller ──────────────────────

def test_the_signed_in_user_is_replaced_by_our_token(monkeypatch):
    """The provider gets a handle that maps to a user id only inside our DB."""
    monkeypatch.setenv("ALAFIA_PSEUDONYM_SECRET", "test-secret")
    privacy.clear_identity()
    privacy.register_identity(user_id=63, name="Jane Doe",
                              email="jane@example.com", phone="+1 (555) 010-9999")
    try:
        out = privacy.scrub_pii("I'm Jane Doe, call me on +1 (555) 010-9999")
        assert "Jane Doe" not in out
        assert privacy.subject_token(63) in out, out
        assert "[phone]" in out, out
    finally:
        privacy.clear_identity()


def test_an_email_is_not_swapped_for_the_subject_token(monkeypatch):
    """Otherwise the prompt reads as though the patient were named after an address."""
    privacy.clear_identity()
    privacy.register_identity(user_id=7, name="Ada Lovelace", email="ada@example.com")
    try:
        out = privacy.scrub_pii("reach ada@example.com about Ada Lovelace")
        assert "[email]" in out, out
        assert out.count(privacy.subject_token(7)) == 1, out
    finally:
        privacy.clear_identity()


def test_no_registered_identity_still_redacts_by_pattern():
    """An unauthenticated or background path must not silently lose redaction."""
    privacy.clear_identity()
    out = privacy.scrub_pii("mail me at a@b.co, Dr. Sarah Okafor said so")
    assert "a@b.co" not in out and "Okafor" not in out, out


@pytest.mark.asyncio
async def test_identity_reaches_egress_without_the_caller_passing_it(monkeypatch):
    """The whole point: no call site has to remember."""
    from alafia_model.capabilities.llm import LLMCapability
    from alafia_model.registry.providers import ProviderSpec

    calls, seen = [], []
    cap = LLMCapability.__new__(LLMCapability)
    spec = ProviderSpec("groq", "https://x/v1", "GROQ_API_KEY", "m", "free", 1.0)
    monkeypatch.setattr("alafia_model.registry.providers.ordered_for_selection", lambda: [spec])
    monkeypatch.setattr(cap, "_adapter_for", lambda s: _Adapter("hosted", calls, seen),
                        raising=False)
    monkeypatch.delenv("OLLAMA_FIRST", raising=False)

    privacy.clear_identity()
    privacy.register_identity(user_id=99, name="Bola Adewale")
    try:
        # Note: no identity_hints in the payload at all.
        result = await cap.infer({
            "task": "chat",
            "messages": [{"role": "user", "content": "Bola Adewale here, potassium 5.2"}],
        })
        assert result.success
        sent = str(seen[-1])
        assert "Bola Adewale" not in sent, sent
        assert "5.2" in sent, "clinical detail must survive"
    finally:
        privacy.clear_identity()
