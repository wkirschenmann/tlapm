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
  what="<code>Timing.start</code> assumed clocks never nest, so a clock started "
       "inside another silently replaced it and the outer one lost its total. The "
       "accounting becomes a stack: starting a clock suspends the enclosing one and "
       "finishing it resumes it.",
  how="<code>--timing</code> on any module: the printed phase totals must sum to "
      "within rounding of the wall clock, which before this change they did not.",
  off="No switch. A defect fix with no behavioural surface outside "
      "<code>--timing</code> output."),
"p02": dict(
  what="The three named pipeline clocks -- generation, fingerprint computation, "
       "fingerprint saving -- were declared in the driver rather than in the timing "
       "module, so nothing outside the driver could reach them.",
  how="Mechanical move; <code>--timing</code> output is unchanged by this commit "
      "alone. The next commit is what makes it non-zero.",
  off="No switch &mdash; a move with no behavioural surface at all."),
"p03": dict(
  what="Those three clocks were never started. <code>--timing</code> therefore "
       "reported <code>0.00</code> for generation, fingerprinting and fingerprint "
       "saving on every run, which is precisely where the time goes on a large one.",
  how="<code>tlapm --timing</code> on any multi-obligation module: the three lines "
      "carry real values, and their sum plus the prover time accounts for the run.",
  off="No switch. This is the commit that makes the tool tell the truth about "
      "itself."),
"p04": dict(
  what="Two defects in one loop. Finished provers were read only after the next task "
       "had been constructed, and constructing a task means encoding an obligation for "
       "its prover, which can take seconds &mdash; so a prover that had already exited "
       "sat unread past its deadline and was then reported as a timeout it did not "
       "have. A zero-timeout <code>select</code> before each launch reaps it first. "
       "PR4 widens that window &mdash; once tasks are pulled from a stream, a launch "
       "also runs the obligation's whole preparation &mdash; which is why this commit "
       "comes before it rather than with it. "
       "And the wall clock was read <em>before</em> <code>select</code> and reused "
       "after it, so run times were under-reported and kills postponed by however "
       "long the wait had been.",
  how="The first defect is a wrong verdict, not a slow one, so the gate is the test "
      "suite: a module with a mix of fast and slow obligations under "
      "<code>--threads 4</code> must report the same verdicts it reports "
      "single-threaded. The second shows in <code>--timing</code>: reported prover "
      "time stops undershooting the wall clock.",
  off="No switch. A wrong verdict is not a feature to make optional."),
"p05": dict(
  what="A timed-out prover was killed with <code>SIGHUP</code>. Under "
       "<code>nohup</code>, and in most editor and CI parents, <code>SIGHUP</code> "
       "is ignored, so the process survived its own timeout and kept its core "
       "busy. It is now <code>SIGTERM</code>.",
  how="Run a module with a deliberately unprovable obligation under "
      "<code>nohup</code> with a short <code>--stretch</code>: no prover process "
      "remains after tlapm exits.",
  off="No switch. Sending the signal that works is not a mode."),
"p06": dict(
  what="<code>Deque.nth</code> rebuilt intermediate lists, <code>first_n</code> "
       "copied rather than shared, and <code>equal</code> compared element by "
       "element with no physical short-circuit. All three are on the hypothesis "
       "lookup path, which elaboration and generation run once per De Bruijn "
       "reference.",
  how="Output-identical: the obligation dump under "
      "<code>-N --toolbox 0 0 --printallobs --nofp</code> is byte-identical before "
      "and after. The deque unit tests cover the rear-heavy cases the rewrite "
      "changes.",
  off="No switch; there is no second implementation to fall back to."),
"p07": dict(
  what="<code>expand_defs</code> recursed front to back and, for <em>each</em> "
       "definition it expanded, applied a substitution to the whole remaining "
       "sequent &mdash; rebuilding it once per expanded definition. For <em>k</em> "
       "definitions over a context of <em>n</em> hypotheses that is <em>k</em> "
       "rebuilds of <em>n</em>, quadratic on an INSTANCE-heavy context. One "
       "front-to-back pass accumulates the composed substitution and rebuilds the "
       "sequent once.",
  how="The substitution accumulated is exactly the composition the iterated version "
      "applied one definition at a time, with the same De Bruijn bookkeeping as "
      "<code>Expr.Subst.app_hyps</code>: bump under a kept hypothesis, cons under an "
      "inlined one. The point to check is that the definition body is read "
      "<em>after</em> the accumulated substitution is applied to its hypothesis, so "
      "earlier inlinings are already substituted into it &mdash; which is what makes "
      "the one-pass result identical rather than merely equivalent. Byte-identical "
      "obligation dumps, and the same fingerprints: the digest is computed on the "
      "const-annotated pre-expansion obligation, so this commit cannot move it.",
  off="No switch. Output-identical, so the old path would be dead code kept alive only to be untested."),
"p08": dict(
  what="The driver built the whole task list before the scheduler started, so every "
       "obligation of the run -- context, expansion, normalised form -- was live "
       "before the first prover was launched. The scheduler now pulls tasks from a "
       "stream and only the obligations in flight are live. The stream is pulled in "
       "document order deliberately: the prefix-resume caches of PR6 assume that "
       "sequence, so streaming and caching compose rather than conflict.",
  how="Obligation stream identical under <code>--printallobs</code>; verdict order "
      "and count unchanged. One behavioural improvement is deliberate: a malformed "
      "<code>USE</code> used to abort the whole batch before anything ran, and now "
      "the obligations already dispatched keep their results.",
  off="No switch. The streamed and materialised orders are the same order, so there is nothing to choose between."),
"p09": dict(
  what="The level memoization is not a table but a mutable cell on each syntax node, "
       "and those nodes belong to the module tree &mdash; they are shared by every "
       "obligation. A filled cell pins the <em>context</em> of the query that filled "
       "it, and during preparation those are per-obligation contexts, so the shared "
       "tree collectively pinned one context per obligation ever prepared. The commit "
       "registers the cells it fills and empties them between obligations.",
  how="The memoization exists to tame a recomputation that is exponential in "
      "expression depth, and it only needs to survive one burst of queries; a hit "
      "across obligations would have required physically equal contexts, which "
      "preparation rebuilds anyway. Levels are a pure function of the expression, so "
      "emptying the cells cannot change a result: byte-identical dumps. The visible "
      "effect is peak resident set.",
  off="No switch. Emptying the cells cannot change a result, only the resident set."),
"p10": dict(
  what="After expansion has inlined every visible use, an obligation's context still "
       "carries the hidden operator and pragma definitions imported by "
       "<code>INSTANCE</code>, most of which the goal never references. The pass "
       "computes what is transitively reachable from the goal and the facts through "
       "De Bruijn references and drops the rest, renumbering with the same "
       "substitution machinery <code>expand_defs</code> uses. This commit drops "
       "<em>only</em> unreferenced hidden operator and pragma definitions: all "
       "declarations, recursive and instance definitions, and every fact are kept.",
  how="Three things make it checkable rather than merely plausible. References point "
      "strictly front-ward, so one rear-to-front pass <em>is</em> the transitive "
      "closure &mdash; there is no fixpoint to get wrong. A hypothesis the pass "
      "cannot analyse conservatively keeps all of its predecessors. And a dropped "
      "slot is filled with a distinctive <code>Opaque \"__pruned__\"</code>, which "
      "because the slot is unreachable can never appear in the result: a "
      "reachability bug surfaces as that marker leaking into an obligation and "
      "failing a proof, never as a silent change of meaning. Structurally, the pass "
      "runs on the backend path after the fingerprint is computed, so fingerprints "
      "and <code>--printallobs</code> cannot move.",
  off="No switch. The pruned form is what the prover receives."),
"p11": dict(
  what="The same reachability treatment for hidden <em>facts</em>. On an "
       "<code>INSTANCE</code>-heavy module these are the instantiated statements of "
       "every earlier theorem, and they are most of the context by weight. A fact is "
       "hidden here only if no <code>BY</code> or <code>USE</code> cited it &mdash; a "
       "citation marks it visible during proof generation, before this pass &mdash; "
       "and the backend translations assert only visible facts, so an unreferenced "
       "hidden fact is weight carried through every encoding pass and never used.",
  how="Two arguments, and the second is the one that constrains where the pass may "
      "run. First: dropping a premise can never make an unprovable sequent provable, "
      "so the risk is a lost proof rather than a wrong result &mdash; which is "
      "exactly what a test suite detects. Second: the triviality check discharges a "
      "support obligation by finding a fact <em>equal to the goal</em>, hidden ones "
      "included, so pruning before it would turn trivially discharged obligations "
      "into prover work. The pass therefore runs on the backend path only, after "
      "every expansion has introduced its references and after the triviality check "
      "&mdash; which is also what puts it after the fingerprint. Gate: fail-set "
      "identical to <code>main</code>'s on the full stack.",
  off="No switch. The pruned form is what the prover receives, as for the commit before it."),
"p12": dict(
  what="Consecutive obligations share a context prefix: on a 30k-obligation module "
       "the median context is 743 hypotheses of which 699 are the physically same "
       "objects as in the previous obligation. <code>expand_defs</code> and "
       "<code>add_constness</code> both fold front to back with a state that only "
       "grows, so the state after position <em>i</em> can be resumed instead of "
       "recomputed.",
  how="Keying the prefix on <em>physical</em> equality is what makes a stale hit "
      "impossible: hypotheses from another module or a rebuilt context compare "
      "unshared and fall back to the full fold, which also refreshes the cache. The "
      "obvious worry is that a cache of contexts is itself the memory problem PR4 "
      "just fixed: it is not, because the snapshots share substructure with the "
      "context they came from, so the footprint is one array of pairs per module "
      "rather than a copy. Byte-identical dumps with and without the cache.",
  off="<code>--debug noprepcache</code> restores the uncached path &mdash; not a "
      "disabled cache but the original code, reached at three call sites: the "
      "full <code>expand_defs</code>, the full normalisation, and "
      "<code>add_constness_nocache</code>. That is what makes the flag usable as "
      "a differential reference rather than merely as an off switch."),
"p13": dict(
  what="The same treatment for <code>Elab.normalize</code>, the third and most "
       "expensive per-obligation pass.",
  how="Byte-identical dumps against <code>--debug noprepcache</code>.",
  off="<code>--debug noprepcache</code>, the same flag as the commit before: one "
      "switch restores the original path for all three cached passes at once, so "
      "a bisection never lands on a half-cached build."),
"p14": dict(
  what="A differential oracle for the two caches above. When it is on, every "
       "obligation is normalised <em>twice</em> &mdash; once through the "
       "prefix-resume fold and once through the original whole-sequent path "
       "&mdash; and the two results are compared structurally, not by their "
       "printed form. A divergence is fatal and names the obligation that caused "
       "it, so a cache bug is reported where it happens rather than surfacing "
       "later as a proof that stopped working.",
  how="This commit <em>is</em> the validation tool for the two before it: running "
      "the whole corpus under it is how the caches were gated. It cannot validate "
      "itself, which is the point &mdash; it has no fast path to be wrong about.",
  off="<strong>Opt-in, and it must stay that way: it doubles the normalisation "
      "cost by construction, because duplicating the work is what lets it "
      "compare.</strong> The duplicate path is entered only when "
      "<code>TLAPM_CHECK_ELABCACHE</code> is set in the environment; unset, the "
      "branch is not taken and preparation runs exactly as it did before the "
      "commit &mdash; the whole residual cost is one <code>getenv</code> per "
      "obligation. The campaign confirms it: on the refinement chain this commit "
      "measures inside the noise of its neighbours."),
"p15": dict(
  what="Elaborating a <code>BY</code> or <code>OBVIOUS</code> asks one question of "
       "the context: does any fact in it cite the <code>ENABLEDaxioms</code> pragma? "
       "The old code answered it by walking every fact and, for each, building a "
       "sliced copy of the context up to that position in order to resolve the "
       "fact's De Bruijn reference &mdash; so the cost was the context size times the "
       "number of facts, on modules whose contexts carry hundreds of imported facts. "
       "Two linear passes replace it: mark which positions hold the pragma, then for "
       "each fact resolve the reference by arithmetic (a fact at front-index "
       "<em>i</em> whose body is <code>Ix k</code> refers to front-index "
       "<em>i&nbsp;&minus;&nbsp;k</em>).",
  how="The arithmetic is exactly what the slice-and-look-up computed, so the answer "
      "is the same and the obligation dumps are byte-identical. The "
      "<code>enabled_cdot</code> test family is the behavioural gate &mdash; a wrong "
      "answer here changes which axioms are available to a proof, so it would show "
      "as a proof that stops working rather than as a wrong result.",
  off="No switch. Two linear passes compute the same set as the quadratic scan."),
"p16": dict(
  what="Building the proof-step tree ran <code>RangeMap.partition</code> over the "
       "whole remaining obligation map for every step -- steps &times; obligations. "
       "The pool keeps the exact claiming semantics (first claimer wins, a claim is "
       "a range intersection, duplicate ranges collapse with the last one winning) "
       "in logarithmic time: "
       "entries sorted by range, a binary search to the window, a forward scan, and "
       "a backward scan bounded by the longest obligation span.",
  how="The gate is the client-visible notification stream: byte-identical between "
      "the old and the new server on the corpora, proof-step marker payloads "
      "included. <code>dune runtest lsp</code> green.",
  off="No switch. The pool preserves the claiming semantics exactly, so the old traversal has nothing left to be right about."),
"p17": dict(
  what="The expression grammar is a family of mutually recursive rules "
       "<code>name b = lazy &hellip;</code> whose one parameter is a boolean &mdash; "
       "whether a bulleted conjunction or disjunction list is allowed at that "
       "position &mdash; so each rule has exactly two useful instances. Every "
       "<em>reference</em> to a rule rebuilt its whole combinator family, choice "
       "lists and thunks included, at every token position. The rules that take no "
       "parameter were already shared top-level thunks, which is what confirms the "
       "sharing is safe. The 21 parameterized bodies move unchanged into "
       "<code>mk_*</code> functions behind a two-slot cache.",
  how="Byte-identical parse: the obligation dump under "
      "<code>-N --toolbox 0 0 --printallobs --nofp</code> is unchanged, and the "
      "parser test corpus is the behavioural gate. A grammar change would show as a "
      "parse error, not as a slow parse.",
  off="No switch. The memoized rules describe the same grammar; a difference would be a parse error, not a slower parse."),
}
