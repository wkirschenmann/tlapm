(* Probe: obligations that are the same up to renaming declared names.

   With TLAPM_FP_CLASSES set, every obligation is digested twice — once
   normally, once with declared names erased ([Fingerprints.fingerprint_anon])
   — and the run ends with a report of the *classes*: groups of obligations
   that carry different fingerprints today but would carry the same one if
   the digest ignored declared names.

   Two readings of a class, both useful:

     * as a spec diagnostic — a class is the same lemma proved once per
       member of a family of declared constants, i.e. a generalisation the
       spec could have stated once and instantiated;
     * as the audit of a possible digest change — a class whose members
       also share the digest of their *shipped* form is a group the provers
       would be solving identically anyway.  That comparison is the sound
       one: the shipped obligation has been pruned, so nothing it contains
       escapes the digest, whereas the pre-shipping form carries hidden
       definitions whose bodies are not hashed.

   Inert without the environment variable.  Nothing here influences
   preparation, proving, fingerprint storage or reporting. *)

let enabled = Sys.getenv_opt "TLAPM_FP_CLASSES" <> None

type entry = {
  e_id : int ;
  e_loc : string ;
  e_fp : string ;              (* the stored fingerprint *)
  e_anon : string ;            (* same digest, declared names erased *)
  mutable e_ship : string option ;
      (* name-erased digest of the shipped form, when the obligation
         reached the backends: the auditable one *)
}

let entries : (int, entry) Hashtbl.t = Hashtbl.create 1024

let loc_of (ob : Proof.T.obligation) =
  match Util.query_locus ob.Proof.T.obl with
  | Some loc -> Loc.string_of_locus_nofile loc
  | None -> "?"

let record (ob : Proof.T.obligation) =
  if enabled then
    match ob.Proof.T.id, ob.Proof.T.fingerprint with
    | Some id, Some fp when not (Hashtbl.mem entries id) ->
        Hashtbl.replace entries id
          { e_id = id ; e_loc = loc_of ob ; e_fp = fp ;
            e_anon = Fingerprints.fingerprint_anon ob ; e_ship = None }
    | _ -> ()

let record_shipped (ob : Proof.T.obligation) =
  if enabled then
    match ob.Proof.T.id with
    | Some id -> begin
        match Hashtbl.find_opt entries id with
        | Some e when e.e_ship = None ->
            e.e_ship <- Some (Fingerprints.fingerprint_anon ob)
        | _ -> ()
      end
    | None -> ()

module SMap = Map.Make (String)

let report () =
  if enabled && Hashtbl.length entries > 0 then begin
    (* group by name-erased digest *)
    let groups =
      Hashtbl.fold
        (fun _ e acc ->
          let prev = try SMap.find e.e_anon acc with Not_found -> [] in
          SMap.add e.e_anon (e :: prev) acc)
        entries SMap.empty in
    let classes =
      SMap.bindings groups
      |> List.filter_map begin fun (anon, es) ->
           let fps = List.sort_uniq compare (List.map (fun e -> e.e_fp) es) in
           if List.length fps < 2 then None
           else Some (anon, List.sort (fun a b -> compare a.e_id b.e_id) es,
                      List.length fps)
         end in
    let n_obl = Hashtbl.length entries in
    let n_fp =
      Hashtbl.fold (fun _ e acc -> SMap.add e.e_fp () acc) entries SMap.empty
      |> SMap.cardinal in
    let n_anon = SMap.cardinal groups in
    Printf.eprintf
      "\n[FP_CLASSES] obligations=%d fingerprints=%d name-erased=%d \
       classes=%d saved=%d\n"
      n_obl n_fp n_anon (List.length classes)
      (List.fold_left (fun a (_, _, k) -> a + k - 1) 0 classes) ;
    List.iter begin fun (anon, es, k) ->
      (* Audit: do the members agree on the shipped form?  "certified"
         means the provers see the same problem up to renaming;
         "unshipped" means too few members reached the backends to tell
         (fingerprint hit, or resolved as trivial). *)
      let ships = List.filter_map (fun e -> e.e_ship) es in
      let uniq_ships = List.sort_uniq compare ships in
      let verdict =
        if List.length ships < 2 then "unshipped"
        else if List.length uniq_ships = 1 then "certified"
        else "DIFFERING-SHIPPED-FORMS" in
      Printf.eprintf "[FP_CLASS] %s members=%d fingerprints=%d audit=%s\n"
        (String.sub anon 0 8) (List.length es) k verdict ;
      List.iter
        (fun e ->
          Printf.eprintf "[FP_CLASS]    id=%-6d %-24s fp=%s\n"
            e.e_id e.e_loc (String.sub e.e_fp 0 8))
        es
    end classes ;
    flush stderr
  end
