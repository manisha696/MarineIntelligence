from fastapi import APIRouter, HTTPException, Query
import requests
import time
from concurrent.futures import ThreadPoolExecutor

router = APIRouter(
    prefix="/risk",
    tags=["Marine Risk Intelligence"],
)

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

CACHE = {}
CACHE_TTL = 10 * 60


def cache_key(latitude, longitude):
    return (
        round(latitude, 2),
        round(longitude, 2),
    )


def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, value))


def calculate_risk(weather, marine):
    """
    Rule-based marine risk calculation.

    Higher values mean more hazardous conditions.

    Factors:
    - Wave height
    - Wind speed
    - Wind gust
    - Ocean current
    - Visibility
    - Precipitation
    """

    wave_height = float(
        marine.get("wave_height") or 0
    )

    wind_speed = float(
        weather.get("wind_speed_10m") or 0
    )

    wind_gust = float(
        weather.get("wind_gusts_10m") or 0
    )

    visibility = float(
        weather.get("visibility") or 10000
    )

    precipitation = float(
        weather.get("precipitation") or 0
    )

    current_velocity = float(
        marine.get("ocean_current_velocity") or 0
    )

    # ---------------------------------
    # Wave risk: 0 - 30
    # ---------------------------------

    if wave_height < 0.5:
        wave_score = 0
    elif wave_height < 1.0:
        wave_score = 8
    elif wave_height < 1.5:
        wave_score = 16
    elif wave_height < 2.5:
        wave_score = 24
    else:
        wave_score = 30

    # ---------------------------------
    # Wind risk: 0 - 25
    # ---------------------------------

    if wind_speed < 10:
        wind_score = 0
    elif wind_speed < 20:
        wind_score = 8
    elif wind_speed < 30:
        wind_score = 16
    elif wind_speed < 40:
        wind_score = 22
    else:
        wind_score = 25

    # ---------------------------------
    # Gust risk: 0 - 15
    # ---------------------------------

    if wind_gust < 15:
        gust_score = 0
    elif wind_gust < 25:
        gust_score = 5
    elif wind_gust < 35:
        gust_score = 10
    else:
        gust_score = 15

    # ---------------------------------
    # Current risk: 0 - 10
    # ---------------------------------

    if current_velocity < 0.5:
        current_score = 0
    elif current_velocity < 1.0:
        current_score = 3
    elif current_velocity < 1.5:
        current_score = 6
    else:
        current_score = 10

    # ---------------------------------
    # Visibility risk: 0 - 10
    # ---------------------------------

    visibility_km = visibility / 1000

    if visibility_km >= 10:
        visibility_score = 0
    elif visibility_km >= 5:
        visibility_score = 3
    elif visibility_km >= 2:
        visibility_score = 6
    else:
        visibility_score = 10

    # ---------------------------------
    # Rain risk: 0 - 10
    # ---------------------------------

    if precipitation < 1:
        rain_score = 0
    elif precipitation < 5:
        rain_score = 3
    elif precipitation < 10:
        rain_score = 6
    else:
        rain_score = 10

    # ---------------------------------
    # Final score
    # ---------------------------------

    risk_score = (
        wave_score
        + wind_score
        + gust_score
        + current_score
        + visibility_score
        + rain_score
    )

    risk_score = int(
        clamp(risk_score, 0, 100)
    )

    # ---------------------------------
    # Risk level
    # ---------------------------------

    if risk_score >= 70:
        risk_level = "HIGH"
    elif risk_score >= 40:
        risk_level = "MODERATE"
    else:
        risk_level = "LOW"

    # ---------------------------------
    # Explain why
    # ---------------------------------

    reasons = []

    if wave_height >= 2.5:
        reasons.append(
            "High wave conditions"
        )
    elif wave_height >= 1.5:
        reasons.append(
            "Elevated wave conditions"
        )

    if wind_speed >= 30:
        reasons.append(
            "Strong wind"
        )
    elif wind_speed >= 20:
        reasons.append(
            "Moderate-to-strong wind"
        )

    if wind_gust >= 35:
        reasons.append(
            "Strong wind gusts"
        )
    elif wind_gust >= 25:
        reasons.append(
            "Elevated wind gusts"
        )

    if current_velocity >= 1.5:
        reasons.append(
            "Strong ocean current"
        )
    elif current_velocity >= 1.0:
        reasons.append(
            "Elevated ocean current"
        )

    if visibility_km < 2:
        reasons.append(
            "Poor visibility"
        )
    elif visibility_km < 5:
        reasons.append(
            "Reduced visibility"
        )

    if precipitation >= 10:
        reasons.append(
            "Heavy precipitation"
        )
    elif precipitation >= 5:
        reasons.append(
            "Moderate precipitation"
        )

    if not reasons:
        reasons.append(
            "No major hazardous conditions detected"
        )

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "reasons": reasons,
        "conditions": {
            "wave_height_m": round(
                wave_height, 2
            ),
            "wind_speed_kmh": round(
                wind_speed, 2
            ),
            "wind_gust_kmh": round(
                wind_gust, 2
            ),
            "ocean_current_kmh": round(
                current_velocity, 2
            ),
            "visibility_km": round(
                visibility_km, 2
            ),
            "precipitation_mm": round(
                precipitation, 2
            ),
        },
    }


def fetch_weather(latitude, longitude):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "wind_speed_10m,"
            "wind_gusts_10m,"
            "visibility,"
            "precipitation,"
            "weather_code"
        ),
        "wind_speed_unit": "kmh",
        "timezone": "auto",
    }

    response = requests.get(
        WEATHER_URL,
        params=params,
        timeout=20,
    )

    if response.status_code != 200:
        raise Exception(
            f"Weather API returned "
            f"HTTP {response.status_code}"
        )

    data = response.json()

    return data.get("current", {})


def fetch_marine(latitude, longitude):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "wave_height,"
            "ocean_current_velocity,"
            "sea_surface_temperature"
        ),
        "timezone": "auto",
    }

    response = requests.get(
        MARINE_URL,
        params=params,
        timeout=20,
    )

    if response.status_code != 200:
        raise Exception(
            f"Marine API returned "
            f"HTTP {response.status_code}"
        )

    data = response.json()

    return data.get("current", {})


@router.get("/assessment")
def risk_assessment(
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
):
    key = cache_key(
        latitude,
        longitude,
    )

    cached = CACHE.get(key)

    if cached:
        age = time.time() - cached["timestamp"]

        if age < CACHE_TTL:
            result = cached["data"].copy()
            result["cached"] = True
            result["cache_age_seconds"] = round(
                age
            )
            return result

    try:
        # Weather and marine APIs are fetched
        # simultaneously to reduce response time.

        with ThreadPoolExecutor(
            max_workers=2
        ) as executor:

            weather_future = executor.submit(
                fetch_weather,
                latitude,
                longitude,
            )

            marine_future = executor.submit(
                fetch_marine,
                latitude,
                longitude,
            )

            weather = weather_future.result()
            marine = marine_future.result()

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Marine risk data service failed: "
                f"{exc}"
            ),
        )

    calculated = calculate_risk(
        weather,
        marine,
    )

    result = {
        "source": {
            "weather": "Open-Meteo Weather",
            "marine": "Open-Meteo Marine",
        },
        "status": "ok",
        "cached": False,
        "model": "rule_based_baseline",
        "center": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "risk": calculated,
        "marine_conditions": {
            "sea_surface_temperature_c": (
                round(
                    float(
                        marine.get(
                            "sea_surface_temperature"
                        ) or 0
                    ),
                    2,
                )
            ),
        },
    }

    CACHE[key] = {
        "timestamp": time.time(),
        "data": result,
    }

    return result