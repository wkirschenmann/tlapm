------------------------ MODULE L0Theorems ------------------------
(* Level 0's citable interface: what holds, proofs elsewhere.  A theorem *)
(* with no proof is exactly how the real stack separates the interface   *)
(* from the proof module, and it is what makes the citation the subject. *)
EXTENDS L0

THEOREM IndInvImpliesInvariant == IndInv => Invariant
THEOREM IndInvPreserved       == IndInv /\ [Next]_vars => IndInv'
THEOREM OwnersAreFinite       == IndInv => IsFiniteSet(live)
=====================================================================
