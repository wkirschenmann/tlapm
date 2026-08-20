(* Chunked parallel runs: split the input into contiguous line ranges,
   prove them in separate processes, replay their output in document
   order and consolidate their fingerprint caches.  See chunked.ml for
   why the split is by module unit and why there should be more ranges
   than workers. *)

val run: string -> int
(* [run file] proves [file] in [Params.chunks] ranges with at most
   [Params.spawn] concurrent processes, and returns the exit status to
   use (0, or the most severe worker status). *)
