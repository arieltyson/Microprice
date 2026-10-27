#!/usr/bin/env bash
# Measures the multicast feed end to end on loopback: replays a LOBSTER file
# through the engine, publishes every book event, and captures it in a second
# process that checks sequence numbers and records one-way latency.
set -euo pipefail
build=${1:-build}
messages=${2:?usage: bench_feed.sh BUILD_DIR MESSAGE_FILE}
out=$(mktemp -d)
"$build/feed/feed_capture" --out "$out/capture.bin" --idle-ms 2000 > "$out/capture.json" &
capture=$!
sleep 1
"$build/feed/feed_replay" --messages "$messages" --symbol 1 > "$out/replay.json"
wait $capture || true
mkdir -p results
python3 - "$out" <<'PY'
import json, sys, pathlib
out = pathlib.Path(sys.argv[1])
report = {"replay": json.loads((out / "replay.json").read_text()), "capture": json.loads((out / "capture.json").read_text())}
pathlib.Path("results/feed_bench.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
PY
