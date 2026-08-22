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
     "Elaborating <code>ENABLED</code> and <code>\\cdot</code> matched every "
     "axiom against every hypothesis. It is quadratic in context size and it runs "
     "on the editor's path."),

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
  off="No switch."),
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
  off="No switch."),
"p05": dict(
  what="A timed-out prover was killed with <code>SIGHUP</code>. Under "
       "<code>nohup</code>, and in most editor and CI parents, <code>SIGHUP</code> "
       "is ignored, so the process survived its own timeout and kept its core "
       "busy. It is now <code>SIGTERM</code>.",
  how="Run a module with a deliberately unprovable obligation under "
      "<code>nohup</code> with a short <code>--stretch</code>: no prover process "
      "remains after tlapm exits.",
  off="No switch."),
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
  what="<code>expand_defs</code> applied one substitution per visible definition, "
       "each of which walked the entire context: for <em>k</em> definitions over a "
       "context of <em>n</em> hypotheses it did <em>k</em> passes over <em>n</em>. "
       "The substitutions compose, so one front-to-back pass with the composed "
       "substitution produces the same term.",
  how="Byte-identical obligation dumps, and the same fingerprints -- the "
      "fingerprint is computed on the const-annotated pre-expansion obligation, so "
      "this commit cannot move it.",
  off="No switch."),
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
  off="No switch."),
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
  off="No switch."),
"p10": dict(
  what="After expansion and normalisation, an obligation's context still carries "
       "the <em>hidden</em> operator and pragma definitions -- ones no longer "
       "reachable from the goal, because expansion has already inlined every visible "
       "use. Unreachable hidden definition slots become "
       "<code>Opaque \"__pruned__\"</code>.",
  how="Soundness is structural: pruning runs on the backend path only, after the "
      "fingerprint is computed, so fingerprints and <code>--printallobs</code> are "
      "unchanged by construction; and a slot that nothing references cannot change "
      "what the sequent means. The gate is the test fail-set plus dump equality on "
      "the generated obligations.",
  off="No switch. The pruned form is what the prover receives; the "
      "<code>__pruned__</code> marker makes an accidental reference fail loudly "
      "rather than silently."),
"p11": dict(
  what="The same treatment for hidden <em>facts</em>. On an INSTANCE-heavy module "
       "these are the instantiated statements of every earlier theorem, and they are "
       "most of the context by weight. A fact is hidden here only if no "
       "<code>BY</code> or <code>USE</code> cited it during generation, and backends "
       "assert only visible facts.",
  how="Dropping a premise can never make an unprovable sequent provable, so the "
      "risk is a lost proof, not a wrong one -- and that is what the test suite "
      "measures. Fail-set identical to <code>main</code>'s on the full stack.",
  off="No switch."),
"p12": dict(
  what="Consecutive obligations share a context prefix: on a 30k-obligation module "
       "the median context is 743 hypotheses of which 699 are the physically same "
       "objects as in the previous obligation. <code>expand_defs</code> and "
       "<code>add_constness</code> both fold front to back with a state that only "
       "grows, so the state after position <em>i</em> can be resumed instead of "
       "recomputed.",
  how="Keying the prefix on <em>physical</em> equality is what makes a stale hit "
      "impossible: hypotheses from another module or a rebuilt context compare "
      "unshared and fall back to the full fold. Byte-identical dumps with and "
      "without the cache.",
  off="<code>--debug noprepcache</code> restores the uncached path for both passes."),
"p13": dict(
  what="The same treatment for <code>Elab.normalize</code>, the third and most "
       "expensive per-obligation pass.",
  how="Byte-identical dumps against <code>--debug noprepcache</code>.",
  off="<code>--debug noprepcache</code>."),
"p14": dict(
  what="A differential oracle for the two caches: with it on, every obligation is "
       "prepared both ways and the results compared, so a divergence is reported at "
       "the obligation that caused it rather than as a proof failure later.",
  how="This commit <em>is</em> the validation tool for the two before it. Running "
      "the whole corpus under it is how the cache was gated.",
  off="Off unless <code>TLAPM_CHECK_ELABCACHE</code> is set; inert otherwise."),
"p15": dict(
  what="Detecting which axioms an <code>ENABLED</code> or <code>\\cdot</code> "
       "elaboration needs matched every candidate axiom against every hypothesis of "
       "the context. Two linear passes -- collect what the context offers, then "
       "select -- produce the same set.",
  how="Same axiom set, so byte-identical dumps; the <code>enabled_cdot</code> test "
      "family is the behavioural gate.",
  off="No switch."),
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
      "parser test family is the behavioural gate. A grammar change would show as a "
      "parse error, not as a slow parse.",
  off="No switch."),
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
  off="No switch."),
}
