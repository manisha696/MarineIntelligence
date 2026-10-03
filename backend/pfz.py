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

# Runtime cache
CACHE = {}

CACHE_TTL = 10 * 60

# Keep last successful PFZ result longer than normal cache.
# This protects the application from temporary NOAA failures.
LAST_SUCCESSFUL_PFZ = {}

LAST_SUCCESSFUL_TTL = 6 * 60 * 60


# ============================================================
# SETTINGS
# ============================================================

MAX_SST_MATCH_DISTANCE_KM = 10.0

MIN_CANDIDATE_SCORE = 40.0

ZONE_GROUP_DISTANCE_KM = 25.0

MIN_ZONE_PIXELS = 2

MAX_ZONES = 12


# ============================================================
# STABLE FALLBACK PFZ LOCATIONS
# ============================================================
#
# These are fixed offshore reference areas.
#
# IMPORTANT:
# These are NOT presented as live satellite observations.
# They are used only when live satellite data is temporarily
# unavailable.
#
# The frontend can identify them using:
# data_source = "fallback"
#
# ============================================================

FALLBACK_PFZ_ZONES = [
    {
        "zone_id": "PFZ-F1",
        "name": "Gujarat Offshore",
        "latitude": 21.31,
        "longitude": 72.43,
        "chlorophyll": 5.8,
        "sst": 28.8,
        "fishing_score": 82.0,
        "potential": "HIGH",
        "zone_radius_km": 28.0,
    },
    {
        "zone_id": "PFZ-F2",
        "name": "Mumbai Offshore",
        "latitude": 18.80,
        "longitude": 72.50,
        "chlorophyll": 4.9,
        "sst": 28.2,
        "fishing_score": 76.0,
        "potential": "HIGH",
        "zone_radius_km": 25.0,
    },
    {
        "zone_id": "PFZ-F3",
        "name": "Ratnagiri Offshore",
        "latitude": 16.95,
        "longitude": 73.20,
        "chlorophyll": 4.4,
        "sst": 27.8,
        "fishing_score": 72.0,
        "potential": "HIGH",
        "zone_radius_km": 24.0,
    },
    {
        "zone_id": "PFZ-F4",
        "name": "Goa Offshore",
        "latitude": 15.90,
        "longitude": 73.55,
        "chlorophyll": 3.8,
        "sst": 27.5,
        "fishing_score": 68.0,
        "potential": "MODERATE",
        "zone_radius_km": 22.0,
    },
    {
        "zone_id": "PFZ-F5",
        "name": "Karnataka Offshore",
        "latitude": 14.50,
        "longitude": 73.60,
        "chlorophyll": 3.6,
        "sst": 27.3,
        "fishing_score": 65.0,
        "potential": "MODERATE",
        "zone_radius_km": 22.0,
    },
    {
        "zone_id": "PFZ-F6",
        "name": "Kerala Offshore",
        "latitude": 10.00,
        "longitude": 75.50,
        "chlorophyll": 3.5,
        "sst": 27.2,
        "fishing_score": 63.0,
        "potential": "MODERATE",
        "zone_radius_km": 20.0,
    },
    {
        "zone_id": "PFZ-F7",
        "name": "Tamil Nadu Offshore",
        "latitude": 11.00,
        "longitude": 80.20,
        "chlorophyll": 3.9,
        "sst": 27.6,
        "fishing_score": 67.0,
        "potential": "MODERATE",
        "zone_radius_km": 24.0,
    },
    {
        "zone_id": "PFZ-F8",
        "name": "Odisha Offshore",
        "latitude": 19.00,
        "longitude": 86.50,
        "chlorophyll": 4.1,
        "sst": 28.0,
        "fishing_score": 71.0,
        "potential": "HIGH",
        "zone_radius_km": 26.0,
    },
]


# ============================================================
# HAVERSINE
# ============================================================

def haversine_km(
    lat1,
    lon1,
    lat2,
    lon2,
):
    radius = 6371.0

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    dlat = math.radians(
        lat2 - lat1
    )

    dlon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(lat1_rad)
        *
        math.cos(lat2_rad)
        *
        math.sin(dlon / 2) ** 2
    )

    return (
        radius
        * 2
        * math.asin(
            math.sqrt(a)
        )
    )


# ============================================================
# CHLOROPHYLL SCORE
# ============================================================

def calculate_chlorophyll_score(
    chlorophyll,
):

    try:
        chlorophyll = float(
            chlorophyll
        )
    except (
        ValueError,
        TypeError,
    ):
        return 0.0

    if chlorophyll <= 0:
        return 0.0

    score = (
        chlorophyll
        / 3.0
    ) * 100.0

    return round(
        min(
            score,
            100.0,
        ),
        2,
    )


# ============================================================
# SST SCORE
# ============================================================

def calculate_sst_score(
    sst,
):

    try:
        sst = float(sst)

    except (
        ValueError,
        TypeError,
    ):
        return 0.0

    score = (
        100.0
        - abs(sst - 27.0)
        * 12.0
    )

    return round(
        max(
            0.0,
            min(
                score,
                100.0,
            ),
        ),
        2,
    )


# ============================================================
# COMBINED SCORE
# ============================================================

def calculate_fishing_score(
    chlorophyll_score,
    sst_score,
):

    score = (
        0.60
        * chlorophyll_score
        +
        0.40
        * sst_score
    )

    return round(
        score,
        2,
    )


# ============================================================
# POTENTIAL
# ============================================================

def get_potential(
    score,
):

    if score >= 70:
        return "HIGH"

    if score >= 40:
        return "MODERATE"

    return "LOW"


# ============================================================
# LOCAL GEOGRAPHIC FILTER
# ============================================================

def is_inside_requested_area(
    point_lat,
    point_lon,
    center_lat,
    center_lon,
    radius,
):

    latitude_ok = (
        center_lat - radius
        <= point_lat
        <= center_lat + radius
    )

    longitude_ok = (
        center_lon - radius
        <= point_lon
        <= center_lon + radius
    )

    return (
        latitude_ok
        and longitude_ok
    )


# ============================================================
# FIND NEAREST SST
# ============================================================

def find_nearest_sst(
    chl_point,
    sst_points,
):

    if not sst_points:
        return None

    try:

        chl_lat = float(
            chl_point["latitude"]
        )

        chl_lon = float(
            chl_point["longitude"]
        )

    except (
        ValueError,
        TypeError,
        KeyError,
    ):
        return None

    nearest = None

    nearest_distance = float(
        "inf"
    )

    for sst_point in sst_points:

        try:

            sst_lat = float(
                sst_point["latitude"]
            )

            sst_lon = float(
                sst_point["longitude"]
            )

            sst_value = float(
                sst_point["sst"]
            )

        except (
            ValueError,
            TypeError,
            KeyError,
        ):
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

    if (
        nearest["distance_km"]
        > MAX_SST_MATCH_DISTANCE_KM
    ):
        return None

    return nearest


# ============================================================
# BUILD CANDIDATE PIXELS
# ============================================================

def build_candidate_pixels(
    latitude,
    longitude,
    radius,
    chlorophyll_data,
    sst_data,
):

    chlorophyll_points = (
        chlorophyll_data.get(
            "points",
            [],
        )
    )

    sst_points = (
        sst_data.get(
            "points",
            [],
        )
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

        if not is_inside_requested_area(
            chl_lat,
            chl_lon,
            latitude,
            longitude,
            radius,
        ):
            continue

        nearest_sst = find_nearest_sst(
            chl_point,
            sst_points,
        )

        if nearest_sst is None:
            continue

        if not is_inside_requested_area(
            nearest_sst["latitude"],
            nearest_sst["longitude"],
            latitude,
            longitude,
            radius,
        ):
            continue

        sst = nearest_sst["sst"]

        chlorophyll_score = (
            calculate_chlorophyll_score(
                chlorophyll
            )
        )

        sst_score = (
            calculate_sst_score(
                sst
            )
        )

        fishing_score = (
            calculate_fishing_score(
                chlorophyll_score,
                sst_score,
            )
        )

        if (
            fishing_score
            < MIN_CANDIDATE_SCORE
        ):
            continue

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

            "latitude": round(
                chl_lat,
                6,
            ),

            "longitude": round(
                chl_lon,
                6,
            ),

            "chlorophyll": round(
                chlorophyll,
                4,
            ),

            "sst": round(
                sst,
                2,
            ),

            "chlorophyll_score":
                chlorophyll_score,

            "sst_score":
                sst_score,

            "fishing_score":
                fishing_score,

            "potential":
                potential,

            "distance_km": round(
                distance,
                2,
            ),
        })

    return candidates


# ============================================================
# GROUP CANDIDATE PIXELS
# ============================================================

def group_into_zones(
    candidates,
):

    if not candidates:
        return []

    candidates = sorted(
        candidates,
        key=lambda point:
            point["fishing_score"],
        reverse=True,
    )

    zones = []

    for candidate in candidates:

        assigned_zone = None

        for zone in zones:

            for existing in zone[
                "pixels"
            ]:

                distance = haversine_km(
                    candidate[
                        "latitude"
                    ],
                    candidate[
                        "longitude"
                    ],
                    existing[
                        "latitude"
                    ],
                    existing[
                        "longitude"
                    ],
                )

                if (
                    distance
                    <= ZONE_GROUP_DISTANCE_KM
                ):

                    assigned_zone = zone
                    break

            if assigned_zone:
                break

        if assigned_zone:

            assigned_zone[
                "pixels"
            ].append(
                candidate
            )

        else:

            zones.append({
                "pixels": [
                    candidate
                ]
            })

    return zones


# ============================================================
# SUMMARIZE ZONE
# ============================================================

def summarize_zone(
    zone,
    user_latitude,
    user_longitude,
    zone_number,
):

    pixels = zone[
        "pixels"
    ]

    if not pixels:
        return None

    center_latitude = (
        sum(
            p["latitude"]
            for p in pixels
        )
        / len(pixels)
    )

    center_longitude = (
        sum(
            p["longitude"]
            for p in pixels
        )
        / len(pixels)
    )

    average_chlorophyll = (
        sum(
            p["chlorophyll"]
            for p in pixels
        )
        / len(pixels)
    )

    average_sst = (
        sum(
            p["sst"]
            for p in pixels
        )
        / len(pixels)
    )

    average_chl_score = (
        sum(
            p["chlorophyll_score"]
            for p in pixels
        )
        / len(pixels)
    )

    average_sst_score = (
        sum(
            p["sst_score"]
            for p in pixels
        )
        / len(pixels)
    )

    average_fishing_score = (
        sum(
            p["fishing_score"]
            for p in pixels
        )
        / len(pixels)
    )

    best_pixel = max(
        pixels,
        key=lambda p:
            p["fishing_score"],
    )

    potential = get_potential(
        average_fishing_score
    )

    distance_from_user = (
        haversine_km(
            user_latitude,
            user_longitude,
            center_latitude,
            center_longitude,
        )
    )

    zone_radius = 0.0

    for point in pixels:

        distance = haversine_km(
            center_latitude,
            center_longitude,
            point["latitude"],
            point["longitude"],
        )

        zone_radius = max(
            zone_radius,
            distance,
        )

    return {

        "zone_id":
            f"PFZ-{zone_number}",

        "latitude": round(
            center_latitude,
            6,
        ),

        "longitude": round(
            center_longitude,
            6,
        ),

        "chlorophyll": round(
            average_chlorophyll,
            4,
        ),

        "sst": round(
            average_sst,
            2,
        ),

        "chlorophyll_score": round(
            average_chl_score,
            2,
        ),

        "sst_score": round(
            average_sst_score,
            2,
        ),

        "fishing_score": round(
            average_fishing_score,
            2,
        ),

        "potential":
            potential,

        "distance_km": round(
            distance_from_user,
            2,
        ),

        "pixel_count":
            len(pixels),

        "zone_radius_km":
            round(
                zone_radius,
                2,
            ),

        "best_pixel": {

            "latitude":
                best_pixel[
                    "latitude"
                ],

            "longitude":
                best_pixel[
                    "longitude"
                ],

            "fishing_score":
                best_pixel[
                    "fishing_score"
                ],

            "chlorophyll":
                best_pixel[
                    "chlorophyll"
                ],

            "sst":
                best_pixel[
                    "sst"
                ],
        },
    }


# ============================================================
# BUILD RELIABLE ZONES
# ============================================================

def build_reliable_zones(
    candidates,
    latitude,
    longitude,
):

    grouped = group_into_zones(
        candidates
    )

    zones = []

    for group in grouped:

        if len(
            group["pixels"]
        ) < MIN_ZONE_PIXELS:
            continue

        zone = summarize_zone(
            group,
            latitude,
            longitude,
            len(zones) + 1,
        )

        if zone:
            zones.append(
                zone
            )

    zones.sort(
        key=lambda zone:
            zone["fishing_score"],
        reverse=True,
    )

    zones = zones[
        :MAX_ZONES
    ]

    for index, zone in enumerate(
        zones,
        start=1,
    ):

        zone["zone_id"] = (
            f"PFZ-{index}"
        )

    return zones


# ============================================================
# FALLBACK ZONES
# ============================================================

def build_fallback_zones(
    latitude,
    longitude,
):

    zones = []

    for fallback in FALLBACK_PFZ_ZONES:

        distance = haversine_km(
            latitude,
            longitude,
            fallback["latitude"],
            fallback["longitude"],
        )

        zone = {
            "zone_id":
                fallback["zone_id"],

            "name":
                fallback["name"],

            "latitude":
                fallback["latitude"],

            "longitude":
                fallback["longitude"],

            "chlorophyll":
                fallback["chlorophyll"],

            "sst":
                fallback["sst"],

            "chlorophyll_score":
                calculate_chlorophyll_score(
                    fallback["chlorophyll"]
                ),

            "sst_score":
                calculate_sst_score(
                    fallback["sst"]
                ),

            "fishing_score":
                fallback["fishing_score"],

            "potential":
                fallback["potential"],

            "distance_km":
                round(
                    distance,
                    2,
                ),

            "pixel_count":
                0,

            "zone_radius_km":
                fallback[
                    "zone_radius_km"
                ],

            "best_pixel": {
                "latitude":
                    fallback["latitude"],

                "longitude":
                    fallback["longitude"],

                "fishing_score":
                    fallback["fishing_score"],

                "chlorophyll":
                    fallback["chlorophyll"],

                "sst":
                    fallback["sst"],
            },

            "fallback":
                True,
        }

        zones.append(
            zone
        )

    # Closest zones first.
    zones.sort(
        key=lambda zone:
            zone["distance_km"]
    )

    # Return nearby useful zones.
    return zones[:MAX_ZONES]


# ============================================================
# COUNTS
# ============================================================

def calculate_counts(
    zones,
):

    high = sum(
        1
        for zone in zones
        if zone["potential"]
        == "HIGH"
    )

    moderate = sum(
        1
        for zone in zones
        if zone["potential"]
        == "MODERATE"
    )

    low = sum(
        1
        for zone in zones
        if zone["potential"]
        == "LOW"
    )

    return (
        high,
        moderate,
        low,
    )


# ============================================================
# CREATE RESPONSE
# ============================================================

def create_response(
    latitude,
    longitude,
    radius,
    zones,
    data_source,
    status="ok",
    message=None,
):

    high, moderate, low = (
        calculate_counts(zones)
    )

    best_zone = (
        zones[0]
        if zones
        else None
    )

    result = {

        "source":
            "NOAA CoastWatch Satellite Data",

        "status":
            status,

        "data_source":
            data_source,

        "cached":
            data_source
            == "cached_satellite",

        "center": {
            "latitude":
                latitude,

            "longitude":
                longitude,
        },

        "search_radius":
            radius,

        "total_zones":
            len(zones),

        "high":
            high,

        "moderate":
            moderate,

        "low":
            low,

        "best_zone":
            best_zone,

        "points":
            zones,
    }

    if message:
        result["message"] = message

    return result


# ============================================================
# MAIN ENDPOINT
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

    # ========================================================
    # 1. SHORT CACHE
    # ========================================================

    cached = CACHE.get(
        cache_key
    )

    if cached:

        age = (
            time.time()
            - cached["timestamp"]
        )

        if age < CACHE_TTL:

            result = (
                cached["data"].copy()
            )

            result["cached"] = True

            result[
                "cache_age_seconds"
            ] = round(age)

            return result

    print(
        "\n================================"
    )

    print(
        "DYNAMIC PFZ REQUEST"
    )

    print(
        f"Center: "
        f"{latitude}, {longitude}"
    )

    print(
        f"Radius: "
        f"{radius}"
    )

    print(
        "================================"
    )

    # ========================================================
    # 2. LIVE SATELLITE DATA
    # ========================================================

    try:

        chlorophyll_data = (
            get_chlorophyll(
                latitude=latitude,
                longitude=longitude,
                radius=radius,
            )
        )

        sst_data = (
            get_sst(
                latitude=latitude,
                longitude=longitude,
                radius=radius,
            )
        )

        candidates = (
            build_candidate_pixels(
                latitude,
                longitude,
                radius,
                chlorophyll_data,
                sst_data,
            )
        )

        print(
            "VALID LOCAL CANDIDATES:",
            len(candidates),
        )

        zones = (
            build_reliable_zones(
                candidates,
                latitude,
                longitude,
            )
        )

        print(
            "LOCAL PFZ ZONES:",
            len(zones),
        )

        # ====================================================
        # LIVE DATA SUCCESS
        # ====================================================

        if zones:

            result = create_response(
                latitude=latitude,
                longitude=longitude,
                radius=radius,
                zones=zones,
                data_source="live_satellite",
                status="ok",
            )

            # Short cache
            CACHE[cache_key] = {
                "timestamp":
                    time.time(),

                "data":
                    result,
            }

            # Long-lived successful result
            LAST_SUCCESSFUL_PFZ[
                cache_key
            ] = {
                "timestamp":
                    time.time(),

                "data":
                    result,
            }

            return result

    except Exception as exc:

        print(
            "PFZ LIVE DATA ERROR:",
            exc,
        )

    # ========================================================
    # 3. LAST SUCCESSFUL SATELLITE RESULT
    # ========================================================

    previous = (
        LAST_SUCCESSFUL_PFZ.get(
            cache_key
        )
    )

    if previous:

        age = (
            time.time()
            - previous["timestamp"]
        )

        if age < LAST_SUCCESSFUL_TTL:

            result = (
                previous["data"].copy()
            )

            result["cached"] = True

            result[
                "data_source"
            ] = "cached_satellite"

            result[
                "cache_age_seconds"
            ] = round(age)

            result[
                "message"
            ] = (
                "Live satellite data is "
                "temporarily unavailable. "
                "Showing the last successful "
                "satellite PFZ result."
            )

            CACHE[cache_key] = {
                "timestamp":
                    time.time(),

                "data":
                    result,
            }

            print(
                "USING LAST SUCCESSFUL PFZ"
            )

            return result

    # ========================================================
    # 4. STABLE FALLBACK
    # ========================================================

    print(
        "USING STABLE PFZ FALLBACK"
    )

    fallback_zones = (
        build_fallback_zones(
            latitude,
            longitude,
        )
    )

    if fallback_zones:

        result = create_response(
            latitude=latitude,
            longitude=longitude,
            radius=radius,
            zones=fallback_zones,
            data_source="fallback",
            status="ok",
            message=(
                "Live satellite data is "
                "temporarily unavailable. "
                "Showing reference PFZ areas "
                "until live data is restored."
            ),
        )

        CACHE[cache_key] = {
            "timestamp":
                time.time(),

            "data":
                result,
        }

        return result

    # ========================================================
    # 5. FINAL EMPTY RESPONSE
    # ========================================================

    return create_response(
        latitude=latitude,
        longitude=longitude,
        radius=radius,
        zones=[],
        data_source="unavailable",
        status="no_data",
        message=(
            "PFZ data is temporarily unavailable."
        ),
    )