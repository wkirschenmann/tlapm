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

# RSS sampler. The pipeline head may be a wrapper chain (stdbuf, timeout)
# around the actual tlapm process, so a parent-pid lookup lands on a 1 MB
# wrapper; instead sample the LARGEST process whose command line carries
# the binary path — that is tlapm itself, never a wrapper.
sleep 1
while kill -0 $FILTER_PID 2> /dev/null; do
    RSS_KB=$(ps -eo rss,args | grep -F "$TLAPM" \
             | grep -vE "grep|stdbuf|timeout|monitor_run" \
             | awk '{print $1}' | sort -rn | head -1)
    [ -z "$RSS_KB" ] && RSS_KB=0
    echo "$(date +%s),$(( RSS_KB / 1024 ))" >> "$OUT.rss.csv"
    sleep "$INT"
done

wait $FILTER_PID
V=$(( $(wc -l < "$OUT.verdicts.csv") - 1 ))
echo "done verdicts=$V out=$OUT.{verdicts,rss}.csv" >&2
