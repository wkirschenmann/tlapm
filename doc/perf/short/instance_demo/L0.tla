---------------------------- MODULE L0 ----------------------------
(***************************************************************************)
(* Level 0's specification and the eight named properties its theorems     *)
(* module declares.                                                        *)
(*                                                                         *)
(* The properties are written in the shape real refinement invariants take: *)
(* typing conjuncts over function spaces, quantified implications,          *)
(* negations, sequence lengths, cardinalities and nested application.  That *)
(* shape is the reason they are here.  A one-line predicate makes a         *)
(* definition that costs nothing to carry, and the quantity this corpus is  *)
(* about is what a context of definitions costs -- so the bodies have to be *)
(* of a realistic weight or the corpus measures the wrong thing.            *)
(*                                                                         *)
(* They are NOT proved anywhere, and do not need to be: level 0's theorems  *)
(* module declares them the way a citable interface does, with the proofs   *)
(* elsewhere.  What is exercised here is citation and context, not          *)
(* discharge.                                                              *)
(***************************************************************************)
EXTENDS L0State

Phases == {"idle", "open", "closing", "closed"}

TypeOK ==
    /\ owner \in [Ids -> Slots \cup {"none"}]
    /\ live \subseteq Ids
    /\ pending \in [Ids -> Seq(Payloads)]
    /\ journal \in Seq(Ids)
    /\ phase \in [Ids -> Phases]

SlotsAreNotShared ==
    /\ \A i \in live, j \in live:
          (i # j /\ owner[i] # "none") => owner[i] # owner[j]
    /\ \A i \in Ids \ live: owner[i] = "none"

PhaseMatchesLiveness ==
    /\ \A i \in live: phase[i] \in {"open", "closing"}
    /\ \A i \in Ids \ live: phase[i] \in {"idle", "closed"}
    /\ \A i \in Ids: phase[i] = "closed" => Len(pending[i]) = 0
    /\ \A i \in Ids: ~(phase[i] = "idle" /\ owner[i] # "none")

QueueBounded ==
    /\ \A i \in Ids: Len(pending[i]) <= Cardinality(Slots)
    /\ \A i \in live: owner[i] = "none" => Len(pending[i]) = 0
    /\ \A i \in Ids: Len(pending[i]) > 0 => phase[i] \in {"open", "closing"}

JournalMentionsKnownIds ==
    /\ \A n \in 1..Len(journal): journal[n] \in Ids
    /\ \A i \in live:
          phase[i] = "closing" => \E n \in 1..Len(journal): journal[n] = i
    /\ Len(journal) = 0 \/ journal[Len(journal)] \in Ids

ClosingDrains ==
    \A i \in Ids:
        phase[i] = "closing" =>
            /\ i \in live
            /\ owner[i] # "none"
            /\ \A k \in 1..Len(pending[i]): pending[i][k] \in Payloads

OwnedImpliesQueueable ==
    \A i \in live:
        owner[i] # "none" =>
            /\ owner[i] \in Slots
            /\ Len(pending[i]) <= Cardinality(Slots)
            /\ ~(phase[i] = "closed")

NoOrphanPayload ==
    /\ \A i \in Ids \ live: Len(pending[i]) = 0
    /\ \A i \in Ids: pending[i] \in Seq(Payloads)

SafetyCore ==
    /\ TypeOK
    /\ SlotsAreNotShared
    /\ PhaseMatchesLiveness
    /\ QueueBounded

IndInv ==
    /\ SafetyCore
    /\ JournalMentionsKnownIds
    /\ ClosingDrains
    /\ OwnedImpliesQueueable
    /\ NoOrphanPayload
    /\ IsFiniteSet(live)

vars == <<owner, live, pending, journal, phase>>

Next ==
    \E i \in Ids:
        /\ phase[i] = "idle"
        /\ live' = live \cup {i}
        /\ phase' = [phase EXCEPT ![i] = "open"]
        /\ UNCHANGED <<owner, pending, journal>>
=====================================================================
