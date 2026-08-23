---------------------------- MODULE L0 ----------------------------
EXTENDS L0State

TypeOK    == owner \in [Ids -> Slots \cup {"none"}] /\ live \subseteq Ids
Invariant == TypeOK /\ \A i \in live: owner[i] # "none"
IndInv    == Invariant /\ IsFiniteSet(live)
vars      == <<owner, live>>
Next      == \E i \in Ids: live' = live \cup {i} /\ owner' = owner
=====================================================================
