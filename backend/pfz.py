from fastapi import APIRouter, Query
import math
import time

from satellite import get_chlorophyll
from sst import get_sst


router = APIRouter(
    prefix="/pfz",
    tags=["Potential Fishing Zone"],
)


# ============================================================
# CACHE
# ============================================================

CACHE = {}
CACHE_TTL = 10 * 60


# ============================================================
# SETTINGS
# ============================================================

# Maximum allowed distance between a chlorophyll pixel
# and its matching SST pixel.
#
# This prevents unrelated satellite pixels from being
# combined into one PFZ.
MAX_SST_MATCH_DISTANCE_KM = 10.0


# ============================================================
# OFFSHORE FALLBACK LOCATIONS
# ============================================================

OFFSHORE_CANDIDATES = [
    ("Mumbai Offshore", 18.80, 72.50),
    ("Alibag Offshore", 18.70, 72.70),
    ("Ratnagiri Offshore", 16.95, 73.20),
    ("Sindhudurg", 16.00, 73.40),
    ("Gujarat", 20.29, 71.02),
    ("Gulf of Khambhat", 21.00, 72.20),
    ("Saurashtra", 21.00, 69.50),
    ("Goa", 15.90, 73.55),
    ("Karnataka", 14.50, 73.60),
    ("Mangalore", 12.80, 74.50),
    ("Kerala", 10.00, 75.50),
    ("Kochi", 9.80, 75.60),
    ("Tamil Nadu", 11.00, 80.20),
    ("Chennai", 13.00, 80.50),
    ("Palk Bay", 9.00, 79.50),
    ("Andhra", 15.50, 81.00),
    ("Odisha", 19.00, 86.50),
    ("West Bengal", 21.00, 88.50),
    ("Bay of Bengal", 18.00, 90.00),
    ("Andaman Sea", 12.00, 94.00),
]


# ============================================================
# HAVERSINE
# ============================================================

def haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371.0

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

    return radius * 2 * math.asin(math.sqrt(a))


# ============================================================
# CHLOROPHYLL SCORE
# ============================================================

def calculate_chlorophyll_score(chlorophyll):

    if chlorophyll is None:
        return 0

    try:
        chlorophyll = float(chlorophyll)
    except (ValueError, TypeError):
        return 0

    if chlorophyll <= 0:
        return 0

    score = (chlorophyll / 3.0) * 100.0

    return round(min(score, 100.0), 2)


# ============================================================
# SST SCORE
# ============================================================

def calculate_sst_score(sst):

    if sst is None:
        return 0

    try:
        sst = float(sst)
    except (ValueError, TypeError):
        return 0

    score = 100.0 - abs(sst - 27.0) * 12.0

    return round(max(0.0, min(score, 100.0)), 2)


# ============================================================
# FISHING SCORE
# ============================================================

def calculate_fishing_score(
    chlorophyll_score,
    sst_score,
):

    score = (
        0.60 * chlorophyll_score
        + 0.40 * sst_score
    )

    return round(score, 2)


# ============================================================
# POTENTIAL LEVEL
# ============================================================

def get_potential(score):

    if score >= 70:
        return "HIGH"

    if score >= 40:
        return "MODERATE"

    return "LOW"


# ============================================================
# FIND NEAREST SST
# ============================================================

def find_nearest_sst(
    chl_point,
    sst_points,
    max_distance_km=MAX_SST_MATCH_DISTANCE_KM,
):
    """
    Find the nearest SST pixel for a chlorophyll pixel.

    IMPORTANT:
    The SST point must be geographically close to the
    chlorophyll point. Otherwise the pair is rejected.
    """

    if not sst_points:
        return None

    try:
        chl_lat = float(chl_point["latitude"])
        chl_lon = float(chl_point["longitude"])
    except (ValueError, TypeError, KeyError):
        return None

    nearest = None
    nearest_distance = float("inf")

    for sst_point in sst_points:

        try:
            sst_lat = float(sst_point["latitude"])
            sst_lon = float(sst_point["longitude"])
            sst_value = float(sst_point["sst"])
        except (ValueError, TypeError, KeyError):
            continue

        distance = haversine_km(
            chl_lat,
            chl_lon,
            sst_lat,
            sst_lon,
        )

        if distance < nearest_distance:

            nearest_distance = distance

            nearest = {
                "sst": sst_value,
                "latitude": sst_lat,
                "longitude": sst_lon,
                "distance_km": distance,
            }

    if nearest is None:
        return None

    # Reject geographically unrelated SST pixels.
    if nearest["distance_km"] > max_distance_km:
        return None

    return nearest


# ============================================================
# SELECT 3 DISTINCT ZONES
# ============================================================

def select_three_zones(points):

    if not points:
        return []

    sorted_points = sorted(
        points,
        key=lambda point: point["fishing_score"],
        reverse=True,
    )

    selected = []

    minimum_distance_km = 15.0

    for point in sorted_points:

        if not selected:
            selected.append(point)
            continue

        too_close = False

        for existing in selected:

            distance = haversine_km(
                point["latitude"],
                point["longitude"],
                existing["latitude"],
                existing["longitude"],
            )

            if distance < minimum_distance_km:
                too_close = True
                break

        if not too_close:
            selected.append(point)

        if len(selected) == 3:
            break

    if len(selected) < 3:

        for point in sorted_points:

            if point in selected:
                continue

            selected.append(point)

            if len(selected) == 3:
                break

    return selected


# ============================================================
# BUILD LOCAL PFZ
# ============================================================

def build_local_pfz(
    latitude,
    longitude,
    chlorophyll_data,
    sst_data,
):

    chlorophyll_points = chlorophyll_data.get(
        "points",
        [],
    )

    sst_points = sst_data.get(
        "points",
        [],
    )

    print(
        "CHLOROPHYLL POINTS:",
        len(chlorophyll_points),
    )

    print(
        "SST POINTS:",
        len(sst_points),
    )

    if not chlorophyll_points:
        return []

    if not sst_points:
        return []

    candidates = []

    for chl_point in chlorophyll_points:

        try:
            chl_lat = float(
                chl_point["latitude"]
            )

            chl_lon = float(
                chl_point["longitude"]
            )

            chlorophyll = float(
                chl_point["chlorophyll"]
            )

        except (
            ValueError,
            TypeError,
            KeyError,
        ):
            continue

        nearest_sst = find_nearest_sst(
            chl_point,
            sst_points,
        )

        # No geographically valid SST match.
        if nearest_sst is None:
            continue

        sst = nearest_sst["sst"]

        chlorophyll_score = (
            calculate_chlorophyll_score(
                chlorophyll
            )
        )

        sst_score = calculate_sst_score(
            sst
        )

        fishing_score = calculate_fishing_score(
            chlorophyll_score,
            sst_score,
        )

        potential = get_potential(
            fishing_score
        )

        distance = haversine_km(
            latitude,
            longitude,
            chl_lat,
            chl_lon,
        )

        candidates.append({
            "latitude": chl_lat,
            "longitude": chl_lon,
            "chlorophyll": round(
                chlorophyll,
                4,
            ),
            "sst": round(
                sst,
                2,
            ),
            "chlorophyll_score": (
                chlorophyll_score
            ),
            "sst_score": sst_score,
            "fishing_score": fishing_score,
            "potential": potential,
            "distance_km": round(
                distance,
                2,
            ),
        })

    if not candidates:
        return []

    return select_three_zones(
        candidates
    )


# ============================================================
# OFFSHORE FALLBACK
# ============================================================

def build_fallback_zone(
    latitude,
    longitude,
):

    candidates = sorted(
        OFFSHORE_CANDIDATES,
        key=lambda candidate:
            haversine_km(
                latitude,
                longitude,
                candidate[1],
                candidate[2],
            ),
    )

    for candidate in candidates:

        name = candidate[0]
        candidate_latitude = candidate[1]
        candidate_longitude = candidate[2]

        try:

            print(
                f"\nTrying fallback: {name} "
                f"({candidate_latitude}, "
                f"{candidate_longitude})"
            )

            chlorophyll_result = get_chlorophyll(
                latitude=candidate_latitude,
                longitude=candidate_longitude,
                radius=1.5,
            )

            sst_result = get_sst(
                latitude=candidate_latitude,
                longitude=candidate_longitude,
                radius=1.5,
            )

            local_points = build_local_pfz(
                candidate_latitude,
                candidate_longitude,
                chlorophyll_result,
                sst_result,
            )

            if local_points:

                for point in local_points:

                    point["distance_km"] = round(
                        haversine_km(
                            latitude,
                            longitude,
                            point["latitude"],
                            point["longitude"],
                        ),
                        2,
                    )

                print(
                    f"Fallback successful: {name}"
                )

                return local_points

        except Exception as exc:

            print(
                f"Fallback candidate failed "
                f"{name}: {exc}"
            )

            continue

    return []


# ============================================================
# MAIN PFZ ENDPOINT
# ============================================================

@router.get("/potential")
def get_potential_fishing_zones(
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

    cache_key = (
        round(latitude, 2),
        round(longitude, 2),
        round(radius, 1),
    )

    cached = CACHE.get(cache_key)

    if cached:

        age = time.time() - cached["timestamp"]

        if age < CACHE_TTL:

            result = cached["data"].copy()

            result["cached"] = True
            result["cache_age_seconds"] = round(
                age
            )

            return result

    # --------------------------------------------------------
    # FETCH NOAA DATA
    # --------------------------------------------------------

    try:

        chlorophyll_data = get_chlorophyll(
            latitude=latitude,
            longitude=longitude,
            radius=radius,
        )

        sst_data = get_sst(
            latitude=latitude,
            longitude=longitude,
            radius=radius,
        )

    except Exception as exc:

        return {
            "source": (
                "NOAA CoastWatch "
                "Satellite Data"
            ),
            "status": "error",
            "message": str(exc),
            "center": {
                "latitude": latitude,
                "longitude": longitude,
            },
            "total_zones": 0,
            "high": 0,
            "moderate": 0,
            "low": 0,
            "points": [],
        }

    # --------------------------------------------------------
    # LOCAL PFZ
    # --------------------------------------------------------

    points = build_local_pfz(
        latitude,
        longitude,
        chlorophyll_data,
        sst_data,
    )

    # --------------------------------------------------------
    # FALLBACK ONLY IF LOCAL DATA FAILS
    # --------------------------------------------------------

    if not points:

        print(
            "\nNo local PFZ points found."
        )

        print(
            "Using offshore fallback..."
        )

        points = build_fallback_zone(
            latitude,
            longitude,
        )

    # --------------------------------------------------------
    # NO DATA
    # --------------------------------------------------------

    if not points:

        result = {
            "source": (
                "NOAA CoastWatch "
                "Satellite Data"
            ),
            "status": "no_data",
            "cached": False,
            "center": {
                "latitude": latitude,
                "longitude": longitude,
            },
            "total_zones": 0,
            "high": 0,
            "moderate": 0,
            "low": 0,
            "best_zone": None,
            "points": [],
        }

        CACHE[cache_key] = {
            "timestamp": time.time(),
            "data": result,
        }

        return result

    # --------------------------------------------------------
    # SORT BEST FIRST
    # --------------------------------------------------------

    points = sorted(
        points,
        key=lambda point:
            point["fishing_score"],
        reverse=True,
    )

    # --------------------------------------------------------
    # COUNTS
    # --------------------------------------------------------

    high = sum(
        1
        for point in points
        if point["potential"] == "HIGH"
    )

    moderate = sum(
        1
        for point in points
        if point["potential"] == "MODERATE"
    )

    low = sum(
        1
        for point in points
        if point["potential"] == "LOW"
    )

    # --------------------------------------------------------
    # BEST ZONE
    # --------------------------------------------------------

    best_zone = points[0]

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    result = {
        "source": (
            "NOAA CoastWatch "
            "Satellite Data"
        ),
        "status": "ok",
        "cached": False,
        "center": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "total_zones": len(points),
        "high": high,
        "moderate": moderate,
        "low": low,
        "best_zone": best_zone,
        "points": points,
    }

    CACHE[cache_key] = {
        "timestamp": time.time(),
        "data": result,
    }

    return result