(*
 * module/m_elab.mli --- module elaboration
 *
 *
 * Copyright (C) 2008-2010  INRIA and Microsoft Corporation
 *)
open Deque
open Expr.T
open Expr.Visit

open M_t


val normalize:
    ?stream:(M_gen.gen_stepper -> unit) ->
    ?gen_only:(modunit -> bool) ->
    ?gencx:Expr.T.ctx ->
    modctx -> Expr.T.ctx -> mule ->
        modctx * mule * summary

val normalize_reuse:
    modctx -> mule ->
    prev_body:modunit list ->
    old_zone:(int * int) ->
    new_zone:(int * int) ->
        (modctx * mule * summary) option
(** Scoped re-elaboration: reuse the previous version's elaborated body
    and re-elaborate only the single top-level theorem spanning the
    given line zones (old and new version coordinates).  [None] when
    the expected shape does not hold; the caller falls back to the full
    [normalize]. *)
