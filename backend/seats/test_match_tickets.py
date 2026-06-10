import os
import tempfile
import unittest

import match_tickets


class MatchTicketsTest(unittest.TestCase):
    def test_build_photo_url(self):
        photos_root = os.path.join("seats-data", "photos_avfms")
        photo = os.path.join(
            photos_root,
            "mercedes_benz_stadium",
            "section217-1.jpg",
        )

        url = match_tickets.build_photo_url(
            photo,
            photos_root,
            "http://localhost:8001",
        )

        self.assertEqual(
            url,
            "http://localhost:8001/photos_avfms/"
            "mercedes_benz_stadium/section217-1.jpg",
        )

    def test_find_photos(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "section217-1.jpg")
            with open(path, "wb"):
                pass

            photos, status = match_tickets.find_photos(folder, "217", "217")

        self.assertEqual(photos, [path])
        self.assertEqual(status, "matched")


if __name__ == "__main__":
    unittest.main()
