---------------------------- MODULE L1 ----------------------------
EXTENDS L1State

(* The one INSTANCE at this level.  No WITH: every parameter of          *)
(* L0Theorems is matched by the identically named declaration reaching   *)
(* here through EXTENDS L0State.                                        *)
L0 == INSTANCE L0Theorems

TypeOK    == held \in [Buffers -> Ids \cup {"none"}]
Invariant == L0!Invariant /\ TypeOK
IndInv    == L0!IndInv /\ TypeOK /\ IsFiniteSet(Buffers)
vars      == <<owner, live, held>>
Next      == L0!Next /\ held' = held
=====================================================================
