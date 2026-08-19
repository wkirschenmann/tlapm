(* Generation of proof obligations.

Copyright (C) 2008-2010  INRIA and Microsoft Corporation
*)
open Proof.T
open M_t


val generate:
    Expr.T.hyp Deque.dq -> mule ->
        mule * obligation list * summary
val count_obligations: mule -> int
val count_obligations_split: mule -> int * int

(* Resumable obligation generation: [gen_stepper cx m] starts a
   traversal; [gen_step] returns the next unit's obligations in
   document order, or [None] when the traversal is over; [gen_summary]
   is the summary accumulated so far (complete once [gen_step] has
   returned [None]). *)
type gen_stepper
val gen_stepper: Expr.T.hyp Deque.dq -> mule -> gen_stepper
val gen_step: gen_stepper -> obligation list option
val gen_summary: gen_stepper -> summary
val collect_usables: mule -> usable option
