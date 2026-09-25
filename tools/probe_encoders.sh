#!/bin/zsh
set -euo pipefail
ROOT="${0:A:h:h}"
CACHE="${PIPELINE_SWIFT_MODULE_CACHE:-/private/tmp/pipeline-video-gen-swift-cache}"
mkdir -p "$CACHE"
swiftc -O -module-cache-path "$CACHE" "$ROOT/adapters/EncoderProbe.swift" -o /private/tmp/pipeline-video-gen-encoder-probe
/private/tmp/pipeline-video-gen-encoder-probe
