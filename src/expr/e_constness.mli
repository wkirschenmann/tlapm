(* Detect constant operators.

Copyright (C) 2008-2010  INRIA and Microsoft Corporation
*)
open E_t
open E_visit


(* returns the const value of the term *)
val is_const : 'a Property.wrapped -> bool
(* checks if const was already computed for this term *)
val has_const : 'a Property.wrapped -> bool

class virtual const_visitor : object
  inherit [unit] E_visit.map
  method ix_lookup : E_t.hyp Deque.dq -> int -> E_t.hyp option
  (* De Bruijn index resolution used by the [Ix] case; defaults to
     [Deque.nth ~backwards:true cx (n - 1)].  Overridable so a caller
     that controls the visit can answer in O(1). *)
end
