#!/usr/bin/env python3
"""Run every deterministic pipeline stage and write a renderer handoff bundle."""
from __future__ import annotations

import argparse
import pathlib
import sys

import pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=pathlib.Path)
    parser.add_argument("candidates", type=pathlib.Path,
                        help="Provider-imported candidates with measured metrics")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()

    plan = pipeline.read(args.manifest)
    errors = pipeline.validate(plan)
    if errors:
        print("Invalid manifest:\n" + "\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    timeline = pipeline.timeline(plan)
    selection = pipeline.select(timeline, pipeline.read(args.candidates))
    joins = pipeline.join_plan(timeline, selection)
    report = pipeline.qc(plan, timeline, selection, joins)
    handoff = {
        "schema": 1,
        "project": plan.get("project"),
        "generatedAt": pipeline.now(),
        "audioIsMasterClock": True,
        "inputs": plan["inputs"],
        "presenterProfile": plan["presenterProfile"],
        "timeline": "timeline.json",
        "selection": "selection.json",
        "joins": "joins.json",
        "supers": plan.get("supers", []),
        "renderPolicy": {
            "intermediateCodec": "ProRes 422 or ProRes 4444",
            "deliveryCodec": "H.264 or HEVC after encoder probe",
            "allowDelivery": report["delivery"] == "allowed",
            "requireFrameByFrameJoinApproval": True,
        },
    }
    for name, value in {
        "timeline.json": timeline,
        "selection.json": selection,
        "joins.json": joins,
        "qc_report.json": report,
        "provenance.json": pipeline.provenance(args.manifest, plan),
        "encoder_probe_policy.json": pipeline.probe(),
        "renderer_handoff.json": handoff,
    }.items():
        pipeline.write(args.out / name, value)
    (args.out / "join_review.html").write_text(pipeline.review(joins), encoding="utf-8")
    print(f"Run bundle written to {args.out}; delivery is {report['delivery']}.")
    return 0 if report["delivery"] == "allowed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
