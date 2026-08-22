set -u
S=/tmp/claude-0/-home-user-tlapm/954b272f-8ed7-5c32-a993-10a52d548a51/scratchpad
W=$S/vwt; OUT=$S/keystroke10.csv
export PATH=/opt/isabelle/bin:$PATH; eval $(opam env --switch=5.1.0 --set-switch) 2>/dev/null
BOOT=$(awk '/btime/{print $2}' /proc/stat)
SPEC=$S/lspwork/FfiGrpcTheorems_proofs.tla
# the pairs that decide whether ENABLED, the grammar memo and the editor pool survive
POINTS="c13:b70585f c14:ba1df8c c16:393164e c17:690a261 c18:9a08f81 c19:4e3ec9f"
[ -f $OUT ] || echo "boot,point,ref,idx,seconds" > $OUT
for p in $POINTS; do
  name=${p%%:*}; ref=${p##*:}
  grep -q ",$name,$ref,10," $OUT && { echo "skip $name"; continue; }
  git -C $W checkout -q --detach $ref || continue
  ( cd $W && dune build lsp src 2>/dev/null ) || continue
  bd=$W/_build/default/lib/tlapm/backends; mkdir -p $bd; rm -rf $bd/Isabelle; ln -s /opt/isabelle $bd/Isabelle
  out=$(timeout 1200 python3 $S/lsp_c0.py $W/_build/default/lsp/bin/tlapm_lsp.exe $SPEC 6053 10 2>/dev/null)
  echo "$out" | sed -n 's/^edit\([0-9]*\)->diag: \([0-9.]*\)s.*/\1 \2/p' | while read n v; do
    echo "$BOOT,$name,$ref,$n,$v" >> $OUT
  done
  echo "  [$name] $(echo "$out" | sed -n 's/^edit[0-9]*->diag: \([0-9.]*\)s.*/\1/p' | tr '\n' ' ')"
done
echo LSP10_DONE
