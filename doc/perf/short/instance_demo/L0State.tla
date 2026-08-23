-------------------------- MODULE L0State --------------------------
(* Level 0's parameters and standing assumptions.  FiniteSets arrives   *)
(* here by EXTENDS and never anywhere else, which is the point: there is *)
(* exactly one IsFiniteSet in the source, and the demonstration is how   *)
(* many copies of it INSTANCE makes.                                     *)
EXTENDS FiniteSets

CONSTANTS Ids, Slots
VARIABLES owner, live

ASSUME FiniteIds == IsFiniteSet(Ids)
ASSUME NoneNotAnId == "none" \notin Ids
=====================================================================
