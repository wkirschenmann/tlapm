#!/bin/sh
# Run tlapm on a spec with real solvers, timestamping every verdict as it
# is emitted on the @!! stream (exact per-verdict times, no polling), and
# sampling the process RSS on the side.
#
# Outputs:
#   <out>.verdicts.csv : epoch_s,verdict_index      (one line per verdict)
#   <out>.rss.csv      : epoch_s,rss_mb             (sampled)
#
# Usage: monitor_run.sh <tlapm-bin> <spec.tla> <out-prefix> [interval_s] [extra args...]

set -u
if [ $# -lt 3 ]; then
    echo "usage: $0 <tlapm-bin> <spec.tla> <out-prefix> [interval_s] [extra args...]" >&2
    exit 2
fi
TLAPM="$1"; SPEC="$2"; OUT="$3"; INT="${4:-5}"
[ $# -ge 4 ] && shift 4 || shift 3

echo "epoch_s,verdict_index" > "$OUT.verdicts.csv"
echo "epoch_s,rss_mb" > "$OUT.rss.csv"

# The awk filter tags each verdict line with the time it arrives; stdbuf
# keeps the pipe line-buffered so timestamps are not batched.
# MON_TIMEOUT (seconds, optional) caps the run: a truncated run still
# yields throughput and RSS-slope data, unlike a plain timeout.
CAP=""
[ -n "${MON_TIMEOUT:-}" ] && CAP="timeout $MON_TIMEOUT"
stdbuf -oL -eL $CAP "$TLAPM" --toolbox 0 0 --nofp "$@" "$SPEC" < /dev/null 2>&1 \
  | stdbuf -oL awk '/@!!status:(proved|trivial|failed)/ { print systime() "," (++n) }' \
  >> "$OUT.verdicts.csv" &
FILTER_PID=$!

# RSS sampler: find the tlapm child of this shell (the pipeline head).
sleep 1
TPID=$(pgrep -P $$ -f "$(basename "$TLAPM")" | head -1)
[ -z "$TPID" ] && TPID=$(pgrep -f "$(basename "$TLAPM").*$(basename "$SPEC")" | head -1)
while [ -n "$TPID" ] && kill -0 "$TPID" 2> /dev/null; do
    RSS=$(( $(ps -o rss= -p "$TPID" 2>/dev/null || echo 0) / 1024 ))
    echo "$(date +%s),$RSS" >> "$OUT.rss.csv"
    sleep "$INT"
done

wait $FILTER_PID
V=$(( $(wc -l < "$OUT.verdicts.csv") - 1 ))
echo "done verdicts=$V out=$OUT.{verdicts,rss}.csv" >&2
