from fastapi import APIRouter, HTTPException, Query
import requests
import time
import math
from urllib.parse import quote


router = APIRouter(
    prefix="/pfz",
    tags=["Potential Fishing Zone"],
)


# ============================================================
# NOAA DATASETS
# ============================================================

CHLOROPHYLL_URL = (
    "https://coastwatch.noaa.gov/"
    "erddap/griddap/"
    "noaacwNPPN20S3ASCIDINEOFDaily.json"
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

CACHE_TTL = 10 * 60          # 10 minutes
LAST_SUCCESS_TTL = 6 * 60*60  # 6 hours


# ============================================================
# BASIC HELPERS
# ============================================================

def cache_key(latitude, longitude, radius):
    return (
        round(latitude, 2),
        round(longitude, 2),
        round(radius, 1),
    )


def safe_float(value):
    try:
        if value is None:
            return None

        number = float(value)

        if math.isnan(number) or math.isinf(number):
            return None

        return number

    except (ValueError, TypeError):
        return None


def haversine_km(lat1, lon1, lat2, lon2):
    """
    Distance between two latitude/longitude points.
    """

    earth_radius = 6371.0

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dlat = lat2 - lat1

    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return earth_radius * c


# ============================================================
# NOAA REQUEST
# ============================================================

def request_noaa(url, query, timeout=90, retries=2):

    encoded_query = quote(
        query,
        safe="[]():,"
    )

    full_url = f"{url}?{encoded_query}"

    headers = {
        "User-Agent": "MarineIntelligence/1.0",
        "Accept": "application/json",
    }

    last_error = None

    for attempt in range(retries + 1):

        try:

            response = requests.get(
                full_url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
            )

            if response.status_code == 200:

                try:
                    return response.json()

                except ValueError:
                    last_error = (
                        "NOAA returned invalid JSON response."
                    )

            elif response.status_code == 429:

                last_error = (
                    "NOAA service is temporarily "
                    "rate-limiting requests."
                )

            else:

                last_error = (
                    f"NOAA HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )

        except requests.RequestException as exc:

            last_error = str(exc)

        if attempt < retries:

            time.sleep(2 * (attempt + 1))

    raise RuntimeError(last_error or "NOAA request failed.")


# ============================================================
# FETCH CHLOROPHYLL
# ============================================================

def fetch_chlorophyll(
    latitude,
    longitude,
    radius,
):

    lat_min = max(
        -89.0,
        latitude - radius
    )

    lat_max = min(
        89.0,
        latitude + radius
    )

    lon_min = max(
        -179.99,
        longitude - radius
    )

    lon_max = min(
        179.99,
        longitude + radius
    )

    query = (
        "chlor_a"
        "[last]"
        "[0]"
        f"[({lat_min}):({lat_max})]"
        f"[({lon_min}):({lon_max})]"
    )

    data = request_noaa(
        CHLOROPHYLL_URL,
        query,
        timeout=90,
        retries=2,
    )

    table = data.get("table", {})

    columns = table.get(
        "columnNames",
        []
    )

    rows = table.get(
        "rows",
        []
    )

    if not rows:

        return []

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

            chlorophyll = safe_float(
                item.get("chlor_a")
            )

            if (
                lat is None
                or lon is None
                or chlorophyll is None
            ):
                continue

            # Valid chlorophyll range
            if chlorophyll <= 0:
                continue

            if chlorophyll > 100:
                continue

            distance = haversine_km(
                latitude,
                longitude,
                lat,
                lon,
            )

            # Keep only requested local region
            if distance > radius * 111.2 * 1.15:
                continue

            points.append(
                {
                    "latitude": lat,
                    "longitude": lon,
                    "chlorophyll": round(
                        chlorophyll,
                        4
                    ),
                    "distance_km": round(
                        distance,
                        2
                    ),
                }
            )

        except (ValueError, TypeError):
            continue

    return points


# ============================================================
# FETCH SST
# ============================================================

def fetch_sst(
    latitude,
    longitude,
    radius,
):

    lat_min = max(
        -89.0,
        latitude - radius
    )

    lat_max = min(
        89.0,
        latitude + radius
    )

    lon_min = max(
        -179.99,
        longitude - radius
    )

    lon_max = min(
        179.99,
        longitude + radius
    )

    query = (
        "sea_surface_temperature"
        "[last]"
        f"[({lat_min}):({lat_max})]"
        f"[({lon_min}):({lon_max})]"
    )

    data = request_noaa(
        SST_URL,
        query,
        timeout=90,
        retries=2,
    )

    table = data.get("table", {})

    columns = table.get(
        "columnNames",
        []
    )

    rows = table.get(
        "rows",
        []
    )

    if not rows:

        return []

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

            # Physically reasonable ocean SST
            if sst < -2:
                continue

            if sst > 40:
                continue

            distance = haversine_km(
                latitude,
                longitude,
                lat,
                lon,
            )

            if distance > radius * 111.2 * 1.15:
                continue

            points.append(
                {
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
                }
            )

        except (ValueError, TypeError):
            continue

    return points


# ============================================================
# CHLOROPHYLL SCORE
# ============================================================

def chlorophyll_score(
    value,
    all_values,
):
    """
    Local percentile based score.

    This avoids assuming that one fixed chlorophyll
    threshold works equally well everywhere.
    """

    if not all_values:
        return 0.0

    values = sorted(
        all_values
    )

    if len(values) == 1:
        return 50.0

    lower_count = sum(
        1
        for x in values
        if x <= value
    )

    percentile = (
        lower_count
        / len(values)
    ) * 100.0

    # Keep useful range between 0-100
    return round(
        max(
            0.0,
            min(
                100.0,
                percentile
            )
        ),
        2
    )


# ============================================================
# SST SCORE
# ============================================================

def sst_score(
    sst
):
    """
    Broad tropical/subtropical marine
    suitability score.

    Around 26-30 C receives the highest score.
    """

    if sst is None:
        return 0.0

    # Excellent zone
    if 27.0 <= sst <= 29.5:
        return 100.0

    # Very good
    if 26.0 <= sst < 27.0:
        return 85.0

    if 29.5 < sst <= 30.5:
        return 85.0

    # Moderate
    if 25.0 <= sst < 26.0:
        return 65.0

    if 30.5 < sst <= 31.5:
        return 65.0

    # Low
    if 24.0 <= sst < 25.0:
        return 45.0

    if 31.5 < sst <= 32.5:
        return 45.0

    return 25.0


# ============================================================
# MATCH SST TO CHLOROPHYLL
# ============================================================

def nearest_sst(
    chl_point,
    sst_points,
    max_distance_km=50.0,
):
    """
    Find nearest SST observation for a
    chlorophyll observation.
    """

    if not sst_points:
        return None

    best = None
    best_distance = None

    for sst_point in sst_points:

        distance = haversine_km(
            chl_point["latitude"],
            chl_point["longitude"],
            sst_point["latitude"],
            sst_point["longitude"],
        )

        if distance > max_distance_km:
            continue

        if (
            best_distance is None
            or distance < best_distance
        ):

            best = sst_point
            best_distance = distance

    return best


# ============================================================
# BUILD PFZ ZONES
# ============================================================

def build_pfz_zones(
    latitude,
    longitude,
    chlorophyll_points,
    sst_points,
):
    """
    Convert live satellite observations into
    potential fishing zones.

    IMPORTANT:
    This does NOT create dummy locations.

    Every returned zone originates from an
    actual satellite observation.
    """

    if not chlorophyll_points:
        return []

    chl_values = [
        p["chlorophyll"]
        for p in chlorophyll_points
    ]

    candidates = []

    # --------------------------------------------------------
    # STEP 1: Evaluate each chlorophyll pixel
    # --------------------------------------------------------

    for chl in chlorophyll_points:

        chl_score = chlorophyll_score(
            chl["chlorophyll"],
            chl_values,
        )

        # Lowered candidate threshold so
        # moderate productive areas are not discarded.
        if chl_score < 50:
            continue

        # ----------------------------------------------------
        # Match nearby SST
        # ----------------------------------------------------

        sst_point = nearest_sst(
            chl,
            sst_points,
            max_distance_km=50.0,
        )

        if sst_point is None:
            # Without SST we don't claim
            # a full PFZ candidate.
            continue

        sst_value = sst_point["sst"]

        sst_sc = sst_score(
            sst_value
        )

        # ----------------------------------------------------
        # Combined fishing score
        # ----------------------------------------------------

        fishing_score = (
            chl_score * 0.60
            + sst_sc * 0.40
        )

        if fishing_score < 50:
            continue

        if fishing_score >= 75:
            potential = "HIGH"

        elif fishing_score >= 60:
            potential = "MODERATE"

        else:
            potential = "LOW"

        distance = haversine_km(
            latitude,
            longitude,
            chl["latitude"],
            chl["longitude"],
        )

        candidates.append(
            {
                "latitude": round(
                    chl["latitude"],
                    6
                ),
                "longitude": round(
                    chl["longitude"],
                    6
                ),
                "chlorophyll": round(
                    chl["chlorophyll"],
                    4
                ),
                "sst": round(
                    sst_value,
                    2
                ),
                "chlorophyll_score": round(
                    chl_score,
                    2
                ),
                "sst_score": round(
                    sst_sc,
                    2
                ),
                "fishing_score": round(
                    fishing_score,
                    2
                ),
                "potential": potential,
                "distance_km": round(
                    distance,
                    2
                ),
            }
        )

    if not candidates:
        return []

    # ========================================================
    # STEP 2: CLUSTER NEARBY CANDIDATES
    # ========================================================

    clusters = []

    for candidate in candidates:

        added_to_cluster = False

        for cluster in clusters:

            center = cluster[0]

            distance = haversine_km(
                candidate["latitude"],
                candidate["longitude"],
                center["latitude"],
                center["longitude"],
            )

            # 25 km clustering radius
            if distance <= 25:

                cluster.append(
                    candidate
                )

                added_to_cluster = True

                break

        if not added_to_cluster:

            clusters.append(
                [candidate]
            )

    # ========================================================
    # STEP 3: CREATE ONE ZONE PER CLUSTER
    # ========================================================

    zones = []

    for index, cluster in enumerate(
        clusters,
        start=1
    ):

        if not cluster:
            continue

        best_pixel = max(
            cluster,
            key=lambda x: (
                x["fishing_score"],
                x["chlorophyll"],
            )
        )

        avg_lat = sum(
            p["latitude"]
            for p in cluster
        ) / len(cluster)

        avg_lon = sum(
            p["longitude"]
            for p in cluster
        ) / len(cluster)

        avg_chl = sum(
            p["chlorophyll"]
            for p in cluster
        ) / len(cluster)

        avg_sst = sum(
            p["sst"]
            for p in cluster
        ) / len(cluster)

        avg_score = sum(
            p["fishing_score"]
            for p in cluster
        ) / len(cluster)

        distance = haversine_km(
            latitude,
            longitude,
            avg_lat,
            avg_lon,
        )

        if avg_score >= 75:
            potential = "HIGH"

        elif avg_score >= 60:
            potential = "MODERATE"

        else:
            potential = "LOW"

        # Estimate zone radius from
        # cluster size, capped to sensible values.
        zone_radius_km = min(
            40.0,
            max(
                8.0,
                math.sqrt(len(cluster))
                * 3.5
            )
        )

        zones.append(
            {
                "zone_id": f"PFZ-{index}",
                "latitude": round(
                    avg_lat,
                    6
                ),
                "longitude": round(
                    avg_lon,
                    6
                ),
                "chlorophyll": round(
                    avg_chl,
                    4
                ),
                "sst": round(
                    avg_sst,
                    2
                ),
                "fishing_score": round(
                    avg_score,
                    2
                ),
                "potential": potential,
                "distance_km": round(
                    distance,
                    2
                ),
                "pixel_count": len(
                    cluster
                ),
                "zone_radius_km": round(
                    zone_radius_km,
                    2
                ),
                "best_pixel": {
                    "latitude": best_pixel[
                        "latitude"
                    ],
                    "longitude": best_pixel[
                        "longitude"
                    ],
                    "fishing_score": best_pixel[
                        "fishing_score"
                    ],
                    "chlorophyll": best_pixel[
                        "chlorophyll"
                    ],
                    "sst": best_pixel[
                        "sst"
                    ],
                },
            }
        )

    # ========================================================
    # STEP 4: REMOVE OVERLAPPING ZONES
    # ========================================================

    final_zones = []

    for zone in sorted(
        zones,
        key=lambda z: (
            z["distance_km"],
            -z["fishing_score"],
        )
    ):

        too_close = False

        for existing in final_zones:

            distance = haversine_km(
                zone["latitude"],
                zone["longitude"],
                existing["latitude"],
                existing["longitude"],
            )

            if distance < 15:

                too_close = True
                break

        if not too_close:

            final_zones.append(
                zone
            )

        # Maximum 10 real zones
        if len(final_zones) >= 10:
            break

    return final_zones


# ============================================================
# PFZ API
# ============================================================

@router.get("/potential")
def get_pfz(
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

    # ========================================================
    # 1. SHORT CACHE
    # ========================================================

    cached = CACHE.get(key)

    if cached:

        age = (
            time.time()
            - cached["timestamp"]
        )

        if age < CACHE_TTL:

            result = cached["data"].copy()

            result["cached"] = True

            result[
                "cache_age_seconds"
            ] = round(age)

            return result

    # ========================================================
    # 2. FETCH LIVE SATELLITE DATA
    # ========================================================

    try:

        chlorophyll_points = (
            fetch_chlorophyll(
                latitude,
                longitude,
                radius,
            )
        )

        sst_points = fetch_sst(
            latitude,
            longitude,
            radius,
        )

    except Exception as exc:

        # ====================================================
        # 3. LAST REAL SATELLITE CACHE
        # ====================================================

        if cached:

            cache_age = (
                time.time()
                - cached["timestamp"]
            )

            if cache_age <= LAST_SUCCESS_TTL:

                result = cached["data"].copy()

                result[
                    "cached"
                ] = True

                result[
                    "data_source"
                ] = "last_real_satellite_cache"

                result[
                    "cache_age_seconds"
                ] = round(cache_age)

                result[
                    "message"
                ] = (
                    "Live satellite service "
                    "was temporarily unavailable. "
                    "Showing the latest real satellite "
                    "result available in memory."
                )

                return result

        # ====================================================
        # 4. NO DUMMY FALLBACK
        # ====================================================

        raise HTTPException(
            status_code=503,
            detail=(
                "Live NOAA satellite data is "
                "temporarily unavailable and "
                "no recent real satellite cache "
                f"is available. Error: {exc}"
            ),
        )

    # ========================================================
    # 5. NO DATA
    # ========================================================

    if not chlorophyll_points:

        result = {
            "source": "NOAA CoastWatch Satellite Data",
            "status": "no_data",
            "data_source": "live_satellite",
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
                "Live satellite data was available, "
                "but no valid chlorophyll observations "
                "were found near the selected location."
            ),
        }

        CACHE[key] = {
            "timestamp": time.time(),
            "data": result,
        }

        return result

    # ========================================================
    # 6. BUILD REAL PFZ ZONES
    # ========================================================

    zones = build_pfz_zones(
        latitude,
        longitude,
        chlorophyll_points,
        sst_points,
    )

    # ========================================================
    # 7. NO PFZ CANDIDATE
    # ========================================================

    if not zones:

        result = {
            "source": "NOAA CoastWatch Satellite Data",
            "status": "no_pfz",
            "data_source": "live_satellite",
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
            "observations": {
                "chlorophyll": len(
                    chlorophyll_points
                ),
                "sst": len(
                    sst_points
                ),
            },
            "message": (
                "Live satellite data was available, "
                "but no PFZ candidate was detected "
                "within your selected area."
            ),
        }

        CACHE[key] = {
            "timestamp": time.time(),
            "data": result,
        }

        return result

    # ========================================================
    # 8. COUNTS
    # ========================================================

    high = sum(
        1
        for z in zones
        if z["potential"] == "HIGH"
    )

    moderate = sum(
        1
        for z in zones
        if z["potential"] == "MODERATE"
    )

    low = sum(
        1
        for z in zones
        if z["potential"] == "LOW"
    )

    # ========================================================
    # 9. BEST ZONE
    # ========================================================
    #
    # Best means strongest fishing score.
    # Not simply the nearest point.
    #

    best_zone = max(
        zones,
        key=lambda z: (
            z["fishing_score"],
            -z["distance_km"],
        )
    )

    # ========================================================
    # 10. FINAL RESPONSE
    # ========================================================

    result = {
        "source": "NOAA CoastWatch Satellite Data",

        "status": "ok",

        "data_source": "live_satellite",

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

        # Flutter currently reads this field.
        "points": zones,

        "observations": {
            "chlorophyll": len(
                chlorophyll_points
            ),
            "sst": len(
                sst_points
            ),
        },

        "message": (
            "PFZ candidates generated from "
            "live NOAA satellite chlorophyll "
            "and sea-surface-temperature observations."
        ),
    }

    # ========================================================
    # 11. SAVE REAL SATELLITE RESULT
    # ========================================================

    CACHE[key] = {
        "timestamp": time.time(),
        "data": result,
    }

    return result