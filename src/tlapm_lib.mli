(*
 * Copyright (C) 2008-2010  INRIA and Microsoft Corporation
 *)

module Module = Module
module Property = Property
module Proof = Proof
module Expr = Expr
module Util = Util
module Loc = Loc
module Ctx = Ctx
module Backend = Backend
module Builtin = Builtin

val main : string list -> unit
val init : unit -> unit

val lsp_gen_scope : (int * int) option ref

val lsp_elab_reuse :
  (Module.T.mule * (int * int) * (int * int)) option ref
(** Scoped re-elaboration for the in-process LSP pipeline: previous
    version's elaborated module, and the edited theorem's line zones in
    the old and new version.  See [Module.Elab.normalize_reuse]. *)

val lsp_elab_reused : bool ref
(** Whether the last [modctx_of_string] took the reuse path. *)

val modctx_of_string :
  content:string ->
  filename:string ->
  loader_paths:string list ->
  prefer_stdlib:bool ->
  (Module.T.modctx * Module.T.mule, string option * string) result
(** Parse and elaborate the specified module and its context
    from a specified string, assume it is located in the
    specified path. *)

val lsp_prove :
  tb_sl:int -> tb_el:int -> Module.T.mule -> Proof.T.obligation list -> unit
(** Prove the given obligations of an already-elaborated module the way
    a `tlapm --toolbox tb_sl tb_el` child would: same toolbox messages
    on stderr, same solver output on stdout, same fingerprint and
    theory files.  Mutates global state like a CLI run — the caller is
    expected to invoke it in a forked process whose stdout/stderr are
    the toolbox pipe and whose working directory is the module's. *)

val module_of_string : string -> Module.T.mule option
(** Parse the specified string as a module. No dependencies
    are considered, nor proof obligations are elaborated. *)

val stdlib_search_paths : string list
(** A list of paths to look for stdlib modules. *)
