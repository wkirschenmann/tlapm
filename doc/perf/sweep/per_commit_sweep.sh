#!/usr/bin/env bash
# Per-commit measurement sweep for a branch of single-subject commits.
#
# Builds one binary per commit and measures, on every corpus given:
#
#   gen   tlapm -N --nofp             parse, elaborate, generate obligations, stop
#   prep  tlapm --noproving --nofp    the whole per-obligation pipeline, no prover
#   peak  maximum resident set of the prep run
#
# Both metrics come from stock flags on a stock build: no probe, no patched
# binary, nothing the measured commits introduce.
#
# Absolute values are only comparable within one boot of one machine, so every
# row is stamped with /proc/stat btime and the readers filter on a single boot.
# Resume is keyed on (phase, boot, point, corpus): a restart costs the point
# that was in flight, not the pass.
#
# Usage:
#   WORKTREE=/path/to/scratch/worktree \
#   CORPORA="small:/path/Small.tla large:/path/Large.tla" \
#   BASE=<sha of the branch point> BRANCH=<branch> \
#   OUT=sweep.csv ./per_commit_sweep.sh
#
# The pass order is deliberate.  Synthetic corpora run first (cheap, and they
# give the whole curve early).  On the large corpora, gen runs for every point
# before any prep does, and prep then runs from the tip backwards: the points
# that do not complete are the baseline ones, so putting them last means an
# interrupted campaign still holds the informative half.

set -u
: "${WORKTREE:?set WORKTREE to a git worktree of the repository}"
: "${CORPORA:?set CORPORA to a list of name:path pairs}"
: "${BASE:?set BASE to the sha the branch starts from}"
: "${BRANCH:?set BRANCH to the branch to sweep}"
OUT=${OUT:-per_commit_sweep.csv}
GEN_TIMEOUT=${GEN_TIMEOUT:-600}
PREP_TIMEOUT=${PREP_TIMEOUT:-900}
ADDR_CAP_KB=${ADDR_CAP_KB:-12000000}     # ulimit -v: a run that exceeds this aborts
BOOT=$(awk '/btime/{print $2}' /proc/stat)

cd "$WORKTREE" || exit 1
# c00 is the branch point; c01.. are the branch commits in order; c00b re-measures
# the branch point at the end of the campaign, which is the drift the run carries.
POINTS="c00:$BASE"
i=0
for sha in $(git rev-list --reverse "$BASE..$BRANCH"); do
  i=$((i+1)); POINTS="$POINTS $(printf 'c%02d:%s' $i "$sha")"
done
POINTS="$POINTS c00b:$BASE"
REVERSED=$(for p in $POINTS; do echo "$p"; done | tac | tr '\n' ' ')

[ -f "$OUT" ] || echo "phase,boot,point,sha,corpus,gen_ms,gen_rc,prep_ms,prep_rc,peak_kb" > "$OUT"

measure () {   # $1 phase  $2 gen|prep|both  $3 points  $4.. corpora
  ph=$1; met=$2; pts=$3; shift 3; corpora="$*"
  for p in $pts; do
    name=${p%%:*}; sha=${p##*:}
    todo=0
    for cp in $corpora; do
      grep -q "^$ph,$BOOT,$name,$sha,${cp%%:*}," "$OUT" || todo=1
    done
    [ $todo -eq 0 ] && continue
    git -C "$WORKTREE" checkout -q --detach "$sha" || { echo "$name: checkout failed" >&2; continue; }
    ( cd "$WORKTREE" && dune build src ) || { echo "$name: build failed" >&2; continue; }
    bin=$WORKTREE/_build/default/src/tlapm.exe
    for cp in $corpora; do
      cn=${cp%%:*}; spec=${cp##*:}
      grep -q "^$ph,$BOOT,$name,$sha,$cn," "$OUT" && continue
      d=$(mktemp -d); gen=-2; grc=0; prep=-2; prc=0; peak=0
      if [ "$met" != prep ]; then
        t0=$(date +%s%N)
        ( cd "$(dirname "$spec")" && timeout "$GEN_TIMEOUT" "$bin" -N --nofp \
            --cache-dir "$d/gen" "$spec" ) >/dev/null 2>&1; grc=$?
        gen=$(( ($(date +%s%N)-t0)/1000000 ))
      fi
      if [ "$met" != gen ]; then
        t0=$(date +%s%N)
        ( ulimit -v "$ADDR_CAP_KB"; cd "$(dirname "$spec")" && \
          timeout "$PREP_TIMEOUT" /usr/bin/time -f "%M" -o "$d/peak" "$bin" \
            --noproving --nofp --cache-dir "$d/prep" "$spec" ) >/dev/null 2>&1; prc=$?
        prep=$(( ($(date +%s%N)-t0)/1000000 ))
        peak=$(tail -1 "$d/peak" 2>/dev/null)
        case "${peak:-}" in ''|*[!0-9]*) peak=0;; esac
      fi
      rm -rf "$d"
      echo "$ph,$BOOT,$name,$sha,$cn,$gen,$grc,$prep,$prc,$peak" >> "$OUT"
      echo "  [$ph] $name $cn gen=${gen}ms(rc$grc) prep=${prep}ms(rc$prc) peak=${peak}kB"
    done
  done
  echo "PHASE_${ph}_DONE"
}

SMALL="" ; LARGE=""
for cp in $CORPORA; do
  case "${cp%%:*}" in
    large*|priv*) LARGE="$LARGE $cp" ;;
    *)            SMALL="$SMALL $cp" ;;
  esac
done

[ -n "$SMALL" ] && measure A  both "$POINTS"   $SMALL
[ -n "$LARGE" ] && measure B0 gen  "$POINTS"   $LARGE
[ -n "$LARGE" ] && measure B1 prep "$REVERSED" $LARGE
echo SWEEP_DONE
