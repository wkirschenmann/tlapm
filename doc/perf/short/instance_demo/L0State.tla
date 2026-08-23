-------------------------- MODULE L0State --------------------------
(***************************************************************************)
(* Level 0's parameters, state and standing assumptions.                    *)
(*                                                                         *)
(* FiniteSets arrives here and nowhere else, which is the point of the     *)
(* corpus: there is exactly one IsFiniteSet in the source, and what is     *)
(* being demonstrated is how many copies of it INSTANCE makes.  Naturals   *)
(* and Sequences come in at the same place for the same reason.            *)
(***************************************************************************)
EXTENDS FiniteSets, Naturals, Sequences

CONSTANTS Ids,          \* call identifiers
          Slots,        \* the finite pool a call may own
          Payloads      \* what a call may have queued

VARIABLES owner,        \* Ids -> Slots \cup {"none"}
          live,         \* SUBSET Ids
          pending,      \* Ids -> Seq(Payloads)
          journal,      \* Seq(Ids)
          phase         \* Ids -> a four-state lifecycle

ASSUME FiniteIds    == IsFiniteSet(Ids)
ASSUME FiniteSlots  == IsFiniteSet(Slots) /\ Slots # {}
ASSUME NoneNotAnId  == "none" \notin Ids
=====================================================================
