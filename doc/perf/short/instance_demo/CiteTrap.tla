------------------------- MODULE CiteTrap -------------------------
(* Two citations of the same shape.  One proves, one does not, and the    *)
(* only difference is which copy of IsFiniteSet the assumption bundle     *)
(* names.                                                                *)
(*                                                                       *)
(* There is ONE IsFiniteSet in the sources -- FiniteSets, EXTENDed once,  *)
(* by L0State.  After instantiation this module sees three symbols with   *)
(* that body and no way to tell them apart by eye:                       *)
(*                                                                       *)
(*     IsFiniteSet          reached by EXTENDS -- no prefix              *)
(*     L1!IsFiniteSet       one INSTANCE hop  -- L2's instance of L1     *)
(*     L1!L0!IsFiniteSet    two INSTANCE hops -- L1's own instance of L0 *)
(*                                                                       *)
(* L1Theorems states its assumptions with the unprefixed IsFiniteSet, so  *)
(* one hop later they read L1!IsFiniteSet.  Naming L1!L0!IsFiniteSet     *)
(* instead is well formed, means the same thing, and does not match.      *)
(*                                                                       *)
(* How that failure PRESENTS depends on the size of the context, which is *)
(* what makes it hard to diagnose on a real stack.  At this scale the     *)
(* prover settles it and answers "no proof".  On a module carrying a few  *)
(* hundred instantiated hypotheses the same mismatch comes back as a      *)
(* TIMEOUT instead -- both copies are opaque one-argument operators, so   *)
(* neither can be refuted, and the search simply runs out the clock.  The *)
(* symptom then reads as a prover too weak for the goal.  The cause is a  *)
(* name.                                                                 *)
(*                                                                       *)
(* THIS MODULE IS EXPECTED TO REPORT ONE FAILED OBLIGATION.  CitesWrong    *)
(* failing is the demonstration; a run where all 26 pass would mean the    *)
(* corpus had stopped showing anything.  It is deliberately NOT part of    *)
(* what harness/instance_demo.sh gates -- that gate covers L2Proofs.tla,   *)
(* which must be entirely green.                                          *)
(***************************************************************************)

EXTENDS L2, TLAPS

\* Wrong: two INSTANCE hops for an assumption that travelled by EXTENDS.
LEMMA AsmWrong ==
    /\ "none" \notin Ids
    /\ L1!L0!IsFiniteSet(Ids)
    /\ L1!IsFiniteSet(Slots) /\ Slots # {}
    /\ L1!IsFiniteSet(Buffers) /\ Buffers # {}
    /\ Ceiling \in Nat \ {0}
    BY NoneNotAnId, FiniteIds, FiniteSlots, FiniteBuffers, CeilingPositive, Zenon
    DEF L1!L0!IsFiniteSet, L1!IsFiniteSet, IsFiniteSet

\* Right: one hop, matching what L1Theorems' own assumptions became.
LEMMA AsmRight ==
    /\ "none" \notin Ids
    /\ L1!IsFiniteSet(Ids)
    /\ L1!IsFiniteSet(Slots) /\ Slots # {}
    /\ L1!IsFiniteSet(Buffers) /\ Buffers # {}
    /\ Ceiling \in Nat \ {0}
    BY NoneNotAnId, FiniteIds, FiniteSlots, FiniteBuffers, CeilingPositive, Zenon
    DEF L1!IsFiniteSet, IsFiniteSet

THEOREM CitesWrong == L1!IndInv => L1!SafetyCore
    BY AsmWrong, L1!IndInvImpliesSafetyCore, Zenon

THEOREM CitesRight == L1!IndInv => L1!SafetyCore
    BY AsmRight, L1!IndInvImpliesSafetyCore, Zenon

\* The escape hatch, for when the right name is not obvious: unfold both
\* copies at the citation and let the prover bridge them itself.  It works,
\* and it costs -- the two definitions enter the obligation expanded.
THEOREM CitesBridged == L1!IndInv => L1!SafetyCore
    BY AsmWrong, L1!IndInvImpliesSafetyCore, Zenon
    DEF L1!IsFiniteSet, L1!L0!IsFiniteSet
=====================================================================
