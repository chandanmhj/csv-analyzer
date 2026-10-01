# CSV Viz Agents

Upload CSVs, link tables, auto-clean (with overrides), get AI-chosen Plotly charts with drill-down, and a plain-English summary.

**Pipeline (LangGraph):** merge, profile, clean, plan (Groq), draw (Plotly), narrate (Groq). pandas does all computation; the LLM only picks charts and writes text. Without a Groq key it falls back to rule-based charts and a simple summary.

## Run locally
```
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && cp .env.example .env   # add GROQ_API_KEY
uvicorn main:app --reload

cd frontend && npm install && cp .env.example .env && npm run dev
```

## Deploy
- **Render** (backend): root dir `backend`, build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`. Set env vars from `.env.example`. Use a 2 GB instance if you allow 60 MB files.
- **Netlify** (frontend): base dir `frontend`, build `npm run build`, publish `dist`, env `VITE_API_URL=<render url>`. Set `FRONTEND_ORIGIN` on Render to the Netlify URL.
- **24 h cleanup:** schedule `curl -X POST <render url>/cleanup -H "x-token: $CLEANUP_TOKEN"` daily (e.g. a GitHub Action).

## Notes
- The browser gzips each CSV before upload; the backend reads `.csv.gz` directly; cleaned data is stored as Parquet.
- Storage is local disk for now. Render's disk is ephemeral, which fits the 24 h auto-delete, but Supabase storage and Postgres are not wired in yet.
