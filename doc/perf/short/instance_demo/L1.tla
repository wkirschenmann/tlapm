---------------------------- MODULE L1 ----------------------------
(***************************************************************************)
(* Level 1's specification.  Its properties are compositional: each names   *)
(* level-0 properties through the instance prefix AND constrains its own    *)
(* state, which is what makes a refinement layer's definitions heavier than *)
(* the layer below and is the growth this corpus exists to exhibit.         *)
(***************************************************************************)
EXTENDS L1State

(* The one INSTANCE at this level.  No WITH: every parameter of L0Theorems  *)
(* is matched by the identically named declaration reaching here through    *)
(* EXTENDS L0State.                                                        *)
L0 == INSTANCE L0Theorems

BufferTypeOK ==
    /\ held \in [Buffers -> Ids \cup {"none"}]
    /\ charge \in [Buffers -> Nat]
    /\ arena \in [Ids -> SUBSET Buffers]
    /\ credit \in [Ids -> Nat]

HeldAgreesWithArena ==
    /\ \A b \in Buffers: held[b] # "none" => b \in arena[held[b]]
    /\ \A i \in Ids: \A b \in arena[i]: held[b] \in {i, "none"}
    /\ \A b \in Buffers, c \in Buffers:
          (b # c /\ held[b] # "none") => ~(held[b] = held[c] /\ b = c)

ChargeUnderCeiling ==
    /\ \A b \in Buffers: charge[b] <= Ceiling
    /\ \A i \in Ids: \A b \in arena[i]: charge[b] <= Ceiling
    /\ \A b \in Buffers: held[b] = "none" => charge[b] = 0

ArenaCoversQueue ==
    /\ \A i \in live: Len(pending[i]) <= Cardinality(arena[i])
    /\ \A i \in Ids \ live: arena[i] = {}
    /\ \A i \in Ids: Len(pending[i]) > 0 => arena[i] # {}

CreditMatchesArena ==
    /\ \A i \in Ids: credit[i] <= Cardinality(Buffers)
    /\ \A i \in live: credit[i] = 0 => arena[i] = {}
    /\ \A i \in Ids: ~(credit[i] > 0 /\ phase[i] = "closed")

ArenaRespectsPhase ==
    \A i \in Ids:
        phase[i] = "closing" =>
            /\ \A b \in arena[i]: held[b] = i
            /\ credit[i] <= Cardinality(arena[i])
            /\ Len(pending[i]) <= credit[i] + Cardinality(arena[i])

NoBufferOutlivesItsCall ==
    /\ \A b \in Buffers: held[b] \in live \cup {"none"}
    /\ \A i \in Ids \ live: \A b \in Buffers: held[b] # i
    /\ \A b \in Buffers: held[b] # "none" => phase[held[b]] # "closed"

RefinementCoupling ==
    /\ L0!SafetyCore
    /\ \A i \in live: owner[i] # "none" => arena[i] # {} \/ credit[i] = 0
    /\ \A b \in Buffers:
          held[b] # "none" => owner[held[b]] \in Slots \cup {"none"}

SafetyCore ==
    /\ L0!SafetyCore
    /\ BufferTypeOK
    /\ HeldAgreesWithArena
    /\ ChargeUnderCeiling

IndInv ==
    /\ L0!IndInv
    /\ SafetyCore
    /\ ArenaCoversQueue
    /\ CreditMatchesArena
    /\ ArenaRespectsPhase
    /\ NoBufferOutlivesItsCall
    /\ RefinementCoupling
    /\ IsFiniteSet(Buffers)

vars == <<owner, live, pending, journal, phase, held, charge, arena, credit>>

Next ==
    /\ L0!Next
    /\ UNCHANGED <<held, charge, arena, credit>>
=====================================================================
