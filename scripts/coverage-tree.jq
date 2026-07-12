def p($c; $t): if $t == 0 then 100 else ($c * 1000 / $t | round / 10) end;
def nodelabel: "\(.label)  \(p(.c; .t))%  \(.c)/\(.t)";

def render($prefix):
  (.children // []) as $ch
  | ($ch | length) as $n
  | reduce range(0; $n) as $i (
      [];
      . + [$prefix + (if $i == $n - 1 then "└─ " else "├─ " end) + ($ch[$i] | nodelabel)]
        + ($ch[$i] | render($prefix + (if $i == $n - 1 then "   " else "│  " end)))
    );

def stacknode($name; $all):
  ($all | map(select(.stack == $name))) as $recs
  | ($recs
      | group_by(.module)
      | sort_by(.[0].module)
      | map({
          label: .[0].module,
          c: (map(.c) | add),
          t: (map(.t) | add),
          children: (sort_by(.file) | map({label: .file, c: .c, t: .t})),
        })) as $mods
  | {label: $name, c: ($recs | map(.c) | add), t: ($recs | map(.t) | add), children: $mods};

($be[0].files
  | to_entries
  | map(select(.value.summary.num_statements > 0))
  | map({
      stack: "backend",
      module: "app",
      file: (.key | sub("^app/"; "")),
      c: .value.summary.covered_lines,
      t: .value.summary.num_statements,
    })) as $bf
| ($fe[0]
    | to_entries
    | map(select(.key != "total"))
    | map({rel: (.key | sub(".*/src/"; "")), c: .value.lines.covered, t: .value.lines.total})
    | map({
        stack: "frontend",
        module: (.rel | if contains("/") then split("/")[0] else "(root)" end),
        file: (.rel | sub("[^/]*/"; "")),
        c: .c,
        t: .t,
      })) as $ff
| ($bf + $ff) as $all
| {
    label: "monori",
    c: ($all | map(.c) | add),
    t: ($all | map(.t) | add),
    children: [stacknode("backend"; $all), stacknode("frontend"; $all)],
  }
| ([nodelabel] + render(""))[]
