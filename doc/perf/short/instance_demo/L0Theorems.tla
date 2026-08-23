------------------------ MODULE L0Theorems ------------------------
(***************************************************************************)
(* Level 0's citable interface: what holds, with the proofs elsewhere.  A   *)
(* theorem with no proof is exactly how a refinement stack separates the    *)
(* interface from the proof module, and it is what makes the citation --    *)
(* rather than the discharge -- the subject of this corpus.                 *)
(***************************************************************************)
EXTENDS L0

THEOREM IndInvImpliesSafetyCore == IndInv => SafetyCore
THEOREM IndInvPreserved        == IndInv /\ [Next]_vars => IndInv'
THEOREM LiveIsFinite           == IndInv => IsFiniteSet(live)

THEOREM P1Holds == IndInv => TypeOK
THEOREM P2Holds == IndInv => SlotsAreNotShared
THEOREM P3Holds == IndInv => PhaseMatchesLiveness
THEOREM P4Holds == IndInv => QueueBounded
THEOREM P5Holds == IndInv => JournalMentionsKnownIds
THEOREM P6Holds == IndInv => ClosingDrains
THEOREM P7Holds == IndInv => OwnedImpliesQueueable
THEOREM P8Holds == IndInv => NoOrphanPayload
=====================================================================
