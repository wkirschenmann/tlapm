------------------------ MODULE L1Theorems ------------------------
EXTENDS L1

THEOREM IndInvImpliesSafetyCore == IndInv => SafetyCore
THEOREM IndInvPreserved        == IndInv /\ [Next]_vars => IndInv'
THEOREM RefinesL0              == IndInv => L0!IndInv

THEOREM Q1Holds == IndInv => BufferTypeOK
THEOREM Q2Holds == IndInv => HeldAgreesWithArena
THEOREM Q3Holds == IndInv => ChargeUnderCeiling
THEOREM Q4Holds == IndInv => ArenaCoversQueue
THEOREM Q5Holds == IndInv => CreditMatchesArena
THEOREM Q6Holds == IndInv => ArenaRespectsPhase
THEOREM Q7Holds == IndInv => NoBufferOutlivesItsCall
THEOREM Q8Holds == IndInv => RefinementCoupling
=====================================================================
