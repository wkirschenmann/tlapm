(* Chunked parallel runs.

   Preparation is single-threaded and dominates a run — measured on a
   30k-obligation module, 233.6 s of a 247.8 s scheduler loop is spent
   forcing it, and the loop never once blocks waiting for a prover —
   so the parallelism has to come from preparing several parts of the
   document at the same time.

   The parent splits the input into contiguous line ranges and runs
   itself on each range, at most [Params.spawn] at a time, handing the
   next range to whichever worker frees up first.  Using more ranges
   than workers is deliberate: with one range per worker the measured
   spread of completion times was 2.2x, which a dynamic hand-out
   absorbs.

   Each worker restricts generation to the module units *starting* in
   its range ([--chunk-lines], see Params.chunk_lines), so every unit
   belongs to exactly one range and the union of the workers generates
   each obligation exactly once.  Each gets its own cache directory;
   the parent consolidates the fingerprints afterwards.

   Worker output is captured and replayed in range order, so what the
   user reads is the document order regardless of completion order.
*)

let line_count file =
  let ic = open_in_bin file in
  let n = ref 0 in
  (try
     while true do
       ignore (input_line ic) ;
       incr n
     done
   with End_of_file -> ()) ;
  close_in ic ;
  max !n 1

(* Contiguous 1-based inclusive ranges partitioning [1, n_lines]. *)
let ranges n_lines n_chunks =
  let n_chunks = max 1 (min n_chunks n_lines) in
  List.init n_chunks begin fun k ->
    ((k * n_lines / n_chunks) + 1, (k + 1) * n_lines / n_chunks)
  end

(* The parent's own command line, minus the flags that would make a
   worker split again, plus the worker's range and cache directory. *)
let worker_argv range_lo range_hi cache_dir =
  let argv = Sys.argv in
  let out = ref [] in
  let i = ref 1 in
  let n = Array.length argv in
  while !i < n do
    (match argv.(!i) with
     | "--chunks" | "--spawn" -> incr i  (* drop the flag and its value *)
     | "--chunk-lines" -> i := !i + 2
     | a -> out := a :: !out) ;
    incr i
  done ;
  let extra =
    [ "--chunk-lines" ; string_of_int range_lo ; string_of_int range_hi ;
      "--cache-dir" ; cache_dir ] in
  Array.of_list (argv.(0) :: List.rev_append !out extra)

type worker = {
  w_pid : int ;
  w_idx : int ;
  w_out : string ;   (* captured stdout *)
  w_err : string ;   (* captured stderr *)
}

let cat_to file oc =
  if Sys.file_exists file then begin
    let ic = open_in_bin file in
    let buf = Bytes.create 65536 in
    let rec loop () =
      let r = input ic buf 0 (Bytes.length buf) in
      if r > 0 then begin
        output oc buf 0 r ;
        loop ()
      end
    in
    loop () ;
    close_in ic ;
    flush oc
  end

(* [run file] proves [file] in chunks.  Returns the exit status to use:
   0 when every worker succeeded, otherwise the most severe worker
   status. *)
let run (file: string): int =
  let n_lines = line_count file in
  let plan = ranges n_lines !Params.chunks in
  let n = List.length plan in
  let par = max 1 (if !Params.spawn > 0 then !Params.spawn else 1) in
  let tmp = Filename.concat (Filename.get_temp_dir_name ())
      (Printf.sprintf "tlapm-chunks-%d" (Unix.getpid ())) in
  Unix.mkdir tmp 0o700 ;
  let cache_root = !Params.cachedir in
  Util.printf
    "(* chunked run: %d ranges over %d lines, %d worker%s *)%!"
    n n_lines par (if par > 1 then "s" else "") ;
  let plan = Array.of_list plan in
  let status = Array.make n (-1) in
  let outs = Array.init n
      (fun k -> Filename.concat tmp (Printf.sprintf "out-%d" k)) in
  let errs = Array.init n
      (fun k -> Filename.concat tmp (Printf.sprintf "err-%d" k)) in
  (* [mkdir] is not recursive and the workers create only their own
     module subdirectory, so the parent owns the cache layout. *)
  let mkdir_p d =
    if not (Sys.file_exists d) then
      try Unix.mkdir d 0o777 with Unix.Unix_error (Unix.EEXIST, _, _) -> ()
  in
  mkdir_p cache_root ;
  let start k =
    let (lo, hi) = plan.(k) in
    let cache = Filename.concat cache_root (Printf.sprintf "chunk-%d" k) in
    mkdir_p cache ;
    let argv = worker_argv lo hi cache in
    let fd_out =
      Unix.openfile outs.(k) [ Unix.O_WRONLY; Unix.O_CREAT; Unix.O_TRUNC ] 0o600
    and fd_err =
      Unix.openfile errs.(k) [ Unix.O_WRONLY; Unix.O_CREAT; Unix.O_TRUNC ] 0o600
    and fd_in = Unix.openfile "/dev/null" [ Unix.O_RDONLY ] 0 in
    let pid =
      Unix.create_process Sys.executable_name argv fd_in fd_out fd_err in
    List.iter Unix.close [ fd_in; fd_out; fd_err ] ;
    { w_pid = pid ; w_idx = k ; w_out = outs.(k) ; w_err = errs.(k) }
  in
  (* Replay finished ranges in document order: emit range [flushed]
     as soon as it is done, never before its predecessors. *)
  let flushed = ref 0 in
  let flush_ready () =
    while !flushed < n && status.(!flushed) >= 0 do
      let k = !flushed in
      cat_to outs.(k) Stdlib.stdout ;
      cat_to errs.(k) Stdlib.stderr ;
      (try Sys.remove outs.(k) with Sys_error _ -> ()) ;
      (try Sys.remove errs.(k) with Sys_error _ -> ()) ;
      incr flushed
    done
  in
  let next = ref 0 in
  let running = ref [] in
  (* Wait on our own workers only: [Unix.wait] would also reap the
     backend version-check subprocesses that Params starts. *)
  let reap () =
    let rec poll () =
      let finished =
        List.filter_map begin fun w ->
          match Unix.waitpid [ Unix.WNOHANG ] w.w_pid with
          | 0, _ -> None
          | _, st -> Some (w, st)
          | exception Unix.Unix_error (Unix.ECHILD, _, _) ->
              Some (w, Unix.WEXITED 0)
        end !running
      in
      if finished = [] then begin
        ignore (Unix.select [] [] [] 0.05) ;
        poll ()
      end else
        List.iter begin fun (w, st) ->
          running := List.filter (fun x -> x.w_pid <> w.w_pid) !running ;
          status.(w.w_idx) <-
            (match st with
             | Unix.WEXITED c -> c
             | Unix.WSIGNALED c | Unix.WSTOPPED c -> 128 + c)
        end finished
    in
    poll () ;
    flush_ready ()
  in
  while !next < n || !running <> [] do
    if !next < n && List.length !running < par then begin
      running := start !next :: !running ;
      incr next
    end else reap ()
  done ;
  (* Consolidate the per-chunk fingerprint caches into the real one. *)
  let module_fp dir =
    if Sys.file_exists dir then
      Array.to_list (Sys.readdir dir)
      |> List.filter (fun e -> Filename.check_suffix e ".tlaps")
      |> List.map (fun e -> Filename.concat (Filename.concat dir e)
                      "fingerprints")
    else []
  in
  let by_module : (string, string list) Hashtbl.t = Hashtbl.create 4 in
  for k = 0 to n - 1 do
    let dir = Filename.concat cache_root (Printf.sprintf "chunk-%d" k) in
    List.iter begin fun fp ->
      let m = Filename.basename (Filename.dirname fp) in
      let prev = try Hashtbl.find by_module m with Not_found -> [] in
      Hashtbl.replace by_module m (prev @ [ fp ])
    end (module_fp dir)
  done ;
  Hashtbl.iter begin fun m sources ->
    let dest_dir = Filename.concat cache_root m in
    if not (Sys.file_exists dest_dir) then
      (try Unix.mkdir dest_dir 0o777 with Unix.Unix_error _ -> ()) ;
    let dest = Filename.concat dest_dir "fingerprints" in
    let sources = if Sys.file_exists dest then sources @ [ dest ] else sources in
    Backend.Fpfile.merge_files sources dest ;
    Util.printf "(* consolidated fingerprints of %d ranges in %S *)%!"
      (List.length sources) dest
  end by_module ;
  (* One aggregate report, from the workers' machine-readable tallies
     (each worker skips its own, which would only show its range). *)
  let totals : (string, int * int) Hashtbl.t = Hashtbl.create 4 in
  for k = 0 to n - 1 do
    let f = Filename.concat
        (Filename.concat cache_root (Printf.sprintf "chunk-%d" k))
        "chunk.summary" in
    if Sys.file_exists f then begin
      let ic = open_in f in
      (try
         while true do
           match String.split_on_char ' ' (input_line ic) with
           | [ m ; total ; failed ] ->
               let (t, fl) =
                 try Hashtbl.find totals m with Not_found -> (0, 0) in
               Hashtbl.replace totals m
                 (t + int_of_string total, fl + int_of_string failed)
           | _ -> ()
         done
       with End_of_file -> () | Failure _ -> ()) ;
      close_in ic
    end
  done ;
  Hashtbl.iter begin fun m (total, failed) ->
    let s = if total > 1 then "s" else "" in
    if failed = 0 then
      Util.eprintf ~prefix:"[INFO]: "
        "module %S: all %d obligation%s proved (%d ranges)." m total s n
    else
      Util.eprintf ~prefix:"[ERROR]: "
        "module %S: %d/%d obligation%s failed (%d ranges)."
        m failed total s n
  end totals ;
  (try Unix.rmdir tmp with Unix.Unix_error _ -> ()) ;
  Array.fold_left (fun acc c -> if c > acc then c else acc) 0 status
