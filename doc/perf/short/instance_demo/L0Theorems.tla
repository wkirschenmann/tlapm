------------------------ MODULE L0Theorems ------------------------
(* Level 0's citable interface: what holds, proofs elsewhere.  A theorem *)
(* with no proof is exactly how the real stack separates the interface   *)
(* from the proof module, and it is what makes the citation the subject. *)
EXTENDS L0

THEOREM IndInvImpliesInvariant == IndInv => Invariant
THEOREM IndInvPreserved       == IndInv /\ [Next]_vars => IndInv'
THEOREM OwnersAreFinite       == IndInv => IsFiniteSet(live)

THEOREM P1Holds == IndInv => P1
THEOREM P2Holds == IndInv => P2
THEOREM P3Holds == IndInv => P3
THEOREM P4Holds == IndInv => P4
THEOREM P5Holds == IndInv => P5
THEOREM P6Holds == IndInv => P6
THEOREM P7Holds == IndInv => P7
THEOREM P8Holds == IndInv => P8
=====================================================================
