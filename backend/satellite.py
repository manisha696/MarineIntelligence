from fastapi import APIRouter, HTTPException, Query
import requests
import time
from urllib.parse import quote

router = APIRouter(
    prefix="/satellite",
    tags=["Satellite Intelligence"],
)

# Working NOAA CoastWatch ERDDAP endpoint
ERDDAP_URL = (
    "https://coastwatch.noaa.gov/"
    "erddap/griddap/noaacwNPPVIIRSchlaDaily.json"
)

# Simple in-memory cache
CACHE = {}
CACHE_TTL = 10 * 60  # 10 minutes


def get_cache_key(latitude, longitude, radius):
    return (
        round(latitude, 2),
        round(longitude, 2),
        round(radius, 1),
    )


@router.get("/chlorophyll")
def get_chlorophyll(
    latitude: float = Query(..., ge=-89, le=89),
    longitude: float = Query(..., ge=-180, le=180),
    radius: float = Query(1.5, ge=0.2, le=5.0),
):

    cache_key = get_cache_key(
        latitude,
        longitude,
        radius,
    )

    # -----------------------------------------
    # 1. Check cache
    # -----------------------------------------
    cached = CACHE.get(cache_key)

    if cached:
        age = time.time() - cached["timestamp"]

        if age < CACHE_TTL:
            result = cached["data"].copy()
            result["cached"] = True
            result["cache_age_seconds"] = round(age)
            return result

    # -----------------------------------------
    # 2. Calculate geographic bounds
    # -----------------------------------------
    lat_min = max(-89.0, latitude - radius)
    lat_max = min(89.0, latitude + radius)

    lon_min = max(-180.0, longitude - radius)
    lon_max = min(180.0, longitude + radius)

    # ERDDAP geographic constraint
    query = (
        "chlor_a"
        "[last]"
        "[0]"
        f"[({lat_min}):({lat_max})]"
        f"[({lon_min}):({lon_max})]"
    )

    url = (
        f"{ERDDAP_URL}?"
        f"{quote(query, safe='[]():,')}"
    )

    headers = {
        "User-Agent": "MarineIntelligence/1.0",
        "Accept": "application/json",
    }

    # -----------------------------------------
    # 3. Request NOAA
    # -----------------------------------------
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=60,
            allow_redirects=True,
        )

    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Satellite service connection failed: "
                f"{exc}"
            ),
        )

    # -----------------------------------------
    # 4. NOAA rate limiting
    # -----------------------------------------
    if response.status_code == 429:
        raise HTTPException(
            status_code=503,
            detail=(
                "NOAA satellite service is temporarily "
                "rate-limiting requests. Please try again later."
            ),
        )

    # -----------------------------------------
    # 5. Other NOAA errors
    # -----------------------------------------
    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=(
                "NOAA satellite service returned "
                f"HTTP {response.status_code}"
            ),
        )

    # -----------------------------------------
    # 6. Parse response
    # -----------------------------------------
    try:
        data = response.json()

    except ValueError:
        raise HTTPException(
            status_code=502,
            detail="NOAA returned invalid JSON data.",
        )

    table = data.get("table", {})

    columns = table.get(
        "columnNames",
        [],
    )

    rows = table.get(
        "rows",
        [],
    )

    # -----------------------------------------
    # 7. No rows
    # -----------------------------------------
    if not rows:

        result = {
            "source": "NOAA CoastWatch VIIRS",
            "dataset": "noaacwNPPVIIRSchlaDaily",
            "status": "no_data",
            "message": (
                "No satellite observations were found "
                "for this region."
            ),
            "points": [],
            "hotspots": [],
        }

        CACHE[cache_key] = {
            "timestamp": time.time(),
            "data": result,
        }

        return result

    # -----------------------------------------
    # 8. Extract valid chlorophyll points
    # -----------------------------------------
    points = []

    for row in rows:

        try:
            item = dict(
                zip(columns, row)
            )

            lat = item.get("latitude")
            lon = item.get("longitude")
            chlor = item.get("chlor_a")

            # Ignore missing/null pixels
            if (
                lat is None
                or lon is None
                or chlor is None
            ):
                continue

            chlor_value = float(chlor)

            # Ignore invalid values
            if (
                chlor_value <= 0
                or chlor_value > 100
            ):
                continue

            points.append(
                {
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "chlorophyll": round(
                        chlor_value,
                        4,
                    ),
                }
            )

        except (
            ValueError,
            TypeError,
        ):
            continue

    # -----------------------------------------
    # 9. No valid ocean pixels
    # -----------------------------------------
    if not points:

        result = {
            "source": "NOAA CoastWatch VIIRS",
            "dataset": "noaacwNPPVIIRSchlaDaily",
            "status": "no_valid_data",
            "message": (
                "Satellite observations were returned, "
                "but no valid chlorophyll pixels were "
                "available for this region."
            ),
            "points": [],
            "hotspots": [],
        }

        CACHE[cache_key] = {
            "timestamp": time.time(),
            "data": result,
        }

        return result

    # -----------------------------------------
    # 10. Calculate hotspot threshold
    # -----------------------------------------
    values = sorted(
        point["chlorophyll"]
        for point in points
    )

    index = int(
        (len(values) - 1) * 0.75
    )

    threshold = values[index]

    # Top 25% chlorophyll pixels
    hotspots = [
        point
        for point in points
        if point["chlorophyll"] >= threshold
    ]

    hotspots = sorted(
        hotspots,
        key=lambda point: point["chlorophyll"],
        reverse=True,
    )[:30]

    # -----------------------------------------
    # 11. Statistics
    # -----------------------------------------
    minimum = min(
        point["chlorophyll"]
        for point in points
    )

    maximum = max(
        point["chlorophyll"]
        for point in points
    )

    result = {
        "source": "NOAA CoastWatch VIIRS",

        "dataset": (
            "noaacwNPPVIIRSchlaDaily"
        ),

        "status": "ok",

        "cached": False,

        "units": "mg m-3",

        "center": {
            "latitude": latitude,
            "longitude": longitude,
        },

        "range": {
            "minimum": round(
                minimum,
                4,
            ),
            "maximum": round(
                maximum,
                4,
            ),
        },

        "hotspot_threshold": round(
            threshold,
            4,
        ),

        "points": points,

        "hotspots": hotspots,
    }

    # -----------------------------------------
    # 12. Cache successful response
    # -----------------------------------------
    CACHE[cache_key] = {
        "timestamp": time.time(),
        "data": result,
    }

    return result