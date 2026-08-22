set -u
S=/tmp/claude-0/-home-user-tlapm/954b272f-8ed7-5c32-a993-10a52d548a51/scratchpad
W=$S/vwt
OUT=$S/variants.csv
eval $(opam env --switch=5.1.0 --set-switch) 2>/dev/null
P=/home/user/tlapm/_perf
BOOT=$(awk '/btime/{print $2}' /proc/stat)
CORPORA="synth300:$P/Synth_L300_S5_D50_C3.tla synth100:$P/Synth_L100_S5_D50_C3.tla ffi:$P/abstractgrpc/FfiGrpcTheorems_proofs.tla mono:$P/oom_repro/timer_wheel_l1_mono.tla"
POINTS="v1:perf-order-v1 v2:perf-order-v2 v3:perf-order-v3"
[ -f $OUT ] || echo "boot,point,ref,corpus,gen_ms,gen_rc,prep_ms,prep_rc,peak_kb,obl_total,obl_done_300s" > $OUT
for p in $POINTS; do
  name=${p%%:*}; ref=${p##*:}
  git -C $W checkout -q --detach $ref || { echo "$name checkout failed"; continue; }
  ( cd $W && dune build src 2>/dev/null ) || { echo "$name BUILD FAILED"; continue; }
  b=$W/_build/default/src/tlapm.exe
  for cp in $CORPORA; do
    cn=${cp%%:*}; spec=${cp##*:}
    grep -q ",$name,$ref,$cn," $OUT && { echo "  skip $name/$cn"; continue; }
    cd $(dirname $spec); d=$(mktemp -d)
    t0=$(date +%s%N)
    timeout 600 $b -N --nofp --cache-dir $d/g $spec >/dev/null 2>&1; grc=$?
    gen=$(( ($(date +%s%N)-t0)/1000000 ))
    t2=$(date +%s%N)
    ( ulimit -v 12000000; timeout 900 /usr/bin/time -f "%M" -o $d/r $b --noproving --nofp --cache-dir $d/q $spec >/dev/null 2>&1 ); prc=$?
    prep=$(( ($(date +%s%N)-t2)/1000000 ))
    peak=$(tail -1 $d/r 2>/dev/null); case "${peak:-}" in ''|*[!0-9]*) peak=0;; esac
    rm -rf $d; cd $W
    echo "$BOOT,$name,$ref,$cn,$gen,$grc,$prep,$prc,$peak,0,0" >> $OUT
    echo "  [$name] $cn gen=${gen}ms prep=${prep}ms(rc$prc) peak=${peak}kB"
  done
done
echo VARIANTS_DONE
