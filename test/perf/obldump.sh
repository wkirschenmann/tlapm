#!/bin/sh
# Golden obligation dumps for the subset-invariant checker.
#
# Usage: obldump.sh <tlapm-bin> <spec.tla> <outdir> [extra tlapm args...]
#
# Runs one solver-free tlapm invocation and splits the @!! toolbox stream:
#   <outdir>/generated.txt  "to be proved" blocks = the obligation set,
#                           emitted before any preparation
#   <outdir>/shipped.txt    "normalized" blocks = the material that would be
#                           sent to the backends (post expansion)
#   <outdir>/raw.log        full stderr, for debugging
#
# --printallobs is load-bearing: it forces the normalization lazy that
# --noproving alone would skip (src/backend/prep.ml:1418-1431).
# --nofp keeps the run independent of any .tlacache fingerprint state.
# --threads 1 keeps the stream ordering deterministic.

set -e

if [ $# -lt 3 ]; then
    echo "usage: $0 <tlapm-bin> <spec.tla> <outdir> [extra tlapm args...]" >&2
    exit 2
fi

TLAPM="$1"; SPEC="$2"; OUT="$3"; shift 3
mkdir -p "$OUT"

"$TLAPM" --toolbox 0 0 --printallobs --noproving --nofp --threads 1 \
         "$@" "$SPEC" 2> "$OUT/raw.log" > /dev/null || {
    echo "tlapm exited non-zero; see $OUT/raw.log" >&2
    # keep going: a partial dump is still useful for diagnosis
}

# Split @!! blocks by status, normalize volatile fields, key by loc.
awk -v gen="$OUT/generated.txt" -v shp="$OUT/shipped.txt" '
    /^@!!BEGIN/    { block = ""; keep = 1; status = ""; next }
    /^@!!END/      {
        if (status == "to be proved") printf "%s@!!END\n\n", block >> gen;
        else if (status == "normalized") printf "%s@!!END\n\n", block >> shp;
        next
    }
    /^@!!time-used:/ { next }             # volatile
    /^@!!id:/        { next }             # renumbered by range; key on loc
    /^@!!status:/    { status = substr($0, 11) }
    { block = block $0 "\n" }
' "$OUT/raw.log"

touch "$OUT/generated.txt" "$OUT/shipped.txt"
gen_n=$(grep -c '^@!!type:obligation' "$OUT/generated.txt" || true)
shp_n=$(grep -c '^@!!type:obligation' "$OUT/shipped.txt" || true)
echo "generated=$gen_n shipped=$shp_n out=$OUT"
