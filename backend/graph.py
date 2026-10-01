import json
from typing import TypedDict
from langgraph.graph import StateGraph, END
import pipeline as P
from agents import run_agent

PLANNER = ("You are a data visualization planner. Given a dataset profile, choose 4-6 charts. "
 'Return JSON: {"charts":[{"type":"histogram|box|bar|line|scatter|heatmap","x":col,"y":col,"title":str}]}. '
 "histogram: x numeric. box: y numeric, optional x categorical. bar: x categorical, optional y numeric (averaged). "
 "line: x datetime or numeric, y numeric. scatter: numeric x and y. heatmap: no columns. Use only existing column names.")
NARRATOR = ("You are a data analyst. In under 250 words of plain English markdown, explain what this data is, key patterns, "
 "the data-quality fixes applied, and caveats. Use only the numbers provided; do not invent facts.")

NAMER = ("You rename unclear spreadsheet column names. Input: JSON of column name to 3 sample values. "
 'Return JSON: {"names":{"old":"new"}}. Only rename names that are cryptic, abbreviated or inconsistent (e.g. cust_nm -> Customer Name). '
 "Keep the same meaning; never invent a different concept. If a name is already clear, return it unchanged. Max 4 words.")

class S(TypedDict, total=False):
    dfs: dict; rels: list; ov: dict; sets: dict; profs: dict
    cleaned: dict; names: dict; cprofs: dict; logs: dict; plans: dict; charts: dict; narrative: str

def n_merge(s): return {"sets": P.merge(s["dfs"], s["rels"])}
def n_profile(s): return {"profs": {n: P.profile(d) for n, d in s["sets"].items()}}

def n_clean(s):
    cl, lg, nm = {}, {}, {}
    for n, d in s["sets"].items():
        df, log = P.clean(d, s["profs"][n], s["ov"])
        sample = {str(c): [str(v) for v in df[c].dropna().head(3)] for c in list(df.columns)[:60]}
        r = run_agent(NAMER, json.dumps(sample), True)
        auto = P.auto_names([str(c) for c in df.columns], (r or {}).get("names"))
        df, names = P.apply_names(df, auto, s["ov"])
        ren = {x["original"]: x["name"] for x in names}
        for l in log: l["column"] = ren.get(l["column"], l["column"])  # keys stay original so overrides keep working
        cl[n], lg[n], nm[n] = df, log, names
    return {"cleaned": cl, "logs": lg, "names": nm, "cprofs": {n: P.profile(d) for n, d in cl.items()}}

def n_plan(s):
    out = {}
    for n, p in s["cprofs"].items():
        brief = {c: {"kind": i["kind"], "unique": i["unique"]} for c, i in list(p["columns"].items())[:60]}
        r = run_agent(PLANNER, json.dumps({"rows": p["rows"], "columns": brief}), True)
        specs = [x for x in (r or {}).get("charts", []) if isinstance(x, dict) and P.valid(x, p["columns"])]
        out[n] = specs[:6] or P.heuristic(p)  # rule-based fallback if the LLM is unavailable or returns junk
    return {"plans": out}

def n_draw(s): return {"charts": {n: P.charts(s["cleaned"][n], sp) for n, sp in s["plans"].items()}}

def n_narrate(s):
    keep = ("kind", "mean", "median", "min", "max", "unique")
    brief = {n: {"rows": p["rows"], "columns": {c: {k: v for k, v in i.items() if k in keep} for c, i in list(p["columns"].items())[:40]}}
             for n, p in s["cprofs"].items()}
    payload = json.dumps({"data": brief, "cleaning": s["logs"],
                          "charts": {n: [c["spec"].get("title") for c in cs] for n, cs in s["charts"].items()}})
    fallback = "\n\n".join(f"**{n}**: {p['rows']} rows, {len(p['columns'])} columns, {len(s['logs'][n])} cleaning actions applied."
                           for n, p in s["cprofs"].items())
    return {"narrative": run_agent(NARRATOR, payload[:12000]) or fallback}

g = StateGraph(S)
seq = [("merge", n_merge), ("profile", n_profile), ("clean", n_clean), ("plan", n_plan), ("draw", n_draw), ("narrate", n_narrate)]
for name, fn in seq: g.add_node(name, fn)
g.set_entry_point("merge")
for (a, _), (b, _) in zip(seq, seq[1:]): g.add_edge(a, b)
g.add_edge("narrate", END)
APP = g.compile()

def run_graph(dfs, rels, ov): return APP.invoke({"dfs": dfs, "rels": rels, "ov": ov})
