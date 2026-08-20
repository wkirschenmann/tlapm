open Util
open Prover

let prover_mutex = Eio.Mutex.create ()

(* Separated form the type [t] to have the value lazily evaluated. *)
module Parsed = struct
  type t = {
    mule : (Tlapm_lib.Module.T.mule, string) result;
    nts : Toolbox.tlapm_notif list;
    ps : Proof_step.t option;
        (** Parsed document structure, a tree of proof steps. It is obtained by
            parsing the document and then updated when obligation proof states
            are received from the prover. *)
  }

  let make ~uri ~(doc_vsn : Doc_vsn.t) ~(ps_prev : Proof_step.t option)
      ?prev_text ~parser () =
    (* Probe (TLAPM_LSP_PHASES=1): per-version cost attribution of the
       in-process pipeline — parse+elaboration+generation vs the
       proof-step tree build (which fingerprints every obligation).
       Inert without the environment variable. *)
    let phases = Sys.getenv_opt "TLAPM_LSP_PHASES" <> None in
    (* Scoped generation (TLAPM_LSP_SCOPED=2): when the edit satisfies
       the body-only criterion, tell the pipeline to generate proofs
       only for the edited step's line window; the missing obligations
       are carried from the previous version in Proof_step. *)
    let gen_scope =
      match Sys.getenv_opt "TLAPM_LSP_SCOPED" with
      | Some lvl when String.trim lvl = "2" -> (
          match (ps_prev, prev_text) with
          | Some ps, Some ot ->
              Proof_step.gen_scope_lines ~prev:ps ~old_text:ot
                ~new_text:(Doc_vsn.text doc_vsn)
          | _ -> None)
      | _ -> None
    in
    let t0 = if phases then Unix.gettimeofday () else 0. in
    match
      Eio.Mutex.use_rw ~protect:true prover_mutex @@ fun () ->
      Tlapm_lib.lsp_gen_scope := gen_scope;
      Fun.protect
        ~finally:(fun () -> Tlapm_lib.lsp_gen_scope := None)
        (fun () ->
          parser ~content:(Doc_vsn.text doc_vsn)
            ~filename:(LspT.DocumentUri.to_path uri))
    with
    | Ok mule ->
        let t1 = if phases then Unix.gettimeofday () else 0. in
        let texts =
          (* Only usable when [ps_prev] was built from exactly this
             text (see [make] below): the positional fingerprint
             carry-over needs the matching baseline. *)
          Option.map (fun ot -> (ot, Doc_vsn.text doc_vsn)) prev_text
        in
        let ps = Proof_step.of_module mule ?prev:ps_prev ?texts in
        if phases then begin
          let t2 = Unix.gettimeofday () in
          Printf.eprintf
            "[LSP_PHASES] parse+elab+gen=%.2fs steps+fp=%.2fs total=%.2fs\n%!"
            (t1 -. t0) (t2 -. t1) (t2 -. t0)
        end;
        { mule = Ok mule; nts = []; ps }
    | Error (loc_opt, msg) ->
        let nts = [ Toolbox.notif_of_loc_msg loc_opt msg ] in
        { mule = Error msg; nts; ps = None }

  let ps_if_ready (p : t Lazy.t) =
    match Lazy.is_val p with false -> None | true -> (Lazy.force p).ps
end

type t = {
  uri : LspT.DocumentUri.t;
  doc_vsn : Doc_vsn.t;
  p_ref : int;
  ps_prev : Proof_step.t option;
      (** Proof steps from the previous version, if there was any.*)
  parser : Util.parser_fun;  (** Parser to use to parse the modules. *)
  parsed : Parsed.t Lazy.t;
      (** Parsed document and information derived from it. *)
}

(** Create new actual document based on the document version [doc_vsn] and port
    the current state from the previous actual document [prev_act], if provided.
*)
let make uri doc_vsn prev_act parser =
  match prev_act with
  | None ->
      (* There is no previous active document, we will not try
         to move the proof state from there. *)
      let parsed =
        lazy (Parsed.make ~uri ~doc_vsn ~ps_prev:None ~parser ()) in
      { uri; doc_vsn; p_ref = 0; ps_prev = None; parser; parsed }
  | Some prev_act ->
      (* We have the previous actual document, thus either use its
         parsed data, or the data it got from its previous. *)
      let ps_prev, prev_text =
        match Parsed.ps_if_ready prev_act.parsed with
        | None ->
            (* An older tree, from an unknown text: no positional
               carry-over baseline. *)
            (prev_act.ps_prev, None)
        | some -> (some, Some (Doc_vsn.text prev_act.doc_vsn))
      in
      let parsed =
        lazy (Parsed.make ~uri ~doc_vsn ~ps_prev ?prev_text ~parser ()) in
      { uri; doc_vsn; p_ref = prev_act.p_ref; ps_prev; parser; parsed }

let with_parser act parser = make act.uri act.doc_vsn (Some act) parser
let parser act = act.parser
let vsn act = Doc_vsn.version act.doc_vsn
let text act = Doc_vsn.text act.doc_vsn

let proof_res (act : t) : Doc_proof_res.t =
  let parsed = Lazy.force act.parsed in
  Doc_proof_res.make parsed.nts parsed.ps

let locate_proof_range (act : t) range =
  let parsed = Lazy.force act.parsed in
  Proof_step.locate_proof_range parsed.ps range

let get_proof_step_details act range =
  let parsed = Lazy.force act.parsed in
  Proof_step.locate_proof_step parsed.ps range

let prover_prepare (act : t) next_p_ref =
  (* Force it to be parsed, then prepare for the next proof session. *)
  match (Lazy.force act.parsed).ps with
  | None -> None
  | Some _ -> Some { act with p_ref = next_p_ref }

let prover_add_obl_provers (act : t) (p_ref : int) (obl_id : int)
    (provers : string list) =
  if act.p_ref = p_ref then
    let parsed = Lazy.force act.parsed in
    let ps = Proof_step.with_provers parsed.ps p_ref obl_id provers in
    let parsed = Lazy.from_val { parsed with ps } in
    Some { act with parsed }
  else None

let prover_add_obl (act : t) (p_ref : int) (obl : Toolbox.Obligation.t) =
  if act.p_ref = p_ref then
    let parsed = Lazy.force act.parsed in
    let ps = Proof_step.with_prover_result parsed.ps p_ref obl in
    let parsed = Lazy.from_val { parsed with ps } in
    Some { act with parsed }
  else None

let prover_add_notif (act : t) p_ref notif =
  if act.p_ref = p_ref then
    let parsed = Lazy.force act.parsed in
    let nts = notif :: parsed.nts in
    let parsed = Lazy.from_val { parsed with nts } in
    Some { act with parsed }
  else None

let prover_terminated (act : t) p_ref =
  if act.p_ref = p_ref then
    let parsed = Lazy.force act.parsed in
    let ps = Proof_step.with_prover_terminated parsed.ps p_ref in
    let parsed = Lazy.from_val { parsed with ps } in
    Some { act with parsed }
  else None

let is_obl_final (act : t) p_ref obl_id =
  if act.p_ref = p_ref then
    let parsed = Lazy.force act.parsed in
    Proof_step.is_obl_final parsed.ps p_ref obl_id
  else None

(* The payload of a forked in-process prove request: the elaborated
   module and all its obligations in document order (the proof-step
   pool carries them all, including the ones carried across versions
   under scoped generation).  [None] when the module failed to parse —
   the caller then falls back to spawning a tlapm child. *)
let prove_payload (act : t) =
  (* Same gate as the prover: only pay the collection walk when the
     forked path can consume it. *)
  if Sys.getenv_opt "TLAPM_LSP_FORK" <> Some "1" then None
  else
    let parsed = Lazy.force act.parsed in
    match parsed.mule with
    | Error _ -> None
    | Ok mule -> Some (mule, Proof_step.all_obligations parsed.ps)

let on_parsed_mule (act : t) f =
  let parsed = Lazy.force act.parsed in
  match parsed.mule with
  | Ok mule -> f mule (Option.get parsed.ps)
  | Error _ -> None
