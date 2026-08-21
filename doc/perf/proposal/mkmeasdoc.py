# -*- coding: utf-8 -*-
"""From commit_sweep.csv, emit (a) the PR-level D list for mkcharts.py and
(b) doc/perf/PER_COMMIT_SWEEP.md — every commit, every corpus, every metric."""
import os, csv, os, collections

S = os.environ.get("SWEEP_DIR", os.path.dirname(os.path.abspath(__file__)))
import sweeplib
_m, BOOT = sweeplib.load()
rows = collections.defaultdict(dict)
for k, v in _m.items():
    if k == "_spread": continue
    pt, cp = k
    rows[pt][cp] = v

ORDER = ["c%02d" % i for i in range(27)]
SUBJ = {
 "c00": ("main", "base of the branch (tlaplus/tlapm master)"),
 "c01": ("445c619", "util/timing: make clock accounting nestable"),
 "c02": ("e71feaf", "util/timing: host the named pipeline clocks"),
 "c03": ("023f200", "timing: attribute generation, fingerprinting and fp saving to their clocks"),
 "c04": ("4901a02", "backend/schedule: reap finished provers early; refresh deadline clock"),
 "c05": ("a0ed498", "fix: kill timed-out provers with SIGTERM, not SIGHUP"),
 "c06": ("cb9ce43", "util/Deque: cheaper nth, first_n and equal on rear-heavy deques"),
 "c07": ("0e47a7e", "backend/prep: expand visible definitions in a single pass"),
 "c08": ("dc37462", "backend/prep: prune hidden definitions unreachable from the goal"),
 "c09": ("be2cb6b", "backend/prep: prune unreferenced hidden facts from obligation contexts"),
 "c10": ("0a00f77", "backend/prep: reuse preparation work across obligations sharing a context prefix"),
 "c11": ("a5158d1", "backend/prep: prefix-resume cache for Elab.normalize"),
 "c12": ("991239f", "backend/prep: differential oracle for the normalize cache"),
 "c13": ("b70585f", "backend/schedule: pull tasks from a stream instead of a materialized list"),
 "c14": ("ba1df8c", "module/Elab: make ENABLED-axioms detection linear in context size"),
 "c15": ("809b30e", "expr/Levels: resolve de Bruijn reference levels without slicing the context"),
 "c16": ("393164e", "backend/toolbox: single-pass definition expansion in the result printer"),
 "c17": ("690a261", "expr/parser: memoize the two instances of each grammar rule"),
 "c18": ("9a08f81", "util/property: monomorphic pid equality, loop-based lookups"),
 "c19": ("4e3ec9f", "lsp: replace the per-step RangeMap.partition by a sorted obligation pool"),
 "c20": ("fba0670", "Ctx: logarithmic index lookup"),
 "c21": ("3525625", "backend/Smtlib: compile identifier-escaping regexes once"),
 "c22": ("16becd8", "expr/Subst: walk substitution spines in app_ix without allocating"),
 "c23": ("abf13ea", "backend+encode: skip identity rebuilds when flattening extracts nothing"),
 "c24": ("1d1b05a", "backend/prep: emit obligation comments into solver files only when kept"),
 "c25": ("2c2b318", "expr/Levels: stop the level cache pinning one context per obligation"),
 "c26": ("bd0ecd1", "expr/Constness: constant-time De Bruijn resolution in add_constness"),
}
CORPORA = [("synth300", "public synthetic, 1 800 obligations"),
           ("synth100", "public synthetic, 600 obligations"),
           ("tiny",     "public synthetic, 71 obligations"),
           ("ffi",      "private refinement chain, 9 967 obligations"),
           ("mono",     "private 30k monolith, 29 965 obligations")]
# PR endpoints, in branch order
PRS = [("main","c00"),("fixes","c05"),("deque","c06"),("expand","c07"),("prune","c09"),
       ("cache","c12"),("stream","c13"),("enabled","c14"),("levels","c15"),("printer","c16"),
       ("parser","c17"),("props","c18"),("lsp","c19"),("ctx","c20"),("smtlib","c21"),
       ("app_ix","c22"),("flatten","c23"),("comments","c24"),("levcache","c25"),("const","c26")]

def g(pt, cp, field):
    if pt == "c00": pt = "c00_first"     # raw first run, not the mean used by the charts
    r = rows.get(pt, {}).get(cp)
    if not r: return None, None
    if field not in r: return None, None
    return r[field], r["m0_rc" if field == "m0_ms" else "m1_rc"]

def s_ms(pt, cp, field):
    v, rc = g(pt, cp, field)
    if v is None: return "—"
    if rc == 124: return "> %d s" % round(v/1000)
    if rc != 0 and field == "m1_ms": return "aborted"
    if v >= 10000: return "%.1f s" % (v/1000.0)
    if v >= 1000: return "%.2f s" % (v/1000.0)
    return "%d ms" % v

def s_mb(pt, cp):
    if pt == "c00": pt = "c00_first"
    r = rows.get(pt, {}).get(cp)
    if not r: return "—"
    kb = r.get("rss_kb") or 0
    if kb == 0: return "—"
    mb = kb/1024.0
    return "%.2f GB" % (mb/1024.0) if mb >= 1024 else "%d MB" % round(mb)

# ---- (a) D list for mkcharts.py
print("D = [")
for lab, pt in PRS:
    m0, _ = g(pt, "synth300", "m0_ms"); m1, _ = g(pt, "synth300", "m1_ms")
    r = rows.get(pt, {}).get("synth300"); s1, _ = g(pt, "synth100", "m1_ms")
    rss = (r or {}).get("rss_kb") or 0
    print(' ("%s",%s%d,%s%d,%s%d,%s%d),' % (lab, " "*(11-len(lab)), m0 or 0, " "*2, m1 or 0,
                                            " "*2, rss, " "*2, s1 or 0))
print("]")

# ---- (b) markdown
md = []
md.append("# Per-commit measurement sweep, `tlapm-performance-upstream-proposal`\n")
md.append("""One binary per commit, built from that commit alone, measured on five corpora.

  * `gen` is `tlapm -N --nofp` — parse, elaborate, generate obligations, stop.
  * `prep` is `tlapm --noproving --nofp` — the whole per-obligation pipeline with
    no prover launched, so the figure is prover-independent.
  * `peak` is the maximum resident set of the `prep` run, from `/usr/bin/time -f %%M`.

One run per cell, each taken immediately after that commit's own build.  `> 900 s`
means the run was stopped at the fifteen-minute ceiling; `aborted` means it hit the
12 GB address-space cap the runs are made under (`ulimit -v 12000000`), and there
the peak *is* the failure.  `main` appears twice, as `c00` at the start of the
campaign and `c00b` at the end, which is the drift the campaign carries.

The whole campaign is **one boot of one container** — absolute values are not
comparable across restarts, so every row in the raw CSV is stamped with the boot
it was measured on, and this table contains rows from boot `%s` only.

Machine: Intel Xeon @ 2.80 GHz, 4 cores, 16 GB, Linux 6.18.44, OCaml 5.1.0 switch.

Three corpora are the public synthetic family, reproducible from the generator.
Two are private specifications: only these aggregate figures are published, and no
specification content appears here or anywhere in the repository.\n""" % BOOT)
# campaign status: which (point, corpus) prep cells exist yet
_pend = []
for cp, _ in CORPORA:
    miss = [pt for pt in ORDER if "m1_ms" not in rows.get(pt, {}).get(cp, {})]
    if miss:
        _pend.append("%s: %s" % (cp, ", ".join(miss)))
if _pend:
    md.append("\n> **This campaign is still running.**  `prep` and `peak` cells shown as\n"
              "> `—` have not been measured yet; nothing here is filled in from another\n"
              "> boot or from an earlier campaign.  Outstanding:\n>\n"
              + "\n".join("> * %s" % x for x in _pend) + "\n")
else:
    md.append("\nCampaign complete: every point measured on every corpus, one boot.\n")

for cp, cname in CORPORA:
    md.append("\n## %s\n" % cname)
    md.append("| point | commit | gen | prep | peak |")
    md.append("|---|---|---:|---:|---:|")
    for pt in ORDER:
        sha, subj = SUBJ[pt]
        md.append("| %s | `%s` %s | %s | %s | %s |" %
                  (pt, sha, subj, s_ms(pt, cp, "m0_ms"), s_ms(pt, cp, "m1_ms"), s_mb(pt, cp)))
    if "c00b" in rows:
        md.append("| c00b | `main` re-measured at the end of the campaign (drift check) | %s | %s | %s |" %
                  (s_ms("c00b", cp, "m0_ms"), s_ms("c00b", cp, "m1_ms"), s_mb("c00b", cp)))
out = os.environ.get("SWEEP_MD", os.path.join(S, "PER_COMMIT_SWEEP.md"))
open(out, "w").write("\n".join(md) + "\n")
print("\nwrote", out)
