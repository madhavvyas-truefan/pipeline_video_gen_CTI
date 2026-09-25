# Input and provider contract

`video_plan.json` is the source of truth. The audio timeline is immutable once
approved. All chunk and super times must be exact frame boundaries.

Provider candidates must be imported as JSON with one entry per generated,
lip-synced clip. Each entry requires `id`, `chunkId`, `path`, and metrics:

- `lipLagMs`: absolute mouth-to-audio lag
- `faceDelta`: normalized framing deviation
- `poseDelta`: normalized torso/head pose deviation at the candidate boundary
- `handDelta`: normalized hand/arm deviation at the candidate boundary
- `greenSpillPercent`: percentage of foreground pixels that retain green spill

Candidates are generated externally. The local pipeline ranks them, decides
whether a join is a direct cut, optical-flow bridge, or regeneration request,
and blocks delivery until every join is approved.

## Renderer handoff

`run.py` produces `renderer_handoff.json`. A macOS renderer must use it to:

1. Decode only selected candidates.
2. Normalize to 1080×1350 at the planned frame rate.
3. Apply presenter-profile despill before final keying.
4. Render bridge frames for `optical-flow-bridge` decisions.
5. Refuse `regenerate-bridge` joins.
6. Use ProRes for intermediates and probe a delivery codec before final export.
7. Re-open the finished file and attach its report to the provenance bundle.
