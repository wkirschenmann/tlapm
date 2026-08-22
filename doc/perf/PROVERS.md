# The prover stack these measurements were taken with, and how to get it

Every correctness gate in this branch's commit messages refers to the
`test/fast` suite run with the **full** stack.  Getting Isabelle in place changes
the result substantially, so it is worth doing before reviewing anything here:

| suite | without Isabelle | with Isabelle 2025 |
|---|---|---|
| `test/fast` | 40 of 48 | **47 of 48** |
| `dune runtest src` | green | green |
| `dune runtest lsp` | 23 of 23 | 23 of 23 |

Seven of the eight failures were Isabelle's absence.  The eighth,
`fast/fingerprint/FingerprintVariablesParameters_test.tla`, fails identically on
`main`: it expects 1 of 2 obligations to fail and gets 2 of 2, because Z3 4.8.9
does not prove `\E y : y # x` here.  That is a prover-version property of the
environment, not a regression — which is why the gate is *fail-set identical to
`main`'s* rather than a pass count.

## Installing it

`deps/isabelle/dune.mk` already pins everything: `Isabelle2025`, the download URL,
and the SHA-256 of the Linux bundle.  The dune rule builds it as part of the
default alias, which is why a plain `dune build src` — what one uses while
iterating — does not pull it in.  To install it once, outside the build tree:

```sh
curl -sSL -o Isabelle2025_linux.tar.gz \
  https://isabelle.in.tum.de/website-Isabelle2025/dist/Isabelle2025_linux.tar.gz
echo "3d1d66de371823fe31aa8ae66638f73575bac244f00b31aee1dcb62f38147c56 *Isabelle2025_linux.tar.gz" \
  | sha256sum -c -                       # the value from deps/isabelle/dune.mk
tar -xzf Isabelle2025_linux.tar.gz -C /opt && mv /opt/Isabelle2025 /opt/isabelle

cd /opt/isabelle
rm -rf contrib/e-3.1-1/src/lib contrib/ProofGeneral* doc heaps/*/HOL contrib/vscod*
awk 'END { print "src/TLA+" } { print }' etc/components > c && mv c etc/components
mkdir -p src/TLA+ && cp -a <tlapm>/isabelle/* src/TLA+/ && chmod -R u+w src/TLA+
./bin/isabelle build -o system_heaps -o document=false -b -v -d src/Pure Pure
./bin/isabelle build -o system_heaps -o document=false -b -c -v -d src/TLA+ TLA+
```

1.08 GB download, 1.5 GB on disk after pruning, and the two heaps build in about
half a minute on four cores.

## The part that is easy to get wrong

Putting `isabelle` on `PATH` is **not** enough, and it fails in a way that looks
like success: tlapm finds the executable, then invokes it with a session root
under its *own* backends directory —
`_build/default/lib/tlapm/backends/Isabelle/src/TLA+` — which does not exist
unless `deps/isabelle` was built in that tree.  The symptom is
`*** Bad session root directory: …` followed by ordinary "obligations failed"
errors, so the run looks like a proof failure rather than a missing backend.

For a tree built with `dune build src`, link the installation where tlapm looks:

```sh
ln -s /opt/isabelle <tree>/_build/default/lib/tlapm/backends/Isabelle
```

That is per build tree, and a rebuild of the backends directory can remove it.
