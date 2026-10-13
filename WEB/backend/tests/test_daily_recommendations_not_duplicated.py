# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""Every recommendation card rendered twice.

Reported from the live screen 2026-10-13: *"every card here is duplicated"* —
Nutrition showed **4** for two real recommendations, Fitness 2 for one, Sleep 2
for one, Medication 2 for one. The section counts agreed with the duplicates,
so the doubling was upstream of the layout.

The API was innocent and the schema was not. `/wellness/recommendations`
returned the same eight items **twice**:

    recommendations  [8]           the flat list, every item carrying `category`
    nutrition        [2]  ┐
    fitness          [1]  │
    sleep            [1]  ├─ the SAME eight items, split by category
    medication       [1]  │
    mood             [1]  │
    hydration        [1]  │
    general          [1]  ┘

Both mobile clients decode only `recommendations` and ignored the mirrors. The
single reader of those seven fields was the web page, which pushed the flat list
and *then* looped the category keys — so **the duplicate field's only reader was
the code it broke**. §3ai's "two computations of one quantity must not disagree",
in the case where they agreed and were added together.

> The web loop also asked for a category the API never sent — `medical` — while
> missing two it did send: `hydration` and `general`. A hand-written list of
> keys standing beside a payload that already names them.
"""

import inspect

import pytest

from app.schemas.wellness import DailyRecommendationsResponse


def test_the_response_carries_ONE_list():
    """The per-category mirrors are gone. A client that wants them grouped
    groups them — every item carries its own `category`."""
    fields = set(DailyRecommendationsResponse.model_fields)
    assert fields == {"date", "recommendations"}, (
        f"unexpected fields {fields - {'date', 'recommendations'}} — a second "
        "view of the same items is what produced duplicate cards")


def test_no_per_category_mirror_returns():
    """Pinned by NAME, so re-adding one fails here rather than on a screen."""
    for mirror in ("nutrition", "fitness", "sleep", "medication", "mood",
                   "hydration", "general"):
        assert mirror not in DailyRecommendationsResponse.model_fields, (
            f"`{mirror}` duplicates items already in `recommendations`")


def test_the_endpoint_does_not_splat_a_second_copy():
    """The construction read `DailyRecommendationsResponse(..., **recs)`, which
    is what put the same items back in a second time.

    ⚠️ Checked on the AST, not the source TEXT. The first version grepped for
    `"**recs"` and failed on the COMMENT that explains the removal — a guard
    tripping over its own documentation. §3av: a scan is evidence only once it
    is shown to see what it claims to, and here it was reading prose rather
    than code.
    """
    import ast
    import textwrap

    from app.api.wellness import get_daily_recommendations

    tree = ast.parse(textwrap.dedent(inspect.getsource(get_daily_recommendations)))
    splats = [
        kw for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "DailyRecommendationsResponse"
        for kw in node.keywords if kw.arg is None      # `**something`
    ]
    assert not splats, (
        "splatting a dict into the response returns every item twice")


@pytest.mark.asyncio
async def test_a_real_user_gets_each_recommendation_once(db):
    """End to end against a seeded account, counting ROWS rather than trusting
    the shape: a dedupe bug that reports the right fields while returning the
    same title twice is exactly what this guards.

    Seeds its own user — dev holds real PHI.
    """
    from app.api.wellness import get_daily_recommendations
    from app.models.user import User

    user = User(email="recs@example.test", hashed_password="not-a-real-hash",
                full_name="Ada Demo")
    db.add(user)
    await db.flush()

    result = await get_daily_recommendations(
        current_user=user, db=db, client_timezone=None)
    items = result.recommendations
    seen = [(r.category, r.title) for r in items]
    assert len(seen) == len(set(seen)), (
        f"a recommendation appears more than once: "
        f"{[s for s in seen if seen.count(s) > 1]}")
