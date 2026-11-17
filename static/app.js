const $ = (s, el = document) => el.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const state = { status: "", q: "" };

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || res.statusText);
  return body;
}

function riskColor(n) {
  return n >= 50 ? "var(--bad)" : n >= 20 ? "var(--warn)" : "var(--ok)";
}

function fmtSize(b) {
  return b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.ceil(b / 1024) + " KB";
}

async function loadConfig() {
  const cfg = await api("/api/config");
  $("#doc-type").innerHTML = cfg.doc_types.map((t) => `<option>${esc(t)}</option>`).join("");
  $("#max-mb").textContent = cfg.max_mb;
  const b = $("#ocr-badge");
  b.textContent = cfg.ocr ? "OCR enabled" : "OCR not installed";
  b.classList.toggle("on", cfg.ocr);
  b.title = cfg.ocr ? "Tesseract detected" : "Install Tesseract OCR to read scanned documents and images";
}

async function loadStats() {
  const s = await api("/api/stats");
  const items = [["total", "Total documents"], ["flagged", "Flagged"], ["review", "Needs review"], ["passed", "Passed checks"], ["pending", "Awaiting decision"]];
  $("#stats").innerHTML = items.map(([k, l]) => `<div class="stat ${k}"><div class="n">${s[k]}</div><div class="l">${l}</div></div>`).join("");
}

async function loadList() {
  const p = new URLSearchParams();
  if (state.status) p.set("status", state.status);
  if (state.q) p.set("q", state.q);
  const docs = await api("/api/documents?" + p);
  $("#empty").hidden = docs.length > 0;
  $("#rows").innerHTML = docs.map((d) => `
    <tr data-id="${d.id}">
      <td>${d.id}</td>
      <td class="file" title="${esc(d.filename)}">${esc(d.filename)}</td>
      <td>${esc(d.doc_type)}</td>
      <td>${esc(d.uploaded_at)}</td>
      <td><div class="risk"><div class="bar"><i style="width:${d.risk_score}%;background:${riskColor(d.risk_score)}"></i></div>${d.risk_score}</div></td>
      <td><span class="pill ${d.auto_status}">${d.auto_status}</span></td>
      <td><span class="pill ${d.review_status}">${d.review_status}</span></td>
    </tr>`).join("");
}

function refresh() {
  return Promise.all([loadStats(), loadList()]);
}

async function uploadFiles(files) {
  const log = $("#upload-log");
  for (const file of files) {
    const li = document.createElement("li");
    li.textContent = `Analyzing ${file.name}…`;
    log.prepend(li);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("doc_type", $("#doc-type").value);
    try {
      const doc = await api("/api/documents", { method: "POST", body: fd });
      li.innerHTML = `${esc(file.name)}: <span class="pill ${doc.auto_status}">${doc.auto_status}</span> (risk ${doc.risk_score}) <a class="link" href="#" data-open="${doc.id}">view</a>`;
      await refresh();
      if (files.length === 1) openDetail(doc.id);
    } catch (e) {
      li.className = "err";
      li.textContent = `${file.name}: ${e.message}`;
    }
  }
}

function fieldsHtml(f) {
  if (!f || !Object.keys(f).length) return `<p class="sub">No text was extracted.</p>`;
  const labels = { gstin: "GSTIN", pan: "PAN", aadhaar: "Aadhaar", ifsc: "IFSC", email: "Email", dates: "Dates", amounts: "Amounts", invoice_numbers: "Invoice no." };
  const rows = Object.entries(labels).filter(([k]) => f[k] && f[k].length).map(([k, l]) => {
    const chips = f[k].map((v) => typeof v === "object"
      ? `<span class="chip ${v.valid ? "good" : "bad"}" title="${v.valid ? "Checksum valid" : "Checksum invalid"}">${esc(v.value)} ${v.valid ? "✓" : "✗"}</span>`
      : `<span class="chip">${esc(v)}</span>`).join("");
    return `<dt>${l}</dt><dd><div class="chips">${chips}</div></dd>`;
  });
  return rows.length ? `<dl class="kv">${rows.join("")}</dl>` : `<p class="sub">No known identifiers found in the text.</p>`;
}

function metaHtml(m) {
  const rows = [];
  const add = (k, v) => v !== undefined && v !== "" && rows.push(`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`);
  if (m.info) Object.entries(m.info).forEach(([k, v]) => add(k, v));
  add("Pages", m.pages);
  add("Revisions (%%EOF)", m.revisions);
  if (m.digitally_signed !== undefined) add("Digitally signed", m.digitally_signed ? "Yes" : "No");
  if (m.format) add("Format", `${m.format} ${m.width}×${m.height} ${m.mode}`);
  if (m.exif) Object.entries(m.exif).slice(0, 25).forEach(([k, v]) => add("EXIF " + k, v));
  if (m.ela) add("ELA stats", `mean ${m.ela.mean}, p99.9 ${m.ela.p999}, hotspot ratio ${m.ela.hotspot_ratio}`);
  add("Text source", m.text_source);
  return rows.length ? `<dl class="kv">${rows.join("")}</dl>` : `<p class="sub">No metadata.</p>`;
}

async function openDetail(id) {
  const d = await api(`/api/documents/${id}`);
  const order = { high: 0, medium: 1, low: 2, info: 3 };
  const findings = [...d.findings].sort((a, b) => order[a.severity] - order[b.severity]);
  const file = `/api/documents/${d.id}/file`;
  const preview = d.kind === "image" ? `<img src="${file}" alt="Original">` : `<a class="link" href="${file}" target="_blank">Open PDF</a>`;

  $("#detail").innerHTML = `
    <div class="detail-head">
      <h2>${esc(d.filename)}</h2>
      <div class="sub">#${d.id} · ${esc(d.doc_type)} · ${fmtSize(d.size)} · uploaded ${esc(d.uploaded_at)}</div>
    </div>
    <div class="verdict">
      <div class="score" style="color:${riskColor(d.risk_score)}">${d.risk_score}</div>
      <div>
        <div>Risk score · <span class="pill ${d.auto_status}">${d.auto_status}</span></div>
        <div class="sub">Decision: <span class="pill ${d.review_status}">${d.review_status}</span>${d.reviewed_at ? " · " + esc(d.reviewed_at) : ""}${d.reviewer_note ? " · " + esc(d.reviewer_note) : ""}</div>
      </div>
    </div>

    <h3>Findings (${findings.length})</h3>
    ${findings.length ? findings.map((f) => `
      <div class="finding">
        <div class="t"><span class="pill ${f.severity}">${f.severity}</span>${esc(f.title)}<span class="cat">${esc(f.category)}</span></div>
        ${f.detail ? `<div class="d">${esc(f.detail)}</div>` : ""}
      </div>`).join("") : `<p class="sub">No issues detected.</p>`}

    <h3>Extracted fields</h3>
    ${fieldsHtml(d.fields)}

    ${d.has_ela ? `
      <h3>Error level analysis</h3>
      <figure class="ela-grid">
        <div>${preview}<figcaption>Original</figcaption></div>
        <div><img src="/api/documents/${d.id}/ela" alt="ELA"><figcaption>ELA: bright, uneven patches suggest edited regions</figcaption></div>
      </figure>` : `<h3>File</h3><p>${preview}</p>`}

    <h3>Metadata</h3>
    ${metaHtml(d.meta)}
    <dl class="kv" style="margin-top:4px"><dt>SHA-256</dt><dd>${esc(d.sha256)}</dd></dl>

    ${d.text_excerpt ? `<h3>Extracted text</h3><pre class="text">${esc(d.text_excerpt)}</pre>` : ""}

    <h3>Reviewer decision</h3>
    <div class="review-box">
      <textarea id="note" placeholder="Note (optional)">${esc(d.reviewer_note || "")}</textarea>
      <div class="actions">
        <button class="btn approve" data-decision="approved">Approve</button>
        <button class="btn reject" data-decision="rejected">Reject</button>
        <button class="btn ghost" data-decision="pending">Reset</button>
        <button class="btn danger" id="del">Delete</button>
      </div>
    </div>`;

  $("#detail").querySelectorAll("[data-decision]").forEach((b) => b.onclick = async () => {
    await api(`/api/documents/${d.id}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: b.dataset.decision, note: $("#note").value }),
    });
    await refresh();
    openDetail(d.id);
  });
  $("#del").onclick = async () => {
    if (!confirm(`Delete document #${d.id}? This removes the file permanently.`)) return;
    await api(`/api/documents/${d.id}`, { method: "DELETE" });
    closeDetail();
    refresh();
  };
  $("#drawer").hidden = false;
}

function closeDetail() { $("#drawer").hidden = true; }

// Events
const drop = $("#drop");
drop.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && $("#file").click());
$("#file").addEventListener("change", (e) => { uploadFiles([...e.target.files]); e.target.value = ""; });
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => uploadFiles([...e.dataTransfer.files]));

$("#tabs").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("active", x === b));
  state.status = b.dataset.status;
  loadList();
});
let t;
$("#search").addEventListener("input", (e) => { clearTimeout(t); t = setTimeout(() => { state.q = e.target.value.trim(); loadList(); }, 250); });
$("#rows").addEventListener("click", (e) => { const tr = e.target.closest("tr"); if (tr) openDetail(tr.dataset.id); });
$("#upload-log").addEventListener("click", (e) => { const a = e.target.closest("[data-open]"); if (a) { e.preventDefault(); openDetail(a.dataset.open); } });
$("#drawer").addEventListener("click", (e) => e.target.closest("[data-close]") && closeDetail());
document.addEventListener("keydown", (e) => e.key === "Escape" && closeDetail());

loadConfig();
refresh();
