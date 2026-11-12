(*  use_thy for tlapm under Isabelle2026.

Isabelle2026 removed the theory loader entry "use_thy" that tlapm's
Isabelle backend calls as  poly --eval "(use_thy \"<path>\"; ...)".
This shim restores it: it reads <path>.thy, begins the theory on its
parents (looked up among the theories of the loaded heaps), and runs its
commands one by one with Toplevel.command_exception, so that the first
failing command raises, as the former loader did.
*)

local

fun lookup_parent name =
  (case Build.lookup_theory name of
    SOME thy => thy
  | NONE =>
      (case Build.lookup_theory ("TLA+." ^ name) of
        SOME thy => thy
      | NONE => error ("tlapm use_thy: unknown parent theory " ^ quote name)));

in

fun use_thy (path_name: string) =
  let
    val file = if String.isSuffix ".thy" path_name then path_name else path_name ^ ".thy";
    val path = Path.explode file;
    val text = File.read path;
    val text_pos = Position.file file;
    val header = Thy_Header.read text_pos text;
    val (thy_name, _) = #name header;
    val parents = map (lookup_parent o #1) (#imports header);
    val master_dir = Path.dir path;
    val thy_rec : Resources.thy =
     {name = {node = file, master_dir = master_dir, theory = thy_name},
      pos = text_pos, imports = [], options = [], keywords = #keywords header,
      condition_bad = (false, ""), errors = [], initiators = []};
    val keywords =
      fold (curry Keyword.merge_keywords o Thy_Header.get_keywords) parents
        (Keyword.add_keywords (#keywords header) Keyword.empty_keywords);
    val spans =
      Outer_Syntax.parse_spans (Keyword.command_kind keywords)
        (Token.explode keywords text_pos text);
    fun init () =
     {skip_theory = false, theory = Resources.begin_theory thy_rec parents};
    fun step span st =
      if Command_Span.is_ignored span then st
      else Toplevel.command_exception (Command.read_span keywords st master_dir init span) st;
    val end_state = fold step spans (Toplevel.make_state NONE);
  in ignore (Toplevel.end_theory Position.none end_state) end;

end;
