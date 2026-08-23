---------------------------- MODULE L2 ----------------------------
EXTENDS L1State

(* Level 2's instance of level 1.  Level 0 is not instantiated here: it  *)
(* arrives inside the copy of L1Theorems, already carrying its own       *)
(* prefix, as L1!L0!.                                                   *)
L1 == INSTANCE L1Theorems
=====================================================================
