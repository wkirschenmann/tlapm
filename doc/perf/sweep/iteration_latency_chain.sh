set -u
S=/tmp/claude-0/-home-user-tlapm/954b272f-8ed7-5c32-a993-10a52d548a51/scratchpad
W=$S/vwt
OUT=$S/iterchain.csv
export PATH=/opt/isabelle/bin:$PATH
eval $(opam env --switch=5.1.0 --set-switch) 2>/dev/null
BOOT=$(awk '/btime/{print $2}' /proc/stat)
read LO HI NOBL < $S/iterchain/range.txt
POINTS="c00:4600b24 c05:a0ed498 c06:cb9ce43 c07:0e47a7e c09:be2cb6b c12:991239f c13:b70585f c14:ba1df8c c15:809b30e c16:393164e c17:690a261 c18:9a08f81 c19:4e3ec9f c20:fba0670 c21:3525625 c22:16becd8 c23:abf13ea c24:1d1b05a c25:2c2b318 c26:bd0ecd1 v1:perf-order-v1 v2:perf-order-v2 v3:perf-order-v3"
[ -f $OUT ] || echo "boot,point,ref,run,ms,rc,proved,failed,trivial" > $OUT
for p in $POINTS; do
  name=${p%%:*}; ref=${p##*:}
  grep -q ",$name,$ref,2," $OUT && { echo "skip $name"; continue; }
  grep -qE ",$name,$ref,1,[0-9]+,124," $OUT && { echo "skip $name (hit the ceiling; one run is the result)"; continue; }
  git -C $W checkout -q --detach $ref || continue
  ( cd $W && dune build src 2>/dev/null ) || { echo "$name BUILD FAILED"; continue; }
  bd=$W/_build/default/lib/tlapm/backends; mkdir -p $bd; rm -rf $bd/Isabelle; ln -s /opt/isabelle $bd/Isabelle
  b=$W/_build/default/src/tlapm.exe
  for r in 1 2; do
    d=$(mktemp -d); cp -r $S/iterchain/cache $d/c
    for f in $S/iterchain/*.tla; do case $(basename $f) in orig.tla|edited.tla) ;; *) cp $f $d/;; esac; done
    cp $S/iterchain/edited.tla $d/FfiGrpcTheorems_proofs.tla
    cd $d; t0=$(date +%s%N)
    timeout 1800 $b --toolbox $LO $HI --threads 4 --cache-dir $d/c FfiGrpcTheorems_proofs.tla > $d/o 2>&1; rc=$?
    ms=$(( ($(date +%s%N)-t0)/1000000 ))
    pv=$(grep -cE '^@!!status:proved' $d/o); fl=$(grep -cE '^@!!status:failed' $d/o); tv=$(grep -cE '^@!!status:trivial' $d/o)
    cd $W; rm -rf $d
    echo "$BOOT,$name,$ref,$r,$ms,$rc,$pv,$fl,$tv" >> $OUT
    echo "  [$name] run$r ${ms}ms rc=$rc proved=$pv failed=$fl trivial=$tv"
    [ $rc -eq 124 ] && break
  done
done
echo ITERCHAIN_DONE
