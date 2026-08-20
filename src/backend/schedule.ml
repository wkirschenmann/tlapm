(*
 * Copyright (C) 2012  Inria and Microsoft Corporation
 *)

(* scheduler for back-end provers *)

open Unix

type task = int * (unit -> computation) list

and computation =
  | Immediate of bool  (* already computed, argument is success *)
  | Todo of command  (* must launch process *)

and command = {
    line: string;  (* shell command line *)
    timeout: float;  (* delay before running timec *)
    timec: timeout_cont;  (* function to call after timeout *)
    donec: result -> float -> bool;
        (* function to call when finished;
        float is time used;
        returns success *)
}

and timeout_cont = unit -> continue

and continue =
  | Timeout
  | Continue of timeout_cont * float

and result =
  | Finished
  | Stopped_kill
  | Stopped_timeout


type process = {
    refid: int;
    pid: int;
    ofd: file_descr;
    start_time: float;
    dl: float;
    tc: timeout_cont;
    dc: result -> float -> bool;
    rest: (unit -> computation) list;
}

let temp_buf = Bytes.create 4096
let read_to_stdout fd =
  try
    let r = Unix.read fd temp_buf 0 (Bytes.length temp_buf) in
    if r = 0 then raise End_of_file;
    output Stdlib.stdout temp_buf 0 r;
    flush Stdlib.stdout
  with Unix_error _ -> raise End_of_file


(* Take a computation, launch the process and return the corresponding
   [process] record. *)
let launch refid cmd t =
  System.harvest_zombies ();
  if !Params.verbose then begin
    Printf.eprintf "launching process: \"%s\"\n" cmd.line;
    flush Stdlib.stderr
  end;
  let (pid, out_read) = System.launch_process cmd.line in
  let start_time = gettimeofday () in
  {
    refid = refid;
    pid = pid;
    ofd = out_read;
    start_time = start_time;
    dl = start_time +. cmd.timeout;
    tc = cmd.timec;
    dc = cmd.donec;
    rest = t;
  }


(* Launch the first process of [comps], if any. *)
let rec start_process refid comps =
  match comps with
  | [] -> []
  | comp :: t ->
     begin match comp () with
     | Immediate false -> start_process refid t
     | Immediate true -> []
     | Todo cmd -> [launch refid cmd t]
     end


(* Kill the process (or not, if reason = Finished) and return the success
   code from its "done" continuation. *)
let kill_process now reason d =
  if reason <> Finished then begin
    System.kill_tree d.pid
  end;
  close d.ofd;
  d.dc reason (now -. d.start_time)


let kill_and_start_next now reason d =
  let success = kill_process now reason d in
  if success then ([], []) else ([], [(d.refid, d.rest)])


(* This function launches the proof tasks and calls their continuation
   functions when their deadlines expire and when they terminate.

   Tasks are pulled one at a time from [next]: [tl] only carries the
   requeued alternatives of killed processes, so at most one fresh task
   is materialized ahead of the provers. Building a whole module's task
   list up front paid every task's eager preparation before the first
   prover started, and pinned every consumed task closure for the whole
   run.

   Note that this uses lists and is inefficient if there are
   many processes.  Optimize it if you have max_threads > 100.
*)
(* Probe (TLAPM_SCHED_TIMES): where the scheduler's wall time goes —
   building the next task (which forces its preparation), launching
   processes, and blocking in [select] waiting for provers.  The point
   of the measurement is the overlap potential: preparation and solver
   waiting are strictly alternating today, so a producer that prepared
   ahead could hide the smaller of the two.  Inert without the
   variable. *)
let sched_probe = Sys.getenv_opt "TLAPM_SCHED_TIMES" <> None
let t_next = ref 0.
let t_launch = ref 0.
let t_wait = ref 0.
let n_wait = ref 0
let sched_time acc f x =
  if not sched_probe then f x
  else begin
    let t0 = Unix.gettimeofday () in
    let r = f x in
    acc := !acc +. (Unix.gettimeofday () -. t0) ;
    r
  end

let sched_report total =
  if sched_probe then begin
    Printf.eprintf
      "[SCHED] total=%.1fs next(prep)=%.1fs launch=%.1fs wait=%.1fs        (selects=%d) other=%.1fs\n%!"
      total !t_next !t_launch !t_wait !n_wait
      (total -. !t_next -. !t_launch -. !t_wait) ;
    Printf.eprintf
      "[SCHED] overlap potential: serial=%.1fs, max(prep+launch, wait)=%.1fs\n%!"
      (!t_next +. !t_launch +. !t_wait)
      (Float.max (!t_next +. !t_launch) !t_wait)
  end

let run_stream max_threads next =
  assert (max_threads >= 1);
  assert (max_threads < 100);
  let t_start_run = Unix.gettimeofday () in
  let rec spin running tl =
    (* Refill: keep at most one pulled-ahead task in [tl]. *)
    let tl =
      if tl = [] then
        (match sched_time t_next next () with Some t -> [t] | None -> [])
      else tl
    in
    let now = Unix.gettimeofday () in
    (* First check stdin for commands from the toolbox. *)
    (* "stop" command *)
    if Toolbox.is_stopped () || Interrupted.is_interrupted () then begin
      List.iter (fun d -> ignore (kill_process now Stopped_kill d)) running;
      raise Exit
    end;
    (* toolbox "kill" command *)
    let kills = Toolbox.get_kills () in
    let f d =
      if List.mem d.refid kills then
        kill_and_start_next now Stopped_kill d
      else
        [d], []
    in
    let newruns, addtasks = List.split (List.map f running) in
    let running = List.flatten newruns in
    let tl = List.flatten addtasks @ tl in

    (* Then compute the next deadline. *)
    let dl = List.fold_left (fun x y -> min x y.dl) infinity running in
    if tl <> [] && List.length running < max_threads && now < dl then begin
      (* Reap already-finished processes before launching the next task:
         constructing a task (encoding an obligation for its prover) can
         take seconds, during which a prover that already exited would
         otherwise sit unread past its deadline and be reported as a
         spurious timeout. A zero-timeout select costs nothing. *)
      let (running, tl) =
        if running = [] then (running, tl)
        else begin
          let outs = List.map (fun x -> x.ofd) running in
          let (ready, _, _) = Unix.select outs [] [] 0.0 in
          if ready = [] then (running, tl)
          else begin
            let now = Unix.gettimeofday () in
            let f d =
              if List.mem d.ofd ready then begin
                try
                  read_to_stdout d.ofd;
                  [d], []
                with End_of_file -> kill_and_start_next now Finished d
              end else
                [d], []
            in
            let newruns, addtasks = List.split (List.map f running) in
            (List.flatten newruns, List.flatten addtasks @ tl)
          end
        end
      in
      (* Then launch new tasks from the task list. This can take time, so
         do it only until the deadline is up. *)
      match tl with
      | [] -> assert false
      | (refid, comps) :: t ->
          spin (sched_time t_launch (start_process refid) comps @ running) t
    end else if running <> [] then begin
      (* Finally, call select and treat the outputs and deadlines. *)
      let outs = List.map (fun x -> x.ofd) running in
      let delay = max 0.0 (min (dl -. Unix.gettimeofday ()) 60.0) in
      let outs = if !Params.toolbox then Unix.stdin :: outs else outs in
      let (ready, _, _) =
        if sched_probe then begin
          incr n_wait ;
          let t0 = Unix.gettimeofday () in
          let r = Unix.select outs [] [] delay in
          t_wait := !t_wait +. (Unix.gettimeofday () -. t0) ;
          r
        end else Unix.select outs [] [] delay
      in
      (* Refresh the clock: select may have slept up to [delay]; dating
         reaps and deadline checks with the stale pre-select timestamp
         under-reports run times and postpones kills. *)
      let now = Unix.gettimeofday () in

      (* outputs *)
      let f d =
        if List.mem d.ofd ready then begin
          try
            read_to_stdout d.ofd;
            [d], []
          with End_of_file -> kill_and_start_next now Finished d
        end else
          [d], []
      in
      let newruns, addtasks = List.split (List.map f running) in
      let running = List.flatten newruns in
      let tl = List.flatten addtasks @ tl in

      (* deadlines *)
      let f d =
        if now >= d.dl then begin
          match d.tc () with
          | Timeout -> kill_and_start_next now Stopped_timeout d
          | Continue (tc, tmo) ->
             [ { d with tc = tc; dl = tmo +. d.start_time } ], []
        end else
          [d], []
      in
      let newruns, addtasks = List.split (List.map f running) in
      let running = List.flatten newruns in
      let tl = List.flatten addtasks @ tl in

      spin running tl
    end (* else we are done. *)
  in
  try
    spin [] [];
    System.harvest_zombies () ;
    sched_report (Unix.gettimeofday () -. t_start_run)
  with Exit ->
    System.harvest_zombies () ;
    sched_report (Unix.gettimeofday () -. t_start_run)


let run max_threads tasks =
  (* List interface kept for existing callers: feed the stream from a
     reference to the remaining tail, so consumed cells become garbage
     as the run progresses instead of staying rooted in this frame. *)
  let rem = ref tasks in
  run_stream max_threads begin fun () ->
    match !rem with
    | [] -> None
    | t :: rest -> rem := rest; Some t
  end
