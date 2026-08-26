# -*- coding: utf-8 -*-
"""The prose of the short proposal: what each pull request is for, and what each
commit does, validates and can be switched off with.

Kept apart from the generator so the text can be read and edited on its own.
Numbers never appear here -- they come from the campaign."""

# (id, title, motivation (<= 3 lines), tag, commits)
PRS = [
    ("PR1", "Correctness fixes", "t-fix", ["p01", "p02", "p03", "p04", "p05"],
     "Five defects. Three make <code>--timing</code> report zero for the phases that "
     "dominate a large run; one turns a finished prover into a spurious timeout; one "
     "leaves killed provers alive. They come first because the rest of the series is "
     "justified by measurement, and these are what make the measurements available "
     "and the verdicts trustworthy."),

    ("PR2", "Deque lookups", "t-lat", ["p06"],
     "A context is a deque, and every hypothesis lookup walked it. The walk is the "
     "innermost loop of elaboration and of every editor interaction, so it sets the "
     "floor under everything else in this series."),

    ("PR3", "Single-pass definition expansion", "t-thr", ["p07"],
     "Expanding the visible definitions of one obligation re-substituted the whole "
     "context once per definition. This is the single change that decides whether a "
     "large module can be re-checked at all."),

    ("PR4", "Bounded memory", "t-mem", ["p08", "p09"],
     "Preparation held every obligation of the run live at once, and each obligation "
     "pinned a copy of its context through a memoization table. Together they make "
     "peak memory grow with the file rather than with one obligation, which is what "
     "turns a slow run into a failed one."),

    ("PR5", "Context pruning", "t-thr", ["p10", "p11"],
     "An obligation ships its whole context to the prover, including hidden "
     "definitions and hidden facts that nothing in it can refer to. Dropping them "
     "sends the prover strictly less, and is what makes the largest specification "
     "complete."),

    ("PR6", "Prefix-resume caches", "t-thr", ["p12", "p13", "p14"],
     "Consecutive obligations of a module share nearly all of their context, and "
     "each of the three preparation passes recomputed all of it. Resuming from the "
     "shared prefix is the largest single step on the metric a user feels most: the "
     "wait after one edit."),

    ("PR7", "Linear ENABLED scan", "t-lat", ["p15"],
     "Every <code>BY</code> and <code>OBVIOUS</code> asked whether the context cites "
     "one pragma, and answered it by re-slicing the context once per fact. It is "
     "quadratic in context size and it runs on the editor's path."),

    ("PR8", "Editor obligation pool", "t-lat", ["p16"],
     "Building the proof-step tree the editor displays scanned the whole obligation "
     "map once per step. On a large module this, and not proving, was most of the "
     "wait after a keystroke."),

    ("PR9", "Memoized grammar rules", "t-lat", ["p17"],
     "Every reference to a grammar rule rebuilt the rule at every token position. "
     "Parsing is a small share of the wait on a mid-sized file and a visible one on a "
     "30k-line module, which is why this is last and why it is here at all."),
]

# per commit: what changes / how to validate / how to switch off
CM = {
"p01": dict(
  what='<code>Timing.start</code> overwrote the running clock instead of stacking it: a clock started inside another lost the outer total. Start now suspends the enclosing clock, finish resumes it.',
  how="Dump identical. Inert unless <code>--timing</code> is passed.",
  off='No switch. A defect fix with no behavioural surface outside <code>--timing</code> output.'),

"p02": dict(
  what='The three named pipeline clocks &mdash; generation, fingerprint compute, fingerprint save &mdash; were declared in the driver, out of reach of the code they time. Moved into the timing module.',
  how="Dump identical. Inert unless <code>--timing</code> is passed.",
  off='No switch &mdash; a move with no behavioural surface at all.'),

"p03": dict(
  what='Those three clocks were never started. <code>--timing</code> reported 0.00&nbsp;s for generation, fingerprinting and fingerprint saving on every run.',
  how="Dump identical. Inert unless <code>--timing</code> is passed.",
  off='No switch. This is the commit that makes the tool tell the truth about itself.'),

"p04": dict(
  what='Finished provers were reaped only after the next task was built, and building a task encodes an obligation for its prover &mdash; seconds. A prover that had already exited sat unread past its deadline and was reported as a timeout it did not have. Reap first, then build.',
  how="Dump identical. Verdicts under <code>--threads 4</code> identical to single-threaded.",
  off='No switch. A wrong verdict is not a feature to make optional.'),

"p05": dict(
  what='A timed-out prover was killed with SIGHUP, which <code>nohup</code>, editors and CI parents ignore: it outlived its own timeout and kept a core busy. SIGTERM.',
  how="Dump identical. No prover survives its timeout.",
  off='No switch. Sending the signal that works is not a mode.'),

"p06": dict(
  what='<code>Deque.nth</code> rebuilt intermediate lists, <code>first_n</code> copied instead of sharing, <code>equal</code> compared element by element with no physical short-circuit. All three are on the hypothesis lookup path, once per De Bruijn reference.',
  how="Dump identical. Deque unit tests cover the rear-heavy cases.",
  off='No switch; there is no second implementation to fall back to.'),

"p07": dict(
  what='<code>expand_defs</code> applied a substitution to the whole remaining sequent once per expanded definition &mdash; <em>k</em> rebuilds of an <em>n</em>-hypothesis context. One front-to-back pass composes the substitution and rebuilds once.',
  how="Dump identical.",
  off='No switch. Output-identical, so the old path would be dead code kept alive only to be untested.'),

"p08": dict(
  what="The whole task list was built before the scheduler started, so every obligation's context, expansion and normal form was live before the first prover launched. The scheduler pulls from a stream; only obligations in flight are live. Same order.",
  how="Dump identical.",
  off='No switch. The streamed and materialised orders are the same order, so there is nothing to choose between.'),

"p09": dict(
  what='The level cache is a mutable cell on each syntax node, and the nodes belong to the module tree every obligation shares. A filled cell pinned the per-obligation context that filled it. The cells are emptied when preparation ends.',
  how="Dump identical.",
  off='No switch. Emptying the cells cannot change a result, only the resident set.'),

"p10": dict(
  what='After expansion, an obligation still carries the hidden operator and pragma definitions <code>INSTANCE</code> imported, most of them unreachable from the goal. One rear-to-front pass keeps what the goal and the facts reach through De Bruijn references, drops the rest and renumbers.',
  how="Dump identical. The pass runs after the fingerprint, on the backend path only: what shrinks is what the prover receives, not what is generated.",
  off='No switch. The pruned form is what the prover receives.'),

"p11": dict(
  what='The same for hidden facts &mdash; on an INSTANCE-heavy module, the instantiated statement of every earlier theorem, and most of the context by weight. A fact is hidden here only if no <code>BY</code> or <code>USE</code> cited it.',
  how="Dump identical. Same position in the pipeline as the commit before it.",
  off='No switch. The pruned form is what the prover receives, as for the commit before it.'),

"p12": dict(
  what='Consecutive obligations share a context prefix: 699 of 743 hypotheses are physically the same objects as in the previous obligation on the 30k module. <code>expand_defs</code> and <code>add_constness</code> fold front to back over a state that only grows, so the fold resumes at the first difference.',
  how="Dump identical. <code>--debug noprepcache</code> restores the uncached path for a differential run.",
  off='<code>--debug noprepcache</code> restores the uncached path &mdash; not a disabled cache but the original code, reached at three call sites: the full <code>expand_defs</code>, the full normalisation, and <code>add_constness_nocache</code>.'),

"p13": dict(
  what='The same for <code>Elab.normalize</code>, the third and most expensive per-obligation pass.',
  how="Dump identical. Same flag.",
  off='<code>--debug noprepcache</code>, the same flag as the commit before: one switch restores the original path for all three cached passes at once, so a bisection never lands on a half-cached build.'),

"p14": dict(
  what='A differential oracle for those two caches: normalise every obligation twice, resumed and whole, and compare the results structurally. A divergence is fatal and names the obligation.',
  how="Dump identical. The second normalisation runs only with <code>TLAPM_CHECK_ELABCACHE</code> set; unset, the cost is one <code>getenv</code> per obligation.",
  off='<strong>Opt-in, and it must stay that way: it doubles the normalisation cost by construction, because duplicating the work is what lets it compare.</strong> The duplicate path is entered only when <code>TLAPM_CHECK_ELABCACHE</code> is set in the environment; unset, the branch is not taken and preparation runs exactly as it did before the commit &mdash; the whole residual cost is one <code>getenv</code> per obligation. The campaign confirms it: {oracle_noise}'),

"p15": dict(
  what='Every <code>BY</code> and <code>OBVIOUS</code> asks whether any fact cites the <code>ENABLEDaxioms</code> pragma. The old answer sliced a copy of the context per fact &mdash; context size squared, per proof step. Two linear passes.',
  how="Dump identical.",
  off='No switch. Two linear passes compute the same set as the quadratic scan.'),

"p16": dict(
  what='Building the proof-step tree ran <code>RangeMap.partition</code> over the whole remaining obligation map for every step. A pool sorted by position keeps the claiming semantics exactly and answers in logarithmic time.',
  how="Dump identical. No obligation path touched &mdash; the diff is under <code>lsp/</code>. <code>dune runtest lsp</code>.",
  off='No switch. The pool preserves the claiming semantics exactly, so the old traversal has nothing left to be right about.'),

"p17": dict(
  what='Each grammar rule has two useful instances &mdash; bulleted list allowed at that position or not &mdash; and every reference to a rule rebuilt its whole combinator family, at every token position. Both instances are built once.',
  how="Dump identical.",
  off='No switch. The memoized rules describe the same grammar.'),

}
