"""Optional OpenSky state-vector connector; no credentials are stored in code."""
from datetime import datetime, timezone

import requests

OPENSKY_URL = "https://opensky-network.org/api/states/all"


def _at(vector, index):
    """State vectors vary in length between API versions; never index past the end."""
    return vector[index] if index < len(vector) else None


def parse_state_vector(s):
    """One OpenSky state vector (a list) -> dict. Missing trailing fields become None."""
    callsign = (_at(s, 1) or "").strip() or None
    return {
        "icao24": _at(s, 0), "callsign": callsign, "origin_country": _at(s, 2),
        "time_position": _at(s, 3), "last_contact": _at(s, 4),
        "longitude": _at(s, 5), "latitude": _at(s, 6), "baro_altitude_m": _at(s, 7),
        "on_ground": _at(s, 8), "velocity_mps": _at(s, 9), "heading_deg": _at(s, 10),
        "vertical_rate_mps": _at(s, 11), "geo_altitude_m": _at(s, 13), "squawk": _at(s, 14),
        "position_source": _at(s, 16),
    }


def fetch_opensky(lat=13.1986, lon=77.7066, half_width=0.3, timeout=12):
    # OpenSky API bounding box: lamin, lomin, lamax, lomax.
    params = {"lamin": lat - half_width, "lomin": lon - half_width, "lamax": lat + half_width, "lomax": lon + half_width}
    try:
        response = requests.get(OPENSKY_URL, params=params, timeout=timeout)
        if response.status_code in (401, 403):
            return {"error": "OpenSky denied the request. Check current authentication requirements, quotas, and API access."}
        if response.status_code == 429:
            return {"error": "OpenSky rate limit reached (HTTP 429). Wait a while before fetching again."}
        response.raise_for_status()
        payload = response.json()
        aircraft = [parse_state_vector(s) for s in (payload.get("states") or [])]
        return {"fetched_at": datetime.now(timezone.utc).isoformat(), "aircraft": aircraft, "time": payload.get("time")}
    except requests.RequestException as exc:
        return {"error": f"OpenSky request failed: {exc}. The simulation can still run with synthetic aircraft."}
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return {"error": f"Could not parse OpenSky response: {exc}"}


def lookup_aircraft_type(icao24, timeout=10):
    """Look up aircraft metadata by ICAO24 using ADSBdb; metadata may be absent."""
    hex_code = (icao24 or "").strip().lower()
    if not hex_code or len(hex_code) != 6:
        return {"error": "Enter a six-character ICAO24 hex address."}
    try:
        response = requests.get(f"https://api.adsbdb.com/v0/aircraft/hex/{hex_code}", timeout=timeout)
        if response.status_code == 404:
            return {"error": "No aircraft metadata found for this ICAO24 address."}
        response.raise_for_status()
        payload = response.json()
        aircraft = payload.get("response", {}).get("aircraft") or payload.get("aircraft") or {}
        if not aircraft:
            return {"error": "The metadata provider returned no aircraft details."}
        return {
            "icao24": hex_code,
            "registration": aircraft.get("registration"),
            "manufacturer": aircraft.get("manufacturer"),
            "type": aircraft.get("type"),
            "icao_type": aircraft.get("icao_type"),
            "registered_owner": aircraft.get("registered_owner"),
            "operator": aircraft.get("operator"),
        }
    except requests.RequestException as exc:
        return {"error": f"Aircraft metadata lookup failed: {exc}"}
    except (ValueError, TypeError, AttributeError) as exc:
        return {"error": f"Could not parse aircraft metadata: {exc}"}
