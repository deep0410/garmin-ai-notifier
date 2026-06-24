"""Token-only Garmin client: extract whitelisted scalar metrics only (no raw JSON)."""

from __future__ import annotations

import logging
from typing import Any

from garminconnect import Garmin

from src import config

logger = logging.getLogger(__name__)

# Daily summary + wellness endpoints only. No activities, courses, GPS, or maps.
_SAFE_API_CALLS = (
    "get_stats",
    "get_sleep_data",
    "get_rhr_day",
    "get_body_battery",
    "get_hrv_data",
    "get_training_readiness",
    "get_stress_data",
    "get_spo2_data",
    "get_body_composition",
    "get_max_metrics",
    "get_fitnessage_data",
)


def _safe_get(obj: Any, *keys: str) -> Any:
    cur = obj
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
        if cur is None:
            return None
    return cur


def _to_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(round(float(val)))
    except (TypeError, ValueError):
        return None


def _first_int(*candidates: Any) -> int | None:
    for c in candidates:
        v = _to_int(c)
        if v is not None:
            return v
    return None


def login() -> Garmin:
    garmin = Garmin()
    garmin.login(config.GARMIN_TOKENSTORE)
    return garmin


def _call(api: Garmin, name: str, *args: Any) -> Any:
    if name not in _SAFE_API_CALLS:
        raise ValueError(f"API call not allowlisted: {name}")
    fn = getattr(api, name, None)
    if fn is None:
        return None
    try:
        return fn(*args)
    except Exception as err:
        logger.warning("Garmin %s failed: %s", name, err)
        return None


def _extract_resting_hr(rhr: Any) -> int | None:
    if not rhr:
        return None
    if isinstance(rhr, dict):
        for key in ("restingHeartRate", "value", "restingHeartRateValue"):
            v = _to_int(rhr.get(key))
            if v is not None:
                return v
        for entry in rhr.values():
            if isinstance(entry, dict):
                v = _to_int(entry.get("restingHeartRate") or entry.get("value"))
                if v is not None:
                    return v
            elif isinstance(entry, list):
                for item in entry:
                    if isinstance(item, dict):
                        v = _to_int(
                            item.get("restingHeartRate") or item.get("value")
                        )
                        if v is not None:
                            return v
    if isinstance(rhr, list) and rhr:
        return _extract_resting_hr(rhr[0])
    return None


def _extract_body_battery(bb: Any) -> tuple[int | None, int | None]:
    """Garmin returns a per-day list; each item has bodyBatteryValuesArray = [[ts, level], ...].
    Derive high/low from those level samples (the old highBodyBattery keys do not exist)."""
    if not bb:
        return None, None
    levels: list[int] = []
    items = bb if isinstance(bb, list) else [bb]
    for item in items:
        if not isinstance(item, dict):
            continue
        # explicit summary keys first, if a future API version provides them
        for k in ("bodyBatteryHighestValue", "highBodyBattery"):
            v = _to_int(item.get(k))
            if v is not None:
                levels.append(v)
        for k in ("bodyBatteryLowestValue", "lowBodyBattery"):
            v = _to_int(item.get(k))
            if v is not None:
                levels.append(v)
        for key in (
            "bodyBatteryValuesArray",
            "bodyBatteryValuesArrayList",
        ):
            arr = item.get(key)
            if not isinstance(arr, list):
                continue
            for pt in arr:
                seq = pt if isinstance(pt, list) else []
                for cand in seq[1:]:  # [timestamp, level, ...] -> skip timestamp
                    v = _to_int(cand)
                    if v is not None and 0 <= v <= 100:
                        levels.append(v)
                        break
    if not levels:
        return None, None
    return max(levels), min(levels)


def _extract_hrv_status(hrv: Any) -> str | None:
    if not isinstance(hrv, dict):
        return None
    summary = hrv.get("hrvSummary") or hrv.get("summary") or hrv
    if isinstance(summary, dict):
        status = summary.get("status")
        if isinstance(status, str) and status.strip():
            return status.strip()
    return None


def _extract_hrv(hrv: Any) -> int | None:
    if not hrv:
        return None
    if isinstance(hrv, dict):
        for key in (
            "lastNightAvg",
            "weeklyAvg",
            "avgHrv",
            "hrvValue",
            "value",
        ):
            v = _to_int(hrv.get(key))
            if v is not None:
                return v
        summary = hrv.get("hrvSummary") or hrv.get("summary")
        if isinstance(summary, dict):
            return _extract_hrv(summary)
    return None


def _extract_training_readiness(tr: Any) -> int | None:
    if not tr:
        return None
    entries: list[dict] = []
    if isinstance(tr, dict):
        if "score" in tr or "trainingReadinessScore" in tr:
            entries.append(tr)
        for key in ("mostRecent", "entries", "readinessList"):
            block = tr.get(key)
            if isinstance(block, list):
                entries.extend(x for x in block if isinstance(x, dict))
            elif isinstance(block, dict):
                entries.append(block)
    elif isinstance(tr, list):
        entries = [x for x in tr if isinstance(x, dict)]

    morning = [
        e for e in entries if e.get("inputContext") == "AFTER_WAKEUP_RESET"
    ]
    for e in morning or entries:
        v = _to_int(e.get("score") or e.get("trainingReadinessScore"))
        if v is not None:
            return v
    return None


def _extract_stress(stress: Any) -> int | None:
    if isinstance(stress, dict):
        return _to_int(
            stress.get("avgStressLevel") or stress.get("averageStressLevel")
        )
    return None


def _extract_spo2(spo2: Any) -> int | None:
    if isinstance(spo2, dict):
        return _to_int(
            spo2.get("averageSpO2")
            or spo2.get("avgSleepSpO2")
            or spo2.get("avgSpO2")
            or _safe_get(spo2, "sleepSpO2Data", "averageSpO2")
        )
    return None


def _extract_body_comp(body: Any) -> tuple[int | None, int | None]:
    weight_g = None
    fat_pct = None
    if not isinstance(body, dict):
        return None, None

    def from_block(block: dict) -> None:
        nonlocal weight_g, fat_pct
        if weight_g is None:
            kg = block.get("weight") or block.get("weightKg")
            if kg is not None:
                weight_g = int(round(float(kg) * 1000))
        if fat_pct is None:
            fat_pct = _to_int(
                block.get("bodyFat")
                or block.get("bodyFatPercentage")
                or block.get("percentFat")
            )

    avg = body.get("totalAverage")
    if isinstance(avg, dict):
        from_block(avg)
    from_block(body)

    for key in ("dateWeightList", "dailyWeightSummaries", "allWeightMetrics"):
        entries = body.get(key)
        if isinstance(entries, list) and entries:
            last = entries[-1]
            if isinstance(last, dict):
                from_block(last)
    return weight_g, fat_pct


def _walk_metrics(node: Any, name_hint: str, out: dict[str, int | None]) -> None:
    if isinstance(node, dict):
        keys = " ".join(str(k) for k in node.keys()).lower()
        values = node.values()
        if "vo2" in keys or (name_hint and "vo2" in name_hint):
            v = _to_int(
                node.get("vo2Max")
                or node.get("vo2MaxValue")
                or node.get("value")
                or node.get("genericValue")
            )
            if v is not None and out.get("vo2_max") is None:
                out["vo2_max"] = v
        if "fitness" in keys and "age" in keys:
            v = _to_int(
                node.get("fitnessAge")
                or node.get("currentFitnessAge")
                or node.get("value")
            )
            if v is not None and out.get("fitness_age") is None:
                out["fitness_age"] = v
        for k, v in node.items():
            hint = f"{name_hint} {k}".lower()
            _walk_metrics(v, hint, out)
    elif isinstance(node, list):
        for item in node:
            _walk_metrics(item, name_hint, out)


def _extract_vo2(max_metrics: Any) -> int | None:
    found: dict[str, int | None] = {}
    _walk_metrics(max_metrics, "", found)
    return found.get("vo2_max")


def _extract_fitness_age(fitnessage: Any) -> int | None:
    if not fitnessage:
        return None
    found: dict[str, int | None] = {}
    _walk_metrics(fitnessage, "fitnessage", found)
    if found.get("fitness_age") is not None:
        return found["fitness_age"]
    if isinstance(fitnessage, dict):
        return _to_int(
            fitnessage.get("fitnessAge")
            or fitnessage.get("currentFitnessAge")
            or fitnessage.get("biometricAge")
        )
    return None


def fetch_day(api: Garmin, iso_date: str) -> dict[str, Any]:
    stats = _call(api, "get_stats", iso_date)
    sleep = _call(api, "get_sleep_data", iso_date)
    rhr = _call(api, "get_rhr_day", iso_date)
    bb = _call(api, "get_body_battery", iso_date, iso_date)
    hrv = _call(api, "get_hrv_data", iso_date)
    tr = _call(api, "get_training_readiness", iso_date)
    stress = _call(api, "get_stress_data", iso_date)
    spo2 = _call(api, "get_spo2_data", iso_date)
    body = _call(api, "get_body_composition", iso_date)
    max_metrics = _call(api, "get_max_metrics", iso_date)
    fitnessage = _call(api, "get_fitnessage_data", iso_date)

    dto = _safe_get(sleep, "dailySleepDTO") or {}
    moderate = _to_int(stats.get("moderateIntensityMinutes")) if stats else None
    vigorous = _to_int(stats.get("vigorousIntensityMinutes")) if stats else None
    intensity = None
    if moderate is not None or vigorous is not None:
        intensity = (moderate or 0) + 2 * (vigorous or 0)

    bb_high, bb_low = _extract_body_battery(bb)
    weight_g, body_fat = _extract_body_comp(body)

    # Sleep score lives at dailySleepDTO.sleepScores.overall.value (older paths kept as fallback).
    sleep_scores = dto.get("sleepScores") if isinstance(dto.get("sleepScores"), dict) else {}
    overall = sleep_scores.get("overall") if isinstance(sleep_scores.get("overall"), dict) else {}
    sleep_score = _to_int(
        overall.get("value")
        or sleep_scores.get("overallScore")
        or dto.get("sleepScoresOverall")
        or dto.get("sleepScore")
    )

    return {
        "day": iso_date,
        "steps": _first_int(stats.get("totalSteps") if stats else None),
        "resting_hr": _extract_resting_hr(rhr)
        or _first_int(stats.get("restingHeartRate") if stats else None),
        "sleep_seconds": _to_int(dto.get("sleepTimeSeconds")),
        "sleep_score": sleep_score,
        "deep_sleep_seconds": _to_int(dto.get("deepSleepSeconds")),
        "rem_sleep_seconds": _to_int(dto.get("remSleepSeconds")),
        "light_sleep_seconds": _to_int(dto.get("lightSleepSeconds")),
        "awake_count": _to_int(dto.get("awakeCount")),
        "avg_sleep_stress": _to_int(dto.get("avgSleepStress")),
        "respiration_avg": _to_int(dto.get("averageRespirationValue")),
        "stress_avg": _extract_stress(stress),
        "stress_max": _to_int(stress.get("maxStressLevel")) if isinstance(stress, dict) else None,
        "body_battery_high": bb_high,
        "body_battery_low": bb_low,
        "hrv_avg": _extract_hrv(hrv),
        "hrv_status": _extract_hrv_status(hrv),
        "training_readiness": _extract_training_readiness(tr),
        "intensity_minutes": intensity,
        "floors_climbed": _first_int(
            stats.get("floorsAscended") if stats else None
        ),
        "active_kcal": _first_int(
            stats.get("activeKilocalories") if stats else None
        ),
        "spo2_avg": _extract_spo2(spo2),
        "weight_grams": weight_g,
        "body_fat_percent": body_fat,
        "vo2_max": _extract_vo2(max_metrics),
        "fitness_age": _extract_fitness_age(fitnessage),
    }
