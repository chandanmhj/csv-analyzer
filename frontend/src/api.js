const B = import.meta.env.VITE_API_URL || "http://localhost:8000";
const j = async (r) => {
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};
const post = (u, b) => fetch(B + u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) }).then(j);
export const api = {
  upload: (blob, name, sid) => { const f = new FormData(); f.append("file", blob, name + ".gz"); f.append("session_id", sid);
    return fetch(B + "/upload", { method: "POST", body: f }).then(j); },
  suggest: (sid) => fetch(`${B}/suggest/${sid}`).then(j),
  analyze: (sid, relationships, overrides) => post(`/analyze/${sid}`, { relationships, overrides }),
  drill: (sid, dataset, filters) => post(`/drill/${sid}`, { dataset, filters }),
  dl: (sid, ds) => `${B}/download/${sid}/${ds}`,
};
// Compress in the browser so a 60 MB CSV fits Supabase/hosting upload caps
export const gzipFile = (f) => new Response(f.stream().pipeThrough(new CompressionStream("gzip"))).blob();
