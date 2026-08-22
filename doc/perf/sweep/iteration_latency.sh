set -u
S=/tmp/claude-0/-home-user-tlapm/954b272f-8ed7-5c32-a993-10a52d548a51/scratchpad
W=$S/vwt
OUT=$S/iterlat.csv
eval $(opam env --switch=5.1.0 --set-switch) 2>/dev/null
BOOT=$(awk '/btime/{print $2}' /proc/stat)
POINTS="c00:4600b24 c05:a0ed498 c06:cb9ce43 c07:0e47a7e c09:be2cb6b c12:991239f c13:b70585f c14:ba1df8c c15:809b30e c16:393164e c17:690a261 c18:9a08f81 c19:4e3ec9f c20:fba0670 c21:3525625 c22:16becd8 c23:abf13ea c24:1d1b05a c25:2c2b318 c26:bd0ecd1 v1:perf-order-v1 v2:perf-order-v2 v3:perf-order-v3"
[ -f $OUT ] || echo "boot,point,ref,run,ms,rc,reproved" > $OUT
for p in $POINTS; do
  name=${p%%:*}; ref=${p##*:}
  grep -q ",$name,$ref,3," $OUT && { echo "skip $name"; continue; }
  git -C $W checkout -q --detach $ref || continue
  ( cd $W && dune build src 2>/dev/null ) || { echo "$name BUILD FAILED"; continue; }
  b=$W/_build/default/src/tlapm.exe
  for r in 1 2 3; do
    d=$(mktemp -d); cp -r $S/iter/cache $d/c; cp $S/iter/edited.tla $d/Synth_L300_S5_D50_C3.tla
    cd $d
    t0=$(date +%s%N)
    timeout 900 $b --toolbox 0 0 --threads 4 --cache-dir $d/c Synth_L300_S5_D50_C3.tla > $d/out 2>&1; rc=$?
    ms=$(( ($(date +%s%N)-t0)/1000000 ))
    rp=$(grep -cE '^@!!status:(proved|failed|being proved)' $d/out || true)
    cd $W; rm -rf $d
    echo "$BOOT,$name,$ref,$r,$ms,$rc,$rp" >> $OUT
    echo "  [$name] run$r ${ms}ms rc=$rc reproved=$rp"
  done
done
echo ITERLAT_DONE
