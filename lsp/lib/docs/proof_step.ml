(* cspell:words mapi modunit summ stepno *)
open Util

(** Element of the original AST attached to the user-visible proof step. *)
module El = struct
  type t =
    | Module of TL.Module.T.mule
    | Theorem of {
        mu : TL.Module.T.modunit;
        name : TL.Util.hint option;
        sq : TL.Expr.T.sequent;
        naxs : int;
        pf : TL.Proof.T.proof;
        orig_pf : TL.Proof.T.proof;
        summ : TL.Module.T.summary;
      }
    | Mutate of { mu : TL.Module.T.modunit; usable : TL.Proof.T.usable }
    | Step of TL.Proof.T.step
    | Qed of TL.Proof.T.qed_step

  let pp_short fmt el =
    match el with
    | Module m ->
        Fmt.pf fmt "Module @%a %a" TL.Loc.pp_locus_compact_opt
          (TL.Util.query_locus m) Fmt.string m.core.name.core
    | Theorem { name; _ } ->
        Fmt.pf fmt "Theorem %a"
          (Fmt.option
             ~none:(fun fmt () -> Fmt.pf fmt "<unnamed>")
             TL.Util.pp_print_hint)
          name
    | Mutate _ -> Fmt.pf fmt "Mutate"
    | Step step ->
        Fmt.pf fmt "Step@%a" TL.Loc.pp_locus_compact_opt
          (TL.Util.query_locus step)
    | Qed qed ->
        Fmt.pf fmt "QED@%a" TL.Loc.pp_locus_compact_opt
          (TL.Util.query_locus qed)

  let pp = pp_short
  let show = Fmt.str "%a" pp
end

type t = {
  el : El.t;
      (** Kind/Type of this proof step along with the reference to the AST
          element. *)
  cx : TL.Expr.T.ctx;  (** Context of the element [el]. *)
  status_parsed : Proof_status.t option;
      (** Status derived at the parse time, if any. This is for the omitted or
          error cases. *)
  status_derived : Proof_status.t;
      (** Derived status. Here we sum-up the states from all the related
          obligations and sub-steps. *)
  full_range : Range.t;
      (** [step_loc] plus all the BY facts included. If an obligation is in
          [full_range] but not in the [step_loc], we consider it supplementary
          (will be shown a bit more hidden). *)
  head_range : Range.t;
      (** The location of the proof sequent. It is always contained within the
          [step_loc]. This is shown as a step in the UI. *)
  obs : Obl.t RangeMap.t;
      (** Obligations associated with this step. Here we include all the
          obligations fitting into [full_range], but not covered by any of the
          [sub] steps. *)
  sub : t list; (* Sub-steps, if any. *)
}

let rec pp_short fmt { el; sub; _ } =
  Fmt.pf fmt "@[{%a,@ sub=[@[%a@]]}@]" El.pp_short el (Fmt.list pp_short) sub

let pp = pp_short
let show = Fmt.str "%a" pp

(** We categorize the proof steps just to make the presentation in the UI
    clearer. *)
module Kind : sig
  type ps := t
  type t = Module | Struct | Leaf | Omitted [@@deriving show]

  val of_proof_step : ps -> t
  val to_string : t -> string
end = struct
  type t = Module | Struct | Leaf | Omitted

  let show = function
    | Module -> "module"
    | Struct -> "struct"
    | Leaf -> "leaf"
    | Omitted -> "omitted"

  let pp fmt k = Fmt.pf fmt "%s" (show k)
  let to_string = show

  let of_proof (pf : TL.Proof.T.proof) : t =
    match pf.core with
    | TL.Proof.T.Steps (_, _) -> Struct
    | TL.Proof.T.Omitted _ -> Omitted
    | TL.Proof.T.Obvious | TL.Proof.T.By _ | TL.Proof.T.Error _ -> Leaf

  let of_proof_step ps =
    match ps.el with
    | El.Module _ -> Module
    | El.Theorem { orig_pf; _ } -> of_proof orig_pf
    | El.Mutate _ -> Leaf
    | El.Step st -> (
        match st.core with
        | Assert (_, pf) -> of_proof pf
        | Suffices (_, pf) -> of_proof pf
        | Pcase (_, pf) -> of_proof pf
        | Pick (_, _, pf) -> of_proof pf
        | PickTuply (_, _, pf) -> of_proof pf
        | TL.Proof.T.Hide _ | TL.Proof.T.Define _ | TL.Proof.T.Use _
        | TL.Proof.T.Have _ | TL.Proof.T.Take _ | TL.Proof.T.TakeTuply _
        | TL.Proof.T.Witness _ | TL.Proof.T.Forget _ ->
            Leaf)
    | El.Qed qs -> ( match qs.core with TL.Proof.T.Qed pf -> of_proof pf)
end

(** Derived status is always a minimum of the parsed, the obligations and the
    sub-steps. *)
let derived_status parsed obs sub =
  let parsed = Option.value ~default:Proof_status.top parsed in
  let ps_min = Proof_status.min in
  let acc =
    RangeMap.fold
      (fun _ (obl : Obl.t) acc ->
        (* Do not count omitted obligations. *)
        if Obl.is_omitted obl then acc else ps_min acc (Obl.status obl))
      obs parsed
  in
  List.fold_left (fun acc sub -> ps_min acc sub.status_derived) acc sub

(** Takes step parameters and a set of remaining unassigned obligations,
    constructs the proof step and returns obligations that are left unassigned.
*)
let make ~el ~cx ~status_parsed ~head_range ~full_range =
  let head_range =
    (* Take the beginning of the first line, if header location is unknown. *)
    match head_range with
    | Some head_range -> Range.(of_points (from full_range) (till head_range))
    | None -> Range.(of_points (from full_range) (from full_range))
  in
  {
    el;
    cx;
    status_parsed;
    status_derived = Proof_status.Progress;
    full_range;
    head_range;
    obs = RangeMap.empty;
    sub = [];
  }

let with_sub ps sub =
  let status_derived = derived_status ps.status_parsed ps.obs sub in
  { ps with status_derived; sub }

(* The pool of obligations the visitor claims from, step by step.
   [RangeMap.partition] over the whole remaining map for every step was
   O(steps × obligations) and dominated the tree build on large files
   (measured: ~45 s of a 59 s keystroke on a 30k-line module, 13 563
   steps × 30 872 obligations).  The pool keeps the exact claiming
   semantics — first claimer wins, a claim is a range intersection —
   in O(log n + matches) per step: entries sorted by range, a binary
   search to the window start, a forward scan over the window, and a
   backward scan bounded by the longest obligation span (an entry
   starting further back cannot reach the window). *)
type obl_pool = {
  entries : (Range.t * Obl.t) array;  (* sorted by [Range.compare] *)
  taken : bool array;
  max_span : int;  (* longest obligation span, in lines *)
}

let pool_of_list l =
  (* Duplicate ranges collapse exactly as the historical
     [RangeMap.of_list] collapsed them (last one wins), and the
     bindings come out sorted. *)
  let entries = Array.of_list (RangeMap.bindings (RangeMap.of_list l)) in
  Array.sort (fun (a, _) (b, _) -> Range.compare a b) entries;
  let max_span =
    Array.fold_left
      (fun m (r, _) -> max m (Range.line_till r - Range.line_from r))
      0 entries
  in
  { entries; taken = Array.make (Array.length entries) false; max_span }

let pool_claim pool w =
  let n = Array.length pool.entries in
  let wlo = Range.line_from w in
  let whi = Range.line_till w in
  (* first index whose range starts at line [wlo] or later *)
  let rec bs a b =
    if a >= b then a
    else
      let m = (a + b) / 2 in
      if Range.line_from (fst pool.entries.(m)) < wlo then bs (m + 1) b
      else bs a m
  in
  let lo = bs 0 n in
  let acc = ref [] in
  let claim i =
    if not pool.taken.(i) then
      let r, o = pool.entries.(i) in
      if Range.intersect r w then begin
        pool.taken.(i) <- true;
        acc := (r, o) :: !acc
      end
  in
  let i = ref (lo - 1) in
  while
    !i >= 0
    && Range.line_from (fst pool.entries.(!i)) >= wlo - pool.max_span
  do
    claim !i;
    decr i
  done;
  let j = ref lo in
  while !j < n && Range.line_from (fst pool.entries.(!j)) <= whi do
    claim !j;
    incr j
  done;
  RangeMap.of_list !acc

let pool_all_taken pool = Array.for_all (fun b -> b) pool.taken

let with_obs ps pool =
  let obs = pool_claim pool ps.full_range in
  let status_derived = derived_status ps.status_parsed obs ps.sub in
  { ps with obs; status_derived }

let with_range ps range =
  { ps with full_range = Range.join_opt range ps.full_range }

(** Iterate over obligations of a particular proof step. *)
let fold_obs f acc ps = RangeMap.fold (fun _ obl acc -> f acc obl) ps.obs acc

(* Recursively collect all the fingerprinted obligations.
   This is used to transfer proof state from the
   previous to the new document version. *)
let obl_by_fp ps =
  let tbl = Hashtbl.create 1024 in
  match ps with
  | None -> tbl
  | Some ps ->
      let rec traverse ps =
        let add_by_fp (o : Obl.t) =
          match Obl.fingerprint o with
          | None -> ()
          | Some fp -> Hashtbl.add tbl fp o
        in
        RangeMap.iter (fun _ o -> add_by_fp o) ps.obs;
        List.iter traverse ps.sub
      in
      traverse ps;
      tbl

(** Just make a flat list of all the proof steps. *)
let flatten ps =
  let rec traverse ps = ps :: List.flatten (List.map traverse ps.sub) in
  match ps with None -> [] | Some ps -> traverse ps

(** Iterate over the proof steps. *)
let fold f acc ps =
  let rec fold_rec acc ps =
    let acc = f acc ps in
    List.fold_left fold_rec acc ps.sub
  in
  match ps with None -> acc | Some ps -> fold_rec acc ps

let el { el; cx; _ } = (el, cx)

let goal ({ obs; _ } : t) : TL.Proof.T.obligation option =
  let found =
    RangeMap.fold
      (fun _ o acc ->
        Option.fold ~none:acc ~some:(fun x -> x :: acc) (Obl.parsed_main o))
      obs []
  in
  match found with
  | [] -> None
  | [ o ] -> Some o
  | _ :: _ -> (
      (* Pick the "best" obligation if several of them are found. *)
      let obl_kind_priority (kind : TL.Proof.T.obligation_kind) : int =
        match kind with
        | TL.Proof.T.Ob_main -> 1
        | TL.Proof.T.Ob_omitted _ -> 2
        | TL.Proof.T.Ob_support -> 3
        | TL.Proof.T.Ob_error _ -> 4
      in
      match
        List.sort
          (fun o1 o2 ->
            let open TL.Proof.T in
            compare (obl_kind_priority o1.kind) (obl_kind_priority o2.kind))
          found
      with
      | [] -> assert false
      | o :: _ -> Some o)

let proof ({ el; _ } : t) : TL.Proof.T.proof option =
  match el with
  | El.Module _ -> None
  | El.Theorem { orig_pf; _ } -> Some orig_pf
  | El.Mutate _ -> None
  | El.Step step -> (
      match step.core with
      | TL.Proof.T.Hide _ | TL.Proof.T.Define _
      | TL.Proof.T.Use (_, _)
      | TL.Proof.T.Have _ | TL.Proof.T.Take _ | TL.Proof.T.TakeTuply _
      | TL.Proof.T.Witness _ | TL.Proof.T.Forget _ ->
          None
      | TL.Proof.T.Assert (_, pf)
      | TL.Proof.T.Suffices (_, pf)
      | TL.Proof.T.Pcase (_, pf)
      | TL.Proof.T.Pick (_, _, pf)
      | TL.Proof.T.PickTuply (_, _, pf) ->
          Some pf)
  | El.Qed qed -> ( match qed.core with TL.Proof.T.Qed pf -> Some pf)

let full_range { full_range; _ } = full_range
let head_range { head_range; _ } = head_range

let step_name (ps : t) : TL.Proof.T.stepno option =
  match ps.el with
  | El.Module _ | El.Theorem _ | El.Mutate _ -> None
  | El.Step step -> TL.Property.query step TL.Proof.T.Props.step
  | El.Qed qed_step -> TL.Property.query qed_step TL.Proof.T.Props.step

(** Level/Depth of a sub-step of a given step. I.e. [x] in
    {v <x>y v} *)
let sub_step_no (parent : t) : int =
  step_name parent |> TL.Proof.T.sub_step_number

let sub_step_label_seq (parent : t) : int Seq.t =
  let max_num =
    List.fold_right
      (fun sub acc ->
        match step_name sub with
        | None -> acc
        | Some sn -> (
            match sn with
            | TL.Proof.T.Named (_, label, _) -> (
                let rec trim_periods s =
                  if String.ends_with ~suffix:"." s then
                    String.sub s 0 (String.length s - 1) |> trim_periods
                  else s
                in
                match label |> trim_periods |> int_of_string_opt with
                | None -> acc
                | Some x -> max x acc)
            | TL.Proof.T.Unnamed (_, _) -> acc))
      parent.sub 0
  in
  Seq.ints (max_num + 1)

let stepno_seq_under_proof_step (parent : t) : TL.Proof.T.stepno Seq.t =
  let sn = sub_step_no parent in
  sub_step_label_seq parent
  |> Seq.map (fun sl -> TL.Proof.T.Named (sn, string_of_int sl, false))

let stepno_seq_under_stepno (parent : TL.Proof.T.stepno option) :
    TL.Proof.T.stepno Seq.t =
  let sn = TL.Proof.T.sub_step_number parent in
  Seq.ints 1
  |> Seq.map (fun sl -> TL.Proof.T.Named (sn, string_of_int sl, false))

let sub_step_unnamed (parent : t) : TL.Proof.T.stepno =
  let sn = sub_step_no parent in
  TL.Proof.T.Unnamed (sn, 0)

let with_prover_terminated (ps : t option) p_ref =
  let rec traverse ps =
    let sub = List.map traverse ps.sub in
    let obs = RangeMap.map (Obl.with_prover_terminated p_ref) ps.obs in
    let status_derived = derived_status ps.status_parsed obs sub in
    { ps with sub; obs; status_derived }
  in
  match ps with None -> None | Some ps -> Some (traverse ps)

let with_provers (ps : t option) p_ref obl_id prover_names =
  let rec traverse ps =
    let found = ref false in
    let try_obl obl =
      if (not !found) && Obl.is_for_obl_id obl p_ref obl_id then (
        found := true;
        Obl.with_prover_names p_ref obl_id prover_names obl)
      else obl
    in
    let try_sub ps =
      if not !found then (
        let ps, sub_found = traverse ps in
        if sub_found then found := true;
        ps)
      else ps
    in
    let obs = RangeMap.map try_obl ps.obs in
    let sub = List.map try_sub ps.sub in
    let ps = { ps with obs; sub } in
    (ps, !found)
  in
  match ps with
  | None -> None
  | Some ps ->
      let ps, _ = traverse ps in
      Some ps

let with_prover_result (ps : t option) p_ref (pr : Prover.Toolbox.Obligation.t)
    =
  let rec traverse (ps : t) (pr : Prover.Toolbox.Obligation.t) =
    if Range.intersect ps.full_range pr.loc then
      let apply_to_sub acc sub_ps =
        match acc with
        | true -> (* Already found previously. *) (acc, sub_ps)
        | false -> (
            (* Not found yet, try the depth-first search. *)
            match traverse sub_ps pr with
            | None -> (acc, sub_ps)
            | Some sub_ps -> (true, sub_ps))
      in
      let found, sub = List.fold_left_map apply_to_sub false ps.sub in
      let ps =
        match found with
        | true -> { ps with sub }
        | false ->
            let upd o = Some (Obl.with_prover_obligation p_ref pr o) in
            let obs = RangeMap.update pr.loc upd ps.obs in
            { ps with obs }
      in
      let status_derived = derived_status ps.status_parsed ps.obs ps.sub in
      Some { ps with status_derived }
    else None
  in
  match ps with
  | None -> None
  | Some ps -> (
      match traverse ps pr with None -> Some ps | Some ps -> Some ps)

let locate_proof_path (ps : t) (r : Range.t) : t list =
  let rec traverse ps =
    if Range.lines_intersect ps.full_range r then
      match List.find_map traverse ps.sub with
      | None -> Some [ ps ]
      | Some sub_ps -> Some (ps :: sub_ps)
    else None
  in
  List.rev (Option.value (traverse ps) ~default:[])

(* Find the deepest proof step that intersects line-wise with the specified position. *)
let locate_proof_step (ps : t option) (position : Range.Position.t) : t option =
  let rec traverse ps =
    if Range.line_covered ps.full_range position then
      match List.find_map traverse ps.sub with
      | None -> Some ps
      | Some sub_ps -> Some sub_ps
    else None
  in
  match ps with None -> None | Some ps -> traverse ps

let locate_proof_range (ps : t option) (range : Range.t) : Range.t =
  let ps_from = locate_proof_step ps (Range.from range) in
  let ps_till = locate_proof_step ps (Range.till range) in
  match (ps_from, ps_till) with
  | None, None -> Range.of_all
  | Some ps_from, None -> ps_from.full_range
  | None, Some ps_till -> ps_till.full_range
  | Some ps_from, Some ps_till ->
      Range.join ps_from.full_range ps_till.full_range

let is_obl_final (ps : t option) p_ref obl_id =
  let rec traverse ps =
    let with_obl_id r =
      Obl.is_for_obl_id (RangeMap.find r ps.obs) p_ref obl_id
    in
    match RangeMap.find_first_opt with_obl_id ps.obs with
    | None -> List.find_map traverse ps.sub
    | Some (_, o) -> Some (Obl.is_final o)
  in
  match ps with None -> None | Some ps -> traverse ps

let as_lsp_tlaps_proof_state_marker ps =
  let status = Proof_status.to_string ps.status_derived in
  let range = Range.as_lsp_range ps.head_range in
  let hover = Proof_status.to_message ps.status_derived in
  Structs.TlapsProofStepMarker.make ~status ~range ~hover

let as_lsp_tlaps_proof_step_details uri ps =
  let kind = Kind.(of_proof_step ps |> to_string) in
  let status = Proof_status.to_string ps.status_derived in
  let location =
    LspT.Location.create ~uri ~range:(Range.as_lsp_range ps.full_range)
  in
  let obligations =
    List.map
      (fun (_, o) -> Obl.as_lsp_tlaps_proof_obligation_state o)
      (RangeMap.to_list ps.obs)
  in
  let sub_count =
    let proved, failed, omitted, missing, pending, progress =
      List.fold_left
        (fun (proved, failed, omitted, missing, pending, progress) sub_ps ->
          match sub_ps.status_derived with
          | Proved -> (proved + 1, failed, omitted, missing, pending, progress)
          | Failed -> (proved, failed + 1, omitted, missing, pending, progress)
          | Omitted -> (proved, failed, omitted + 1, missing, pending, progress)
          | Missing -> (proved, failed, omitted, missing + 1, pending, progress)
          | Pending -> (proved, failed, omitted, missing, pending + 1, progress)
          | Progress -> (proved, failed, omitted, missing, pending, progress + 1))
        (0, 0, 0, 0, 0, 0) ps.sub
    in
    Structs.CountByStepStatus.make ~proved ~failed ~omitted ~missing ~pending
      ~progress
  in
  Structs.TlapsProofStepDetails.make ~kind ~status ~location ~obligations
    ~sub_count

(** Construct the view of the AST in terms of user-visible proof steps. *)
module Builder : sig
  val of_module :
    TL.Module.T.mule -> t option -> (string * string) option -> t option

  val gen_scope_lines : t -> string -> string -> (int * int) option
  (** [gen_scope_lines prev old_text new_text] is the line window of the
      current version whose proofs must be generated — the edited
      top-level step, in new coordinates — when the edit satisfies the
      body-only criterion; [None] otherwise (generate everything). *)

  val last_carried : unit -> int
  (** How many fingerprints the last [of_module] carried over from the
      previous version instead of recomputing (scoped fingerprinting;
      for tests and probes). *)
end = struct
  let in_file file wrapped =
    match Tlapm_lib.Util.query_locus wrapped with
    | Some loc when loc.file = file -> true
    | Some _ -> false
    | None -> false

  let if_in_file file cx wrapped fn =
    match Tlapm_lib.Util.query_locus wrapped with
    | Some loc when loc.file = file -> fn (Range.of_locus_must loc)
    | Some _ -> ((cx, wrapped), None)
    | None -> ((cx, wrapped), None)

  let if_in_file_opt file wrapped fn =
    match Tlapm_lib.Util.query_locus wrapped with
    | Some loc when loc.file = file -> fn (Range.of_locus_must loc)
    | Some _ -> None
    | None -> None

  let join_range_of_wrapped wrapped acc =
    List.fold_left
      (fun acc w ->
        Range.of_wrapped w |> Option.fold ~none:acc ~some:(Range.join acc))
      acc wrapped

  let join_range_of_wrapped_opt ?(acc = None) wrapped =
    List.fold_left
      (fun acc w ->
        Range.of_wrapped w
        |> Option.fold ~none:acc ~some:(fun r -> Some (Range.join_opt acc r)))
      acc wrapped

  let join_range_of_usable (usable : TL.Proof.T.usable) (acc : Range.t) =
    acc
    |> join_range_of_wrapped usable.defs
    |> join_range_of_wrapped usable.facts

  let join_range_of_usable_opt (usable : TL.Proof.T.usable) =
    let acc = join_range_of_wrapped_opt usable.defs in
    join_range_of_wrapped_opt ~acc usable.facts

  (** Derive a status of a step by structure of its proof (as parsed), if
      possible. *)
  let parsed_status_of_proof (proof : TL.Proof.T.proof) =
    match proof.core with
    | TL.Proof.T.Omitted omission -> (
        match omission with
        | TL.Proof.T.Implicit -> Some Proof_status.Missing
        | TL.Proof.T.Explicit -> Some Proof_status.Omitted
        | TL.Proof.T.Elsewhere _ -> Some Proof_status.Omitted)
    | TL.Proof.T.Error _ -> Some Proof_status.Failed
    | TL.Proof.T.Obvious | TL.Proof.T.By (_, _) | TL.Proof.T.Steps (_, _) ->
        None

  (* Probe (TLAPM_LSP_PHASES=1): accumulate the time spent computing
     obligation fingerprints while building the proof-step tree. *)
  let fp_probe = ref false
  let fp_time = ref 0.
  let fp_count = ref 0
  let fp_carried = ref 0
  let last_carried () = !fp_carried

  (* Scoped fingerprinting (TLAPM_LSP_SCOPED=1).  When the edit between
     the previous and the current version is confined to the proof BODY
     of a single top-level step, only that step's obligations can
     change: statements — the only thing later material sees — are
     untouched, so every obligation outside the edited step keeps a
     sequent identical up to line positions, and fingerprints do not
     depend on positions (the whole cross-version state carry-over
     relies on that).  Those obligations therefore inherit the previous
     version's fingerprint, found positionally: same range before the
     edit, line-shifted after it.  The fingerprint is the key of the
     existing proof-state carry-over, so inheriting it carries the
     state too.  Any situation outside this criterion — edit touching a
     statement, module-level material, several steps, no positional
     match — falls back to a real fingerprint computation, so a carry
     only ever skips recomputing an identical value. *)
  type edit_scope = {
    es_wl : int;        (* edited window, old 1-based line coordinates *)
    es_wh_old : int;    (* end of the old window (may be < es_wl) *)
    es_delta : int;     (* new line count minus old line count *)
    es_hz_lo : int;     (* the edited (host) step, old coordinates *)
    es_hz_hi : int;
  }

  (* The soundness criterion shared by both carry-over modes: the edit
     between the two versions must be confined to the proof BODY of a
     single top-level step of the previous version.  Statements — the
     only thing later material sees — are then untouched, so everything
     outside that step keeps a sequent identical up to line positions.
     Returns [None] whenever the criterion does not hold (statement
     touched, module-level edit, several steps, no previous tree). *)
  let compute_scope (prev : t) (old_text : string) (new_text : string) =
    let ol = Array.of_list (String.split_on_char '\n' old_text) in
    let nl = Array.of_list (String.split_on_char '\n' new_text) in
    let no = Array.length ol and nn = Array.length nl in
    let p = ref 0 in
    while !p < no && !p < nn && ol.(!p) = nl.(!p) do incr p done;
    let s = ref 0 in
    while
      !s < no - !p && !s < nn - !p && ol.(no - 1 - !s) = nl.(nn - 1 - !s)
    do
      incr s
    done;
    let delta = nn - no in
    let wl = !p + 1 in
    let wh_true = no - !s in
    let wh = max wh_true wl in
    let host =
      List.find_opt
        (fun st ->
          Range.line_from st.full_range <= wl
          && wh <= Range.line_till st.full_range
          && wl > Range.line_till st.head_range)
        prev.sub
    in
    Option.map
      (fun host ->
        { es_wl = wl; es_wh_old = wh_true; es_delta = delta;
          es_hz_lo = Range.line_from host.full_range;
          es_hz_hi = Range.line_till host.full_range })
      host

  (* Previous-version material outside the edited step, keyed by its
     expected range in the NEW version: identical before the edit,
     line-shifted after it.  [carry_fold] drives both carry modes. *)
  let carry_fold (prev : t) sc f acc =
    let acc = ref acc in
    let each r (o : Obl.t) =
      let rf = Range.line_from r and rt = Range.line_till r in
      if rt >= sc.es_hz_lo && rf <= sc.es_hz_hi then ()
      else
        let lf, cf = Range.Position.as_pair (Range.from r) in
        let lt, ct = Range.Position.as_pair (Range.till r) in
        if rt < sc.es_wl then acc := f !acc (lf, cf, lt, ct) o
        else if rf > sc.es_wh_old then
          acc :=
            f !acc (lf + sc.es_delta, cf, lt + sc.es_delta, ct) o
    in
    let rec traverse ps =
      RangeMap.iter each ps.obs;
      List.iter traverse ps.sub
    in
    traverse prev;
    !acc

  (* Mode 1 (fingerprints only): expected-new-range -> fingerprint. *)
  let carry_table (prev : t) sc =
    let tbl = Hashtbl.create 4096 in
    carry_fold prev sc
      (fun () k o ->
        match Obl.fingerprint o with
        | None -> ()
        | Some fp -> Hashtbl.replace tbl k fp)
      ();
    tbl

  (* Mode 2 (scoped generation): the whole previous obligations, at
     their expected new ranges, ready to enter the pool.  Their inner
     locations are the previous version's (stale by [es_delta] lines
     after the edit) — the tree ranges come from the fresh parse, so
     markers and statuses are unaffected. *)
  let carried_obligations (prev : t) sc =
    carry_fold prev sc
      (fun acc (lf, cf, lt, ct) o ->
        (Range.of_ints ~lf ~cf ~lt ~ct, o) :: acc)
      []

  let gen_scope_lines prev old_text new_text =
    Option.map
      (fun sc -> (sc.es_hz_lo, sc.es_hz_hi + sc.es_delta))
      (compute_scope prev old_text new_text)

  class step_visitor (file : string) =
    object (self : 'self)
      inherit TL.Module.Visit.map as m_super
      inherit [unit] TL.Proof.Visit.iter as p_super
      val mutable acc_steps : t list = []
      val mutable acc_range : Range.t option = None
      val mutable mu_curr : TL.Module.T.modunit option = None
      val mutable obs : obl_pool = pool_of_list []

      (* Scoped fingerprinting: previous-version fingerprints by
         expected new-version range; see [compute_carry]. *)
      val mutable carry :
          (int * int * int * int, string) Hashtbl.t option =
        None

      method set_carry c = carry <- c

      (* Scoped generation: previous-version obligations for the steps
         whose proofs were not generated this time. *)
      val mutable extra_obs : (Range.t * Obl.t) list = []
      method set_extra l = extra_obs <- l

      method private take_mu () =
        let mu = Option.get mu_curr in
        mu_curr <- None;
        mu

      method private extend_range r =
        r
        |> Option.iter @@ fun r ->
           let r =
             match acc_range with
             | None -> r
             | Some acc_range -> Range.join acc_range r
           in
           acc_range <- Some r

      (* This function mainly here to maintain all the mutable variables in one place. *)
      method private define_step : 'x. (unit -> 'x * t option) -> 'x =
        fun f ->
          let prev_steps = acc_steps in
          let prev_range = acc_range in
          acc_steps <- [];
          acc_range <- None;
          let res, step = f () in
          (match step with
          | None ->
              assert (acc_steps = []);
              acc_steps <- prev_steps;
              acc_range <- prev_range
          | Some step ->
              let step = with_sub step (List.rev acc_steps) in
              let step = with_range step acc_range in
              let step = with_obs step obs in
              acc_steps <- step :: prev_steps;
              acc_range <- Some (Range.join_opt prev_range step.full_range));
          res

      (* That's the entry point to the visitor. *)
      method process (mule : TL.Module.T.mule)
          (prev_obs : (string, Obl.t) Hashtbl.t) : t option =
        if in_file file mule then (
          let mule_obl (o : Tlapm_lib.Proof.T.obligation) =
            (* Keep only the obligations from the current file.
             We will use the fingerprints to retain the
             proof status between the modifications.*)
            if_in_file_opt file o.obl @@ fun o_range ->
            let carried_fp =
              match carry with
              | None -> None
              | Some tbl ->
                  let lf, cf = Range.Position.as_pair (Range.from o_range) in
                  let lt, ct = Range.Position.as_pair (Range.till o_range) in
                  Hashtbl.find_opt tbl (lf, cf, lt, ct)
            in
            let o =
              (match (o.fingerprint, carried_fp) with
                | None, Some fp ->
                    incr fp_carried ;
                    { o with fingerprint = Some fp }
                | None, None ->
                    let t0 =
                      if !fp_probe then Unix.gettimeofday () else 0. in
                    let o =
                      Tlapm_lib.Backend.Fingerprints.write_fingerprint o in
                    if !fp_probe then begin
                      fp_time := !fp_time +. (Unix.gettimeofday () -. t0) ;
                      incr fp_count
                    end;
                    o
                | Some _, _ -> o)
              |> Obl.of_parsed_obligation
              |> Obl.with_proof_state_from (Hashtbl.find_opt prev_obs)
            in
            Some (o_range, o)
          in
          obs <-
            (match mule.core.stage with
              | TL.Module.T.Special -> []
              | TL.Module.T.Parsed -> []
              | TL.Module.T.Flat -> []
              | TL.Module.T.Final final -> Array.to_list final.final_obs)
            |> List.filter_map mule_obl
            |> (fun l -> pool_of_list (l @ extra_obs));
          ignore (self#tla_module_root mule);
          assert (pool_all_taken obs);
          match acc_steps with
          | [] -> None
          | [ step ] -> Some step
          | _ -> assert false)
        else None

      (* This can be the main module, or any sub-module. *)
      method! tla_module cx mule =
        self#define_step @@ fun () ->
        let cx, mule = m_super#tla_module cx mule in
        if_in_file file cx mule @@ fun mule_loc ->
        let step =
          make ~el:(Module mule) ~status_parsed:None ~cx ~head_range:None
            ~full_range:mule_loc
        in
        ((cx, mule), Some step)

      (* Submodules are not traversed in m_super, thus we traverse them here. *)
      method! submod cx mule =
        let cx, mule = self#tla_module cx mule in
        m_super#submod cx mule

      (* We don't have the range at the theorem, so we try to track it by inspecting module units. *)
      method! module_unit cx mu =
        mu_curr <- Some mu;
        m_super#module_unit cx mu

      (* Leaf at the `Module.Visit.map as m_super`.
       We will look at `orig_pf`, it is closer to the initial source code. *)
      method! theorem cx name sq naxs pf orig_pf summ =
        self#define_step @@ fun () ->
        let mu = self#take_mu () in
        let step =
          if in_file file mu then (
            Range.of_wrapped mu
            |> Option.map @@ fun mu_loc ->
               self#proof ((), cx) orig_pf;
               let el = El.Theorem { mu; name; sq; naxs; pf; orig_pf; summ } in
               let full_range = mu_loc in
               let head_range = Range.(of_wrapped sq.active) in
               let status_parsed = parsed_status_of_proof orig_pf in
               make ~el ~cx ~status_parsed ~head_range ~full_range)
          else None
        in
        (m_super#theorem cx name sq naxs pf orig_pf summ, step)

      method! mutate cx change usable =
        self#define_step @@ fun () ->
        let mu = self#take_mu () in
        let use =
          (* Visible proof steps are only needed for USE with some facts listed. *)
          match change with
          | `Use _ -> usable.facts != []
          | `Hide -> false
        in
        let step =
          if use && in_file file mu then
            Range.of_wrapped mu
            |> Option.map @@ fun mu_loc ->
               let el = El.Mutate { mu; usable } in
               let full_range = join_range_of_usable usable mu_loc in
               let head_range = Some full_range in
               make ~el ~cx ~status_parsed:None ~head_range ~full_range
          else None
        in
        (m_super#mutate cx change usable, step)

      (* Ordinary, non-QED step of a structural proof. *)
      method! step cx st =
        self#define_step @@ fun () ->
        let full_range = Range.of_wrapped_must st in
        let status_parsed =
          match TL.Property.unwrap st with
          | TL.Proof.T.Hide _ | TL.Proof.T.Forget _ | TL.Proof.T.Define _
          | TL.Proof.T.Have _ | TL.Proof.T.Use _ | TL.Proof.T.Take _
          | TL.Proof.T.TakeTuply _ | TL.Proof.T.Witness _ ->
              None
          | TL.Proof.T.Assert (_, proof)
          | TL.Proof.T.Suffices (_, proof)
          | TL.Proof.T.Pcase (_, proof)
          | TL.Proof.T.Pick (_, _, proof)
          | TL.Proof.T.PickTuply (_, _, proof) ->
              parsed_status_of_proof proof
        in
        let step = make ~el:(Step st) ~cx:(snd cx) ~status_parsed ~full_range in
        let step =
          match TL.Property.unwrap st with
          | TL.Proof.T.Hide _ | TL.Proof.T.Forget _ | TL.Proof.T.Define _ ->
              None
          | TL.Proof.T.Assert (sequent, _proof)
          | TL.Proof.T.Suffices (sequent, _proof) ->
              Some (step ~head_range:(Range.of_wrapped sequent.active))
          | TL.Proof.T.Pcase (expr, _)
          | TL.Proof.T.Pick (_, expr, _)
          | TL.Proof.T.PickTuply (_, expr, _) ->
              Some (step ~head_range:(Range.of_wrapped expr))
          | TL.Proof.T.Have _ | TL.Proof.T.Take _ | TL.Proof.T.TakeTuply _
          | TL.Proof.T.Use (_, _)
          | TL.Proof.T.Witness _ ->
              Some (step ~head_range:(Some full_range))
        in
        (p_super#step cx st, step)

      (* The QED step of a structural proof step. *)
      method! qed cx qed =
        self#define_step @@ fun () ->
        p_super#qed cx qed;
        let full_range = Range.of_wrapped_must qed in
        let head_range =
          TL.Property.query qed TL.Proof.Parser.qed_loc_prop
          |> Range.of_locus_opt
        in
        let status_parsed =
          match qed.core with
          | TL.Proof.T.Qed proof -> parsed_status_of_proof proof
        in
        let step =
          make ~el:(Qed qed) ~cx:(snd cx) ~status_parsed ~full_range ~head_range
        in
        ((), Some step)

      (* Include all the usable facts to the range of the containing step. *)
      method! usable cx usable =
        self#extend_range (join_range_of_usable_opt usable);
        p_super#usable cx usable
    end

  (** Make a view of a module in terms of the user-visible proof steps. *)
  let of_module (mule : TL.Module.T.mule) (prev : t option)
      (texts : (string * string) option) : t option =
    let prev_obs = obl_by_fp prev in
    let file =
      match TL.Util.query_locus mule with
      | None -> failwith "of_module, has no file location"
      | Some m_locus -> m_locus.file
    in
    fp_probe := Sys.getenv_opt "TLAPM_LSP_PHASES" <> None ;
    fp_time := 0. ;
    fp_count := 0 ;
    let carry, extra =
      match (Sys.getenv_opt "TLAPM_LSP_SCOPED", prev, texts) with
      | Some lvl, Some prev_ps, Some (old_text, new_text) -> (
          match compute_scope prev_ps old_text new_text with
          | None -> (None, [])
          | Some sc ->
              if String.trim lvl = "2" then
                (None, carried_obligations prev_ps sc)
              else (Some (carry_table prev_ps sc), []))
      | _ -> (None, [])
    in
    fp_carried := List.length extra ;
    let v = new step_visitor file in
    v#set_carry carry ;
    v#set_extra extra ;
    let r = v#process mule prev_obs in
    if !fp_probe then
      Printf.eprintf "[LSP_PHASES] fingerprints=%.2fs (n=%d carried=%d)\n%!"
        !fp_time !fp_count !fp_carried ;
    r
end

let of_module ?prev ?texts mule = Builder.of_module mule prev texts

let gen_scope_lines ~prev ~old_text ~new_text =
  Builder.gen_scope_lines prev old_text new_text

(* ========================================================================== *)

let%test_unit "determine proof steps" =
  let mod_file = "test_obl_expand.tla" in
  let mod_text =
    {|
      ---- MODULE test_obl_expand ----
      EXTENDS FiniteSetTheorems
      THEOREM FALSE
          <1>1. TRUE OBVIOUS
          <1>2. TRUE
          <1>3. TRUE
          <1>q. QED BY <1>1, <1>2, <1>3
      THEOREM FALSE
          <1>q. QED
              <2>1. TRUE
              <2>q. QED BY <2>1
        ----- MODULE sub ------
        VARIABLE X
        LEMMA X = X
        =======================
      ====
    |}
  in
  let mule =
    Result.get_ok
      (Parser.module_of_string ~content:mod_text ~filename:mod_file
         ~loader_paths:[])
  in
  let ps = of_module mule in
  match flatten ps with
  | [
      _m_test_obl_expand;
      _th1;
      _th1_11;
      _th1_12;
      _th1_13;
      _th1_1q;
      _th2;
      _th2_1q;
      _th2_1q_21;
      _th2_1q_2q;
      _m_sub;
      _th3;
    ] as all -> (
      List.iteri
        (fun i ps ->
          Format.printf "Step[%d]: |obs|=%d, full_range=%s, head_range=%s\n" i
            (RangeMap.cardinal ps.obs)
            (Range.string_of_range ps.full_range)
            (Range.string_of_range ps.head_range))
        all;
      assert (RangeMap.cardinal _th2_1q_2q.obs = 2);
      assert (
        RangeMap.cardinal
          (RangeMap.filter
             (fun _ o -> Obl.role o = Obl.Role.Main true)
             _th2_1q_2q.obs)
        = 1);
      let _, _th2_1q_2q_obl = RangeMap.choose _th2_1q_2q.obs in
      match Obl.text_normalized _th2_1q_2q_obl with
      | Some "ASSUME TRUE \nPROVE  FALSE" -> ()
      | Some s -> failwith (Format.sprintf "Unexpected %s" s)
      | None -> failwith "Unexpected none")
  | pss ->
      failwith
        (Format.sprintf "unexpected, number of steps=%d" (List.length pss))

let%test_unit "determine proof steps for USE statements" =
  let mod_file = "test_use.tla" in
  let mod_text =
    {|
      ---- MODULE test_use ----
      op == TRUE
      USE DEF op
      USE TRUE
      USE FALSE
      HIDE TRUE
      THEOREM TRUE
          <1> USE TRUE
          <1> USE FALSE
          <1> HIDE TRUE
          <1> QED
      ====
    |}
  in
  let mule =
    Result.get_ok
      (Parser.module_of_string ~content:mod_text ~filename:mod_file
         ~loader_paths:[])
  in
  let ps = of_module mule in
  match flatten ps with
  | [
      _m_test_use;
      _use_true;
      _use_false;
      _th;
      _th_use_true;
      _th_use_false;
      _th_qed;
    ] as all ->
      List.iteri
        (fun i ps ->
          Format.printf "Step[%d]: |obs|=%d, full_range=%s, head_range=%s\n" i
            (RangeMap.cardinal ps.obs)
            (Range.string_of_range ps.full_range)
            (Range.string_of_range ps.head_range))
        all;
      assert (RangeMap.cardinal _use_true.obs = 1);
      assert (RangeMap.cardinal _use_false.obs = 1)
  | pss ->
      failwith
        (Format.sprintf "unexpected, number of steps=%d" (List.length pss))

let%test_unit "scoped fingerprint carry-over: exact, and scoped correctly" =
  let mod_file = "test_scoped_carry.tla" in
  let text_of body2 =
    Printf.sprintf
      {|
      ---- MODULE test_scoped_carry ----
      THEOREM ThmA == TRUE
          <1>1. TRUE OBVIOUS
          <1>q. QED BY <1>1
      THEOREM ThmB == TRUE
          %s
          <1>q. QED BY <1>1
      ====
    |}
      body2
  in
  let parse text =
    Result.get_ok
      (Parser.module_of_string ~content:text ~filename:mod_file
         ~loader_paths:[])
  in
  let fps ps =
    let acc = ref [] in
    let rec go ps =
      acc :=
        fold_obs (fun l o -> (Obl.loc o, Obl.fingerprint o) :: l) !acc ps;
      List.iter go ps.sub
    in
    Option.iter go ps;
    List.sort compare !acc
  in
  let t_a = text_of "<1>1. TRUE OBVIOUS" in
  (* a body-only edit inside ThmB's proof *)
  let t_b = text_of "<1>1. TRUE  OBVIOUS" in
  let ps_a = of_module (parse t_a) in
  Unix.putenv "TLAPM_LSP_SCOPED" "1";
  let ps_scoped = of_module ?prev:ps_a ~texts:(t_a, t_b) (parse t_b) in
  let carried_scoped = Builder.last_carried () in
  Unix.putenv "TLAPM_LSP_SCOPED" "";
  Sys.getenv "TLAPM_LSP_SCOPED" |> ignore;
  let ps_full = of_module ?prev:ps_a (parse t_b) in
  let carried_full = Builder.last_carried () in
  (* the carry must have fired for the body edit, and be byte-exact *)
  assert (carried_scoped > 0);
  assert (carried_full = 0);
  assert (fps ps_scoped = fps ps_full);
  (* a statement edit must fall back to full recomputation *)
  let t_c =
    Str.global_replace (Str.regexp_string "THEOREM ThmB == TRUE")
      "THEOREM ThmB == TRUE /\\ TRUE" t_b
  in
  Unix.putenv "TLAPM_LSP_SCOPED" "1";
  let ps_c_scoped = of_module ?prev:ps_scoped ~texts:(t_b, t_c) (parse t_c) in
  let carried_stmt = Builder.last_carried () in
  Unix.putenv "TLAPM_LSP_SCOPED" "";
  let ps_c_full = of_module ?prev:ps_scoped (parse t_c) in
  assert (carried_stmt = 0);
  assert (fps ps_c_scoped = fps ps_c_full)

let%test_unit "check if parsing works with nested local instances." =
  let mod_file = "test_loc_ins.tla" in
  let mod_text =
    {|
      ---- MODULE test_loc_ins ----
      LOCAL INSTANCE FiniteSets
      ====
    |}
  in
  let _mule =
    Result.get_ok
      (Parser.module_of_string ~content:mod_text ~filename:mod_file
         ~loader_paths:[])
  in
  ()
