(*
 * property.ml --- properties
 *
 *
 * Copyright (C) 2008-2010  INRIA and Microsoft Corporation
 *)

(** Property lists implemented using unsafe ocaml features *)

open Ext

type uuid = Int64.t * Int64.t
[@@deriving show]

let uuid_of_string s : uuid =
  assert (String.length s = 36) ;
  assert (s.[8] = '-' && s.[13] = '-' && s.[18] = '-' && s.[23] = '-') ;
  Scanf.sscanf s "%8Lx-%4Lx-%4Lx-%4Lx-%12Lx" begin
    fun a b c d e ->
      let a = Int64.shift_left a 32 in
      let b = Int64.shift_left b 16 in
      let l = Int64.logor (Int64.logor a b) c in
      let d = Int64.shift_left d 48 in
      let r = Int64.logor d e in
      (l, r)
  end

type pid =
  | Pid of int
  | Puuid of uuid
[@@deriving show]

type prop = pid * Obj.t

let pp_prop_name (fmt : Format.formatter) (p : prop) : unit =
  let (pid, _obj) = p in
  Format.fprintf fmt "prop[pid=%a]" pp_pid pid

(* [(Pid(7), Obj.t); ...]  *)
type props = prop list

let pp_prop_names (fmt : Format.formatter) (ps : props) : unit =
  Format.fprintf fmt "[%a]" (Format.pp_print_list pp_prop_name) ps

type 'a pfuncs = {
  get : prop -> 'a ;
  set : 'a -> prop ;
  pid : pid ;
  rep : string ;
}

let ids : int ref = ref 0

let fresh () = incr ids ; !ids

let pid (id, _) = id

(* Property lookups run on every property read of every node visit —
   they are among the hottest paths of the whole prover.  Pid equality
   is therefore monomorphic (the generic structural equality is a C
   call per list element), and the lookups below are direct loops: no
   closure per call, no [Not_found] round-trip on a miss ([query]
   misses are the common case). *)
let pid_eq a b =
  match a, b with
  | Pid i, Pid j -> i = j
  | Puuid (a1, a2), Puuid (b1, b2) -> Int64.equal a1 b1 && Int64.equal a2 b2
  | Pid _, Puuid _ | Puuid _, Pid _ -> false

let make ?uuid rep =
  let pid = match uuid with
    | Some uus -> Puuid (uuid_of_string uus)
    | None -> Pid (fresh ())
  in
  let set x = (pid, Obj.repr x) in
  let get (qid, ob) =
    if pid_eq pid qid then Obj.obj ob
    else invalid_arg "Property.get"
  in
    { get = get ; set = set
    ; pid = pid ; rep = rep }

type 'a wrapped = {
  core : 'a ;
  props : props ;
}

let rec mem_prop pid = function
  | [] -> false
  | (qid, _) :: rest -> pid_eq pid qid || mem_prop pid rest

let rec find_prop pid = function
  | [] -> raise Not_found
  | ((qid, _) as p) :: rest -> if pid_eq pid qid then p else find_prop pid rest

let has w pf =
  mem_prop pf.pid w.props

let get w pf =
  pf.get (find_prop pf.pid w.props)

let query w pf =
  let rec go = function
    | [] -> None
    | ((qid, _) as p) :: rest ->
        if pid_eq pf.pid qid then Some (pf.get p) else go rest
  in
  go w.props

let assign w pf v =
  { w with
    props = pf.set v :: List.filter (fun p -> not (pid_eq pf.pid (fst p))) w.props }

let with_prop pf v w = assign w pf v

let remove w pf =
  { w with props = List.filter (fun p -> not (pid_eq pf.pid (fst p))) w.props }

let unwrap x = x.core

let noprops x = { core = x ; props = [] }

let nowhere : unit wrapped = noprops ()

(* adds (only) new properties from bw to aw *)
let ( $$ ) aw bw =
  let forall_fun i2 = function
    | (Pid i,_) -> i <> i2
    | _ -> true in
  let filter_fun = function
    | (Pid i,_) -> List.for_all (forall_fun i) aw.props
    | _ -> true in
  let pr = List.append aw.props (List.filter filter_fun bw.props) in
  {aw with props = pr}

let ( @@ ) a bw = { bw with core = a }

let ( %% ) a ps = { core = a ; props = ps }

(** {6 unsafe} *)

let unsafe_con e =
  let er = Obj.repr e.core in
    Obj.tag er

external props_of_value : 'a -> props = "%field0"

let props_of a =
  if Obj.is_int (Obj.repr a) then props_of_value a     (* FIXME BUG *)
  else invalid_arg "props_of"

let unsafe_has a pf =
  mem_prop pf.pid (props_of a)

let unsafe_get a pf = (* should this be really unsafe ? *)
  try pf.get (find_prop pf.pid (props_of a))
  with Not_found -> assert false

let unsafe_query a pf =
  let rec go = function
    | [] -> None
    | ((qid, _) as p) :: rest ->
        if pid_eq pf.pid qid then Some (pf.get p) else go rest
  in
  go (props_of a)

let unsafe_assign (a : 'a) pf v : 'a =
  let br = Obj.dup (Obj.repr a) in
    Obj.set_field br 0 begin
      Obj.repr
        (pf.set v
         :: List.filter (fun p -> not (pid_eq pf.pid (fst p))) (props_of a))
    end ;
    Obj.obj br


let print_prop = function
  | (Pid i, _) -> print_int i
  | (Puuid (i1,i2), _) ->  print_string (Int64.to_string i1); print_string (Int64.to_string i2)

let print_all_props = function
  | {props = ls} -> List.iter print_prop ls
