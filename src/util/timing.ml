(*
 * timing.ml --- time tracking
 *
 *
 * Copyright (C) 2008-2010  INRIA and Microsoft Corporation
 *)

(**********************************************)
(* Simple timers *)

type timer = float

let start_timer () = Unix.gettimeofday ()

let get_timer t = Unix.gettimeofday () -. t

(**********************************************)
(* Old clock stuff (remove?) *)

type clock = { desc : string ;
               mutable time : float ;
               mutable count : int }

let new_clock desc = { desc = desc ;
                       time = 0.0 ;
                       count = 0 }

let ambient = new_clock "other"

let beginning_of_the_world = Unix.gettimeofday ()

(* Stack of running clocks, bottom element is [ambient]. The interval
   since [last_event] is always attributed to the clock on top, so a
   clocked region nested inside another one (e.g. fingerprinting inside
   the backend phase) is subtracted from the enclosing clock and, when
   it stops, the enclosing clock resumes instead of [ambient]. *)
let stack = ref [ambient]

let last_event = ref beginning_of_the_world

let account now =
  begin match !stack with
  | cl :: _ -> cl.time <- cl.time +. now -. !last_event
  | [] -> ()
  end;
  last_event := now

let start cl =
  account (Unix.gettimeofday ());
  cl.count <- cl.count + 1;
  stack := cl :: !stack

let stop () =
  account (Unix.gettimeofday ());
  match !stack with
  | _ :: (_ :: _ as rest) -> stack := rest
  | _ -> ()  (* unbalanced [stop]: keep [ambient] at the bottom *)

let total desc = {
    desc = desc;
    time = Unix.gettimeofday () -. beginning_of_the_world;
    count = 0;
  }

let string_of_clock cl =
  (* Flush the running interval if [cl] is the clock being timed, so the
     report includes time accrued since the last event. *)
  begin match !stack with
  | top :: _ when top.desc == cl.desc -> account (Unix.gettimeofday ())
  | _ -> ()
  end;
  Printf.sprintf "%s | %-13.6f" cl.desc cl.time
