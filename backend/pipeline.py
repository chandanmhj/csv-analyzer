import json, re, warnings
import pandas as pd, plotly.express as px
warnings.filterwarnings("ignore")

NA = ["", "NA", "N/A", "n/a", "NaN", "null", "NULL", "None", "?", "--"]
MISS = ["mean", "median", "mode", "ffill", "drop_rows", "drop_column", "none"]

def read_csv(src):
    return pd.read_csv(src, na_values=NA, low_memory=False)  # compression inferred from .gz

def kind(s):
    if pd.api.types.is_bool_dtype(s): return "categorical"
    if pd.api.types.is_numeric_dtype(s):
        return "id" if s.dtype.kind == "i" and len(s) > 20 and s.nunique() == len(s) else "numeric"
    if pd.api.types.is_datetime64_any_dtype(s): return "datetime"
    d = s.dropna().astype(str).head(200)
    if len(d) and pd.to_datetime(d, errors="coerce").notna().mean() > .9: return "datetime"
    return "categorical" if s.nunique() <= max(50, .05 * len(s)) else "text"

def profile(df):
    cols = {}
    for c in df.columns:
        s = df[c]; k = kind(s)
        i = {"kind": k, "missing": int(s.isna().sum()), "unique": int(s.nunique())}
        if k == "numeric" and s.notna().any():
            q1, q3 = s.quantile([.25, .75]); r = q3 - q1
            lo, hi = float(q1 - 1.5 * r), float(q3 + 1.5 * r)
            i.update(mean=round(float(s.mean()), 3), median=float(s.median()), min=float(s.min()), max=float(s.max()),
                     lo=lo, hi=hi, outliers=int(((s < lo) | (s > hi)).sum()))
        cols[str(c)] = i
    return {"rows": len(df), "columns": cols}

def suggest(dfs):
    out, names = [], list(dfs)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for ca in dfs[a].columns:
                for cb in dfs[b].columns:
                    if str(ca).lower() != str(cb).lower(): continue
                    sa = set(dfs[a][ca].dropna().astype(str)); sb = set(dfs[b][cb].dropna().astype(str))
                    if sa and sb and len(sa & sb) / min(len(sa), len(sb)) > .3:
                        out.append({"from_table": a, "from_col": ca, "to_table": b, "to_col": cb,
                                    "match": round(len(sa & sb) / min(len(sa), len(sb)), 2)})
    return out

def merge(dfs, rels):
    frames, rep = dict(dfs), {n: n for n in dfs}
    for r in rels:
        a, b = rep[r["from_table"]], rep[r["to_table"]]
        if a == b: continue
        frames[a] = frames[a].merge(frames.pop(b), left_on=r["from_col"], right_on=r["to_col"],
                                    how=r.get("how", "inner"), suffixes=("", "_" + r["to_table"]))
        if len(frames[a]) > 3_000_000:
            raise ValueError("This join produces too many rows. Check the relationship keys (many-to-many?).")
        rep = {n: (a if v == b else v) for n, v in rep.items()}
    return frames

def clean(df, prof, ov):
    df, log = df.copy(), []
    for c, i in prof["columns"].items():
        if i["kind"] == "datetime": df[c] = pd.to_datetime(df[c], errors="coerce")
    for c, i in prof["columns"].items():
        if c not in df: continue
        k, m = i["kind"], int(df[c].isna().sum())
        if m:
            pct = m / max(len(df), 1)
            d = ("drop_column" if pct > .5 else "median" if k == "numeric" and i.get("outliers") else
                 "mean" if k == "numeric" else "ffill" if k == "datetime" else "mode" if k == "categorical" else "drop_rows")
            a = ov.get(c, d)
            if a in ("mean", "median") and k != "numeric": a = "mode"
            if a == "drop_column": df = df.drop(columns=c)
            elif a == "drop_rows": df = df.dropna(subset=[c])
            elif a == "mean": df[c] = df[c].fillna(df[c].mean())
            elif a == "median": df[c] = df[c].fillna(df[c].median())
            elif a == "mode":
                md = df[c].mode()
                if len(md): df[c] = df[c].fillna(md[0])
            elif a == "ffill": df[c] = df[c].ffill().bfill()
            log.append({"key": c, "column": c, "type": "missing", "issue": f"{m} missing ({pct:.0%})", "action": a, "options": MISS})
        if c in df and k == "numeric" and i.get("outliers"):
            a = ov.get(c + "__outliers", "cap")
            if a == "cap": df[c] = df[c].clip(i["lo"], i["hi"])
            log.append({"key": c + "__outliers", "column": c, "type": "outliers",
                        "issue": f'{i["outliers"]} outliers outside [{i["lo"]:.4g}, {i["hi"]:.4g}]', "action": a, "options": ["cap", "keep"]})
    return df, log

ABBR = {"nm": "name", "qty": "quantity", "amt": "amount", "dt": "date", "cust": "customer", "num": "number", "no": "number",
        "desc": "description", "addr": "address", "avg": "average", "cat": "category", "prod": "product", "tot": "total",
        "pct": "percent", "yr": "year", "mnth": "month", "emp": "employee", "dept": "department", "id": "ID"}

def auto_names(cols, llm=None):
    """Readable names: the LLM's suggestion if given, else a rule-based cleanup of cryptic/abbreviated names."""
    out = {}
    for c in cols:
        n = llm.get(c) if isinstance(llm, dict) else None
        if not (isinstance(n, str) and n.strip()):
            toks = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", c)
            if re.search(r"[_\-]|[a-z][A-Z]", c) or any(t.lower() in ABBR for t in toks):
                ws = [ABBR.get(t.lower(), t) for t in toks]
                n = " ".join(w if w == "ID" else w.capitalize() for w in ws)
            else: n = c
        out[c] = n.strip()[:40] or c
    return out

def apply_names(df, auto, ov):
    """User renames (ov['rename:<original>']) win over automatic ones. Returns renamed df and a name list for the UI."""
    final, used = {}, set()
    for c in df.columns:
        n = str(ov.get("rename:" + str(c)) or auto.get(str(c), c)).strip()[:40] or str(c)
        if n in used or (n != c and n in df.columns): n = str(c)
        final[c] = n; used.add(n)
    return df.rename(columns=final), [{"original": str(c), "name": n, "changed": n != str(c)} for c, n in final.items()]

def valid(s, cols):
    k = lambda n: cols.get(n, {}).get("kind")
    x, y = s.get("x"), s.get("y")
    return {"histogram": k(x) == "numeric", "box": k(y) == "numeric",
            "bar": k(x) == "categorical" and (not y or k(y) == "numeric"),
            "line": k(x) in ("datetime", "numeric") and k(y) == "numeric",
            "scatter": k(x) == "numeric" and k(y) == "numeric",
            "heatmap": sum(i["kind"] == "numeric" for i in cols.values()) >= 2}.get(s.get("type"), False)

def heuristic(prof, skip=()):
    cols = prof["columns"]
    g = lambda *ks: [c for c, i in cols.items() if i["kind"] in ks and c not in skip]
    num, cat, dt = g("numeric"), g("categorical"), g("datetime")
    s = []
    if dt and num: s.append({"type": "line", "x": dt[0], "y": num[0], "title": f"{num[0]} over {dt[0]}"})
    if cat: s.append({"type": "bar", "x": cat[0], "y": num[0] if num else None, "title": f"{num[0] if num else 'Count'} by {cat[0]}"})
    s += [{"type": "histogram", "x": c, "title": f"Distribution of {c}"} for c in num[:2]]
    if cat and num: s.append({"type": "box", "x": cat[0], "y": num[0], "title": f"{num[0]} spread by {cat[0]}"})
    if len(num) >= 2: s.append({"type": "scatter", "x": num[0], "y": num[1], "title": f"{num[1]} vs {num[0]}"})
    if len(num) >= 3: s.append({"type": "heatmap", "title": "Correlations"})
    return s[:6]

def build(df, s):
    t, x, y, ti = s["type"], s.get("x"), s.get("y"), s.get("title") or s["type"]
    if t == "histogram": f = px.histogram(df, x=x, title=ti)
    elif t == "box":
        f = px.box(df, x=x, y=y, title=ti) if x and df[x].nunique() <= 15 else px.box(df, y=y, title=ti)
    elif t == "bar":
        d = (df.groupby(x)[y].mean().nlargest(15).reset_index() if y
             else df[x].value_counts().head(15).rename_axis(x).reset_index(name="count"))
        f = px.bar(d, x=x, y=y or "count", title=ti)
    elif t == "line": f = px.line(df.groupby(x)[y].mean().reset_index().sort_values(x), x=x, y=y, title=ti)
    elif t == "scatter": f = px.scatter(df.sample(min(len(df), 3000), random_state=0), x=x, y=y, title=ti)
    else: f = px.imshow(df.select_dtypes("number").iloc[:, :12].corr(), text_auto=".2f", title=ti)
    f.update_layout(template="plotly_white")
    return json.loads(f.to_json())

def charts(df, specs):
    out = []
    for s in specs:
        try: out.append({"spec": s, "fig": build(df, s)})
        except Exception as e: print("chart failed:", s, e)
    return out
