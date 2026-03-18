import unittest
from unittest.mock import patch

from taxi_bot.geocode import format_place_label, reverse_geocode


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class GeocodeTests(unittest.TestCase):
    @patch("taxi_bot.geocode.urlopen")
    def test_reverse_geocode_uses_display_name(self, mock_urlopen) -> None:
        mock_urlopen.return_value = _FakeResponse(
            b'{"display_name": "MG Road, Bengaluru, Karnataka, India"}'
        )
        place = reverse_geocode(12.9716, 77.5946)
        self.assertIn("MG Road", place)

    @patch("taxi_bot.geocode.urlopen", side_effect=RuntimeError("network down"))
    def test_format_place_label_falls_back_to_coordinates(self, mock_urlopen) -> None:
        label = format_place_label(13.0827, 80.2707)
        self.assertEqual(label, "13.082700, 80.270700 (13.082700, 80.270700)")
        self.assertTrue(mock_urlopen.called)


if __name__ == "__main__":
    unittest.main()
