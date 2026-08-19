(* Generation of proof obligations.

Copyright (C) 2008-2010  INRIA and Microsoft Corporation
*)
open Ext
open Property

open Expr.T
open Expr.Subst
open Proof.T

open M_t


(* let debug = Printf.eprintf *)


(* [generate] is expressed as a resumable stepper so that a caller can
   consume obligations module-unit by module-unit — numbering, preparing
   and proving them before the whole module has been traversed (the
   lazy-generation track).  [gen_step] returns the next unit's
   obligations (a theorem's, or a module-level USE/HIDE's), in document
   order; when the traversal is over it returns [None] and the rewritten
   module is available in [gs_result].  The eager [generate] below
   drains the stepper and presents the historical interface; its
   behavior is unchanged. *)

type gen_frame = {
  gf_mule : mule ;                       (* module being rebuilt *)
  gf_wrap : modunit option ;             (* enclosing [Submod] unit *)
  mutable gf_cx : hyp Deque.dq ;         (* running context *)
  mutable gf_todo : modunit list ;       (* units not yet visited *)
  mutable gf_done : modunit list ;       (* rewritten units, reversed *)
}

type gen_stepper = {
  mutable gs_stack : gen_frame list ;
  mutable gs_summ : summary ;
  mutable gs_result : mule option ;      (* set when the traversal ends *)
  gs_only : (Loc.locus -> bool) option ;
      (* Scoped generation: a theorem whose locus fails this predicate
         is traversed for its context contribution only — its proof is
         neither generated nor collected, so it yields no obligations.
         The caller owns supplying those obligations by other means
         (the LSP carries them from the previous document version). *)
}

let gen_stepper ?only cx m = {
  gs_stack = [ { gf_mule = m ; gf_wrap = None ; gf_cx = cx ;
                 gf_todo = m.core.body ; gf_done = [] } ] ;
  gs_summ = empty_summary ;
  gs_result = None ;
  gs_only = only ;
}

let rec gen_step st =
  match st.gs_stack with
  | [] -> None
  | fr :: rest -> begin
      match fr.gf_todo with
      | [] ->
          let m = { fr.gf_mule with
                    core = { fr.gf_mule.core with
                             body = List.rev fr.gf_done } } in
          st.gs_stack <- rest ;
          begin match rest, fr.gf_wrap with
          | parent :: _, Some mu ->
              parent.gf_done <- (Submod m @@ mu) :: parent.gf_done ;
              gen_step st
          | [], None ->
              st.gs_result <- Some m ;
              None
          | _ ->
              Errors.bug "Module.Gen.gen_step: inconsistent stack"
          end
      | mu :: mus ->
          fr.gf_todo <- mus ;
          begin match mu.core with
          | Theorem (nm, sq, naxs, prf, prf_orig, _) ->
              let cx = match nm with
                | Some nm ->
                    Deque.snoc fr.gf_cx
                      (Defn (Operator (nm, exprify_sequent sq @@ nm)
                       @@ mu, Proof Always , Visible, Export) @@ mu)
                | _ ->
                    fr.gf_cx
              in
              let in_scope =
                match st.gs_only with
                | None -> true
                | Some f ->
                    (match Util.query_locus mu with
                     | Some loc -> f loc
                     | None -> true)
              in
              if not in_scope then begin
                (* context contribution only: same [cx] flow as below,
                   the proof left as parsed, no obligations *)
                let he = if nm = None then exprify_sequent sq else Ix 1 in
                fr.gf_cx <- Deque.snoc cx (Fact (he @@ mu, Hidden, Always) @@ mu) ;
                fr.gf_done <- mu :: fr.gf_done ;
                gen_step st
              end else
              let prf, obs, summ =
                let psq = if nm = None then sq else app_sequent (shift 1) sq in
                (* the addition of the sequent context to the global context
                 * might invalidate the later generality. I.e. the added
                 * assumptions from the sequent might prevent the boxifying of
                 * all assumptions *)
                let psq = { psq with context = Deque.append cx psq.context } in
                let time_flag = Expr.Temporal_props.check_time_change
                psq.context Always in
                Proof.Gen.reset_stats () ;
                let prf = Proof.Gen.generate psq prf time_flag in
                let (obs, prf) = Proof.Gen.collect prf in
                let sts = Proof.Gen.get_stats () in
                let summ = { sum_total = sts.Proof.Gen.total
                           ; sum_absent = (List.length sts.Proof.Gen.absent, sts.Proof.Gen.absent)
                           ; sum_omitted = (List.length sts.Proof.Gen.omitted, sts.Proof.Gen.omitted)
                           ; sum_suppressed = (List.length sts.Proof.Gen.suppressed, sts.Proof.Gen.suppressed)
                           } in
                prf, obs, summ in
              st.gs_summ <- cat_summary st.gs_summ summ ;
              let mu = { mu with core = Theorem (nm, sq, naxs, prf, prf_orig, summ) } in
              let he = if nm = None then exprify_sequent sq else Ix 1 in
              fr.gf_cx <- Deque.snoc cx (Fact (he @@ mu, Hidden, Always) @@ mu) ;
              fr.gf_done <- mu :: fr.gf_done ;
              if obs = [] then gen_step st else Some obs
          | Submod m ->
              st.gs_stack <-
                { gf_mule = m ; gf_wrap = Some mu ; gf_cx = fr.gf_cx ;
                  gf_todo = m.core.body ; gf_done = [] } :: st.gs_stack ;
              gen_step st
          | Mutate (uh, us) ->
              let (cx, obs) = Proof.Gen.mutate fr.gf_cx uh (us @@ mu) Always in
              fr.gf_cx <- cx ;
              fr.gf_done <- mu :: fr.gf_done ;
              if obs = [] then gen_step st else Some obs
          | Anoninst _ ->
              Errors.bug ~at:mu "Module.Gen.generate: unnamed INSTANCE"
          | _ ->
              fr.gf_cx <- Deque.append_list fr.gf_cx (hyps_of_modunit mu) ;
              fr.gf_done <- mu :: fr.gf_done ;
              gen_step st
          end
    end

(* Count the obligations [generate] would return, without running it:
   a pure walk of the module units and proof trees — no contexts, no
   sequents.  Lets the caller announce the obligation total before a
   lazy generation pass has produced anything; kept in lockstep with
   [gen_step] above (checked by the TLAPM_COUNT_CHECK probe in
   Module.Elab.normalize). *)
let rec count_obligations_split m =
  List.fold_left begin fun (n, o) mu ->
    match mu.core with
    | Theorem (_, _, _, prf, _, _) ->
        let (n', o') = Proof.Gen.count_proof_split prf in (n + n', o + o')
    | Submod sm ->
        let (n', o') = count_obligations_split sm in (n + n', o + o')
    | Mutate (`Use _, us) -> (n + List.length us.facts, o)
    | Mutate (`Hide, _) -> (n, o)
    | _ -> (n, o)
  end (0, 0) m.core.body

let count_obligations m = fst (count_obligations_split m)

let gen_summary st = st.gs_summ

let generate ?only cx m =
  let st = gen_stepper ?only cx m in
  let rec drain acc = match gen_step st with
    | Some obs -> drain (List.rev_append obs acc)
    | None -> List.rev acc
  in
  let obs = drain [] in
  match st.gs_result with
  | Some m -> (m, obs, st.gs_summ)
  | None -> Errors.bug "Module.Gen.generate: traversal ended without a result"

(****************************************************************************)

let step_name x = match Property.query x Props.step with
  | None -> 0,""
  | Some (Named (sn, sl, _)) -> (sn,sl)
  | Some (Unnamed (sn, sid)) -> (sn,"")

let toolbox_consider prf =
  let loc = Option.get (Util.query_locus prf) in
    (!Params.tb_sl-1 < (Loc.line loc.Loc.start))
  && ((Loc.line loc.Loc.stop) < !Params.tb_el+1)

let p_collect_usables prf : Proof.T.usable list =
  let coll = ref [] in
  let main_step = ref (0,"") in
  let toolbox_main n = (!Params.tb_sl = n) in
  let visitor = object (self : 'self)
    inherit [unit] Proof.Visit.iter as super
    method step scx st =
      let loc = Option.get (Util.query_locus st) in
      if toolbox_main (Loc.line loc.Loc.start)
        then main_step := (step_name st) else ();
      super#step scx st
    method proof scx prf =
      match prf.core with
      | By (u,_) when toolbox_consider prf ->
          let ff = List.filter (fun e ->
            match e.core with
            | Opaque s when s.[0] = '<' ->
                let parse_step s =
                    if Str.string_match (Str.regexp "<\\([0-9].*\\)>\\(.*\\)") s 0 then
                  (int_of_string (Str.matched_group 1 s), Str.matched_group 2 s)
                    else (0,"")
                    in
                let sn,sl = parse_step s in
                if sn < (fst !main_step) then true else
                   sn = (fst !main_step) && String.compare sl (snd !main_step) <= 0
            | _ -> true
            ) u.facts in
          let u = {u with facts = ff} in
          if u.facts = [] && u.defs = [] then () else coll := u :: !coll
      | Steps (inits, ({core = Qed pq} as q)) ->
          let scx = self#steps scx inits in
          let loc = Option.get (Util.query_locus pq) in
          if toolbox_main ((Loc.line loc.Loc.start) - 1)
            then main_step := (step_name q) else ();
          self#proof scx pq
      | _ ->
          super#proof scx prf
  end in
  visitor#proof ((), Deque.empty) prf;
  List.rev !coll

let collect_usables (m:mule) : Proof.T.usable option =
  let remove_repeated_ex es =
    let e_mem e es = List.exists (Expr.Eq.expr e) es in
    List.fold_left (fun r e -> if e_mem e r then r else e :: r) [] es
    |> List.rev
  in
  let remove_repeated_def (ds:use_def wrapped list) =
    let use_def_eq d e =
      match d.core, e.core with
      | Dvar s, Dvar t when s = t -> true
      | Dx n, Dx m when n = m -> true
      | _ -> false
    in
    let e_mem x ds = List.exists (use_def_eq x) ds in
    List.fold_left (fun r e -> if e_mem e r then r else e :: r) [] ds
    |> List.rev
  in

  let mloc = Option.get (Util.query_locus m) in
  let rec visit (mus:modunit list) =
    match mus with
    | [] -> []
    | mu :: mus -> begin
        match mu.core with
        | Theorem (nm, _, _, _, prf_orig, _)
            when !Params.toolbox
              (* && (not !Params.toolbox_all) *) ->
            let loc = Option.get (Util.query_locus prf_orig) in
            if loc.Loc.file = mloc.Loc.file
            then begin
             (List.rev (p_collect_usables prf_orig)) @ visit mus
            end
            else visit mus
        | Submod _ ->
            visit mus
        | Mutate (_, us) -> (** more usables here *)
            visit mus
        | Anoninst _ ->
            Errors.bug ~at:mu "collect_usables: unnamed INSTANCE"
        | _ ->
            visit mus
      end
  in
  let us = visit m.core.body in
  let ffs,dds = List.fold_left (fun (fs,ds) u -> (u.facts @ fs, u.defs @ ds)) ([],[]) us in
  let ffs = remove_repeated_ex ffs in
  let dds = remove_repeated_def dds in
  if ffs = [] && dds = [] then None else Some { facts = ffs ; defs = dds }
