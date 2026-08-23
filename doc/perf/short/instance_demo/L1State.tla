-------------------------- MODULE L1State --------------------------
(* Level 1 refines level 0.  It reaches level 0's parameters and         *)
(* assumptions by EXTENDS -- so no prefix -- and adds its own.           *)
EXTENDS L0State

CONSTANT Buffers
VARIABLE held

ASSUME FiniteBuffers == IsFiniteSet(Buffers) /\ Buffers # {}
=====================================================================
