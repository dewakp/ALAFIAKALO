"""First/last name as separate fields, and the profile photo.

Two rules are pinned here because both were, at some point, enforced only in a
form: the 3-character minimum (a client-side check is UX, never enforcement)
and the derivation of `full_name` (85 rows and every greeting read it, so the
two forms drifting apart makes whichever surface you check second look broken).
"""

import io

import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate
from app.services.avatar import AvatarError, build_avatar


def _account(**over):
    base = dict(email="a@example.com", password="SecureP@ss123")
    base.update(over)
    return UserCreate(**base)


class TestNameParts:
    def test_the_parts_derive_the_full_name(self):
        u = _account(first_name="Adaeze", last_name="Okafor")
        assert u.full_name == "Adaeze Okafor"

    def test_a_two_letter_name_is_refused_at_the_boundary(self):
        # "Each field must be longer than 2 letters" — enforced by the API, so
        # web, iOS and Android cannot disagree about it.
        with pytest.raises(ValidationError):
            _account(first_name="Li", last_name="Okafor")
        with pytest.raises(ValidationError):
            _account(first_name="Adaeze", last_name="Ng")

    def test_neither_form_supplied_is_refused(self):
        with pytest.raises(ValidationError):
            _account()

    def test_a_shipped_client_sending_only_full_name_still_registers(self):
        # TestFlight 1.5 and the distributed APK post `full_name` alone.
        # Refusing them would break signup for everyone who has not updated.
        u = _account(full_name="Adaeze Okafor")
        assert (u.first_name, u.last_name) == ("Adaeze", "Okafor")

    def test_a_one_word_legacy_name_does_not_become_XXX(self):
        # `auth.register` used to send the literal "XXX" to the identity
        # service whenever a name had no second word.
        u = _account(full_name="Adaeze")
        assert u.first_name == "Adaeze"
        assert u.last_name == "Adaeze"
        assert "XXX" not in (u.first_name, u.last_name)

    def test_a_multiword_surname_survives_when_the_parts_are_sent(self):
        # The whole reason the parts are carried rather than re-split: no
        # amount of splitting recovers "Van Der Berg" from the joined string.
        u = _account(first_name="Ada", last_name="Van Der Berg")
        assert u.last_name == "Van Der Berg"


class TestAvatar:
    def _jpeg(self, size=(1200, 1600), colour=(30, 120, 200)):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", size, colour).save(buf, format="JPEG")
        return buf.getvalue()

    def test_a_phone_photo_becomes_a_small_square_data_uri(self):
        out = build_avatar(self._jpeg(), "image/jpeg")
        assert out.startswith("data:image/jpeg;base64,")
        # A 12 MB phone photo stored verbatim would ride on every user payload.
        assert len(out) < 120_000

    def test_a_transparent_png_does_not_come_back_black(self):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGBA", (400, 400), (255, 0, 0, 0)).save(buf, format="PNG")
        out = build_avatar(buf.getvalue(), "image/png")
        assert out.startswith("data:image/jpeg;base64,")

    def test_a_non_image_is_refused_with_a_sentence_a_person_can_read(self):
        with pytest.raises(AvatarError) as exc:
            build_avatar(b"this is not a photo", "image/jpeg")
        # Not a stack trace and not "422" — the message is shown to whoever
        # picked the file.
        assert "image" in str(exc.value).lower()

    def test_an_empty_upload_is_refused(self):
        with pytest.raises(AvatarError):
            build_avatar(b"", "image/jpeg")


class TestSignupCarriesPhone:
    """Phone survives the consolidation onto the two-step flow.

    Web registration used to be a one-step form that collected a phone number;
    `auth.register` stored it as `users.phone_number` and the login path looks
    accounts up by it. `pending_registrations` had no column for it, so merging
    the two forms without noticing would have removed phone login for every new
    account — invisibly, because nothing errors when a field simply stops being
    collected.
    """

    def test_the_pending_row_has_somewhere_to_put_it(self):
        from app.models.pending_registration import PendingRegistration
        assert "phone" in PendingRegistration.__table__.columns

    def test_the_endpoint_accepts_it_and_it_is_optional(self):
        from app.api.signup import SignupStart
        base = dict(email="a@example.com", password="SecureP@ss123",
                    first_name="Adaeze", last_name="Okafor",
                    date_of_birth="1990-01-01")
        assert SignupStart(**base).phone is None
        assert SignupStart(**base, phone="+15551234567").phone == "+15551234567"

    def test_it_reaches_the_created_user(self):
        # `materialise` is what turns a pending row into an account. If it does
        # not copy the phone across, the column is filled at signup and empty
        # on the user — which reads as "phone login is broken" rather than
        # "phone was never carried".
        import inspect
        from app.services import signup_service
        src = inspect.getsource(signup_service.materialise)
        assert "phone_number=pending.phone" in src
