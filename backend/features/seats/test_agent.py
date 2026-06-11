"""Tests for the seat agent: rubric coercion + ring banding (no live Gemini)."""

from backend.features.seats import agent, service


def test_ring_banding():
    assert agent._ring_for(90) == "excellent"
    assert agent._ring_for(72) == "great"
    assert agent._ring_for(60) == "good"
    assert agent._ring_for(45) == "fair"
    assert agent._ring_for(10) == "poor"


def test_coerce_recomputes_overall_from_weights():
    raw = {
        "overall": 999,  # bogus — must be ignored / recomputed
        "ring": "garbage",
        "dimensions": {
            "view_clarity": {"score": 80, "note": "open"},
            "proximity": {"score": 60, "note": "mid"},
            "value": {"score": 70, "note": "ok"},
            "obstruction": {"score": 90, "note": "clear"},
            "atmosphere": {"score": 50, "note": "quiet"},
        },
        "summary": "decent",
        "confidence": "high",
    }
    out = agent._coerce(raw)
    # weighted: 80*.3 + 60*.25 + 70*.2 + 90*.15 + 50*.1 = 24+15+14+13.5+5 = 71.5 -> 72
    assert out["overall"] == 72
    assert out["ring"] == "great"
    assert out["confidence"] == "high"
    assert set(out["dimensions"]) == set(agent.DIMENSION_WEIGHTS)


def test_coerce_rejects_missing_dimensions():
    assert agent._coerce({"summary": "no dims"}) is None


def test_match_seats_scores_only_top_n(monkeypatch, tmp_path):
    venue_dir = tmp_path / "mercedes_benz_stadium"
    venue_dir.mkdir()
    for sec in ("101", "102", "103", "104", "105"):
        (venue_dir / f"section{sec}-1.jpg").write_bytes(b"")

    calls: list[str] = []

    def fake_score_seat(section, photo_path, price=None, view=None):
        calls.append(section)
        return {"overall": 80, "ring": "great", "dimensions": {},
                "summary": "", "confidence": "high"}

    monkeypatch.setattr(agent, "score_seat", fake_score_seat)

    listings = [
        {"section": "101", "section_type": "section", "price": 500},
        {"section": "102", "section_type": "section", "price": 100},
        {"section": "103", "section_type": "section", "price": 300},
        {"section": "104", "section_type": "section", "price": 200},
        {"section": "105", "section_type": "section", "price": 400},
    ]

    service.match_seats(
        "Mercedes-Benz Stadium",
        listings,
        photos_root=str(tmp_path),
        with_agent_score=True,
        score_top_n=2,
    )

    # Without a buyer section, an even price spread is graded (cheapest +
    # priciest), not just the two cheapest.
    assert len(calls) == 2
    assert "102" in calls  # cheapest
    assert "101" in calls  # priciest


def test_select_scoring_order_brackets_buyer_section(monkeypatch, tmp_path):
    venue_dir = tmp_path / "mercedes_benz_stadium"
    venue_dir.mkdir()
    for sec in ("101", "102", "103", "104", "105"):
        (venue_dir / f"section{sec}-1.jpg").write_bytes(b"")

    calls: list[str] = []

    def fake_score_seat(section, photo_path, price=None, view=None):
        calls.append(section)
        return {"overall": 80, "ring": "great", "dimensions": {},
                "summary": "", "confidence": "high"}

    monkeypatch.setattr(agent, "score_seat", fake_score_seat)

    listings = [
        {"section": "101", "section_type": "section", "price": 500},
        {"section": "102", "section_type": "section", "price": 100},
        {"section": "103", "section_type": "section", "price": 300},  # buyer
        {"section": "104", "section_type": "section", "price": 200},
        {"section": "105", "section_type": "section", "price": 400},
    ]

    local = service.attach_seat_photos(
        "Mercedes-Benz Stadium", listings, photos_root=str(tmp_path)
    )
    order = service.select_scoring_order(
        listings, local, 3, prioritize_section="103"
    )
    picked = [listings[i]["section"] for i in order]

    # Buyer's section leads, and the set brackets it (something pricier AND
    # something cheaper than 300).
    assert picked[0] == "103"
    prices = [listings[i]["price"] for i in order]
    assert any(p > 300 for p in prices)
    assert any(p < 300 for p in prices)

