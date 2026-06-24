"""Garmin endpoint diagnostic.

Probes a broad set of wellness endpoints for one day, reports which return data for
THIS device/account, and dumps raw JSON so we can fix extractor key paths and decide
which new metrics are worth storing.

Usage:
    python scripts/diagnose_garmin.py [YYYY-MM-DD]

Default date is yesterday (more likely to be a complete day than today).
Raw JSON is written to docs/diagnostic_<date>.json (gitignored). No data leaves your machine.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# (label, method_name, arg_kind): date -> fn(d) | range -> fn(d, d) | steps -> fn(d, d) | none -> fn()
PROBES: list[tuple[str, str, str]] = [
    ("stats", "get_stats", "date"),
    ("user_summary", "get_user_summary", "date"),
    ("sleep", "get_sleep_data", "date"),
    ("rhr", "get_rhr_day", "date"),
    ("body_battery", "get_body_battery", "range"),
    ("body_battery_events", "get_body_battery_events", "date"),
    ("hrv", "get_hrv_data", "date"),
    ("training_readiness", "get_training_readiness", "date"),
    ("morning_training_readiness", "get_morning_training_readiness", "date"),
    ("training_status", "get_training_status", "date"),
    ("stress", "get_stress_data", "date"),
    ("all_day_stress", "get_all_day_stress", "date"),
    ("spo2", "get_spo2_data", "date"),
    ("respiration", "get_respiration_data", "date"),
    ("max_metrics", "get_max_metrics", "date"),
    ("fitnessage", "get_fitnessage_data", "date"),
    ("endurance_score", "get_endurance_score", "range"),
    ("hill_score", "get_hill_score", "range"),
    ("race_predictions", "get_race_predictions", "none"),
    ("floors", "get_floors", "date"),
    ("body_composition", "get_body_composition", "range"),
    ("hydration", "get_hydration_data", "date"),
    ("intensity_minutes", "get_intensity_minutes_data", "date"),
    ("daily_steps", "get_daily_steps", "steps"),
]


def _is_empty(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, (dict, list, str)) and len(val) == 0:
        return True
    return False


def _call(api: Any, method: str, kind: str, target: str) -> Any:
    fn = getattr(api, method, None)
    if fn is None:
        raise AttributeError(f"{method} not available in this garminconnect version")
    if kind == "date":
        return fn(target)
    if kind in ("range", "steps"):
        return fn(target, target)
    if kind == "none":
        return fn()
    raise ValueError(f"unknown arg kind: {kind}")


def scalar_paths(node: Any, prefix: str = "", out: list | None = None, cap: int = 40) -> list:
    """Flatten to leaf (path, value) pairs with non-null scalars. Lists: descend first item only."""
    out = [] if out is None else out
    if len(out) >= cap:
        return out
    if isinstance(node, dict):
        for k, v in node.items():
            scalar_paths(v, f"{prefix}.{k}" if prefix else str(k), out, cap)
    elif isinstance(node, list):
        if node and isinstance(node[0], (dict, list)):
            scalar_paths(node[0], f"{prefix}[0]", out, cap)
        elif node:
            out.append((prefix or "(list)", f"[{len(node)} items] e.g. {node[0]!r}"))
    elif node is not None:
        out.append((prefix or "(value)", node)) if not isinstance(node, str) or node else None
    return out


def _shape(val: Any) -> str:
    if isinstance(val, dict):
        return f"dict({len(val)} keys)"
    if isinstance(val, list):
        return f"list({len(val)})"
    return type(val).__name__


# --- focused checks on the three known-broken metrics --------------------------------

def resolve_sleep_score(sleep: Any) -> tuple[Any, str]:
    if not isinstance(sleep, dict):
        return None, "no sleep dict"
    dto = sleep.get("dailySleepDTO") or {}
    candidates = [
        ("dailySleepDTO.sleepScores.overall.value",
         (((dto.get("sleepScores") or {}).get("overall") or {}).get("value"))),
        ("dailySleepDTO.sleepScores.overallScore",
         ((dto.get("sleepScores") or {}).get("overallScore"))),
        ("dailySleepDTO.sleepScoresOverall (current code path)", dto.get("sleepScoresOverall")),
        ("dailySleepDTO.sleepScore", dto.get("sleepScore")),
    ]
    for path, v in candidates:
        if v is not None:
            return v, path
    return None, "not found in tried paths"


def resolve_body_battery(bb: Any) -> tuple[Any, Any, str]:
    items = bb if isinstance(bb, list) else [bb]
    levels: list[float] = []
    arr_key = None
    for it in items:
        if not isinstance(it, dict):
            continue
        for key in ("bodyBatteryValuesArray", "bodyBatteryValuesArrayList", "bodyBatteryValueDescriptorDTOList"):
            arr = it.get(key)
            if isinstance(arr, list) and arr:
                arr_key = key
                for pt in arr:
                    seq = pt if isinstance(pt, list) else [pt.get("value")] if isinstance(pt, dict) else []
                    for cand in (seq[1:] if isinstance(pt, list) else seq):
                        if isinstance(cand, (int, float)) and 0 <= cand <= 100:
                            levels.append(cand)
                            break
                break
    if levels:
        return max(levels), min(levels), f"derived from {arr_key} ({len(levels)} pts)"
    return None, None, "no level array found"


def resolve_training_readiness(tr: Any, mtr: Any) -> tuple[Any, str]:
    def score(x: Any) -> Any:
        entries = x if isinstance(x, list) else [x]
        for e in entries:
            if isinstance(e, dict):
                v = e.get("score") or e.get("trainingReadinessScore")
                if v is not None:
                    return v
        return None
    s = score(tr)
    if s is not None:
        return s, "get_training_readiness"
    s = score(mtr)
    if s is not None:
        return s, "get_morning_training_readiness"
    return None, "neither endpoint returned a score"


# --- main collection / rendering -----------------------------------------------------

def collect(api: Any, target: str) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for label, method, kind in PROBES:
        rec: dict[str, Any] = {"method": method, "kind": kind}
        try:
            val = _call(api, method, kind, target)
            rec["status"] = "empty" if _is_empty(val) else "ok"
            rec["shape"] = _shape(val)
            rec["sample_paths"] = [f"{p} = {v}" for p, v in scalar_paths(val)]
            rec["raw"] = val
        except Exception as err:  # noqa: BLE001 - diagnostic wants every failure captured
            rec["status"] = "error"
            rec["error"] = f"{type(err).__name__}: {err}"
        results[label] = rec
    return results


def render(results: dict[str, Any], target: str) -> str:
    lines: list[str] = []
    order = {"ok": 0, "empty": 1, "error": 2}
    lines.append(f"=== Garmin endpoint diagnostic for {target} ===\n")
    counts = {"ok": 0, "empty": 0, "error": 0}
    for label in sorted(results, key=lambda k: (order.get(results[k]["status"], 9), k)):
        r = results[label]
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        mark = {"ok": "OK   ", "empty": "EMPTY", "error": "ERROR"}.get(r["status"], "?")
        extra = r.get("shape", r.get("error", ""))
        lines.append(f"[{mark}] {label:28s} {r['method']:32s} {extra}")
    lines.append(f"\nTotals: {counts.get('ok',0)} ok, {counts.get('empty',0)} empty, {counts.get('error',0)} error\n")

    # focused checks on the three known-broken metrics
    lines.append("--- Known-broken metric resolution ---")
    sleep = results.get("sleep", {}).get("raw")
    ss, ss_path = resolve_sleep_score(sleep)
    lines.append(f"sleep_score        : {ss}   (via {ss_path})")
    bb = results.get("body_battery", {}).get("raw")
    hi, lo, bb_note = resolve_body_battery(bb)
    lines.append(f"body_battery hi/lo : {hi}/{lo}   ({bb_note})")
    tr = results.get("training_readiness", {}).get("raw")
    mtr = results.get("morning_training_readiness", {}).get("raw")
    trv, tr_path = resolve_training_readiness(tr, mtr)
    lines.append(f"training_readiness : {trv}   (via {tr_path})")

    # field discovery for endpoints we don't yet store
    lines.append("\n--- Scalar fields found in NEW candidate endpoints ---")
    for label in ("training_status", "respiration", "all_day_stress", "endurance_score",
                  "hill_score", "race_predictions", "floors", "hrv"):
        r = results.get(label)
        if not r or r.get("status") != "ok":
            lines.append(f"{label}: {r.get('status') if r else 'absent'}")
            continue
        lines.append(f"{label}:")
        for p in r.get("sample_paths", [])[:12]:
            lines.append(f"    {p}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    target = argv[0] if argv else (date.today() - timedelta(days=1)).isoformat()

    from src import garmin_client

    print(f"Logging in to Garmin... (target day: {target})")
    api = garmin_client.login()
    results = collect(api, target)

    out_dir = _ROOT / "docs"
    out_dir.mkdir(exist_ok=True)
    raw_path = out_dir / f"diagnostic_{target}.json"
    raw_path.write_text(json.dumps(results, indent=2, default=str))

    report = render(results, target)
    print("\n" + report)
    print(f"\nRaw JSON dumped to: {raw_path}")
    print("(gitignored — safe to delete after we patch the extractors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
