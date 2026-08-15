"""Account-holder age rule.

The interesting cases are the boundaries: the day before a birthday, the
birthday itself, a leap-day birth evaluated in a non-leap year, and an unknown
country falling back to the strictest threshold rather than a permissive one.
"""

from datetime import date

import pytest

from app.core.age_policy import (
    STRICTEST_MINIMUM_AGE,
    AgeRestricted,
    InvalidDateOfBirth,
    age_on,
    assert_adult,
    minimum_age_for,
)


class TestAgeOn:
    def test_birthday_not_yet_reached_this_year(self):
        # Born 1 June; on 31 May they are still one year younger.
        assert age_on(date(2010, 6, 1), date(2026, 5, 31)) == 15

    def test_on_the_birthday_they_are_the_new_age(self):
        assert age_on(date(2010, 6, 1), date(2026, 6, 1)) == 16

    def test_leap_day_birth_turns_older_on_1_march_in_a_common_year(self):
        # 2026 has no 29 February. A leap-day child must not age a day early.
        assert age_on(date(2008, 2, 29), date(2026, 2, 28)) == 17
        assert age_on(date(2008, 2, 29), date(2026, 3, 1)) == 18

    def test_uses_calendar_years_not_365_25_days(self):
        # Four consecutive years including a leap year is exactly 4.
        assert age_on(date(2000, 3, 1), date(2004, 3, 1)) == 4


class TestMinimumAgeForCountry:
    @pytest.mark.parametrize("country,expected", [
        ("US", 13), ("us", 13), (" gb ", 13),   # COPPA / UK GDPR
        ("FR", 15), ("DE", 16), ("IT", 14),     # GDPR Art. 8, per member state
    ])
    def test_known_countries(self, country, expected):
        assert minimum_age_for(country) == expected

    @pytest.mark.parametrize("country", [None, "", "  ", "ZZ", "Atlantis"])
    def test_unknown_country_uses_the_strictest_threshold(self, country):
        # Never guess permissively: admitting a child we were not permitted to
        # is the failure that carries regulatory weight.
        assert minimum_age_for(country) == STRICTEST_MINIMUM_AGE == 16


class TestAssertAdult:
    def test_adult_is_allowed_and_age_returned(self):
        assert assert_adult("1990-06-01", "US", today=date(2026, 1, 1)) == 35

    def test_thirteen_year_old_allowed_in_the_us_but_not_in_germany(self):
        dob, today = "2013-01-01", date(2026, 6, 1)
        assert assert_adult(dob, "US", today=today) == 13
        with pytest.raises(AgeRestricted) as exc:
            assert_adult(dob, "DE", today=today)
        assert exc.value.minimum_age == 16
        assert exc.value.age == 13

    def test_exactly_at_the_threshold_is_permitted(self):
        # Boundary: 16th birthday, threshold 16 → allowed, not off by one.
        assert assert_adult("2010-06-01", "DE", today=date(2026, 6, 1)) == 16

    def test_one_day_before_the_threshold_is_refused(self):
        with pytest.raises(AgeRestricted):
            assert_adult("2010-06-01", "DE", today=date(2026, 5, 31))

    def test_unknown_country_applies_sixteen(self):
        with pytest.raises(AgeRestricted) as exc:
            assert_adult("2012-01-01", None, today=date(2026, 6, 1))
        assert exc.value.minimum_age == 16

    @pytest.mark.parametrize("bad", [None, "", "   ", "not-a-date", "01/02/2010"])
    def test_missing_or_malformed_dob_is_rejected(self, bad):
        with pytest.raises(InvalidDateOfBirth):
            assert_adult(bad, "US")

    def test_future_date_of_birth_is_rejected(self):
        # Must not slip through as a negative age.
        with pytest.raises(InvalidDateOfBirth):
            assert_adult("2999-01-01", "US", today=date(2026, 6, 1))

    def test_accepts_a_full_iso_timestamp(self):
        assert assert_adult("1990-06-01T00:00:00Z", "US", today=date(2026, 1, 1)) == 35
