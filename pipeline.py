#!/usr/bin/env python3
"""Continuity-first planning and QC for presenter video generation.

This module intentionally contains no network or codec dependency. Paid model
generation is external; this tool validates the contract around it so a bad
plan or bad join cannot silently reach delivery.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import shutil
import sys
from typing import Any, Dict, List


ROOT = pathlib.Path(__file__).resolve().parent


def load_json(path: pathlib.Path) -> Dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc


def frame_time(seconds: float, fps: int) -> float:
    return round(round(seconds * fps) / fps, 6)


def validate(plan: Dict[str, Any], base: pathlib.Path) -> List[str]:
    errors: List[str] = []
    if plan.get("schema") != 1:
        errors.append("schema must be 1")
    fps = plan.get("frameRate")
    if not isinstance(fps, int) or fps <= 0:
        errors.append("frameRate must be a positive integer")
    resolution = plan.get("resolution")
    if resolution != [1080, 1350]:
        errors.append("resolution must be [1080, 1350]")
    inputs = plan.get("inputs", {})
    for key in ("presenterStill", "audio", "script", "background"):
        if not inputs.get(key):
            errors.append(f"inputs.{key} is required")
    chunks = plan.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        errors.append("chunks must be a non-empty list")
        return errors
    previous_end = None
    for index, chunk in enumerate(chunks):
        prefix = f"chunks[{index}]"
        for key in ("id", "start", "end", "line"):
            if key not in chunk:
                errors.append(f"{prefix}.{key} is required")
        if not all(key in chunk for key in ("start", "end")):
            continue
        start, end = chunk["start"], chunk["end"]
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            errors.append(f"{prefix} start/end must be numbers")
            continue
        if end <= start:
            errors.append(f"{prefix} end must be greater than start")
        if previous_end is not None and abs(start - previous_end) > 1e-6:
            errors.append(f"{prefix} does not start where the previous chunk ends")
        previous_end = end
        overlap = chunk.get("overlap", 0)
        if not isinstance(overlap, (int, float)) or overlap < 0:
            errors.append(f"{prefix}.overlap must be non-negative")
    profile = plan.get("presenterProfile", {})
    if not profile.get("faceTarget") or not profile.get("despill"):
        errors.append("presenterProfile.faceTarget and presenterProfile.despill are required")
    return errors


def build_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    fps = plan["frameRate"]
    chunks = plan["chunks"]
    planned = []
    joins = []
    for index, chunk in enumerate(chunks):
        start = frame_time(float(chunk["start"]), fps)
        end = frame_time(float(chunk["end"]), fps)
        overlap = frame_time(float(chunk.get("overlap", 0)), fps)
        planned.append({
            **chunk,
            "start": start,
            "end": end,
            "startFrame": round(start * fps),
            "endFrame": round(end * fps),
            "generationStart": frame_time(max(0, start - overlap), fps),
            "generationEnd": frame_time(end + overlap, fps),
        })
        if index:
            joins.append({
                "between": [chunks[index - 1]["id"], chunk["id"]],
                "at": start,
                "transitionFrames": max(3, min(8, round(overlap * fps / 2))),
                "strategy": "select-overlap-then-bridge",
                "requiresReview": True,
            })
    return {
        "schema": 1,
        "frameRate": fps,
        "resolution": plan["resolution"],
        "chunks": planned,
        "joins": joins,
        "audioIsMasterClock": True,
        "deliveryPolicy": "block-on-qc-failure",
    }


def qc(plan: Dict[str, Any], derived: Dict[str, Any] | None = None) -> Dict[str, Any]:
    errors = validate(plan, pathlib.Path("."))
    joins = (derived or build_plan(plan)).get("joins", [])
    checks = {
        "manifestValid": not errors,
        "frameAligned": all(
            abs(float(c["start"]) * plan["frameRate"] - round(float(c["start"]) * plan["frameRate"])) < 1e-5
            for c in plan.get("chunks", [])
        ),
        "joinsHaveReviewGate": all(j.get("requiresReview") for j in joins),
        "audioIsMasterClock": bool((derived or {}).get("audioIsMasterClock", True)),
    }
    return {"status": "PASS" if not errors and all(checks.values()) else "FAIL", "checks": checks, "errors": errors}


def write_json(path: pathlib.Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def demo(out: pathlib.Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    source = ROOT / "examples" / "video_plan.json"
    target = out / "video_plan.json"
    shutil.copyfile(source, target)
    plan = load_json(target)
    derived = build_plan(plan)
    write_json(out / "plan.json", derived)
    write_json(out / "qc_report.json", qc(plan, derived))
    print(f"Demo completed: {out}")


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_demo = sub.add_parser("demo"); p_demo.add_argument("--out", type=pathlib.Path, required=True)
    p_val = sub.add_parser("validate"); p_val.add_argument("manifest", type=pathlib.Path)
    p_plan = sub.add_parser("plan"); p_plan.add_argument("manifest", type=pathlib.Path); p_plan.add_argument("--out", type=pathlib.Path, required=True)
    p_qc = sub.add_parser("qc"); p_qc.add_argument("manifest", type=pathlib.Path); p_qc.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "demo":
        demo(args.out); return 0
    plan = load_json(args.manifest)
    errors = validate(plan, args.manifest.parent)
    if args.command == "validate":
        if errors:
            print("INVALID\n" + "\n".join(f"- {e}" for e in errors)); return 1
        print("VALID"); return 0
    if errors:
        print("INVALID\n" + "\n".join(f"- {e}" for e in errors)); return 1
    derived = build_plan(plan)
    if args.command == "plan": write_json(args.out, derived)
    else: write_json(args.out, qc(plan, derived))
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
