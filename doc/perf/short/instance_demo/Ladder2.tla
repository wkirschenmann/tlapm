--------------------------- MODULE Ladder2 ---------------------------
(* 2 INSTANCE(s) of L1Theorems, one obligation.  Only the instance count *)
(* varies, so the context table below measures the copying and nothing    *)
(* else.                                                                 *)
EXTENDS L1State

J1 == INSTANCE L1Theorems
J2 == INSTANCE L1Theorems

THEOREM Probe == J1!IndInv => J1!Invariant
    BY J1!IndInvImpliesInvariant
=====================================================================
