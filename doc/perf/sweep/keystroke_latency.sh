set -u
S=/tmp/claude-0/-home-user-tlapm/954b272f-8ed7-5c32-a993-10a52d548a51/scratchpad
W=$S/vwt; OUT=$S/keystroke.csv
export PATH=/opt/isabelle/bin:$PATH; eval $(opam env --switch=5.1.0 --set-switch) 2>/dev/null
BOOT=$(awk '/btime/{print $2}' /proc/stat)
SPEC=$S/lspwork/FfiGrpcTheorems_proofs.tla
POINTS="c00:4600b24 c05:a0ed498 c06:cb9ce43 c07:0e47a7e c09:be2cb6b c12:991239f c13:b70585f c14:ba1df8c c15:809b30e c16:393164e c17:690a261 c18:9a08f81 c19:4e3ec9f c20:fba0670 c21:3525625 c22:16becd8 c23:abf13ea c24:1d1b05a c25:2c2b318 c26:bd0ecd1"
[ -f $OUT ] || echo "boot,point,ref,kind,idx,seconds" > $OUT
for p in $POINTS; do
  name=${p%%:*}; ref=${p##*:}
  grep -q ",$name,$ref,edit,3," $OUT && { echo "skip $name"; continue; }
  git -C $W checkout -q --detach $ref || continue
  ( cd $W && dune build lsp src 2>/dev/null ) || { echo "$name BUILD FAILED"; continue; }
  bd=$W/_build/default/lib/tlapm/backends; mkdir -p $bd; rm -rf $bd/Isabelle; ln -s /opt/isabelle $bd/Isabelle
  out=$(timeout 1200 python3 $S/lsp_c0.py $W/_build/default/lsp/bin/tlapm_lsp.exe $SPEC 6053 3 2>/dev/null)
  o=$(echo "$out" | sed -n 's/^open->markers: \([0-9.]*\)s/\1/p')
  [ -n "$o" ] && echo "$BOOT,$name,$ref,open,0,$o" >> $OUT
  i=0
  echo "$out" | sed -n 's/^edit\([0-9]*\)->diag: \([0-9.]*\)s.*/\1 \2/p' | while read n v; do
    echo "$BOOT,$name,$ref,edit,$n,$v" >> $OUT
  done
  echo "  [$name] open=${o}s edits=$(echo "$out" | sed -n 's/^edit[0-9]*->diag: \([0-9.]*\)s.*/\1/p' | tr '\n' ' ')"
done
echo LSPSWEEP_DONE
