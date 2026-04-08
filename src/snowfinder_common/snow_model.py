"""Snow model: physics-based snow/rain discrimination and snowfall computation.

Core snow physics shared between analyzer (calibration) and predictor (forecasts).
Uses 850hPa temperature as primary discriminator, with surface temperature and
wet-bulb adjustments. Snow-to-liquid ratio (SLR) is temperature-dependent.
"""

import math


def _approx_wet_bulb(temp_c: float, rh_pct: float) -> float:
    """Approximate wet-bulb temperature using Stull (2011) formula.

    Valid for RH 5-99% and temp -20 to 50°C.
    """
    t = temp_c
    rh = max(5.0, min(99.0, rh_pct))

    tw = (
        t * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * (rh**1.5) * math.atan(0.023101 * rh)
        - 4.686035
    )
    return tw


def compute_snow_fraction(
    temp_850_c: float,
    temp_surface_c: float,
    rh_surface_pct: float,
) -> float:
    """Compute fraction of precipitation falling as snow (0.0-1.0).

    Primary discriminator: 850hPa temperature
    - Below -2°C: 100% snow
    - Above +2°C: 0% snow
    - Linear transition between -2 and +2°C

    Secondary adjustment: surface wet-bulb temperature
    - If surface wet-bulb < 0°C, boost snow fraction
    - If surface wet-bulb > 3°C, reduce snow fraction
    """
    # Primary: 850hPa temperature linear ramp
    if temp_850_c <= -2.0:
        frac = 1.0
    elif temp_850_c >= 2.0:
        frac = 0.0
    else:
        frac = 1.0 - (temp_850_c + 2.0) / 4.0

    # Secondary: surface wet-bulb adjustment
    wet_bulb = _approx_wet_bulb(temp_surface_c, rh_surface_pct)
    if wet_bulb < 0.0:
        # Cold surface boosts snow probability
        boost = min(0.2, -wet_bulb * 0.05)
        frac = min(1.0, frac + boost)
    elif wet_bulb > 3.0:
        # Warm surface reduces snow probability
        penalty = min(0.3, (wet_bulb - 3.0) * 0.1)
        frac = max(0.0, frac - penalty)

    return frac


def compute_slr(temp_850_c: float) -> float:
    """Compute snow-to-liquid ratio (cm snow per mm LWE).

    Temperature-dependent:
    - Very cold (< -15°C): ~15:1 (fluffy powder)
    - Cold (-10°C): ~12:1
    - Moderate (-5°C): ~10:1 (standard)
    - Near freezing (0°C): ~8:1 (wet/heavy)
    - Warm (> 0°C): ~6:1
    """
    if temp_850_c <= -15.0:
        return 1.5  # 15:1 ratio (cm per mm)
    elif temp_850_c <= -10.0:
        # Linear interpolation 15:1 -> 12:1
        t = (temp_850_c + 15.0) / 5.0  # 0 to 1
        return 1.5 - t * 0.3
    elif temp_850_c <= -5.0:
        # 12:1 -> 10:1
        t = (temp_850_c + 10.0) / 5.0
        return 1.2 - t * 0.2
    elif temp_850_c <= 0.0:
        # 10:1 -> 8:1
        t = (temp_850_c + 5.0) / 5.0
        return 1.0 - t * 0.2
    else:
        # 8:1 -> 6:1 (capped)
        t = min(1.0, temp_850_c / 5.0)
        return 0.8 - t * 0.2


def compute_snowfall(
    precip_mm: float,
    temp_850_c: float,
    temp_surface_c: float,
    rh_surface_pct: float,
) -> tuple[float, float, float]:
    """Convert precipitation to snowfall and rain.

    Returns: (snowfall_cm, rain_mm, snow_fraction)
    """
    if precip_mm <= 0.0:
        return 0.0, 0.0, 0.0

    snow_frac = compute_snow_fraction(temp_850_c, temp_surface_c, rh_surface_pct)
    snow_lwe_mm = precip_mm * snow_frac
    rain_mm = precip_mm * (1.0 - snow_frac)

    slr = compute_slr(temp_850_c)
    snowfall_cm = snow_lwe_mm * slr

    return snowfall_cm, rain_mm, snow_frac
