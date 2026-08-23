---------------------------- MODULE L0 ----------------------------
(* Level 0's specification, plus the eight named properties its theorems *)
(* module declares.  They are deliberately shallow: the corpus exists to  *)
(* measure context handling, so every property is a one-line predicate   *)
(* over the level-0 variables and no prover ever has to work at it.      *)
EXTENDS L0State

TypeOK    == owner \in [Ids -> Slots \cup {"none"}] /\ live \subseteq Ids
Invariant == TypeOK /\ \A i \in live: owner[i] # "none"
IndInv    == Invariant /\ IsFiniteSet(live)
vars      == <<owner, live>>
Next      == \E i \in Ids: live' = live \cup {i} /\ owner' = owner

P1 == live \subseteq Ids
P2 == \A i \in live: owner[i] # "none"
P3 == IsFiniteSet(live)
P4 == owner \in [Ids -> Slots \cup {"none"}]
P5 == \A i \in Ids \ live: TRUE
P6 == "none" \notin live
P7 == \A i \in live: i \in Ids
P8 == live = {} \/ live # {}
=====================================================================
