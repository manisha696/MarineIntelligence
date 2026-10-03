from fastapi import APIRouter, HTTPException, Query
import requests
import time
import math
from urllib.parse import quote


router = APIRouter(
    prefix="/pfz",
    tags=["PFZ Intelligence"],
)


# ============================================================
# NOAA DATASETS
# ============================================================

CHLOROPHYLL_URL = (
    "https://coastwatch.noaa.gov/"
    "erddap/griddap/"
    "noaacwNPPN20VIIRSchlociDaily.json"
)

SST_URL = (
    "https://coastwatch.noaa.gov/"
    "erddap/griddap/"
    "noaacwLEOACSPOSSTL3SnrtCDaily.json"
)


# ============================================================
# CACHE
# ============================================================

CACHE = {}

CACHE_TTL = 10 * 60

# Last real satellite PFZ result.
# This is NOT dummy data.
LAST_SUCCESSFUL_PFZ = {}

LAST_SUCCESSFUL_TTL = 6 * 60 * 60


# ============================================================
# HTTP SETTINGS
# ============================================================

HEADERS = {
    "User-Agent": "MarineIntelligence/1.0",
    "Accept": "application/json",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def cache_key(latitude, longitude, radius):
    return (
        round(latitude, 2),
        round(longitude, 2),
        round(radius, 1),
    )


def haversine_km(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two geographic coordinates.
    """

    earth_radius = 6371.0

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return earth_radius * c


def safe_float(value):
    try:
        if value is None:
            return None

        number = float(value)

        if not math.isfinite(number):
            return None

        return number

    except (TypeError, ValueError):
        return None


# ============================================================
# NOAA REQUEST
# ============================================================

def request_noaa(url):
    """
    Request NOAA data with a few retries.

    No dummy data is generated.
    """

    last_error = None

    for attempt in range(3):

        try:

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=90,
                allow_redirects=True,
            )

            if response.status_code == 200:
                return response

            if response.status_code == 429:
                last_error = (
                    "NOAA rate limit "
                    f"(HTTP {response.status_code})"
                )

            else:
                last_error = (
                    f"NOAA HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                )

        except requests.RequestException as exc:

            last_error = str(exc)

        if attempt < 2:
            time.sleep(2 * (attempt + 1))

    raise RuntimeError(
        last_error or "NOAA request failed"
    )


# ============================================================
# CHLOROPHYLL
# ============================================================

def fetch_chlorophyll(
    latitude,
    longitude,
    radius,
):
    """
    Fetch actual NOAA VIIRS chlorophyll data
    around the user's location.
    """

    lat_min = max(-89.0, latitude - radius)
    lat_max = min(89.0, latitude + radius)

    lon_min = max(-179.0, longitude - radius)
    lon_max = min(179.0, longitude + radius)

    query = (
        "chlor_a"
        "[last]"
        f"[({lat_min}):({lat_max})]"
        f"[({lon_min}):({lon_max})]"
    )

    url = (
        f"{CHLOROPHYLL_URL}?"
        f"{quote(query, safe='[]():,')}"
    )

    response = request_noaa(url)

    data = response.json()

    table = data.get("table", {})

    columns = table.get(
        "columnNames",
        []
    )

    rows = table.get(
        "rows",
        []
    )

    points = []

    for row in rows:

        try:

            item = dict(
                zip(columns, row)
            )

            lat = safe_float(
                item.get("latitude")
            )

            lon = safe_float(
                item.get("longitude")
            )

            chlor = safe_float(
                item.get("chlor_a")
            )

            if (
                lat is None
                or lon is None
                or chlor is None
            ):
                continue

            # Basic physical/data-quality filtering.
            if chlor <= 0:
                continue

            if chlor > 100:
                continue

            distance = haversine_km(
                latitude,
                longitude,
                lat,
                lon,
            )

            # IMPORTANT:
            # Never allow a point outside user's
            # requested marine search radius.
            radius_km = radius * 111.2

            if distance > radius_km * 1.15:
                continue

            points.append({
                "latitude": lat,
                "longitude": lon,
                "chlorophyll": round(
                    chlor,
                    4
                ),
                "distance_km": round(
                    distance,
                    2
                ),
            })

        except Exception:
            continue

    return points


# ============================================================
# SST
# ============================================================

def fetch_sst(
    latitude,
    longitude,
    radius,
):
    """
    Fetch actual NOAA SST data around
    the user's location.
    """

    lat_min = max(
        -89.0,
        latitude - radius
    )

    lat_max = min(
        89.0,
        latitude + radius
    )

    lon_min = max(
        -179.0,
        longitude - radius
    )

    lon_max = min(
        179.0,
        longitude + radius
    )

    query = (
        "sea_surface_temperature"
        "[last]"
        f"[({lat_min}):({lat_max})]"
        f"[({lon_min}):({lon_max})]"
    )

    url = (
        f"{SST_URL}?"
        f"{quote(query, safe='[]():,')}"
    )

    response = request_noaa(url)

    data = response.json()

    table = data.get(
        "table",
        {}
    )

    columns = table.get(
        "columnNames",
        []
    )

    rows = table.get(
        "rows",
        []
    )

    points = []

    for row in rows:

        try:

            item = dict(
                zip(columns, row)
            )

            lat = safe_float(
                item.get("latitude")
            )

            lon = safe_float(
                item.get("longitude")
            )

            sst = safe_float(
                item.get(
                    "sea_surface_temperature"
                )
            )

            if (
                lat is None
                or lon is None
                or sst is None
            ):
                continue

            # Physical SST sanity check.
            if sst < -2 or sst > 40:
                continue

            distance = haversine_km(
                latitude,
                longitude,
                lat,
                lon,
            )

            radius_km = radius * 111.2

            if distance > radius_km * 1.15:
                continue

            points.append({
                "latitude": lat,
                "longitude": lon,
                "sst": round(
                    sst,
                    2
                ),
                "distance_km": round(
                    distance,
                    2
                ),
            })

        except Exception:
            continue

    return points


# ============================================================
# FIND NEAREST SST
# ============================================================

def nearest_sst(
    latitude,
    longitude,
    sst_points,
):
    """
    Find nearest SST observation for a
    chlorophyll pixel.
    """

    if not sst_points:
        return None

    best = None
    best_distance = float("inf")

    for point in sst_points:

        distance = haversine_km(
            latitude,
            longitude,
            point["latitude"],
            point["longitude"],
        )

        if distance < best_distance:

            best_distance = distance
            best = point

    # Do not pair completely unrelated
    # satellite pixels.
    if best_distance > 30:
        return None

    return best


# ============================================================
# SCORE CHLOROPHYLL
# ============================================================

def chlorophyll_score(
    value,
    minimum,
    maximum,
):
    """
    Relative score based ONLY on
    the current local satellite field.

    No hard-coded fake chlorophyll values.
    """

    if maximum <= minimum:
        return 50.0

    score = (
        (value - minimum)
        / (maximum - minimum)
    ) * 100

    return round(
        max(0.0, min(100.0, score)),
        1
    )


# ============================================================
# SCORE SST
# ============================================================

def sst_score(value):
    """
    Soft suitability score for tropical
    Indian marine waters.

    This is an algorithmic component,
    not an official INCOIS PFZ score.
    """

    # Broad comfortable marine band.
    if 26.0 <= value <= 30.0:

        distance = abs(
            value - 28.0
        )

        score = 100 - (
            distance * 10
        )

        return round(
            max(0.0, min(100.0, score)),
            1
        )

    if value < 26.0:

        score = 100 - (
            (26.0 - value) * 12
        )

        return round(
            max(0.0, min(100.0, score)),
            1
        )

    score = 100 - (
        (value - 30.0) * 12
    )

    return round(
        max(0.0, min(100.0, score)),
        1
    )


# ============================================================
# BUILD PFZ CANDIDATES
# ============================================================

def build_pfz_zones(
    latitude,
    longitude,
    chlorophyll_points,
    sst_points,
):
    """
    Build PFZ candidate zones only from
    actual satellite observations in the
    user's requested area.
    """

    if not chlorophyll_points:
        return []

    if not sst_points:
        return []

    chlor_values = [
        point["chlorophyll"]
        for point in chlorophyll_points
    ]

    minimum = min(
        chlor_values
    )

    maximum = max(
        chlor_values
    )

    candidates = []

    for chl in chlorophyll_points:

        sst = nearest_sst(
            chl["latitude"],
            chl["longitude"],
            sst_points,
        )

        if sst is None:
            continue

        chl_score = chlorophyll_score(
            chl["chlorophyll"],
            minimum,
            maximum,
        )

        temperature_score = sst_score(
            sst["sst"]
        )

        # Combined algorithmic score.
        fishing_score = (
            chl_score * 0.60
            + temperature_score * 0.40
        )

        # Require meaningful local
        # chlorophyll potential.
        if chl_score < 65:
            continue

        if fishing_score >= 75:
            potential = "HIGH"

        elif fishing_score >= 55:
            potential = "MODERATE"

        else:
            potential = "LOW"

        distance = haversine_km(
            latitude,
            longitude,
            chl["latitude"],
            chl["longitude"],
        )

        candidates.append({
            "latitude": chl["latitude"],
            "longitude": chl["longitude"],
            "chlorophyll": round(
                chl["chlorophyll"],
                4
            ),
            "sst": round(
                sst["sst"],
                2
            ),
            "chlorophyll_score": chl_score,
            "sst_score": temperature_score,
            "fishing_score": round(
                fishing_score,
                2
            ),
            "potential": potential,
            "distance_km": round(
                distance,
                2
            ),
        })

    if not candidates:
        return []

    # Highest potential first,
    # then closest to user.
    candidates.sort(
        key=lambda item: (
            -item["fishing_score"],
            item["distance_km"],
        )
    )

    # ========================================================
    # CLUSTER NEARBY PIXELS
    # ========================================================

    zones = []

    cluster_distance_km = 25.0

    for candidate in candidates:

        belongs_to_existing = False

        for zone in zones:

            zone_distance = haversine_km(
                candidate["latitude"],
                candidate["longitude"],
                zone["latitude"],
                zone["longitude"],
            )

            if zone_distance <= cluster_distance_km:

                belongs_to_existing = True

                # Keep strongest candidate
                # inside this local zone.
                if (
                    candidate["fishing_score"]
                    > zone["fishing_score"]
                ):
                    zone.update(
                        candidate
                    )

                break

        if not belongs_to_existing:

            zone = dict(candidate)

            zones.append(zone)

        # Avoid returning too many
        # individual satellite pixels.
        if len(zones) >= 15:
            break

    # ========================================================
    # ADD ZONE INFORMATION
    # ========================================================

    final_zones = []

    for index, zone in enumerate(
        zones,
        start=1
    ):

        if zone["potential"] == "HIGH":
            zone_radius = 20.0

        elif zone["potential"] == "MODERATE":
            zone_radius = 15.0

        else:
            zone_radius = 10.0

        final_zones.append({
            "zone_id": f"PFZ-{index}",
            "latitude": zone["latitude"],
            "longitude": zone["longitude"],
            "chlorophyll": zone["chlorophyll"],
            "sst": zone["sst"],
            "chlorophyll_score": zone[
                "chlorophyll_score"
            ],
            "sst_score": zone[
                "sst_score"
            ],
            "fishing_score": zone[
                "fishing_score"
            ],
            "potential": zone[
                "potential"
            ],
            "distance_km": zone[
                "distance_km"
            ],
            "pixel_count": 1,
            "zone_radius_km": zone_radius,
            "best_pixel": {
                "latitude": zone[
                    "latitude"
                ],
                "longitude": zone[
                    "longitude"
                ],
                "fishing_score": zone[
                    "fishing_score"
                ],
                "chlorophyll": zone[
                    "chlorophyll"
                ],
                "sst": zone[
                    "sst"
                ],
            },
            "fallback": False,
        })

    return final_zones


# ============================================================
# API ENDPOINT
# ============================================================

@router.get("/potential")
def get_pfz_potential(
    latitude: float = Query(
        ...,
        ge=-89,
        le=89,
    ),
    longitude: float = Query(
        ...,
        ge=-180,
        le=180,
    ),
    radius: float = Query(
        1.5,
        ge=0.2,
        le=5.0,
    ),
):

    key = cache_key(
        latitude,
        longitude,
        radius,
    )

    print(
        "\n================================"
    )

    print(
        "LIVE PFZ REQUEST"
    )

    print(
        f"User location: "
        f"{latitude}, {longitude}"
    )

    print(
        f"Search radius: {radius}"
    )

    print(
        "================================"
    )

    # ========================================================
    # SHORT CACHE
    # ========================================================

    cached = CACHE.get(key)

    if cached:

        age = (
            time.time()
            - cached["timestamp"]
        )

        if age < CACHE_TTL:

            result = dict(
                cached["data"]
            )

            result["cached"] = True
            result["cache_age_seconds"] = round(
                age
            )

            return result

    # ========================================================
    # LIVE SATELLITE
    # ========================================================

    try:

        chlorophyll_points = (
            fetch_chlorophyll(
                latitude,
                longitude,
                radius,
            )
        )

        print(
            "CHLOROPHYLL POINTS:",
            len(chlorophyll_points)
        )

        sst_points = fetch_sst(
            latitude,
            longitude,
            radius,
        )

        print(
            "SST POINTS:",
            len(sst_points)
        )

        zones = build_pfz_zones(
            latitude,
            longitude,
            chlorophyll_points,
            sst_points,
        )

        print(
            "PFZ ZONES:",
            len(zones)
        )

        # ====================================================
        # LIVE PFZ FOUND
        # ====================================================

        if zones:

            high = sum(
                1
                for zone in zones
                if zone["potential"] == "HIGH"
            )

            moderate = sum(
                1
                for zone in zones
                if zone["potential"] == "MODERATE"
            )

            low = sum(
                1
                for zone in zones
                if zone["potential"] == "LOW"
            )

            best_zone = zones[0]

            result = {
                "source": (
                    "NOAA CoastWatch "
                    "Satellite Data"
                ),
                "status": "ok",
                "data_source": (
                    "live_satellite"
                ),
                "cached": False,
                "center": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "search_radius": radius,
                "total_zones": len(zones),
                "high": high,
                "moderate": moderate,
                "low": low,
                "best_zone": best_zone,
                "points": zones,
                "message": (
                    "PFZ candidates detected "
                    "from live satellite "
                    "chlorophyll and SST data "
                    "within the requested area."
                ),
            }

            CACHE[key] = {
                "timestamp": time.time(),
                "data": result,
            }

            LAST_SUCCESSFUL_PFZ[key] = {
                "timestamp": time.time(),
                "data": result,
            }

            return result

        # ====================================================
        # LIVE SATELLITE AVAILABLE BUT
        # NO PFZ CANDIDATE
        # ====================================================

        result = {
            "source": (
                "NOAA CoastWatch "
                "Satellite Data"
            ),
            "status": "no_pfz",
            "data_source": (
                "live_satellite"
            ),
            "cached": False,
            "center": {
                "latitude": latitude,
                "longitude": longitude,
            },
            "search_radius": radius,
            "total_zones": 0,
            "high": 0,
            "moderate": 0,
            "low": 0,
            "best_zone": None,
            "points": [],
            "message": (
                "Live satellite data was "
                "available, but no PFZ "
                "candidate was detected "
                "within your selected area."
            ),
        }

        return result

    except Exception as exc:

        print(
            "LIVE PFZ ERROR:",
            str(exc)
        )

        # ====================================================
        # LAST REAL SATELLITE RESULT
        # ====================================================

        previous = LAST_SUCCESSFUL_PFZ.get(
            key
        )

        if previous:

            age = (
                time.time()
                - previous["timestamp"]
            )

            if age < LAST_SUCCESSFUL_TTL:

                result = dict(
                    previous["data"]
                )

                result["data_source"] = (
                    "cached_satellite"
                )

                result["cached"] = True

                result[
                    "cache_age_seconds"
                ] = round(age)

                result["message"] = (
                    "Live satellite service "
                    "is temporarily unavailable. "
                    "Showing the last successful "
                    "real satellite PFZ result "
                    "for this location."
                )

                return result

        # ====================================================
        # NO FAKE FALLBACK
        # ====================================================

        return {
            "source": (
                "NOAA CoastWatch "
                "Satellite Data"
            ),
            "status": "no_data",
            "data_source": "none",
            "cached": False,
            "center": {
                "latitude": latitude,
                "longitude": longitude,
            },
            "search_radius": radius,
            "total_zones": 0,
            "high": 0,
            "moderate": 0,
            "low": 0,
            "best_zone": None,
            "points": [],
            "message": (
                "Live satellite data is "
                "temporarily unavailable "
                "for this request. No "
                "synthetic or dummy PFZ "
                "locations were generated."
            ),
        }