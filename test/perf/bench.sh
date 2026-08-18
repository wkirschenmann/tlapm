#!/bin/sh
# Measurement matrix M0-M3 (see README.md). Solver-free by construction.
#
# Usage: bench.sh <tlapm-bin> <outdir> <spec.tla> [<spec.tla> ...]
#
# Writes <outdir>/bench.csv with rows: spec,level,metric,value
# and keeps per-run --timing reports under <outdir>/.
#
# M4 (real solvers) is deliberately NOT here: it is run manually at
# milestones only (doc/perf/ANALYSIS.md section 6.5).

set -e

if [ $# -lt 3 ]; then
    echo "usage: $0 <tlapm-bin> <outdir> <spec.tla>..." >&2
    exit 2
fi

TLAPM="$1"; OUT="$2"; shift 2
mkdir -p "$OUT"
CSV="$OUT/bench.csv"
echo "spec,level,metric,value" > "$CSV"

REPEAT=${REPEAT:-3}
FINGERTIP_SAMPLES=${FINGERTIP_SAMPLES:-5}

now_ms() { date +%s%N | cut -c1-13; }

# median of the space-separated ms values in $1
median() {
    echo "$1" | tr ' ' '\n' | grep -v '^$' | sort -n | awk '
        { a[NR] = $1 } END { print (NR % 2) ? a[(NR+1)/2] : (a[NR/2]+a[NR/2+1])/2 }'
}

timed() { # timed <n> <cmd...> -> median wall ms on stdout
    n="$1"; shift
    samples=""
    i=0
    while [ "$i" -lt "$n" ]; do
        t0=$(now_ms)
        "$@" > /dev/null 2> /dev/null || true
        t1=$(now_ms)
        samples="$samples $((t1 - t0))"
        i=$((i + 1))
    done
    median "$samples"
}

for SPEC in "$@"; do
    name=$(basename "$SPEC" .tla)
    echo "== $name"

    # ---- M0: obligation count + context stats (fast, once) --------------
    log="$OUT/$name.m0.log"
    TLAPM_TRACE_DEFS=1 "$TLAPM" -N --toolbox 0 0 --nofp "$SPEC" \
        > /dev/null 2> "$log" || true
    count=$(grep '^@!!count:' "$log" | tail -1 | cut -d: -f2)
    echo "$name,M0,obligations,${count:-NA}" >> "$CSV"
    m0=$(timed "$REPEAT" "$TLAPM" -N --toolbox 0 0 --nofp "$SPEC")
    echo "$name,M0,wall_ms,$m0" >> "$CSV"

    # ---- M1: full prep pipeline, no solver ------------------------------
    m1=$(timed "$REPEAT" "$TLAPM" --toolbox 0 0 --printallobs --noproving \
                --nofp --threads 1 "$SPEC")
    echo "$name,M1,wall_ms,$m1" >> "$CSV"
    # keep one --timing report
    "$TLAPM" --toolbox 0 0 --printallobs --noproving --nofp --threads 1 \
             --timing "$SPEC" > "$OUT/$name.m1.timing" 2>&1 || true

    # ---- M3: max RSS of an M1 run ---------------------------------------
    if command -v /usr/bin/time > /dev/null 2>&1; then
        /usr/bin/time -v "$TLAPM" --toolbox 0 0 --printallobs --noproving \
            --nofp --threads 1 "$SPEC" > /dev/null 2> "$OUT/$name.m3.time" \
            || true
        rss=$(grep 'Maximum resident set size' "$OUT/$name.m3.time" \
              | awk '{print $NF}')
        echo "$name,M3,max_rss_kb,${rss:-NA}" >> "$CSV"
    fi

    # ---- M2: fingertip latency at sampled obligation lines --------------
    # Sample obligation start lines evenly from the M0 dump.
    lines=$("$TLAPM" --toolbox 0 0 -N --nofp "$SPEC" 2>&1 \
            | grep '^@!!loc:' | cut -d: -f2 | sort -n | uniq \
            | awk -v n="$FINGERTIP_SAMPLES" \
                  'NR==1{first=$0} {a[NR]=$0}
                   END{ if (NR==0) exit;
                        step = (NR<n) ? 1 : int(NR/n);
                        for (i=1; i<=NR && cnt<n; i+=step) {print a[i]; cnt++} }')
    total=""
    for L in $lines; do
        t=$(timed 1 "$TLAPM" --toolbox "$L" "$L" --noproving --printallobs \
                   --nofp --threads 1 "$SPEC")
        total="$total $t"
        echo "$name,M2,fingertip_line_${L}_ms,$t" >> "$CSV"
    done
    if [ -n "$total" ]; then
        echo "$name,M2,fingertip_median_ms,$(median "$total")" >> "$CSV"
    fi
done

echo "wrote $CSV"
