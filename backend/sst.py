from fastapi import APIRouter, HTTPException, Query
import requests
import time
from urllib.parse import quote

router = APIRouter(
    prefix="/satellite",
    tags=["Satellite Intelligence"],
)

ERDDAP_URL = (
    "https://coastwatch.noaa.gov/"
    "erddap/griddap/"
    "noaacwLEOACSPOSSTL3SnrtCDaily.json"
)

CACHE = {}
CACHE_TTL = 10 * 60


def get_cache_key(latitude, longitude, radius):
    return (
        round(latitude, 2),
        round(longitude, 2),
        round(radius, 1),
    )


@router.get("/sst")
def get_sst(
    latitude: float = Query(..., ge=-89, le=89),
    longitude: float = Query(..., ge=-180, le=180),
    radius: float = Query(1.5, ge=0.2, le=5.0),
):
    cache_key = get_cache_key(latitude, longitude, radius)

    # ==========================================================
    # CACHE
    # ==========================================================

    cached = CACHE.get(cache_key)

    if cached:
        age = time.time() - cached["timestamp"]

        if age < CACHE_TTL:
            result = cached["data"].copy()
            result["cached"] = True
            result["cache_age_seconds"] = round(age)
            return result

    # ==========================================================
    # REGION
    # ==========================================================

    lat_min = max(-89.99, latitude - radius)
    lat_max = min(89.99, latitude + radius)

    lon_min = max(-179.99, longitude - radius)
    lon_max = min(179.99, longitude + radius)

    # ==========================================================
    # NOAA ERDDAP QUERY
    #
    # IMPORTANT:
    # Request a reduced grid instead of every available
    # high-resolution pixel.
    # ==========================================================

    query = (
        "sea_surface_temperature"
        "[last]"
        f"[({lat_min}):4:({lat_max})]"
        f"[({lon_min}):4:({lon_max})]"
    )

    url = (
        f"{ERDDAP_URL}?"
        f"{quote(query, safe='[]():,')}"
    )

    headers = {
        "User-Agent": "MarineIntelligence/1.0",
        "Accept": "application/json",
    }

    # ==========================================================
    # NOAA REQUEST
    # ==========================================================

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=45,
            allow_redirects=True,
        )

    except requests.Timeout:
        raise HTTPException(
            status_code=504,
            detail="NOAA SST request timed out.",
        )

    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"NOAA SST connection failed: {exc}",
        )

    # ==========================================================
    # NOAA RESPONSE
    # ==========================================================

    if response.status_code == 429:
        raise HTTPException(
            status_code=503,
            detail=(
                "NOAA SST service is temporarily "
                "rate-limiting requests."
            ),
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=(
                "NOAA SST service returned "
                f"HTTP {response.status_code}: "
                f"{response.text[:300]}"
            ),
        )

    # ==========================================================
    # JSON
    # ==========================================================

    try:
        data = response.json()

    except ValueError:
        raise HTTPException(
            status_code=502,
            detail="NOAA returned invalid SST JSON.",
        )

    table = data.get("table", {})

    columns = table.get("columnNames", [])
    rows = table.get("rows", [])

    # ==========================================================
    # NO DATA
    # ==========================================================

    if not rows:
        result = {
            "source": "NOAA CoastWatch ACSPO",
            "dataset": "noaacwLEOACSPOSSTL3SnrtCDaily",
            "status": "no_data",
            "message": (
                "No SST satellite observations "
                "were found for this region."
            ),
            "points": [],
        }

        CACHE[cache_key] = {
            "timestamp": time.time(),
            "data": result,
        }

        return result

    # ==========================================================
    # PARSE POINTS
    # ==========================================================

    points = []

    for row in rows:
        try:
            item = dict(zip(columns, row))

            lat = item.get("latitude")
            lon = item.get("longitude")
            sst = item.get("sea_surface_temperature")

            if lat is None or lon is None or sst is None:
                continue

            sst_value = float(sst)

            # Remove invalid physical values.
            if sst_value < -2 or sst_value > 40:
                continue

            points.append({
                "latitude": float(lat),
                "longitude": float(lon),
                "sst": round(sst_value, 2),
            })

        except (ValueError, TypeError):
            continue

    # ==========================================================
    # NO VALID POINTS
    # ==========================================================

    if not points:
        result = {
            "source": "NOAA CoastWatch ACSPO",
            "dataset": "noaacwLEOACSPOSSTL3SnrtCDaily",
            "status": "no_valid_data",
            "message": (
                "SST observations were returned, "
                "but no valid SST pixels were available."
            ),
            "points": [],
        }

        CACHE[cache_key] = {
            "timestamp": time.time(),
            "data": result,
        }

        return result

    # ==========================================================
    # RANGE
    # ==========================================================

    values = [
        point["sst"]
        for point in points
    ]

    result = {
        "source": "NOAA CoastWatch ACSPO",
        "dataset": "noaacwLEOACSPOSSTL3SnrtCDaily",
        "status": "ok",
        "cached": False,
        "units": "degree_C",
        "center": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "range": {
            "minimum": round(min(values), 2),
            "maximum": round(max(values), 2),
        },
        "points": points,
    }

    # ==========================================================
    # SAVE CACHE
    # ==========================================================

    CACHE[cache_key] = {
        "timestamp": time.time(),
        "data": result,
    }

    return result