------------------------ MODULE L1Theorems ------------------------
EXTENDS L1

THEOREM IndInvImpliesInvariant == IndInv => Invariant
THEOREM IndInvPreserved       == IndInv /\ [Next]_vars => IndInv'
THEOREM RefinesL0             == IndInv => L0!IndInv

THEOREM Q1Holds == IndInv => Q1
THEOREM Q2Holds == IndInv => Q2
THEOREM Q3Holds == IndInv => Q3
THEOREM Q4Holds == IndInv => Q4
THEOREM Q5Holds == IndInv => Q5
THEOREM Q6Holds == IndInv => Q6
THEOREM Q7Holds == IndInv => Q7
THEOREM Q8Holds == IndInv => Q8
=====================================================================
