"""Full-history statistics digest (all math here; LLM only narrates)."""

from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta
from typing import Any

from src import config

CORE_METRICS = list(config.METRICS.keys())
FLAT_SLOPE_THRESHOLD = 0.02


def _val(row: dict[str, Any], key: str) -> float | None:
    v = row.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _series(rows: list[dict], key: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for r in rows:
        v = _val(r, key)
        if v is not None:
            out.append((r["day"], v))
    return out


def _mean(vals: list[float]) -> float | None:
    return statistics.mean(vals) if vals else None


def _median(vals: list[float]) -> float | None:
    return statistics.median(vals) if vals else None


def _std(vals: list[float]) -> float | None:
    if len(vals) < 2:
        return 0.0 if vals else None
    return statistics.stdev(vals)


def _percentile_rank(yesterday: float, history: list[float]) -> float | None:
    if not history:
        return None
    below = sum(1 for v in history if v < yesterday)
    equal = sum(1 for v in history if v == yesterday)
    return round(100 * (below + 0.5 * equal) / len(history), 1)


def _ols_slope(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    n = len(points)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in points)
    den = sum((x - x_mean) ** 2 for x in xs)
    if den == 0:
        return None
    return num / den


def _trend_label(slope: float | None, good: str, metric: str) -> str | None:
    if slope is None:
        return None
    if good == "target":
        return "flat"
    threshold = FLAT_SLOPE_THRESHOLD
    if metric == "sleep_seconds":
        threshold = 300
    if abs(slope) < threshold:
        return "flat"
    improving = slope > 0 if good == "up" else slope < 0
    return "improving" if improving else "declining"


def _in_target(val: float, metric: str) -> bool:
    if metric == "sleep_seconds":
        lo, hi = config.SLEEP_TARGET_SECONDS
        return lo <= val <= hi
    if metric == "steps":
        return val >= config.STEP_GOAL
    return False


def _meets_goal(val: float, metric: str, good: str) -> bool:
    if good == "target":
        return _in_target(val, metric)
    if metric == "steps":
        return val >= config.STEP_GOAL
    return True


def _streak(rows: list[dict], key: str, as_of: str, good: str) -> int:
    ordered = sorted(
        (r for r in rows if r["day"] <= as_of),
        key=lambda r: r["day"],
        reverse=True,
    )
    mean_30 = _window_mean(_series(rows, key), as_of, 30)
    streak = 0
    for r in ordered:
        v = _val(r, key)
        if v is None:
            break
        if good == "target" or key == "steps":
            if not _meets_goal(v, key, good):
                break
            streak += 1
        elif mean_30 is not None:
            if good == "up" and v < mean_30:
                break
            if good == "down" and v > mean_30:
                break
            streak += 1
        else:
            break
    return streak


def _record_flag(
    yesterday: float,
    all_vals: list[float],
    recent_90: list[float],
    good: str,
    insufficient: bool,
) -> str | None:
    if insufficient or not all_vals:
        return None

    def best(vals: list[float]) -> bool:
        return yesterday == max(vals) and yesterday > min(vals)

    def worst(vals: list[float]) -> bool:
        return yesterday == min(vals) and yesterday < max(vals)

    if good == "down":
        if best(all_vals):
            return "all_time_worst"
        if worst(all_vals):
            return "all_time_best"
        if recent_90 and best(recent_90):
            return "90d_worst"
        if recent_90 and worst(recent_90):
            return "90d_best"
    else:
        if best(all_vals):
            return "all_time_best"
        if worst(all_vals):
            return "all_time_worst"
        if recent_90 and best(recent_90):
            return "90d_best"
        if recent_90 and worst(recent_90):
            return "90d_worst"
    return None


def _window_mean(series: list[tuple[str, float]], as_of: str, days: int) -> float | None:
    cutoff = (datetime.strptime(as_of, "%Y-%m-%d").date() - timedelta(days=days - 1)).isoformat()
    vals = [v for d, v in series if cutoff <= d <= as_of]
    return _mean(vals)


def _dow_baseline(rows: list[dict], key: str, as_of: str) -> tuple[float | None, float | None]:
    dt = datetime.strptime(as_of, "%Y-%m-%d")
    dow = dt.weekday()
    vals = []
    for r in rows:
        if r["day"] >= as_of:
            continue
        if datetime.strptime(r["day"], "%Y-%m-%d").weekday() != dow:
            continue
        v = _val(r, key)
        if v is not None:
            vals.append(v)
    baseline = _mean(vals)
    y = _val(next((r for r in rows if r["day"] == as_of), {}), key)
    delta = (y - baseline) if y is not None and baseline is not None else None
    return baseline, delta


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _lagged_pairs(
    rows: list[dict], driver: str, outcome: str, lag: int = 1
) -> tuple[list[float], list[float]]:
    by_day = {r["day"]: r for r in rows}
    xs, ys = [], []
    for r in rows:
        d = r["day"]
        x = _val(r, driver)
        if x is None:
            continue
        next_d = (datetime.strptime(d, "%Y-%m-%d").date() + timedelta(days=lag)).isoformat()
        nr = by_day.get(next_d)
        if not nr:
            continue
        y = _val(nr, outcome)
        if y is not None:
            xs.append(x)
            ys.append(y)
    return xs, ys


def _resolve_as_of(rows: list[dict]) -> tuple[str, str]:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    days = {r["day"] for r in rows}
    if yesterday in days:
        return yesterday, "yesterday"
    for r in reversed(rows):
        if any(_val(r, k) is not None for k in CORE_METRICS):
            return r["day"], "latest_available"
    if rows:
        return rows[-1]["day"], "latest_row"
    return yesterday, "empty"


def _metric_block(
    rows: list[dict], key: str, as_of: str, meta: dict[str, str]
) -> dict[str, Any] | None:
    series = _series(rows, key)
    if not series:
        return None
    hist = [v for _, v in series]
    y_entry = next((v for d, v in series if d == as_of), None)
    if y_entry is None:
        return None

    insufficient = len(hist) < config.MIN_HISTORY_DAYS
    std = _std(hist)
    mean = _mean(hist)
    zscore = None
    if mean is not None and std is not None and std > 0:
        zscore = round((y_entry - mean) / std, 2)

    recent_90 = [v for d, v in series if d >= (datetime.strptime(as_of, "%Y-%m-%d").date() - timedelta(days=89)).isoformat()]

    last_30 = [(i, v) for i, (_, v) in enumerate(series[-30:])]
    slope = _ols_slope(last_30)
    good = meta["good"]

    baseline, delta_dow = _dow_baseline(rows, key, as_of)

    block: dict[str, Any] = {
        "label": meta["label"],
        "unit": meta["unit"],
        "good_direction": good,
        "yesterday": round(y_entry, 2) if key != "sleep_seconds" else int(y_entry),
        "all_time": {
            "mean": round(mean, 2) if mean is not None else None,
            "median": round(_median(hist), 2) if hist else None,
            "std": round(std, 2) if std is not None else None,
            "min": round(min(hist), 2),
            "max": round(max(hist), 2),
            "n": len(hist),
        },
        "mean_7d": round(_window_mean(series, as_of, 7), 2) if series else None,
        "mean_30d": round(_window_mean(series, as_of, 30), 2) if series else None,
        "mean_90d": round(_window_mean(series, as_of, 90), 2) if series else None,
        "insufficient_history": insufficient,
    }

    if not insufficient:
        block["percentile"] = _percentile_rank(y_entry, hist)
        block["zscore"] = zscore
        block["record_flag"] = _record_flag(y_entry, hist, recent_90, good, insufficient)
    else:
        block["percentile"] = None
        block["zscore"] = None
        block["record_flag"] = None

    block["trend_30d"] = {
        "slope": round(slope, 4) if slope is not None else None,
        "label": _trend_label(slope, good, key),
    }
    block["dow_baseline"] = (
        round(baseline, 2) if baseline is not None else None
    )
    block["delta_vs_dow"] = (
        round(delta_dow, 2) if delta_dow is not None else None
    )
    block["streak"] = _streak(rows, key, as_of, good)

    if key == "sleep_seconds":
        block["yesterday_hours"] = round(y_entry / 3600, 2)

    return block


def _correlation_block(
    rows: list[dict],
    driver: str,
    outcome: str,
    lag: int,
    label: str,
    as_of: str,
) -> dict[str, Any] | None:
    xs, ys = _lagged_pairs(rows, driver, outcome, lag)
    if len(xs) < config.MIN_HISTORY_DAYS:
        return None
    coef = _pearson(xs, ys)
    if coef is None:
        return None

    driver_y = _val(next((r for r in rows if r["day"] == as_of), {}), driver)
    driver_hist = [x for _, x in _series(rows, driver)]
    ctx = None
    if driver_y is not None and driver_hist:
        pct = _percentile_rank(driver_y, driver_hist)
        level = "high" if pct and pct >= 70 else "low" if pct and pct <= 30 else "moderate"
        direction = "positive" if coef > 0.1 else "negative" if coef < -0.1 else "weak"
        ctx = (
            f"yesterday's {label} was {level} (percentile {pct}); "
            f"historical {direction} link (r={round(coef, 2)})"
        )

    return {
        "driver": driver,
        "outcome": outcome,
        "lag_days": lag,
        "coefficient": round(coef, 3),
        "n_pairs": len(xs),
        "yesterday_context": ctx,
        "interpretation_hint": (
            f"More {label} tends to associate with "
            f"{'higher' if coef > 0 else 'lower' if coef < 0 else 'little change in'} "
            f"next-day {outcome} (r={round(coef, 2)}, n={len(xs)})"
        ),
    }


def _salience_score(metric: dict[str, Any], key: str) -> float:
    if metric.get("insufficient_history"):
        z = 0
    else:
        z = abs(metric.get("zscore") or 0)
    pct = metric.get("percentile")
    pct_ext = 0
    if pct is not None:
        pct_ext = max(0, (50 - abs(pct - 50)) / 50) * 3
    streak = min(metric.get("streak") or 0, 14) / 7
    record_bonus = 2 if metric.get("record_flag") else 0
    return 2 * z + pct_ext + streak + record_bonus


def _top_signals(
    metrics: dict[str, Any],
    correlations: list[dict[str, Any]],
) -> list[dict[str, str]]:
    candidates: list[tuple[float, str, str]] = []

    for key, m in metrics.items():
        if m.get("insufficient_history"):
            continue
        score = _salience_score(m, key)
        label = m.get("label", key)
        parts = []
        if m.get("zscore") is not None:
            parts.append(f"z={m['zscore']}")
        if m.get("percentile") is not None:
            parts.append(f"percentile={m['percentile']}")
        if m.get("record_flag"):
            parts.append(m["record_flag"])
        if m.get("streak", 0) >= 3:
            parts.append(f"{m['streak']}-day streak")
        trend = m.get("trend_30d", {}).get("label")
        if trend and trend != "flat":
            parts.append(f"30d trend {trend}")
        if parts:
            candidates.append((score, label, "; ".join(parts)))

    for c in correlations:
        if abs(c.get("coefficient", 0)) < 0.25:
            continue
        ctx = c.get("yesterday_context") or c.get("interpretation_hint", "")
        if ctx and "moderate" not in ctx:
            candidates.append(
                (1.5 + abs(c["coefficient"]), c["driver"] + "→" + c["outcome"], ctx)
            )

    candidates.sort(key=lambda x: x[0], reverse=True)
    top = candidates[:5]
    return [{"label": lbl, "detail": det} for _, lbl, det in top]


def build_digest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "as_of": (date.today() - timedelta(days=1)).isoformat(),
            "as_of_note": "no_data",
            "metrics": {},
            "correlations": [],
            "top_signals": [],
        }

    as_of, note = _resolve_as_of(rows)
    metrics: dict[str, Any] = {}
    for key, meta in config.METRICS.items():
        block = _metric_block(rows, key, as_of, meta)
        if block:
            metrics[key] = block

    correlations = []
    specs = [
        ("sleep_seconds", "resting_hr", 1, "sleep"),
        ("intensity_minutes", "hrv_avg", 1, "intensity"),
        ("intensity_minutes", "body_battery_high", 1, "intensity"),
        ("stress_avg", "sleep_score", 0, "stress"),
    ]
    for driver, outcome, lag, label in specs:
        if driver not in metrics or outcome not in metrics:
            continue
        if lag == 0:
            xs = [_val(r, driver) for r in rows]
            ys = [_val(r, outcome) for r in rows]
            pairs_x, pairs_y = [], []
            for x, y, r in zip(xs, ys, rows):
                if x is not None and y is not None:
                    pairs_x.append(x)
                    pairs_y.append(y)
            block = None
            if len(pairs_x) >= config.MIN_HISTORY_DAYS:
                coef = _pearson(pairs_x, pairs_y)
                if coef is not None:
                    driver_y = _val(next((r for r in rows if r["day"] == as_of), {}), driver)
                    driver_hist = [x for _, x in _series(rows, driver)]
                    pct = _percentile_rank(driver_y, driver_hist) if driver_y and driver_hist else None
                    level = "high" if pct and pct >= 70 else "low" if pct and pct <= 30 else "moderate"
                    block = {
                        "driver": driver,
                        "outcome": outcome,
                        "lag_days": 0,
                        "coefficient": round(coef, 3),
                        "n_pairs": len(pairs_x),
                        "yesterday_context": (
                            f"yesterday's {label} was {level}; same-day sleep score link r={round(coef, 2)}"
                            if pct
                            else None
                        ),
                        "interpretation_hint": f"Stress vs sleep score r={round(coef, 2)} (n={len(pairs_x)})",
                    }
        else:
            block = _correlation_block(rows, driver, outcome, lag, label, as_of)
        if block:
            correlations.append(block)

    digest = {
        "as_of": as_of,
        "as_of_note": note,
        "step_goal": config.STEP_GOAL,
        "sleep_target_hours": list(config.SLEEP_TARGET_HOURS),
        "metrics": metrics,
        "correlations": correlations,
        "top_signals": _top_signals(metrics, correlations),
    }
    return digest
