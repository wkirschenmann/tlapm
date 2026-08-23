------------------------ MODULE L1Theorems ------------------------
EXTENDS L1

THEOREM IndInvImpliesInvariant == IndInv => Invariant
THEOREM IndInvPreserved       == IndInv /\ [Next]_vars => IndInv'
THEOREM RefinesL0             == IndInv => L0!IndInv
=====================================================================
