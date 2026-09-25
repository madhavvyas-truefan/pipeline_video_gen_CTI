# Pipeline Video Gen CTI

Continuity-first presenter-video pipeline for macOS.

This repository provides the deterministic part of the workflow: input validation, canonical audio timeline planning, safe join selection, presenter calibration, continuity scoring, despill configuration, QC gates, manifests, and reproducible render metadata. Higgsfield/Seedance and Sync Lipsync 3 remain external providers and are represented by adapters; the pipeline never claims to generate those paid-model assets locally.

## Requirements

- macOS 13+
- Python 3.9+
- Swift 5.7+ only when using the optional AVFoundation adapter
- No ffmpeg dependency

## Quick start

```bash
python3 pipeline.py demo --out demo_run
python3 pipeline.py validate demo_run/video_plan.json
python3 pipeline.py plan demo_run/video_plan.json --out demo_run/plan.json
python3 pipeline.py qc demo_run/video_plan.json --out demo_run/qc_report.json
```

The demo completes without network access or paid model credentials and writes a valid plan plus QC report. A real run uses the same manifest shape with actual media paths and provider outputs.

## Real workflow

1. Create `video_plan.json` from the example in `examples/video_plan.json`.
2. Run `validate` before generating anything.
3. Generate overlapping provider candidates through the external-provider adapter.
4. Run `plan` to choose safe boundaries and identify bridge candidates.
5. Normalize accepted clips to the presenter profile and apply calibrated despill.
6. Composite graphics from the timeline manifest.
7. Run `qc`; delivery is blocked if any gate fails.

The audio timeline is authoritative. Chunk boundaries are frame-aligned at the declared frame rate, and each join carries a continuity decision instead of silently dissolving mismatched poses.

