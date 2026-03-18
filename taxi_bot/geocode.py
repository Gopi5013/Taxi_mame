import json
from functools import lru_cache
from urllib.parse import urlencode
from urllib.request import Request, urlopen


NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "vinayaga-taxi-bot/1.0 (telegram)"


def _coords_text(latitude: float, longitude: float) -> str:
    return f"{latitude:.6f}, {longitude:.6f}"


@lru_cache(maxsize=1024)
def _reverse_geocode_cached(latitude: float, longitude: float) -> str:
    query = urlencode(
        {
            "format": "jsonv2",
            "lat": f"{latitude:.6f}",
            "lon": f"{longitude:.6f}",
            "zoom": 16,
            "addressdetails": 1,
        }
    )
    request = Request(f"{NOMINATIM_URL}?{query}", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=5) as response:  # nosec B310
        payload = json.loads(response.read().decode("utf-8"))

    display_name = payload.get("display_name")
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()

    return _coords_text(latitude, longitude)


def reverse_geocode(latitude: float, longitude: float) -> str:
    try:
        key_lat = round(float(latitude), 4)
        key_lon = round(float(longitude), 4)
        return _reverse_geocode_cached(key_lat, key_lon)
    except Exception:
        return _coords_text(latitude, longitude)


def format_place_label(latitude: float, longitude: float) -> str:
    place_name = reverse_geocode(latitude, longitude)
    return f"{place_name} ({_coords_text(latitude, longitude)})"
