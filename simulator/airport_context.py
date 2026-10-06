"""Optional airport directory and live weather context. Research simulation only."""
from datetime import datetime, timezone
from functools import lru_cache
from io import BytesIO
import requests
import pandas as pd

AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"

FEATURED_AIRPORTS = [
    {"name": "Kempegowda International Airport", "iata": "BLR", "icao": "VOBL", "municipality": "Bengaluru", "latitude_deg": 13.1986, "longitude_deg": 77.7066, "type": "large_airport"},
    {"name": "Indira Gandhi International Airport", "iata": "DEL", "icao": "VIDP", "municipality": "Delhi", "latitude_deg": 28.5562, "longitude_deg": 77.1000, "type": "large_airport"},
    {"name": "Chhatrapati Shivaji Maharaj International Airport", "iata": "BOM", "icao": "VABB", "municipality": "Mumbai", "latitude_deg": 19.0896, "longitude_deg": 72.8656, "type": "large_airport"},
    {"name": "Chennai International Airport", "iata": "MAA", "icao": "VOMM", "municipality": "Chennai", "latitude_deg": 12.9941, "longitude_deg": 80.1709, "type": "large_airport"},
    {"name": "Rajiv Gandhi International Airport", "iata": "HYD", "icao": "VOHS", "municipality": "Hyderabad", "latitude_deg": 17.2403, "longitude_deg": 78.4294, "type": "large_airport"},
    {"name": "Heathrow Airport", "iata": "LHR", "icao": "EGLL", "municipality": "London", "latitude_deg": 51.4700, "longitude_deg": -0.4543, "type": "large_airport"},
    {"name": "John F. Kennedy International Airport", "iata": "JFK", "icao": "KJFK", "municipality": "New York", "latitude_deg": 40.6413, "longitude_deg": -73.7781, "type": "large_airport"},
    {"name": "Los Angeles International Airport", "iata": "LAX", "icao": "KLAX", "municipality": "Los Angeles", "latitude_deg": 33.9416, "longitude_deg": -118.4085, "type": "large_airport"},
    {"name": "Singapore Changi Airport", "iata": "SIN", "icao": "WSSS", "municipality": "Singapore", "latitude_deg": 1.3644, "longitude_deg": 103.9915, "type": "large_airport"},
    {"name": "Dubai International Airport", "iata": "DXB", "icao": "OMDB", "municipality": "Dubai", "latitude_deg": 25.2532, "longitude_deg": 55.3657, "type": "large_airport"},
    {"name": "Frankfurt Airport", "iata": "FRA", "icao": "EDDF", "municipality": "Frankfurt", "latitude_deg": 50.0379, "longitude_deg": 8.5622, "type": "large_airport"},
    {"name": "Sydney Kingsford Smith Airport", "iata": "SYD", "icao": "YSSY", "municipality": "Sydney", "latitude_deg": -33.9399, "longitude_deg": 151.1753, "type": "large_airport"},
    {"name": "Denver International Airport", "iata": "DEN", "icao": "KDEN", "municipality": "Denver", "latitude_deg": 39.8561, "longitude_deg": -104.6737, "type": "large_airport"},
]


@lru_cache(maxsize=1)
def _load_airport_directory(timeout=5):
    """Load the public airport CSV once per app process; keep network waits short."""
    response = requests.get(AIRPORTS_URL, timeout=timeout)
    response.raise_for_status()
    df = pd.read_csv(BytesIO(response.content), usecols=lambda c: c in {
        "name", "iata_code", "gps_code", "ident", "municipality", "latitude_deg", "longitude_deg", "type"
    }, low_memory=False)
    return df[df["type"].isin(["large_airport", "medium_airport"])].copy()


def _featured_matches(q):
    return [a for a in FEATURED_AIRPORTS
            if q in " ".join(str(a.get(k, "")) for k in ("name", "iata", "icao", "municipality")).lower()]


def search_airports(query, timeout=5):
    """Return instant featured-airport matches, then use a cached global directory if needed."""
    q = (query or "").strip().lower()
    if not q:
        return FEATURED_AIRPORTS

    # Common airports and codes return immediately without a network request.
    featured = _featured_matches(q)
    if featured:
        return featured

    try:
        df = _load_airport_directory(timeout)
        mask = (
            df["name"].fillna("").str.lower().str.contains(q, regex=False)
            | df["iata_code"].fillna("").str.lower().eq(q)
            | df["gps_code"].fillna("").str.lower().eq(q)
            | df["ident"].fillna("").str.lower().eq(q)
            | df["municipality"].fillna("").str.lower().str.contains(q, regex=False)
        )
        matches = df[mask].dropna(subset=["latitude_deg", "longitude_deg"]).head(40)
        if not matches.empty:
            return [{
                "name": str(row.get("name", "Airport")),
                "iata": str(row.get("iata_code", "") or ""),
                "icao": str(row.get("gps_code", "") or row.get("ident", "") or ""),
                "municipality": str(row.get("municipality", "") or ""),
                "latitude_deg": float(row["latitude_deg"]),
                "longitude_deg": float(row["longitude_deg"]),
                "type": str(row.get("type", "airport")),
            } for _, row in matches.iterrows()]
    except (requests.RequestException, ValueError, OSError, KeyError):
        # A slow/unavailable directory must never block common airport selection.
        pass
    return featured


def fetch_weather(lat, lon, timeout=12):
    """Fetch current Open-Meteo conditions; values are context, not flight restrictions."""
    params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,rain,showers,snowfall,weather_code,cloud_cover,pressure_msl,surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m",
        "hourly": "visibility,precipitation_probability",
        "forecast_days": 1,
        "timezone": "auto",
    }
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=timeout)
        r.raise_for_status()
        payload = r.json()
        current = payload.get("current", {})
        units = payload.get("current_units", {})
        return {"fetched_at": datetime.now(timezone.utc).isoformat(), "time": current.get("time"), "current": current, "units": units, "timezone": payload.get("timezone"), "hourly": payload.get("hourly", {})}
    except (requests.RequestException, ValueError) as exc:
        return {"error": f"Weather request failed: {exc}"}
