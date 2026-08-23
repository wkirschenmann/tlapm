-------------------------- MODULE L1State --------------------------
(***************************************************************************)
(* Level 1 refines level 0.  It reaches level 0's parameters, state and     *)
(* assumptions by EXTENDS -- so with no prefix -- and adds its own.  That   *)
(* asymmetry is what CiteTrap.tla is about: EXTENDS does not rename,        *)
(* INSTANCE does.                                                          *)
(***************************************************************************)
EXTENDS L0State

CONSTANTS Buffers,      \* the buffer arena
          Ceiling       \* per-buffer charge limit

VARIABLES held,         \* Buffers -> Ids \cup {"none"}
          charge,       \* Buffers -> Nat
          arena,        \* Ids -> SUBSET Buffers
          credit        \* Ids -> Nat

ASSUME FiniteBuffers  == IsFiniteSet(Buffers) /\ Buffers # {}
ASSUME CeilingPositive == Ceiling \in Nat \ {0}
=====================================================================
