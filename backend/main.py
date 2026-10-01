import os, re, gzip, shutil, time, uuid
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
import pipeline as P
from graph import run_graph

DATA = Path(os.getenv("DATA_DIR", "data")); DATA.mkdir(exist_ok=True)
MAX_BYTES, TTL = 55 * 1024 * 1024, 24 * 3600
app = FastAPI(title="CSV Viz Agents")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("FRONTEND_ORIGIN", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])

def sdir(sid):
    if not re.fullmatch(r"[a-f0-9]{32}", sid): raise HTTPException(400, "Bad session id")
    return DATA / sid
def stem(n): return re.sub(r"[^A-Za-z0-9_-]", "_", re.sub(r"\.csv(\.gz)?$", "", n, flags=re.I))[:60] or "table"
def raw_files(sid): return {p.name[:-7]: p for p in (sdir(sid) / "raw").glob("*.csv.gz")}

@app.post("/upload")
async def upload(file: UploadFile = File(...), session_id: str = Form("")):
    sid = session_id or uuid.uuid4().hex
    d = sdir(sid); (d / "raw").mkdir(parents=True, exist_ok=True)
    if not (d / ".created").exists(): (d / ".created").write_text(str(time.time()))
    data = await file.read()
    if len(data) > MAX_BYTES: raise HTTPException(413, "File is too large (limit about 55 MB compressed).")
    fn = file.filename or "table.csv"
    name = stem(fn); path = d / "raw" / f"{name}.csv.gz"
    path.write_bytes(data if fn.lower().endswith(".gz") else gzip.compress(data))
    try: cols = [str(c) for c in pd.read_csv(path, nrows=0).columns]
    except Exception: path.unlink(); raise HTTPException(400, "Could not read this file as CSV.")
    return {"session_id": sid, "name": name, "columns": cols}

@app.get("/suggest/{sid}")
def suggest(sid: str):
    return P.suggest({n: pd.read_csv(p, nrows=20000, na_values=P.NA) for n, p in raw_files(sid).items()})

class Req(BaseModel):
    relationships: list = []
    overrides: dict = {}

@app.post("/analyze/{sid}")
def analyze(sid: str, req: Req):
    files = raw_files(sid)
    if not files: raise HTTPException(404, "No files in this session. Upload a CSV first.")
    try: st = run_graph({n: P.read_csv(p) for n, p in files.items()}, req.relationships, req.overrides)
    except ValueError as e: raise HTTPException(400, str(e))
    cd = sdir(sid) / "clean"; cd.mkdir(exist_ok=True)
    for n, df in st["cleaned"].items(): df.to_parquet(cd / f"{n}.parquet")
    return {"datasets": {n: {"profile": st["cprofs"][n], "log": st["logs"][n], "names": st["names"][n], "charts": st["charts"][n]} for n in st["cleaned"]},
            "narrative": st["narrative"]}

class Drill(BaseModel):
    dataset: str
    filters: list

@app.post("/drill/{sid}")
def drill(sid: str, r: Drill):
    path = sdir(sid) / "clean" / f"{stem(r.dataset)}.parquet"
    if not path.exists(): raise HTTPException(404, "Run the analysis first.")
    df = pd.read_parquet(path)
    for f in r.filters:
        if f["column"] not in df: raise HTTPException(400, "Unknown column")
        df = df[df[f["column"]].astype(str) == str(f["value"])]
    if df.empty: raise HTTPException(404, "No rows match.")
    return {"rows": len(df), "charts": P.charts(df, P.heuristic(P.profile(df), {f["column"] for f in r.filters}))}

@app.get("/download/{sid}/{ds}")
def download(sid: str, ds: str):
    path = sdir(sid) / "clean" / f"{stem(ds)}.parquet"
    if not path.exists(): raise HTTPException(404, "Not found")
    return Response(pd.read_parquet(path).to_csv(index=False), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{stem(ds)}_cleaned.csv"'})

@app.post("/cleanup")  # call daily (cron / GitHub Action) to delete sessions older than 24 h
def cleanup(x_token: str = Header("")):
    if os.getenv("CLEANUP_TOKEN") and x_token != os.getenv("CLEANUP_TOKEN"): raise HTTPException(403, "Forbidden")
    n = 0
    for d in DATA.iterdir():
        c = d / ".created"
        if c.exists() and time.time() - float(c.read_text()) > TTL: shutil.rmtree(d); n += 1
    return {"deleted": n}
