import { useState, useRef } from "react";
import ReactFlow, { Background, Controls, Handle, Position, ConnectionMode, addEdge, useNodesState, useEdgesState } from "reactflow";
import "reactflow/dist/style.css";
import JSZip from "jszip";
import factory from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import Scene from "./Scene";
import { api, gzipFile } from "./api";

const Plot = (factory.default ?? factory)(Plotly);
const HOW = ["inner", "left", "right"];
const PAPER = { bg: "#fbfaf6", ink: "#16140f", grid: "#e6dfd0", colors: ["#2b4c7e", "#c8553d", "#3f7d5c", "#b08900", "#7a5195"] };

function TableNode({ data }) {
  return (
    <div className="tbl">
      <div className="tbl-h">{data.name}</div>
      {data.columns.map((c) => (
        <div className="tbl-r" key={c}>
          <Handle type="target" position={Position.Left} id={c} /><span>{c}</span><Handle type="source" position={Position.Right} id={c} />
        </div>
      ))}
    </div>
  );
}
const nodeTypes = { table: TableNode };
const Pen = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
  </svg>
);

export default function App() {
  const [sid, setSid] = useState("");
  const [files, setFiles] = useState([]);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [res, setRes] = useState(null);
  const [ov, setOv] = useState({});
  const [drill, setDrill] = useState(null);
  const [edit, setEdit] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const gds = useRef({});
  const key = (ds, i) => `${ds}:${i}`;
  const fname = (c, i) => (c.spec.title || `chart_${i + 1}`).replace(/[^\w-]+/g, "_").slice(0, 50);
  const one = (ds, c, i, f) => Plotly.downloadImage(gds.current[key(ds, i)], { format: f, width: 1200, height: 700, filename: fname(c, i) });
  async function all(ds, charts, f) {
    const z = new JSZip();
    for (const [i, c] of charts.entries()) {
      const gd = gds.current[key(ds, i)]; if (!gd) continue;
      const url = await Plotly.toImage(gd, { format: f, width: 1200, height: 700 });
      const body = url.slice(url.indexOf(",") + 1);
      if (f === "svg") z.file(`${fname(c, i)}.svg`, decodeURIComponent(body)); else z.file(`${fname(c, i)}.${f}`, body, { base64: true });
    }
    const a = document.createElement("a"); a.href = URL.createObjectURL(await z.generateAsync({ type: "blob" }));
    a.download = `${ds}_charts.zip`; a.click(); URL.revokeObjectURL(a.href);
  }

  const rels = edges.map((e) => ({ from_table: e.source, from_col: e.sourceHandle, to_table: e.target, to_col: e.targetHandle, how: e.data?.how || "inner" }));

  async function onFiles(e) {
    setErr(""); setBusy("Uploading…");
    try {
      let id = sid; const added = [];
      for (const f of e.target.files) {
        if (f.size > 60 * 1024 * 1024) throw new Error(`${f.name} is over the 60 MB limit.`);
        const r = await api.upload(await gzipFile(f), f.name, id); id = r.session_id; added.push(r);
      }
      const all = [...files.filter((o) => !added.some((a) => a.name === o.name)), ...added];
      setSid(id); setFiles(all);
      setNodes(all.map((f, i) => ({ id: f.name, type: "table", position: { x: i * 280, y: 20 }, data: { name: f.name, columns: f.columns } })));
    } catch (x) { setErr(x.message); }
    setBusy("");
  }
  async function suggest() {
    try {
      const s = await api.suggest(sid);
      setEdges((es) => s.reduce((acc, r) => addEdge({ source: r.from_table, sourceHandle: r.from_col, target: r.to_table, targetHandle: r.to_col, data: { how: "inner" }, label: "inner" }, acc), es));
    } catch (x) { setErr(x.message); }
  }
  async function analyze(o = {}) {
    setErr(""); setBusy("Analyzing…"); setDrill(null); setEdit(null);
    try { setRes(await api.analyze(sid, rels, o)); setOv(o); } catch (x) { setErr(x.message); }
    setBusy("");
  }
  async function doDrill(ds, filters) {
    try { const r = await api.drill(sid, ds, filters); setDrill({ ds, filters, charts: r.charts, rows: r.rows }); } catch (x) { setErr(x.message); }
  }
  function saveName(original) {
    const o = { ...ov }, v = edit.v.trim();
    if (v) o["rename:" + original] = v; else delete o["rename:" + original];  // empty = back to the automatic name
    analyze(o);
  }
  const cycle = (_, edge) => setEdges((es) => es.map((e) => {
    if (e.id !== edge.id) return e;
    const how = HOW[(HOW.indexOf(e.data?.how || "inner") + 1) % 3];
    return { ...e, data: { how }, label: how };
  }));

  return (
    <>
      <Scene />
      <nav className="top">
        <span className="brand">CHANDAN MHJ</span>
        <a className="navlink" href="https://products.chandanmhj.in">Products</a>
        <a className="btn" href="https://chandanmhj.in">Get in touch</a>
      </nav>

      <main>
        <header className="hero">
          <p className="eyebrow">02 / Data tool</p>
          <h1>CSV-READER</h1>
          <p className="lede">Upload one or more CSV files. Get clean data, easy-to-read column names, charts you can drill into, and a plain-English summary.</p>
          <div className="row">
            <label className="pick">{files.length ? files.map((f) => f.name).join(", ") : "Choose CSV files (up to 60 MB each)"}
              <input type="file" accept=".csv" multiple hidden onChange={onFiles} /></label>
            <button className="btn solid" disabled={!files.length || !!busy} onClick={() => analyze({})}>{busy || "Analyze CSV"}</button>
          </div>
          <p className="hint">Files are deleted after 24 hours.</p>
          {err && <p className="err">{err}</p>}
        </header>

        {files.length > 1 && (
          <section className="linker">
            <div className="bar"><h3 className="label">Link your tables</h3><button onClick={suggest}>Suggest links</button></div>
            <div className="flow">
              <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
                onConnect={(c) => setEdges((es) => addEdge({ ...c, data: { how: "inner" }, label: "inner" }, es))}
                onEdgeClick={cycle} connectionMode={ConnectionMode.Loose} fitView>
                <Background color="#222" /><Controls showInteractive={false} />
              </ReactFlow>
            </div>
            <p className="hint">Drag from one column to another to link tables. Click a link to switch inner, left or right join. Select a link and press Backspace to remove it.</p>
          </section>
        )}

        {res && (
          <article className="paper">
            <div className="meta"><span>[ Result ]</span><span>Data dossier</span></div>
            <h3 className="label">What the data says</h3>
            <div className="narr">{res.narrative}</div>
            {Object.entries(res.datasets).map(([name, d]) => {
              const active = drill?.ds === name;
              const shown = active ? drill.charts : d.charts;
              return (
                <section key={name}>
                  <h2 className="title">{name}</h2>
                  <p className="stats">Read {d.profile.rows} rows and {Object.keys(d.profile.columns).length} columns. {d.log.length} cleaning actions applied.</p>
                  <p><a href={api.dl(sid, name)}>Download cleaned CSV</a></p>

                  <h3 className="label">Column names</h3>
                  <p className="note">Unclear names are rewritten so they are easier to read. Use the pen to set your own name.</p>
                  <table><thead><tr><th>Original</th><th>Name used</th></tr></thead><tbody>
                    {d.names.map((n) => (
                      <tr key={n.original}>
                        <td className="mono">{n.original}</td>
                        <td>{edit?.ds === name && edit.o === n.original ? (
                          <input autoFocus value={edit.v} maxLength={40} aria-label={`New name for ${n.original}`}
                            onChange={(e) => setEdit({ ...edit, v: e.target.value })}
                            onKeyDown={(e) => { if (e.key === "Enter") saveName(n.original); if (e.key === "Escape") setEdit(null); }} />
                        ) : (
                          <>{n.name}
                            <button className="pen" aria-label={`Rename ${n.name}`} onClick={() => setEdit({ ds: name, o: n.original, v: n.name })}><Pen /></button>
                            {n.changed && <span className="tag">renamed</span>}</>
                        )}</td>
                      </tr>
                    ))}
                  </tbody></table>
                  {edit?.ds === name && <p className="note">Press Enter to save, Escape to cancel. Leave it empty to use the automatic name.</p>}

                  {d.log.length > 0 && (
                    <>
                      <h3 className="label">Cleaning</h3>
                      <table><thead><tr><th>Column</th><th>Issue</th><th>Action</th></tr></thead><tbody>
                        {d.log.map((l) => (
                          <tr key={l.key}><td>{l.column}</td><td>{l.issue}</td>
                            <td><select value={ov[l.key] ?? l.action} onChange={(e) => setOv({ ...ov, [l.key]: e.target.value })}>
                              {l.options.map((o) => <option key={o}>{o}</option>)}</select></td></tr>
                        ))}
                      </tbody></table>
                      <button disabled={!!busy} onClick={() => analyze(ov)}>Apply changes</button>
                    </>
                  )}

                  <h3 className="label">Charts</h3>
                  <div className="bar">
                    <button onClick={() => all(name, shown, "png")}>Download PNG</button>
                    <button onClick={() => all(name, shown, "svg")}>Download SVG</button>
                  </div>
                  {active && (
                    <p className="crumb"><button className="link" onClick={() => setDrill(null)}>All</button>
                      {drill.filters.map((f) => ` › ${f.column} = ${f.value}`)} ({drill.rows} rows)</p>
                  )}
                  <div className="grid">
                    {shown.map((c, i) => (
                      <figure key={i}>
                        <Plot data={c.fig.data}
                          layout={{ ...c.fig.layout, autosize: true, margin: { l: 50, r: 20, t: 50, b: 50 }, paper_bgcolor: PAPER.bg, plot_bgcolor: PAPER.bg,
                            font: { color: PAPER.ink }, colorway: PAPER.colors,
                            xaxis: { ...c.fig.layout.xaxis, gridcolor: PAPER.grid }, yaxis: { ...c.fig.layout.yaxis, gridcolor: PAPER.grid } }}
                          config={{ responsive: true, displaylogo: false }} useResizeHandler style={{ width: "100%", height: 340 }}
                          onInitialized={(_, gd) => { gds.current[key(name, i)] = gd; }} onUpdate={(_, gd) => { gds.current[key(name, i)] = gd; }}
                          onClick={(ev) => c.spec.type === "bar" && doDrill(name, [...(active ? drill.filters : []), { column: c.spec.x, value: ev.points[0].x }])} />
                        <button className="link" onClick={() => one(name, c, i, "png")}>PNG</button>
                        <button className="link" onClick={() => one(name, c, i, "svg")}>SVG</button>
                      </figure>
                    ))}
                  </div>
                  <p className="note">Click a bar to drill into it.</p>
                </section>
              );
            })}
          </article>
        )}
      </main>

      <footer>
        <a className="btn" href="https://chandanmhj.in">Meet the developer</a>
        <span className="copy">© 2026 CHANDAN MHJ</span>
      </footer>
    </>
  );
}
