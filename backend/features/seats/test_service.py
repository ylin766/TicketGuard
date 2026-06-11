"""Tests for the seats matching service (in-memory port of match_tickets)."""

import os
import tempfile

from backend.features.seats import service


def test_build_photo_url():
    photos_root = os.path.join("seats-data", "photos_avfms")
    photo = os.path.join(
        photos_root, "mercedes_benz_stadium", "section217-1.jpg"
    )

    url = service._build_photo_url(photo, photos_root, "/seat-photos")

    assert url == (
        "/seat-photos/photos_avfms/mercedes_benz_stadium/section217-1.jpg"
    )


def test_find_photos():
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "section217-1.jpg")
        with open(path, "wb"):
            pass

        photos, status = service._find_photos(folder, "217", "217")

    assert photos == [path]
    assert status == "matched"


def test_match_seats_enriches_listings():
    with tempfile.TemporaryDirectory() as root:
        venue_dir = os.path.join(root, "mercedes_benz_stadium")
        os.makedirs(venue_dir)
        with open(os.path.join(venue_dir, "section217-1.jpg"), "wb"):
            pass

        listings = [
            {"section": "217", "section_type": "section"},
            {"section": "999", "section_type": "section"},
            {"section": "Category 1", "section_type": "category"},
        ]

        out = service.match_seats(
            "Mercedes-Benz Stadium",
            listings,
            image_base_url="/seat-photos",
            photos_root=root,
        )

    assert out[0]["match_status"] == "matched"
    assert out[0]["photo_count"] == 1
    assert out[0]["photo_urls"][0].endswith(
        "/mercedes_benz_stadium/section217-1.jpg"
    )
    assert out[1]["match_status"] == "no_photo"
    assert out[1]["photo_urls"] == []
    assert out[2]["match_status"] == "category"
