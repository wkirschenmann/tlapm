(* Elaborate expressions

Copyright (C) 2008-2010  INRIA and Microsoft Corporation
*)
open Deque
open E_t

val desugar : (string list E_visit.scx -> expr -> expr) ->
              (string list E_visit.scx -> expr -> expr) ->
              string list E_visit.scx -> expr -> expr

  (* moved to action frontend *)
(* val prime_normalize : hyp Deque.dq -> expr -> expr *)
val normalize : hyp Deque.dq -> expr -> expr

val non_temporal : expr -> bool
(* The pieces of [normalize], per hypothesis, for callers that fold a
   context with a cross-obligation prefix cache (Backend.Prep): the
   except pass runs only when [non_temporal] holds of the whole sequent,
   then the let pass, each hypothesis visited in the scx of its own
   pass's already-visited prefix — exactly the visitors' sequent case. *)
val except_normalize : unit E_visit.scx -> expr -> expr
val let_normalize : unit E_visit.scx -> expr -> expr
val except_normalize_hyp : unit E_visit.scx -> hyp -> unit E_visit.scx * hyp
val let_normalize_hyp : unit E_visit.scx -> hyp -> unit E_visit.scx * hyp

val replace_at : unit E_visit.scx -> expr -> expr -> expr
val get_at : expr -> expr
