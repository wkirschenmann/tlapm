# -*- coding: utf-8 -*-
"""Generate section 06 of the proposal from the branch descriptors + commit_sweep.csv."""
import os, csv, os, html, re, sys

S = os.environ.get("SWEEP_DIR", os.path.dirname(os.path.abspath(__file__)))
SWEEP = os.environ.get("SWEEP_CSV", os.path.join(S, "commit_sweep.csv"))

CORPORA = [("synth300", "medium synthetic — 1 800 obligations"),
           ("synth100", "small synthetic — 600 obligations"),
           ("ffi",      "refinement chain — 9 967 obligations"),
           ("mono",     "30k monolith — 29 965 obligations")]

# point id -> sha, in branch order.  c00 is main.
ORDER = ["c00","c01","c02","c03","c04","c05","c06","c07","c08","c09","c10","c11","c12",
         "c13","c14","c15","c16","c17","c18","c19","c20","c21","c22","c23","c24","c25","c26"]

import sweeplib, subprocess

REPO = os.environ.get("TLAPM_REPO", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
def numstat(sha):
    """[(path, added, removed)] for one commit, in the order git reports"""
    out = subprocess.check_output(
        ["git", "-C", REPO, "show", "--numstat", "--format=", sha], text=True)
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        a, r, path = line.split("\t")
        rows.append((path, int(a), int(r)))
    return rows

def files_line(sha):
    rows = numstat(sha)
    tot_a = sum(a for _, a, _ in rows); tot_r = sum(r for _, _, r in rows)
    parts = ['<code>%s</code>&nbsp;<span class="pm">+%d/&minus;%d</span>' % (pa, a, r)
             for pa, a, r in rows]
    head = "%d file%s, +%d/&minus;%d" % (len(rows), "" if len(rows) == 1 else "s", tot_a, tot_r)
    return '<span class="fl-h">%s</span> %s' % (head, " ".join(parts))
DATA, BOOT = sweeplib.load()
def _get(pt, cp):
    return DATA.get((pt, cp))


def cell(pt_before, pt_after, corpus, field):
    """'before -> after (xk)' for one metric, or an em dash when not measured."""
    a = _get(pt_before, corpus); b = _get(pt_after, corpus)
    if not a or not b: return "&mdash;"
    def val(row):
        if field not in row: return None, "&mdash;"
        rc = row["m0_rc" if field == "m0_ms" else "m1_rc"]
        ms = row[field]
        if rc == 124:
            return None, "&gt; %d s" % round(ms/1000)
        if rc != 0 and field == "m1_ms":
            return None, "aborted"
        if field == "rss_kb":
            v = row["rss_kb"]
            return (v, fmt_mb(v)) if v else (None, "&mdash;")
        return ms, fmt_ms(ms)
    va, sa = val(a); vb, sb = val(b)
    if sa == "&mdash;" and sb == "&mdash;": return "&mdash;"
    if sa == "&mdash;" or sb == "&mdash;": return "not measured"
    if va and vb:
        ratio = va / vb
        if ratio >= 1.03:
            r = "%.1f" % ratio if ratio >= 10 else "%.2f" % ratio
            tail = " <span class=\"r\">&times;%s</span>" % r
        elif ratio <= 0.97:
            tail = " <span class=\"w\">+%d&thinsp;%%</span>" % round((1/ratio - 1) * 100)
        else:
            tail = ""
        return "%s &rarr; %s%s" % (sa, sb, tail)
    return "%s &rarr; %s" % (sa, sb)

def fmt_ms(ms):
    if ms >= 10000: return "%.1f s" % (ms/1000.0)
    if ms >= 1000:  return "%.2f s" % (ms/1000.0)
    return "%d ms" % ms

def fmt_mb(kb):
    mb = kb/1024.0
    if mb >= 1024: return "%.2f GB" % (mb/1024.0)
    return "%d MB" % round(mb)

# ---------------------------------------------------------------- descriptors
# each PR: n, title, tag, files, motivation, commits[(point, sha, subject, what, gate, guard, model)]
PRS = [
 dict(n="0", title="The five bugfixes", tag=("t-fix","bugfix"),
   files=["src/util/timing.ml{,i}","src/tlapm_lib.ml","src/backend/prep.ml","src/backend/fpfile.ml","src/backend/schedule.ml","src/system.ml"],
   motive="""Two of these are correctness bugs with performance consequences, three repair the
   instrument every later pull request is argued with. They are grouped because the decision to take
   them is of a different kind: none of them is an optimization, and a maintainer should be able to
   merge the group without having read anything else here.""",
   commits=[
    dict(pt="c01", sha="445c619", subject="util/timing: make clock accounting nestable",
      what="""A clocked region nested inside another was charged to the innermost clock that
      happened to be running, and the outer region's remainder fell into <code>other</code>.
      <code>store_module</code> is clocked as <em>analysis</em> from inside the <em>simplification</em>
      region, so on <code>main</code> every large run mis-attributes its two biggest phases.
      Keep a stack; on push, suspend the enclosing clock; on pop, resume it.""",
      gate="Both suites green; the phase table's <em>total</em> row is unchanged and the sum of the rows now equals it.",
      model="Fable 5"),
    dict(pt="c02", sha="e71feaf", subject="util/timing: host the named pipeline clocks",
      what="""The named clocks lived in <code>Backend</code>, which cannot be referenced from
      <code>Util</code>; moving them into <code>Util.Timing</code> is what lets the next commit start
      them where the work happens.""",
      gate="Both suites green; no behaviour change (a move plus one new accessor).",
      model="Fable 5"),
    dict(pt="c03", sha="023f200", subject="timing: attribute generation, fingerprinting and fp saving to their clocks",
      what="""Three clocks — <code>generation</code>, <code>fp_compute</code>, <code>fp_saving</code> —
      are declared and printed by <code>--timing</code> on <code>main</code> but never started, so they
      read <code>0.000000</code> on every run. Start and stop them at the three sites that do the work.""",
      gate="Both suites green; the three rows become non-zero and <em>total</em> is unchanged, so nothing was double-counted.",
      model="Fable 5"),
    dict(pt="c04", sha="4901a02", subject="backend/schedule: reap finished provers early; refresh deadline clock",
      what="""The scheduler computed its <code>select</code> deadline once and then blocked on it even
      when children had already exited, so a finished prover's slot stayed occupied until the deadline
      elapsed. Reap non-blocking before each wait and recompute the deadline from the live set.""",
      gate="""Verdict parity on a real prover run: the set of timed-out obligations may only lose
      members, never gain them, and no obligation changes verdict.""",
      model="Fable 5"),
    dict(pt="c05", sha="a0ed498", subject="fix: kill timed-out provers with SIGTERM, not SIGHUP",
      what="""<code>System.unix_kill</code> sent signal 1. A process started with <code>nohup</code>,
      or from any launcher that sets SIGHUP to <code>SIG_IGN</code>, inherits that disposition through
      both <code>fork</code> and <code>exec</code> — so the prover ignores the kill and the timeout
      silently stops working. Send SIGTERM.""",
      gate="""Reproduced before the fix and absent after: the same module under <code>nohup</code>,
      with <code>ps</code> sampling the child set and <code>/usr/bin/time -v</code> the peak RSS.
      On <code>main</code> the run takes 725 s against 285 s in the foreground and leaks live provers;
      after the fix the two agree.""",
      model="Opus 5"),
   ]),

 dict(n="1", title="Deque lookups on rear-heavy deques", tag=("t-lat","latency"),
   files=["src/util/deque.ml{,i}"],
   motive="""Contexts are built with <code>snoc</code>, so their elements live reversed in the rear
   list, and <code>nth</code> popped elements through <code>front</code> — reversing the whole rear
   into fresh cells on first use. That is an O(size) allocation per context lookup, on the single
   hottest read in the compiler.""",
   commits=[
    dict(pt="c06", sha="cb9ce43", subject="util/Deque: cheaper nth, first_n and equal on rear-heavy deques",
      what="""<code>nth</code> indexes the two underlying lists directly, with the same
      <code>None</code>/<code>Failure</code> behaviour; <code>first_n</code> shares structure with its
      input instead of re-consing the prefix; <code>equal</code> short-circuits on physical equality,
      which its main caller (the expression-level cache) hits by comparing a deque with itself.""",
      gate="Output-preserving: obligation stream identical, both suites green, known-failing set unchanged.",
      model="Fable 5"),
   ]),

 dict(n="2", title="Expand visible definitions in a single pass", tag=("t-thr","throughput"),
   files=["src/backend/prep.ml"],
   motive="""<code>expand_defs</code> walked the definition list and applied one substitution per
   definition, rebuilding the whole sequent each time: &Theta;(k&middot;D) work per obligation for
   k definitions over a context of D entries. Compose the substitutions front-to-back and apply once.""",
   commits=[
    dict(pt="c07", sha="0e47a7e", subject="backend/prep: expand visible definitions in a single pass",
      what="""One fold builds the composed substitution in definition order; a single application
      replaces the k applications. Same order, so the same fixpoint.""",
      gate="""Output-preserving and verified as such, but it is a rewrite of a substitution
      composition: the obligation stream is compared on the synthetic family and on both private
      specifications, not only on the test suite.""",
      guard="""None on the branch, and this is the one output-preserving change where we would
      argue for one anyway: the iterated formulation is gone from the file, so a future
      &ldquo;the prover sees something different&rdquo; report has no bisection tool.
      <code>--debug oldexpand</code>, kept for one release, would also make this pull request's own
      A/B observable inside a single binary.""",
      model="Fable 5"),
   ]),

 dict(n="3", title="Prune the hidden context", tag=("t-thr","throughput"),
   files=["src/backend/prep.ml"],
   motive="""After expansion, an obligation's context still carries every hidden definition and every
   instantiated theorem statement in scope, whether or not the goal can reach them. These are the two
   commits on the branch that change what the provers receive — everything else is byte-identical.""",
   commits=[
    dict(pt="c08", sha="dc37462", subject="backend/prep: prune hidden definitions unreachable from the goal",
      what="""A marking pass from the goal and the visible facts computes the reachable set over the
      hidden definitions; unreachable slots are replaced by <code>Opaque \"__pruned__\"</code>, which
      makes a reachability mistake fail loudly at encoding time rather than silently changing a
      verdict. Runs after expansion, normalisation and the triviality check, and after the fingerprint
      is computed — so fingerprints and the <code>--printallobs</code> dump are unchanged by
      construction.""",
      gate="""Subset, not identity. The generated obligation stream is identical; the shipped form is
      checked on the solver input files, keyed by their <code>;; Generated from file &hellip;</code>
      line, with <code>diff -ru before/ after/ | grep '^+[^+]'</code> required to be empty. Plus
      verdict parity at the locus level on a real prover run.""",
      guard="""None on the branch. Our recommendation to the maintainers is that one should land
      <em>with</em> these two commits rather than after the first bug report:
      <code>--prune-context=none|defs|defs+facts</code>, or the cheaper <code>--debug noprune</code>.
      Since no stock output prints what the solvers receive, that switch is the only way a user can
      bisect a prune-related failure.""",
      model="Fable 5"),
    dict(pt="c09", sha="be2cb6b", subject="backend/prep: prune unreferenced hidden facts from obligation contexts",
      what="""Extends the same marking pass to hidden <em>facts</em> — the instantiated theorem
      statements, which are the bulk of the context on refinement-heavy specifications. Same slot
      replacement, same self-check. Must land after the previous commit: same function, same pass.""",
      gate="""Same subset protocol. On the arm pair covering both commits: <strong>4 200 deleted
      lines, 0 added</strong> across 11 paired solver inputs, and 5 664 of 7 509 hypothesis slots
      (75.4 %) removed on the sampled range with identical verdicts.""",
      model="Fable 5"),
   ]),

 dict(n="4", title="Prefix-resume caches", tag=("t-thr","throughput"),
   files=["src/backend/prep.ml","src/expr.mli","src/expr/e_elab.ml{,i}"],
   motive="""Consecutive obligations share almost their whole context: median 743 hypotheses of which
   699 are <em>physically</em> the same objects as the previous obligation's, with a median divergent
   tail of one. Preparation nevertheless redid the full context from scratch every time.""",
   commits=[
    dict(pt="c10", sha="0a00f77", subject="backend/prep: reuse preparation work across obligations sharing a context prefix",
      what="""Keep the previous obligation's context and the folds' intermediate states; on the next
      obligation, walk forward while the entries are physically equal and resume the
      <code>find_meth</code>, <code>add_constness</code> and <code>expand_defs</code> folds from the
      divergence point. Physical equality only — no structural comparison, so a false negative costs
      one full fold and a false positive is impossible.""",
      gate="""Output-preserving, and the guard makes it self-checking: the same binary with and
      without <code>--debug noprepcache</code> must produce the identical obligation stream. Both
      suites green.""",
      guard="<code>--debug noprepcache</code> restores the uncached path for all three folds. Caches on by default.",
      model="Opus 5"),
    dict(pt="c11", sha="a5158d1", subject="backend/prep: prefix-resume cache for Elab.normalize",
      what="""The same prefix idea for <code>Expr.Elab.normalize</code>, which is the single most
      expensive per-obligation pass: normalise the divergent tail against the retained normalised
      prefix instead of the whole sequent.""",
      gate="Output-preserving; same <code>--debug noprepcache</code> A/B; both suites green.",
      guard="<code>--debug noprepcache</code>.",
      model="Opus 5"),
    dict(pt="c12", sha="991239f", subject="backend/prep: differential oracle for the normalize cache",
      what="""<code>TLAPM_CHECK_ELABCACHE=1</code> runs both the resumed and the whole-sequent
      normalisation on every obligation and compares the results structurally, aborting on divergence.
      Off by default and inert; it exists so that the previous commit's invariant is testable rather
      than asserted.""",
      gate="""Inert without the variable, so the obligation stream is trivially unchanged. With the
      variable set, a full run over both private specifications and the synthetic family reports no
      divergence.""",
      guard="<code>TLAPM_CHECK_ELABCACHE=1</code>. Off by default.",
      model="unrecorded version"),
   ]),

 dict(n="5", title="Pull tasks from a stream", tag=("t-thr","memory"),
   files=["src/backend/schedule.ml{,i}","src/tlapm_lib.ml"],
   motive="""The scheduler received an array of all N tasks, materialised before the first prover was
   launched. On a 30 000-obligation module that array pins every obligation's data for the whole run,
   which is one half of the single-pass memory wall.""",
   commits=[
    dict(pt="c13", sha="b70585f", subject="backend/schedule: pull tasks from a stream instead of a materialized list",
      what="""<code>Schedule.run</code> takes a producer it pulls from as slots free up; per-obligation
      data is live only while in flight. The sequential pull order is preserved, which is what keeps
      the prefix caches of pull request 4 effective.""",
      gate="""Output-preserving: identical obligation stream and identical result-message order.
      Both suites green.""",
      model="Fable 5"),
   ]),

 dict(n="6", title="Linear ENABLED-axioms detection", tag=("t-lat","latency"),
   files=["src/module/m_elab.ml"],
   motive="""Elaboration decided which ENABLED axioms a module needs by testing every candidate against
   every theorem against every context entry — O(B&middot;T&middot;N) on the number of bound
   operators, theorems and hypotheses.""",
   commits=[
    dict(pt="c14", sha="ba1df8c", subject="module/Elab: make ENABLED-axioms detection linear in context size",
      what="Two linear passes — collect, then intersect — producing the same set in the same order.",
      gate="Output-preserving: identical obligation stream, both suites green.",
      model="Fable 5"),
   ]),

 dict(n="7", title="Reference levels without slicing the context", tag=("t-lat","latency"),
   files=["src/expr/e_levels.ml"],
   motive="""Reading the level of a de Bruijn reference built a sliced copy of the context up to that
   index. The level is already stored on the hypothesis; the slice was only there to reach it.""",
   commits=[
    dict(pt="c15", sha="809b30e", subject="expr/Levels: resolve de Bruijn reference levels without slicing the context",
      what="""Read the level off the hypothesis directly, with a fallback to the old path when the
      annotation is absent, so the result is identical in both cases.""",
      gate="Output-preserving: identical obligation stream, both suites green.",
      model="Fable 5"),
   ]),

 dict(n="8", title="Single-pass expansion in the result printer", tag=("t-thr","throughput"),
   files=["src/backend/toolbox.ml"],
   motive="""A fingerprint hit still re-expanded and re-normalised the obligation just to print it,
   with the same iterated formulation pull request 2 replaced in the prover path. That is the whole
   cost of a warm run, where every fingerprint is present.""",
   commits=[
    dict(pt="c16", sha="393164e", subject="backend/toolbox: single-pass definition expansion in the result printer",
      what="Compose the substitutions once, as in pull request 2, in the printer's own expansion.",
      gate="""Output-preserving: the printed obligations are byte-identical, which is directly
      observable since this code path <em>is</em> the output. Both suites green.""",
      model="unrecorded version"),
   ]),

 dict(n="9", title="Memoize the grammar", tag=("t-lat","latency"),
   files=["src/expr/e_parser.ml"],
   motive="""Two grammar instances were reconstructed inside the per-token loop, so the parser rebuilt
   a large part of its own grammar for every token of every file — the dominant term in
   edit-to-diagnostics latency.""",
   commits=[
    dict(pt="c17", sha="690a261", subject="expr/parser: memoize the two instances of each grammar rule",
      what="Hoist the two instances into memoized thunks; the grammar is built once per process.",
      gate="""Output-preserving: identical obligation stream and identical parse errors, including
      their positions, on the test suite and on both private specifications.""",
      model="unrecorded version"),
   ]),

 dict(n="10", title="Monomorphic property lookups", tag=("t-thr","throughput"),
   files=["src/util/property.ml"],
   motive="""Every annotation read on every expression node went through polymorphic comparison and a
   <code>List</code> higher-order search. This is not a hot spot in one place; it is a few per cent of
   <em>all</em> preparation.""",
   commits=[
    dict(pt="c18", sha="9a08f81", subject="util/property: monomorphic pid equality, loop-based lookups",
      what="Integer equality on the property id, and hand-written loops instead of the closures.",
      gate="Output-preserving: identical obligation stream, both suites green.",
      model="Fable 5"),
   ]),

 dict(n="11", title="A sorted obligation pool in the editor", tag=("t-lat","latency"),
   files=["lsp/lib/docs/proof_step.ml"],
   motive="""Attaching obligations to proof steps ran a <code>RangeMap.partition</code> per step over
   the whole obligation set — quadratic in the number of steps, paid on every document update. This is
   the only pull request in the set that touches the language server.""",
   commits=[
    dict(pt="c19", sha="4e3ec9f", subject="lsp: replace the per-step RangeMap.partition by a sorted obligation pool",
      what="""Sort the obligations once by position and consume them in step order, which is the same
      assignment computed in one pass.""",
      gate="""The notification stream the server emits is byte-identical before and after over a
      recorded editing session, and <code>dune runtest lsp</code> is green.""",
      model="unrecorded version"),
   ]),

 dict(n="12", title="Logarithmic context index", tag=("t-thr","throughput"),
   files=["src/ctx.ml"],
   motive="""The context's name-to-index lookup was a linear association list. Below the noise floor on
   its own; the argument is the complexity of a structure consulted once per name resolved.""",
   commits=[
    dict(pt="c20", sha="fba0670", subject="Ctx: logarithmic index lookup",
      what="A map beside the list, kept in step with it; the list stays authoritative for ordering.",
      gate="Output-preserving: identical obligation stream, both suites green.",
      model="Fable 5"),
   ]),

 dict(n="13", title="Compile the SMT escaping regexes once", tag=("t-thr","throughput"),
   files=["src/backend/smtlib.ml"],
   motive="""The identifier-escaping regexes were compiled inside the function that prints an
   identifier, so once per identifier written to every solver file.""",
   commits=[
    dict(pt="c21", sha="3525625", subject="backend/Smtlib: compile identifier-escaping regexes once",
      what="Module-level compiled regexes.",
      gate="""Output-preserving, and observable directly: the solver input files are byte-identical
      across the change under <code>--debug tempfiles</code>.""",
      model="Fable 5"),
   ]),

 dict(n="14", title="Allocation-free spine walk in app_ix", tag=("t-thr","throughput"),
   files=["src/expr/e_subst.ml"],
   motive="""<code>app_ix</code> allocated one intermediate per step while walking a substitution
   spine, on the hottest walk in substitution.""",
   commits=[
    dict(pt="c22", sha="16becd8", subject="expr/Subst: walk substitution spines in app_ix without allocating",
      what="An accumulator loop over the spine; same result, no intermediates.",
      gate="Output-preserving: identical obligation stream, both suites green.",
      model="Fable 5"),
   ]),

 dict(n="15", title="Skip identity rebuilds when flattening extracts nothing", tag=("t-thr","throughput"),
   files=["src/backend/prep.ml","src/encode/n_flatten.ml"],
   motive="""The sequent was rebuilt after the flattening pass even when the pass had extracted
   nothing, which is the common case.""",
   commits=[
    dict(pt="c23", sha="abf13ea", subject="backend+encode: skip identity rebuilds when flattening extracts nothing",
      what="Return the input unchanged when the extracted set is empty, preserving physical sharing — which also helps pull request 4's prefix walk.",
      gate="Output-preserving: identical obligation stream, both suites green.",
      model="Fable 5"),
   ]),

 dict(n="16", title="Write the obligation comment only into files that are kept", tag=("t-thr","throughput"),
   files=["src/backend/prep.ml"],
   motive="""Every solver file opened with the obligation pretty-printed as a comment — including the
   files deleted immediately after the prover exits, which is all of them unless
   <code>--debug tempfiles</code> is given.""",
   commits=[
    dict(pt="c24", sha="1d1b05a", subject="backend/prep: emit obligation comments into solver files only when kept",
      what="Emit the comment under the same condition that keeps the file.",
      gate="""Output-preserving for the provers &mdash; and this is the one change that alters a byte
      of solver input, so it is stated precisely: with <code>--debug tempfiles</code> the files are
      byte-identical; without it, the comment is absent from files no one reads. The problem term sent
      to the solver is unchanged in both cases.""",
      model="Fable 5"),
   ]),

 dict(n="17", title="Stop the level cache pinning one context per obligation", tag=("t-thr","memory"),
   files=["src/backend/prep.ml","src/expr.mli","src/expr/e_levels.ml{,i}"],
   motive="""The level cache keyed its entries on the context, holding one full context alive per
   obligation for the whole run. With pull request 5, this is the other half of the single-pass memory
   wall: the heap grew monotonically instead of flat.""",
   commits=[
    dict(pt="c25", sha="2c2b318", subject="expr/Levels: stop the level cache pinning one context per obligation",
      what="Scope the cache to the obligation being prepared and drop it with the obligation.",
      gate="""Output-preserving: identical obligation stream, both suites green. The memory claim is
      checked on the <em>shape</em> of the RSS curve sampled with <code>ps</code> during a run, not on
      the peak alone.""",
      model="Opus 5"),
   ]),

 dict(n="18", title="Constant-time De Bruijn resolution in add_constness", tag=("t-thr","throughput"),
   files=["src/backend/prep.ml","src/expr.mli","src/expr/e_constness.ml{,i}","src/util/deque.ml{,i}"],
   motive="""<code>add_constness</code> resolved each reference by walking the context deque backwards
   from the current position, so the cost of annotating an obligation grew with the distance of the
   references it mentions.""",
   commits=[
    dict(pt="c26", sha="bd0ecd1", subject="expr/Constness: constant-time De Bruijn resolution in add_constness",
      what="""Maintain a mirror array of the deque's entries alongside the fold, indexed directly, so
      resolution is O(1). Kept consistent with the deque at every push, and reset with the fold.""",
      gate="""Output-preserving: identical obligation stream, both suites green. Measured with the
      instrumented build at &minus;73 % of the deque walks in the stage; the wall-clock share is a few
      per cent, so the local proof is the complexity argument, not the point in the curve.""",
      model="Opus 5"),
   ]),
]

def prev_point(pt):
    i = ORDER.index(pt)
    return ORDER[i-1]

out = []
A = out.append
A('<section>')
A('  <div class="sec-head"><span class="n">06</span><h2>The pull requests, commit by commit</h2></div>')
A("""  <p>Nineteen pull requests, twenty-six commits. Each block states why the change exists, then per
  commit: what it changes, the correctness gate that applies to it, the switch that turns it off where
  there is one, and the measured effect of <em>that commit alone</em> &mdash; the point before it
  against the point at it, on the two synthetic sizes and on both private specifications. Every commit
  message on the branch carries the same gate text, so a reviewer reading <code>git log</code> sees it
  without this page.</p>""")
A("""  <div class="claim"><strong>Reading the measurement tables.</strong> <code>gen</code> is
  <code>tlapm -N --nofp</code> &mdash; parse, elaborate, generate. <code>prep</code> is
  <code>tlapm --noproving --nofp</code> &mdash; the whole per-obligation pipeline, no prover.
  <code>peak</code> is the maximum resident set of the <code>prep</code> run. One run per cell, so
  ratios under about 1.1 are noise and are labelled as such in the commit's own text; the tables are
  there so that no commit can hide behind a group total. A cell reading <code>&gt; 900 s</code> is a
  run stopped at the fifteen-minute ceiling.</div>""")
A("""  <h4>Which model wrote which commit</h4>
  <p>The work was done with Claude Code. Per commit, the <code>Co-Authored-By</code> trailer records
  the model: <strong>Claude Fable 5</strong> on sixteen commits, <strong>Claude Opus 5</strong> on six,
  and three trailers name only <code>Claude</code> &mdash; those were written in sessions served by
  Sonnet 5 and Opus 5 before we started recording the version, and we do not know which of the two
  wrote which, so they are marked <em>unrecorded version</em> below rather than guessed. One commit
  (pull request 11) carries no trailer. Every design decision, every measurement protocol and every
  rejection in &sect;7 was reviewed by a human; the numbers were produced by running the code, not by
  a model.</p>""")

for pr in PRS:
    tagc, tagl = pr["tag"]
    first = pr["commits"][0]["pt"]; last = pr["commits"][-1]["pt"]
    ncom = len(pr["commits"])
    A('  <div class="pr">')
    A('    <div class="pr-head"><span class="pr-n">%s</span><h3>%s</h3><span class="tag %s">%s</span></div>' %
      ("#" + pr["n"], pr["title"], tagc, tagl))
    tot_a = tot_r = 0
    touched = set()
    for c in pr["commits"]:
        for pa, a, r in numstat(c["sha"]):
            tot_a += a; tot_r += r; touched.add(pa)
    A('    <p class="pr-meta">%d commit%s &middot; %d file%s &middot; +%d/&minus;%d</p>'
      % (ncom, "" if ncom == 1 else "s", len(touched), "" if len(touched) == 1 else "s",
         tot_a, tot_r))
    A('    <p>%s</p>' % re.sub(r"\s+", " ", pr["motive"]).strip())
    for c in pr["commits"]:
        A('    <div class="cm">')
        A('      <p class="cm-h"><code>%s</code> %s <span class="mdl">%s</span></p>' %
          (c["sha"], html.escape(c["subject"]), c["model"]))
        A('      <p class="cm-files">%s</p>' % files_line(c["sha"]))
        A('      <p><span class="lbl">changes</span> %s</p>' % re.sub(r"\s+", " ", c["what"]).strip())
        A('      <p><span class="lbl">gate</span> %s</p>' % re.sub(r"\s+", " ", c["gate"]).strip())
        if c.get("guard"):
            A('      <p><span class="lbl">switch</span> %s</p>' % re.sub(r"\s+", " ", c["guard"]).strip())
        b = prev_point(c["pt"])
        A('      <div class="scroller"><table><thead><tr><th>corpus</th><th class="num">gen</th>'
          '<th class="num">prep</th><th class="num">peak</th></tr></thead><tbody>')
        for key, label in CORPORA:
            A('        <tr><td>%s</td><td class="num">%s</td><td class="num">%s</td><td class="num">%s</td></tr>' %
              (label, cell(b, c["pt"], key, "m0_ms"), cell(b, c["pt"], key, "m1_ms"),
               cell(b, c["pt"], key, "rss_kb")))
        A('      </tbody></table></div>')
        A('    </div>')
    A('  </div>')

A('</section>')

sec = "\n".join(out) + "\n"
path = os.environ.get("PROPOSAL_HTML", os.path.join(S, "PROPOSAL.html"))
src = open(path).read()
start = src.index('<section>\n  <div class="sec-head"><span class="n">06</span>')
end = src.index('<section>\n  <div class="sec-head"><span class="n">07</span>')
open(path, "w").write(src[:start] + sec + "\n" + src[end:])
print("section 06 written: %d lines" % len(out))
