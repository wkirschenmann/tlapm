#!/usr/bin/env bash
# keystroke -> diagnostics, measured at the LSP protocol boundary:
# didChange sent, publishDiagnostics received.  N edits per point.
set -u
# Set WORK to a scratch directory (worktree, cached binaries, CSVs) and
# CORPUS to the directory holding the .tla corpora.  Both default to values
# that suit a checkout of this repository.
WORK=${WORK:-"$(git rev-parse --show-toplevel)/_perf/short-campaign"}
CORPUS=${CORPUS:-"$(git rev-parse --show-toplevel)/_perf"}
mkdir -p "$WORK"
S=$WORK
W=$S/shortwt; OUT=$S/short_keystroke.csv
NRUN=${NRUN:-3}
export PATH=/opt/isabelle/bin:$PATH
eval $(opam env --switch=5.1.0 --set-switch) 2>/dev/null
BOOT=$(awk '/btime/{print $2}' /proc/stat)
SPEC=$S/lspwork/FfiGrpcTheorems_proofs.tla
PTS=${PTS:-"p00 p05 p06 p07 p08 p09 p10 p11 p12 p13 p14 p15 p16 p17"}
ALL="p00:$(git rev-parse main) $(i=0; for s in $(git rev-list --reverse main..tlapm-perf-short); do i=$((i+1)); printf 'p%02d:%s ' $i $s; done)"
[ -f $OUT ] || echo "boot,point,sha,kind,idx,seconds,n" > $OUT
for q in $PTS; do
  for p in $ALL; do [ "${p%%:*}" = "$q" ] && { n=$q; sha=${p##*:}; }; done
  grep -q ",$n,$sha,edit,$((NRUN-1)),.*,$NRUN$" $OUT && { echo "skip $n"; continue; }
  git -C $W checkout -q --detach $sha || continue
  ( cd $W && dune build lsp src 2>$S/ks_$n.log ) || { echo "$n BUILD FAILED"; continue; }
  bd=$W/_build/default/lib/tlapm/backends; mkdir -p $bd; rm -rf $bd/Isabelle 2>/dev/null
  ln -s /opt/isabelle $bd/Isabelle 2>/dev/null
  out=$(timeout 2400 python3 "$(git rev-parse --show-toplevel)/doc/perf/short/harness/lsp_keystroke_client.py" $W/_build/default/lsp/bin/tlapm_lsp.exe $SPEC 6053 $NRUN 2>/dev/null)
  o=$(echo "$out" | sed -n 's/^open->markers: \([0-9.]*\)s/\1/p')
  [ -n "$o" ] && echo "$BOOT,$n,$sha,open,0,$o,$NRUN" >> $OUT
  echo "$out" | sed -n 's/^edit\([0-9]*\)->diag: \([0-9.]*\)s.*/\1 \2/p' | while read i v; do
    echo "$BOOT,$n,$sha,edit,$i,$v,$NRUN" >> $OUT
  done
  echo "  [ks] $n open=${o}s edits=$(echo "$out" | sed -n 's/^edit[0-9]*->diag: \([0-9.]*\)s.*/\1/p' | tr '\n' ' ')"
done
echo KEYSTROKE_DONE
