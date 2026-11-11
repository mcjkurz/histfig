"use strict";
/* HistFig UI — vanilla JS, hash routing:
   #/                      figures
   #/figure/:id            manage a figure (documents, persona, search test)
   #/chat/:id[/:convId]    chat
   #/settings              configuration overview */

const app = document.getElementById("app");
let cleanup = []; // functions run when leaving a page (timers, aborts)
let PUBLIC = false; // read-only server (`histfig serve --public`): visitors can only chat

// ---------------------------------------------------------------- helpers

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const init = { ...opts, headers: { ...(opts.headers || {}) } };
  if (opts.json !== undefined) {
    init.body = JSON.stringify(opts.json);
    init.headers["Content-Type"] = "application/json";
  }
  const res = await fetch("/api" + path, init);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail
        : Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join("; ") : msg;
    } catch (_) {}
    throw new Error(msg);
  }
  const type = res.headers.get("content-type") || "";
  return type.includes("json") ? res.json() : res.text();
}

function toast(msg, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = "toast" + (isError ? " err" : "");
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (el.hidden = true), isError ? 6000 : 2500);
}

const fail = (e) => toast(e.message || String(e), true);

function initials(name) {
  return esc((name || "?").trim().split(/\s+/).map((w) => [...w][0]).slice(0, 2).join("").toUpperCase());
}

function avatar(fig, size = "") {
  return fig.image_url
    ? `<img class="avatar ${size}" src="${fig.image_url}?v=${encodeURIComponent(fig.image)}" alt="">`
    : `<div class="avatar ${size}">${initials(fig.name)}</div>`;
}

/* A "?" that shows an explanation in a bubble on hover, focus or tap. */
function help(text) {
  return `<button type="button" class="help" aria-label="${esc(text)}" data-help="${esc(text)}">?</button>`;
}

/* Years are whole numbers; negative = BC. Mirrors prompts.years() on the server. */
function years(fig) {
  const parse = (v) => (v === "" || v == null || !/^-?\d+$/.test(String(v).trim()) ? null : Number(v));
  const b = parse(fig.birth_year), d = parse(fig.death_year);
  if (b === null && d === null) return "";
  if ((b ?? 0) < 0 && (d ?? 0) < 0 && b !== null && d !== null) return `${-b}–${-d} BC`;
  const bc = (b ?? 0) < 0 || (d ?? 0) < 0;
  const one = (y) => (y === null ? "?" : y < 0 ? `${-y} BC` : bc ? `AD ${y}` : `${y}`);
  return `${one(b)}–${one(d)}`;
}

/* Minimal, safe text → HTML: paragraphs, line breaks, **bold**, *italic*. */
function renderText(text) {
  return esc(text.trim())
    .split(/\n{2,}/)
    .map((p) => "<p>" + p
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
      .replace(/\n/g, "<br>") + "</p>")
    .join("");
}

/* Passage numbers the model cites, "[2]" or "[1, 3]", as small source buttons that open the
   passage in the Sources panel. A number without a passage (the model got it wrong) is greyed out. */
function linkCitations(html, sources) {
  if (!sources.length) return html;
  return html.replace(/\s*\[(?:source:?\s*)?(\d+(?:\s*[,，、]\s*\d+)*)\]/gi, (all, list) =>
    `<span class="cite">${list.split(/\s*[,，、]\s*/).map(Number).map((n) => {
      const h = sources[n - 1];
      return h ? `<a href="#" data-cite="${n}" title="${esc(h.filename)}, part ${h.chunk + 1}">${n}</a>`
        : `<a class="missing" title="No passage ${n}">${n}</a>`;
    }).join("")}</span>`);
}

/* Split model output into thinking + answer (handles inline <think> tags). */
function splitThinking(raw) {
  const thinking = [];
  let answer = raw.replace(/<think>([\s\S]*?)<\/think>/g, (_, t) => { thinking.push(t); return ""; });
  const open = answer.indexOf("<think>");
  if (open !== -1) { thinking.push(answer.slice(open + 7)); answer = answer.slice(0, open); }
  return { thinking: thinking.join("\n").trim(), answer: answer.trim() };
}

function modal(html, onMount) {
  const bg = document.createElement("div");
  bg.className = "modal-bg";
  bg.innerHTML = `<div class="modal card">${html}</div>`;
  const close = () => bg.remove();
  bg.addEventListener("click", (e) => { if (e.target === bg) close(); });
  document.body.appendChild(bg);
  onMount(bg.querySelector(".modal"), close);
  return close;
}

function figureForm(fig = {}) {
  return `
    <label>Name</label><input name="name" required maxlength="200" value="${esc(fig.name)}">
    <div class="row years-row">
      <div style="flex:1"><div class="label-row"><label>Born</label>${help(
        "Whole years. Leave empty if unknown. Use a minus sign for years BC: -551 means 551 BC.")}</div>
        <input name="birth_year" type="number" step="1" min="-99999" max="99999" value="${esc(fig.birth_year)}" placeholder="e.g. 1881 or -551"></div>
      <div style="flex:1"><div class="label-row"><label>Died</label></div>
        <input name="death_year" type="number" step="1" min="-99999" max="99999" value="${esc(fig.death_year)}" placeholder="e.g. 1936 or -479"></div>
    </div>
    <div class="hint years-preview"></div>
    <label>Short description</label>
    <textarea name="description" rows="3" maxlength="2000">${esc(fig.description)}</textarea>
    <label>Persona instructions <span class="muted">(optional — how the figure should speak and behave)</span></label>
    <textarea name="persona" rows="5" maxlength="4000" placeholder="You are Liang Qichao, a reformist scholar…">${esc(fig.persona)}</textarea>`;
}

/* "12,345 tokens · $0.0012" — whatever the provider reported. */
function usageText(tokens, cost) {
  if (!tokens) return "";
  const money = cost > 0 ? ` · $${cost < 0.01 ? cost.toPrecision(2) : cost.toFixed(2)}` : "";
  return `${Number(tokens).toLocaleString()} tokens${money}`;
}

/* The chat model list, loaded once in the background (the provider can be slow). */
let modelsPromise = null;
function getModels() {
  modelsPromise ??= api("/models").catch(() => { modelsPromise = null; return { models: [], default: "" }; });
  return modelsPromise;
}

// ---------------------------------------------------------------- prompts (shared)

const PLACEHOLDER_HELP = {
  name: "the figure's name",
  years: "e.g. 1881–1936 or 551–479 BC",
  description: "the short description",
  persona: "the persona instructions (or “You are … (years).” if empty)",
};

/* One row in a prompt list: name, badge, actions, and the full text (scrollable). */
function promptRow(p, { isDefault = false, canDefault = false } = {}) {
  return `<li data-prompt="${p.id}">
    <div class="prompt-head"><b>${esc(p.name)}</b>
      ${isDefault ? `<span class="badge ready">default</span>` : ""}
      <span class="spacer"></span>
      <button type="button" class="btn small" data-edit="${p.id}">Edit</button>
      ${canDefault && !isDefault ? `<button type="button" class="btn small" data-default="${p.id}">Make default</button>` : ""}
      ${isDefault ? "" : `<button type="button" class="link icon danger" data-remove="${p.id}" title="Delete">✕</button>`}
    </div>
    <div class="prompt-full">${esc(p.text)}</div></li>`;
}

/* Edit a prompt in place in its list (or add a new one at the top).
   onDone() re-renders the list, after saving or cancelling. */
async function editPrompt({ list, prompt = null, figureId = null, onDone }) {
  const builtin = await api("/prompts/builtin");
  list.querySelector("li.prompt-editing")?.remove(); // one editor at a time
  let li = prompt ? list.querySelector(`li[data-prompt="${prompt.id}"]`) : null;
  if (!li) {
    li = document.createElement("li");
    list.querySelector("li.muted")?.remove(); // "no prompts yet"
    list.prepend(li);
  }
  li.className = "prompt-editing";
  li.innerHTML = `<form>
      <div class="prompt-head"><input name="name" required maxlength="100" value="${esc(prompt?.name || "")}"
        placeholder="Prompt name, e.g. Socratic tutor" class="prompt-name"></div>
      <textarea name="text" required rows="14" maxlength="20000" class="prompt-text">${esc(prompt?.text ?? builtin.text)}</textarea>
      <div class="chips">${builtin.placeholders.map((p) =>
        `<button type="button" class="chip" data-ph="${p}" title="${esc(PLACEHOLDER_HELP[p] || "")}">{${p}}</button>`).join("")}
        ${help("Click a placeholder to insert it at the cursor; it is replaced with the figure's details.")}
        <span class="spacer"></span>
        <button type="button" class="link small" data-builtin>Reset to built-in</button></div>
      <div class="row" style="margin-top:12px"><span class="spacer"></span>
        <button type="button" class="btn small" data-cancel>Cancel</button>
        <button class="btn small primary">Save</button></div>
    </form>`;
  const form = li.querySelector("form"), text = form.text;
  li.querySelector(".chips").onclick = (e) => {
    const ph = e.target.closest("[data-ph]");
    if (!ph) return;
    const at = text.selectionStart ?? text.value.length;
    text.setRangeText(`{${ph.dataset.ph}}`, at, text.selectionEnd ?? at, "end");
    text.focus();
  };
  li.querySelector("[data-builtin]").onclick = () => {
    if (text.value === builtin.text || confirm("Replace the text with the built-in prompt?")) text.value = builtin.text;
  };
  li.querySelector("[data-cancel]").onclick = () => onDone();
  form.onkeydown = (e) => { if (e.key === "Escape") onDone(); };
  form.onsubmit = async (e) => {
    e.preventDefault();
    const body = { name: form.name.value.trim(), text: text.value };
    try {
      if (prompt) await api(`/prompts/${prompt.id}`, { method: "PUT", json: body });
      else await api("/prompts", { method: "POST", json: { ...body, figure_id: figureId } });
      toast("Prompt saved");
      onDone();
    } catch (err) { fail(err); }
  };
  (prompt ? text : form.name).focus();
  li.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

/* Show how the years will be displayed ("551–479 BC") while typing. */
function wireYears(form) {
  const preview = form.querySelector(".years-preview");
  const update = () => {
    const shown = years({ birth_year: form.birth_year.value, death_year: form.death_year.value });
    preview.textContent = shown ? `Shown as ${shown}` : "";
  };
  form.birth_year.addEventListener("input", update);
  form.death_year.addEventListener("input", update);
  update();
}

const formData = (form) => Object.fromEntries(new FormData(form).entries());

const IMAGE_ACCEPT = "image/png,image/jpeg,image/gif,image/webp";

/* Set a figure's portrait from a file (preferred) or an image URL; returns the figure, or null. */
async function setPortrait(id, file, url) {
  if (file) {
    const body = new FormData();
    body.append("file", file);
    return api(`/figures/${id}/image`, { method: "POST", body });
  }
  if (url && url.trim()) return api(`/figures/${id}/image-url`, { method: "POST", json: { url: url.trim() } });
  return null;
}

// ---------------------------------------------------------------- router

const routes = [
  [/^#?\/?$/, pageFigures],
  [/^#\/figure\/(\d+)$/, pageFigure],
  [/^#\/chat\/(\d+)(?:\/(\d+))?$/, pageChat],
  [/^#\/chat$/, pageLastChat],
  [/^#\/settings$/, pageSettings],
];

function route() {
  cleanup.forEach((fn) => fn());
  cleanup = [];
  const hash = location.hash || "#/";
  if (PUBLIC && /^#\/(settings|figure\/)/.test(hash)) { location.replace("#/"); return; } // not for visitors
  const section = hash.startsWith("#/settings") ? "settings" : hash.startsWith("#/chat") ? "chat" : "figures";
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === section));
  // "Figures" returns to the figure page you were on; clicked while there, it goes to the list.
  if (section === "figures") prefs.set("lastFigures", hash);
  document.querySelector('[data-nav="figures"]').href = section === "figures" ? "#/" : prefs.get("lastFigures", "#/");
  updateChatNav();
  for (const [re, page] of routes) {
    const m = hash.match(re);
    if (m) return page(...m.slice(1).map((x) => (x ? Number(x) : undefined))).catch(fail);
  }
  app.innerHTML = `<div class="page"><h1>Not found</h1><a href="#/">Back to figures</a></div>`;
}
window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", async () => {
  PUBLIC = (await api("/info").catch(() => ({}))).public === true;
  document.body.classList.toggle("public", PUBLIC); // hides everything marked .admin-only
  route();
  getModels();
  if (!PUBLIC) api("/settings").then((st) => { // not set up yet → start on the Settings page
    if (st.problems.length && (location.hash === "" || location.hash === "#/")) location.hash = "#/settings";
  }).catch(() => {});
});

// ---------------------------------------------------------------- figures

async function pageFigures() {
  const figures = await api("/figures");
  app.innerHTML = `
    <div class="page">
      <div class="row" style="margin-bottom:16px"><h1>Figures</h1></div>
      <div class="grid">
        ${figures.map((f) => `
          <div class="card figure-card">
            <div class="head">${avatar(f)}<div><h3 style="margin:0">${esc(f.name)}</h3>
              <div class="muted small">${years(f)}</div></div></div>
            <p>${esc(f.description) || "<i>No description</i>"}</p>
            <div class="muted small">${f.documents} document${f.documents === 1 ? "" : "s"} · ${f.chunks} passages
              ${f.working ? " · <span class='badge processing'>processing</span>" : ""}
              ${f.needs_rebuild ? " · <span class='badge error'>needs rebuild</span>" : ""}</div>
            <div class="row"><a class="btn primary" href="#/chat/${f.id}">Chat</a>
              <a class="btn admin-only" href="#/figure/${f.id}">Manage</a></div>
          </div>`).join("")}
        <button class="card new-card admin-only" id="new-figure">+ New figure</button>
      </div>
      ${figures.length ? "" : `<p class="muted admin-only" style="margin-top:24px">Create a figure, upload their writings
        (txt, md, pdf, docx), and start a conversation.</p>`}
    </div>`;
  document.getElementById("new-figure").onclick = () => modal(`
      <h2>New figure</h2><form>${figureForm()}
      <label>Portrait <span class="muted">(optional — an image file, or a link to one)</span></label>
      <input type="file" name="image_file" accept="${IMAGE_ACCEPT}">
      <input type="url" name="image_url" maxlength="2000" placeholder="…or paste an image link (https://…)" style="margin-top:6px">
      <div class="row" style="margin-top:16px"><span class="spacer"></span>
        <button type="button" data-close>Cancel</button><button class="primary">Create</button></div></form>`,
    (el, close) => {
      el.querySelector("[data-close]").onclick = close;
      el.querySelector("input").focus();
      wireYears(el.querySelector("form"));
      el.querySelector("form").onsubmit = async (e) => {
        e.preventDefault();
        const { image_file, image_url, ...fields } = formData(e.target);
        const submit = e.target.querySelector("button.primary");
        submit.disabled = true;
        try {
          const fig = await api("/figures", { method: "POST", json: fields });
          try {
            await setPortrait(fig.id, e.target.image_file.files[0], image_url);
          } catch (err) { fail(new Error(`Figure created, but the portrait failed: ${err.message}`)); }
          close();
          location.hash = `#/figure/${fig.id}`;
        } catch (err) { fail(err); submit.disabled = false; }
      };
    });
}

// ---------------------------------------------------------------- figure detail

async function pageFigure(id) {
  let fig;
  try { fig = await api(`/figures/${id}`); }
  catch (err) { prefs.set("lastFigures", "#/"); location.replace("#/"); throw err; } // deleted meanwhile
  app.innerHTML = `
    <div class="page">
      <div class="row" style="margin-bottom:16px">
        <a href="#/" class="link">← Figures</a><span class="spacer"></span>
        <a class="btn primary" href="#/chat/${id}">Chat with ${esc(fig.name)}</a>
      </div>
      <div id="rebuild-banner"></div>
      <div class="two-col">
        <div class="card">
          <div class="row"><div id="portrait">${avatar(fig, "lg")}</div>
            <div><h2 style="margin:0">${esc(fig.name)}</h2><div class="muted">${years(fig)}</div>
              <div class="row" style="margin-top:8px;gap:6px">
                <label class="btn small">Portrait from file
                  <input type="file" id="image-input" accept="${IMAGE_ACCEPT}" hidden></label>
                <button type="button" class="small" id="image-url-btn">Portrait from URL</button></div></div></div>
          <form id="fig-form">${figureForm(fig)}
            <div class="row" style="margin-top:14px"><button class="primary">Save</button>
              <span class="spacer"></span><button type="button" class="danger" id="delete-fig">Delete figure</button></div>
          </form>
        </div>
        <div>
          <div class="card">
            <h2>Documents</h2>
            <div class="dropzone" id="dropzone">Drop files here or click to choose<br>
              <span class="small">txt · md · pdf · docx — several at once is fine</span>
              <input type="file" id="file-input" multiple accept=".txt,.md,.pdf,.docx" hidden></div>
            <ul class="doc-list" id="docs"></ul>
            <div class="row small muted" style="margin-top:10px">
              <span id="embed-info"></span><span class="spacer"></span>
              <button class="link" id="rebuild" title="Re-chunk and re-embed everything with the current settings">Rebuild index</button>
            </div>
          </div>
          <div class="card" style="margin-top:16px">
            <div class="row card-head"><h2>Prompts</h2>${help(
              "Prompts tell the model how to play the figure. General prompts (managed in Settings) work for every figure; prompts added here are only for this figure. Each conversation can pick one under ⚙ Options.")}
              <span class="spacer"></span><button type="button" class="btn small" id="new-prompt">+ New prompt</button></div>
            <div class="setting" style="border-top:none;padding-top:0">
              <label for="fig-default-prompt">New conversations use</label>
              <select id="fig-default-prompt"></select>
            </div>
            <ul class="prompt-list" id="fig-prompts"></ul>
            <p class="small muted" style="margin:10px 0 0">General prompts are edited in <a href="#/settings">Settings</a>.</p>
          </div>
        </div>
      </div>
    </div>`;

  const renderBanner = () => {
    document.getElementById("rebuild-banner").innerHTML = fig.needs_rebuild
      ? `<div class="banner">These documents were embedded with <b>${esc(fig.embed_model)}</b>, but the configured
         model is <b>${esc(fig.current_embed_model)}</b>. Search falls back to keywords until you
         <button class="link" onclick="document.getElementById('rebuild').click()"><u>rebuild the index</u></button>.</div>` : "";
    const used = usageText(fig.embed_tokens_total, fig.embed_cost_total);
    document.getElementById("embed-info").innerHTML = [
      fig.embed_model ? `Vectors: ${esc(fig.embed_model)} (${fig.embed_dim}d)` : "",
      used ? `<span title="Total embedding usage for this figure so far, including rebuilds">Used so far: <b>${used}</b></span>` : "",
    ].filter(Boolean).join(" · ");
  };
  renderBanner();

  // Documents list with polling while work is in progress
  let timer = null;
  const loadDocs = async () => {
    const docs = await api(`/figures/${id}/documents`);
    const el = document.getElementById("docs");
    if (!el) return;
    el.innerHTML = docs.length ? docs.map((d) => {
      const pct = d.chunk_count ? Math.round((100 * d.embedded_count) / d.chunk_count) : 0;
      const working = d.status === "pending" || d.status === "processing";
      return `<li>
        <span class="name">${esc(d.filename)}</span>
        <span class="row"><span class="badge ${d.status}">${d.status === "processing" ? `embedding ${pct}%` : d.status}</span>
          ${d.status === "error" ? `<button class="link" data-retry="${d.id}">retry</button>` : ""}
          <button class="link danger" data-del="${d.id}" title="Delete">✕</button></span>
        <span class="muted small">${d.chunk_count ? `${d.chunk_count} passages · ${d.char_count.toLocaleString()} characters` : ""}${d.embed_tokens ? ` · ${usageText(d.embed_tokens, d.embed_cost)}` : ""}
          ${d.error ? `<span class="error">${esc(d.error)}</span>` : ""}</span>
        ${working ? `<div class="progress"><div style="width:${pct}%"></div></div>` : ""}
      </li>`;
    }).join("") : `<li class="muted">No documents yet.</li>`;
    clearTimeout(timer);
    fig = await api(`/figures/${id}`); renderBanner(); // keeps the usage total live
    if (docs.some((d) => d.status === "pending" || d.status === "processing")) {
      timer = setTimeout(() => loadDocs().catch(fail), 1500);
    }
  };
  cleanup.push(() => clearTimeout(timer));
  await loadDocs();

  document.getElementById("docs").onclick = async (e) => {
    const del = e.target.closest("[data-del]"), retry = e.target.closest("[data-retry]");
    try {
      if (del && confirm("Delete this document and its passages?")) {
        await api(`/documents/${del.dataset.del}`, { method: "DELETE" });
        fig = await api(`/figures/${id}`); renderBanner();
      }
      if (retry) await api(`/documents/${retry.dataset.retry}/retry`, { method: "POST" });
      await loadDocs();
    } catch (err) { fail(err); }
  };

  // Uploads
  const upload = async (files) => {
    if (!files.length) return;
    const body = new FormData();
    for (const f of files) body.append("files", f);
    try {
      toast(`Uploading ${files.length} file(s)…`);
      const res = await api(`/figures/${id}/documents`, { method: "POST", body });
      if (res.skipped.length) toast("Skipped: " + res.skipped.map((s) => `${s.filename} (${s.reason})`).join(", "), true);
      else toast(`Added ${res.added.length} file(s); processing in the background.`);
      await loadDocs();
    } catch (err) { fail(err); }
  };
  const dz = document.getElementById("dropzone"), fileInput = document.getElementById("file-input");
  dz.onclick = () => fileInput.click();
  fileInput.onchange = () => { upload([...fileInput.files]); fileInput.value = ""; };
  dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("over"); };
  dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = (e) => { e.preventDefault(); dz.classList.remove("over"); upload([...e.dataTransfer.files]); };

  document.getElementById("rebuild").onclick = async () => {
    if (!confirm("Re-chunk and re-embed all documents with the current settings? This may take a while.")) return;
    try {
      await api(`/figures/${id}/rebuild`, { method: "POST" });
      fig = await api(`/figures/${id}`); renderBanner(); await loadDocs();
    } catch (err) { fail(err); }
  };

  // Portrait
  const changePortrait = async (file, url) => {
    try {
      const updated = await setPortrait(id, file, url);
      if (updated) { fig = updated; document.getElementById("portrait").innerHTML = avatar(fig, "lg"); }
    } catch (err) { fail(err); }
  };
  document.getElementById("image-input").onchange = (e) => changePortrait(e.target.files[0]);
  document.getElementById("image-url-btn").onclick = () => {
    const url = prompt("Link to an image (PNG, JPEG, GIF or WebP):");
    if (url) changePortrait(null, url);
  };

  // Metadata
  wireYears(document.getElementById("fig-form"));
  document.getElementById("fig-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      fig = await api(`/figures/${id}`, { method: "PUT", json: formData(e.target) });
      toast("Saved");
    } catch (err) { fail(err); }
  };
  document.getElementById("delete-fig").onclick = async () => {
    if (!confirm(`Delete ${fig.name}, all documents and all conversations? This cannot be undone.`)) return;
    try {
      await api(`/figures/${id}`, { method: "DELETE" });
      if (prefs.get("lastChat", null)?.figureId === id) prefs.set("lastChat", null);
      location.hash = "#/";
    } catch (err) { fail(err); }
  };

  // Prompts
  let generalDefaultId = null;
  const loadPrompts = async () => {
    const all = await api(`/prompts?figure_id=${id}`);
    const general = all.filter((p) => p.figure_id === null), own = all.filter((p) => p.figure_id === id);
    const generalDefault = general.find((p) => p.is_default);
    generalDefaultId = generalDefault?.id ?? null;
    const selected = fig.default_prompt_id ?? generalDefaultId;
    // One plain list: the default first, then other general prompts, then this figure's own.
    document.getElementById("fig-default-prompt").innerHTML = all.map((p) =>
      `<option value="${p.id}" ${p.id === selected ? "selected" : ""}>${esc(p.name)}</option>`).join("");
    document.getElementById("fig-prompts").innerHTML = own.length
      ? own.map((p) => promptRow(p, { isDefault: false })).join("")
      : `<li class="muted small">No prompts for this figure yet — the general ones are used.</li>`;
    return own;
  };
  let ownPrompts = await loadPrompts();
  document.getElementById("new-prompt").onclick = () =>
    editPrompt({ list: document.getElementById("fig-prompts"), figureId: id,
      onDone: async () => { ownPrompts = await loadPrompts(); } });
  document.getElementById("fig-default-prompt").onchange = async (e) => {
    try {
      fig = await api(`/figures/${id}/default-prompt`, { method: "PUT", json: { prompt_id: Number(e.target.value) === generalDefaultId ? null : Number(e.target.value) } });
      toast("Saved");
    } catch (err) { fail(err); }
  };
  document.getElementById("fig-prompts").onclick = async (e) => {
    const edit = e.target.closest("[data-edit]"), del = e.target.closest("[data-remove]");
    try {
      if (edit) {
        const prompt = ownPrompts.find((p) => p.id === Number(edit.dataset.edit));
        editPrompt({ list: document.getElementById("fig-prompts"), prompt,
          onDone: async () => { ownPrompts = await loadPrompts(); } });
      }
      if (del && confirm("Delete this prompt? Conversations using it switch to the default.")) {
        await api(`/prompts/${del.dataset.remove}`, { method: "DELETE" });
        fig = await api(`/figures/${id}`);
        ownPrompts = await loadPrompts();
      }
    } catch (err) { fail(err); }
  };
}

function hitHtml(h, i) {
  const n = i + 1;
  const sim = h.similarity == null ? "" : ` · similarity ${h.similarity.toFixed(2)}`;
  const kw = h.bm25 ? ` · keywords ${h.bm25.toFixed(1)}` : "";
  return `<div class="source" data-n="${n}"><div class="meta">[${n}] ${esc(h.filename)}, part ${h.chunk + 1}${sim}${kw}</div>
    <div class="text" onclick="this.classList.toggle('open')">${esc(h.text)}</div></div>`;
}

// ---------------------------------------------------------------- chat

const prefs = {
  get(key, fallback) { try { const v = localStorage.getItem("histfig." + key); return v === null ? fallback : JSON.parse(v); } catch (_) { return fallback; } },
  set(key, value) { try { localStorage.setItem("histfig." + key, JSON.stringify(value)); } catch (_) {} },
};

async function pageChat(figureId, convId) {
  let fig, convs, conv;
  try {
    [fig, convs, conv] = await Promise.all([
      api(`/figures/${figureId}`), api(`/figures/${figureId}/conversations`),
      convId ? api(`/conversations/${convId}`).catch(() => null) : null,
    ]);
  } catch (err) { // figure deleted: forget it and go back to the list
    if (prefs.get("lastChat", null)?.figureId === figureId) prefs.set("lastChat", null);
    location.replace("#/");
    throw err;
  }
  if (convId && !conv) convId = undefined; // conversation deleted meanwhile
  if (!convId && convs.length) {
    const remembered = prefs.get("lastConv", {})[figureId];
    const target = convs.some((c) => c.id === remembered) ? remembered : convs[0].id;
    location.replace(`#/chat/${figureId}/${target}`);
    return;
  }
  rememberChat(figureId, convId);
  let models = { models: [], default: "" }; // filled in by getModels() below

  app.innerHTML = `
    <div class="chat" id="chat">
      <aside class="sidebar" id="sidebar">
        <div class="row">${avatar(fig, "sm")}<div style="min-width:0"><b>${esc(fig.name)}</b>
          <div class="muted small">${years(fig)}</div></div></div>
        <button class="primary block" id="new-conv">+ New conversation</button>
        <ul class="conv-list">${convs.map((c) => `
          <li class="${c.id === convId ? "active" : ""}" data-id="${c.id}">
            <a href="#/chat/${figureId}/${c.id}" class="conv-name">${esc(c.title || "Untitled")}</a>
            <button class="link icon" data-rename="${c.id}" title="Rename">✎</button>
            <button class="link icon" data-delete="${c.id}" title="Delete">✕</button></li>`).join("")}</ul>
        <p class="small admin-only" style="margin-top:16px"><a href="#/figure/${figureId}">Manage documents →</a></p>
      </aside>
      <section class="chat-main">
        <div class="chat-head">
          <button class="btn small only-mobile" id="toggle-sidebar" title="Conversations">☰</button>
          <div class="chat-title">
            ${conv ? `<div class="row nowrap"><h2 id="conv-title" title="Click to rename">${esc(conv.title || "Untitled")}</h2>
              <button class="link icon" id="rename-title" title="Rename">✎</button></div>`
              : `<h2>New conversation</h2>`}
          </div>
          <div class="head-actions">
            ${conv ? `<a class="btn small" href="/api/conversations/${conv.id}/export" title="Download as Markdown">Export</a>` : ""}
            <button class="btn small" id="toggle-sources">Sources</button>
            <button class="btn small" id="toggle-settings" title="Options for this conversation">⚙ Options</button>
          </div>
        </div>
        <div class="messages" id="messages"><div class="messages-inner" id="messages-inner"></div></div>
        <div class="composer"><form id="composer">
          <textarea id="input" rows="1" placeholder="Ask ${esc(fig.name)} something…"></textarea>
          <button class="primary" id="send">Send</button>
          <button type="button" id="stop" class="hidden">Stop</button>
        </form><div class="small muted" style="text-align:center;margin-top:6px">
          Answers are generated by a language model playing ${esc(fig.name)} — check the sources.</div></div>
      </section>
      <aside class="side hidden" id="side">
        <div class="row side-head"><h3 id="side-title">Sources</h3><span class="spacer"></span>
          <button class="link icon" id="close-side" title="Close">✕</button></div>
        <div id="side-sources" class="small muted">Sources for an answer appear here.</div>
        <div id="side-settings" class="hidden">
          <div class="setting hidden" id="model-setting">
            <div class="label-row"><label for="model">Model</label>${help(
              "The chat models chosen in Settings. The default is used unless you pick another one here.")}</div>
            <select id="model"><option value="${esc(conv?.model || "")}"></option></select>
          </div>
          <div class="setting">
            <div class="label-row"><label for="prompt">Prompt</label>${help(
              "The instructions that tell the model how to play the figure. Prompts are edited on the figure's page and in Settings.")}
              <span class="spacer"></span><a class="small admin-only" href="#/figure/${figureId}">Edit prompts</a></div>
            <select id="prompt"></select>
          </div>
          <div class="setting">
            <div class="label-row"><label for="temperature">Temperature</label>${help(
              "Lower = more focused and consistent answers, higher = more varied and creative ones.")}
              <span class="spacer"></span><b id="temperature-value"></b></div>
            <input type="range" id="temperature" min="0" max="2" step="0.1">
            <button type="button" class="link small hidden" id="temperature-reset"></button>
          </div>
          <div class="setting">
            <div class="label-row"><label for="documents">Documents</label>${help(
              "Simple search: the passages that best match each question are given to the model. " +
              "Agent search: the model looks things up itself first (several searches, exact words, " +
              "neighbouring passages) and picks what fits; slower, and a few more model calls per question. " +
              "Don't use: chat without looking anything up.")}</div>
            <select id="documents">
              <option value="simple">Simple search</option>
              <option value="agent">Agent search</option>
              <option value="off">Don't use</option>
            </select>
          </div>
          <div class="setting">
            <div class="label-row"><label for="top-k">Passages per question</label>${help(
              "How many passages from the documents are given to the model with each question.")}</div>
            <input type="number" id="top-k" min="1" max="30">
          </div>
          <div class="setting label-row">
            <label class="check"><input type="checkbox" id="immersive">Immersive</label>${help(
              "Just the conversation: hides sources, source numbers, research steps and thinking. Turn off to see them again.")}
          </div>
          <div class="setting label-row">
            <label class="check"><input type="checkbox" id="show-thinking">Show thinking</label>${help(
              "For reasoning models: show their thought process above the answer.")}
          </div>
        </div>
      </aside>
    </div>`;

  const $ = (sel) => document.getElementById(sel);
  const inner = $("messages-inner"), scroller = $("messages"), input = $("input");
  const documents = $("documents"), topK = $("top-k"), showThinking = $("show-thinking"), modelInput = $("model");
  documents.value = prefs.get("documents", prefs.get("useRag", true) ? "simple" : "off");
  topK.value = prefs.get("topK", 5);
  showThinking.checked = prefs.get("showThinking", false);
  const immersive = $("immersive");
  const setImmersive = (on) => {
    $("chat").classList.toggle("immersive", on);
    if (on && sideView === "sources") closeSide();
  };
  immersive.checked = prefs.get("immersive", false);
  immersive.onchange = () => { prefs.set("immersive", immersive.checked); setImmersive(immersive.checked); };
  documents.onchange = () => prefs.set("documents", documents.value);

  // Temperature: null = the configured default (known once the model info arrives)
  const temp = $("temperature");
  let defaultTemp = 0.7;
  const showTemp = () => {
    const custom = prefs.get("temperature", null);
    temp.value = custom ?? defaultTemp;
    $("temperature-value").textContent = Number(temp.value).toFixed(1) + (custom === null ? " (default)" : "");
    const reset = $("temperature-reset");
    reset.textContent = `Reset to default (${defaultTemp})`;
    reset.classList.toggle("hidden", custom === null);
  };
  temp.oninput = () => {
    const v = Math.round(Number(temp.value) * 10) / 10;
    prefs.set("temperature", v === defaultTemp ? null : v);
    showTemp();
  };
  $("temperature-reset").onclick = () => { prefs.set("temperature", null); showTemp(); };
  showTemp();
  topK.onchange = () => prefs.set("topK", Number(topK.value) || 5);
  showThinking.onchange = () => {
    prefs.set("showThinking", showThinking.checked);
    document.querySelectorAll(".thinking").forEach((d) => d.classList.toggle("hidden", !showThinking.checked || !d.textContent.trim()));
  };
  // Prompt for this conversation (choosing the figure's default = follow the default)
  const promptSelect = $("prompt");
  let promptDefaultId = null;
  const promptChoice = () => (Number(promptSelect.value) === promptDefaultId ? 0 : Number(promptSelect.value) || 0);
  api(`/prompts?figure_id=${figureId}`).then((all) => {
    if (!document.body.contains(promptSelect)) return;
    const general = all.filter((p) => p.figure_id === null);
    const fallback = all.find((p) => p.id === fig.default_prompt_id) || general.find((p) => p.is_default);
    promptDefaultId = fallback?.id ?? null;
    const selected = conv?.prompt_id ?? promptDefaultId;
    promptSelect.innerHTML = all.map((p) =>
      `<option value="${p.id}" ${p.id === selected ? "selected" : ""}>${esc(p.name)}</option>`).join("");
  }).catch(fail);
  promptSelect.onchange = async () => {
    if (!conv) return; // used when the conversation is created
    try {
      await api(`/conversations/${conv.id}`, { method: "PATCH", json: { prompt_id: promptChoice() } });
      toast("Prompt changed for this conversation");
    } catch (err) { fail(err); }
  };

  getModels().then((m) => {
    if (!document.body.contains(modelInput)) return; // left the page meanwhile
    models = m;
    if (typeof m.temperature === "number") { defaultTemp = m.temperature; showTemp(); }
    const choices = (m.allowed || []).filter((name) => name !== m.default);
    const current = choices.includes(conv?.model) ? conv.model : "";
    modelInput.innerHTML = `<option value="">${esc(m.default)} (default)</option>` +
      choices.map((name) => `<option value="${esc(name)}" ${name === current ? "selected" : ""}>${esc(name)}</option>`).join("");
    $("model-setting").classList.toggle("hidden", !choices.length); // nothing to choose → no dropdown
  });

  // Right-hand panel: Sources or Settings
  const side = $("side"), chatEl = $("chat");
  let sideView = null, lastSources = [];
  const openSide = (view) => {
    sideView = view;
    $("side-title").textContent = view === "sources" ? "Sources" : "Conversation options";
    $("side-sources").classList.toggle("hidden", view !== "sources");
    $("side-settings").classList.toggle("hidden", view !== "settings");
    side.classList.remove("hidden");
    chatEl.classList.add("with-side");
    $("toggle-sources").classList.toggle("active", view === "sources");
    $("toggle-settings").classList.toggle("active", view === "settings");
    prefs.set("sidePanel", view);
  };
  const closeSide = () => {
    sideView = null;
    side.classList.add("hidden");
    chatEl.classList.remove("with-side");
    $("toggle-sources").classList.remove("active");
    $("toggle-settings").classList.remove("active");
    prefs.set("sidePanel", null);
  };
  const showSources = (hits, focus = null) => {
    $("side-sources").innerHTML = hits?.length ? hits.map(hitHtml).join("")
      : `<p class="muted">No passages were used for this answer.</p>`;
    openSide("sources");
    const el = focus && $("side-sources").querySelector(`.source[data-n="${focus}"]`);
    if (el) { // a clicked citation: show that passage in full
      el.classList.add("focus");
      el.querySelector(".text").classList.add("open");
      el.scrollIntoView({ block: "start" });
    }
  };
  $("close-side").onclick = closeSide;
  $("toggle-sources").onclick = () => (sideView === "sources" ? closeSide() : showSources(lastSources));
  $("toggle-settings").onclick = () => (sideView === "settings" ? closeSide() : openSide("settings"));
  $("toggle-sidebar").onclick = () => $("sidebar").classList.toggle("open");

  const scrollDown = () => { scroller.scrollTop = scroller.scrollHeight; };

  const addUser = (text) => {
    inner.insertAdjacentHTML("beforeend", `<div class="msg user"><div class="bubble">${esc(text)}</div></div>`);
  };
  const addAssistant = (text = "", sources = [], steps = []) => {
    const wrap = document.createElement("div");
    wrap.className = "msg assistant";
    wrap.innerHTML = `${avatar(fig, "sm")}<div class="bubble">
      <details class="research hidden"><summary></summary><ol></ol></details>
      <details class="thinking hidden"><summary>Thinking</summary><div></div></details>
      <div class="answer"></div><div class="tools"></div></div>`;
    inner.appendChild(wrap);
    const view = {
      raw: text, thinking: "", sources, steps: [...steps],
      render(streaming = false) {
        const res = wrap.querySelector(".research"), researching = streaming && !this.raw;
        res.classList.toggle("hidden", !this.steps.length);
        if (researching !== this.researching) res.open = this.researching = researching; // folds once the answer starts
        res.querySelector("summary").textContent = researching ? "Researching…"
          : `Research · ${this.steps.length} step${this.steps.length === 1 ? "" : "s"}`;
        res.querySelector("ol").innerHTML = this.steps.map((t) => `<li>${esc(t)}</li>`).join("");
        const { thinking, answer } = splitThinking(this.raw);
        const t = (this.thinking + "\n" + thinking).trim();
        const det = wrap.querySelector(".thinking");
        det.classList.toggle("hidden", !t || !showThinking.checked);
        det.querySelector("div").textContent = t;
        const ans = wrap.querySelector(".answer");
        ans.innerHTML = linkCitations(renderText(answer), this.sources) || (streaming ? "<p></p>" : "");
        ans.classList.toggle("cursor", streaming);
      },
      setSources(hits) {
        this.sources = hits;
        wrap.querySelector(".tools").innerHTML = hits.length
          ? `<button class="link small">${hits.length} source${hits.length === 1 ? "" : "s"}</button>` : "";
        const b = wrap.querySelector(".tools button");
        if (b) b.onclick = () => showSources(this.sources);
      },
      showSource(n) { lastSources = this.sources; showSources(this.sources, n); },
      error(msg) { wrap.querySelector(".answer").insertAdjacentHTML("beforeend", `<p class="error">${esc(msg)}</p>`); },
    };
    wrap.querySelector(".answer").addEventListener("click", (e) => {
      const a = e.target.closest("[data-cite]");
      if (a) { e.preventDefault(); view.showSource(Number(a.dataset.cite)); }
    });
    view.render();
    view.setSources(sources);
    return view;
  };

  if (conv && conv.messages.length) {
    for (const m of conv.messages) {
      if (m.role === "user") addUser(m.content);
      else { addAssistant(m.content, m.sources, m.steps); lastSources = m.sources; }
    }
  } else {
    inner.innerHTML = `<div class="empty-chat">${avatar(fig, "lg")}<h2>${esc(fig.name)}</h2>
      <p>${esc(fig.description) || "Start the conversation below."}</p>
      ${fig.chunks ? "" : `<p class="small admin-only">No documents yet — answers won't be grounded in sources.
        <a href="#/figure/${figureId}">Upload some</a>.</p>`}</div>`;
  }
  setImmersive(immersive.checked);
  if (prefs.get("sidePanel", null) === "settings") openSide("settings");
  else if (prefs.get("sidePanel", null) === "sources") showSources(lastSources);
  scrollDown();

  // Renaming in place (sidebar entry or the title above the chat)
  const setTitle = (id, title) => {
    const text = title || "Untitled";
    const link = document.querySelector(`.conv-list li[data-id="${id}"] .conv-name`);
    if (link) link.textContent = text;
    if (id === convId && $("conv-title")) $("conv-title").textContent = text;
  };
  const editInPlace = (el, id) => {
    if (el.querySelector("input")) return;
    const old = el.textContent === "Untitled" ? "" : el.textContent;
    const box = document.createElement("input");
    box.className = "inline-edit";
    box.value = old;
    box.maxLength = 200;
    el.replaceChildren(box);
    el.classList.add("editing");
    box.focus(); box.select();
    let done = false;
    const finish = async (save) => {
      if (done) return;
      done = true;
      el.classList.remove("editing");
      const title = box.value.trim();
      setTitle(id, old);
      if (!save || title === old) return;
      try {
        await api(`/conversations/${id}`, { method: "PATCH", json: { title } });
        setTitle(id, title);
      } catch (err) { fail(err); }
    };
    box.onkeydown = (e) => {
      if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); finish(true); }
      if (e.key === "Escape") { e.preventDefault(); finish(false); }
    };
    box.onblur = () => finish(true);
    box.onclick = (e) => { e.preventDefault(); e.stopPropagation(); };
  };
  if (conv) {
    $("conv-title").onclick = () => editInPlace($("conv-title"), conv.id);
    $("rename-title").onclick = () => editInPlace($("conv-title"), conv.id);
  }

  // Sidebar actions
  $("new-conv").onclick = async () => {
    try {
      const c = await api(`/figures/${figureId}/conversations`, { method: "POST", json: {} });
      location.hash = `#/chat/${figureId}/${c.id}`;
    } catch (err) { fail(err); }
  };
  document.querySelector(".conv-list").onclick = async (e) => {
    const ren = e.target.closest("[data-rename]"), del = e.target.closest("[data-delete]");
    if (ren) {
      const id = Number(ren.dataset.rename);
      editInPlace(document.querySelector(`.conv-list li[data-id="${id}"] .conv-name`), id);
      return;
    }
    if (del && confirm("Delete this conversation?")) {
      try {
        await api(`/conversations/${del.dataset.delete}`, { method: "DELETE" });
        if (Number(del.dataset.delete) === convId) location.hash = `#/chat/${figureId}`;
        else route();
      } catch (err) { fail(err); }
    }
  };
  document.querySelector(".conv-list").addEventListener("click", (e) => {
    if (e.target.closest(".editing")) e.preventDefault(); // don't follow the link while typing a name
  }, true);

  // Model for this conversation (from the list made available in Settings)
  modelInput.onchange = async () => {
    const value = modelInput.value;
    if (!conv) return; // used when the conversation is created
    try {
      await api(`/conversations/${conv.id}`, { method: "PATCH", json: { model: value } });
      toast(value ? `Using ${value} for this conversation` : "Using the configured model");
    } catch (err) { fail(err); }
  };

  // Composer
  input.oninput = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 220) + "px"; };
  input.onkeydown = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("composer").requestSubmit(); }
  };
  let controller = null;
  cleanup.push(() => controller?.abort());
  $("stop").onclick = () => controller?.abort();

  $("composer").onsubmit = async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || controller) return;
    let target = conv;
    if (!target) {
      try {
        target = await api(`/figures/${figureId}/conversations`, { method: "POST", json: { model: modelInput.value.trim(), prompt_id: promptChoice() } });
      } catch (err) { return fail(err); }
    }
    if (!conv) inner.innerHTML = "";
    input.value = ""; input.oninput();
    addUser(text);
    const view = addAssistant();
    view.render(true);
    scrollDown();
    $("send").classList.add("hidden"); $("stop").classList.remove("hidden");
    controller = new AbortController();
    try {
      await streamChat(target.id, {
        content: text, documents: documents.value, top_k: Number(topK.value) || undefined,
        temperature: prefs.get("temperature", null) ?? undefined,
      }, controller.signal, (ev) => {
        const nearBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 80;
        if (ev.type === "sources") {
          view.setSources(ev.sources); lastSources = ev.sources;
          if (sideView === "sources") showSources(lastSources);
        }
        else if (ev.type === "step") { view.steps.push(ev.text); view.render(true); }
        else if (ev.type === "content") { view.raw += ev.text; view.render(true); }
        else if (ev.type === "thinking") { view.thinking += ev.text; view.render(true); }
        else if (ev.type === "warning") toast(ev.message, true);
        else if (ev.type === "error") view.error(ev.message);
        if (nearBottom) scrollDown();
      });
    } catch (err) {
      if (err.name !== "AbortError") view.error(err.message);
    } finally {
      controller = null;
      view.render(false);
      $("send").classList.remove("hidden"); $("stop").classList.add("hidden");
      if (!conv) location.replace(`#/chat/${figureId}/${target.id}`); // reload sidebar with the new conversation
      input.focus();
    }
  };
  input.focus();
}

/* Remember where the user was chatting, for the "Chat" tab and for reopening a figure. */
function rememberChat(figureId, convId) {
  prefs.set("lastChat", { figureId, convId: convId || null });
  if (convId) prefs.set("lastConv", { ...prefs.get("lastConv", {}), [figureId]: convId });
  updateChatNav();
}

function updateChatNav() {
  const last = prefs.get("lastChat", null);
  const link = document.querySelector('[data-nav="chat"]');
  if (link) link.hidden = !last;
}

async function pageLastChat() {
  const last = prefs.get("lastChat", null);
  location.replace(last ? `#/chat/${last.figureId}${last.convId ? "/" + last.convId : ""}` : "#/");
}

async function streamChat(convId, body, signal, onEvent) {
  const res = await fetch(`/api/conversations/${convId}/messages`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of block.split("\n")) {
        if (line.startsWith("data:")) {
          try { onEvent(JSON.parse(line.slice(5))); } catch (_) {}
        }
      }
    }
  }
}

// ---------------------------------------------------------------- settings

async function pageSettings(notes = []) {
  const s = await api("/settings");
  const c = s.config;
  const SERVICES = {
    chat: [["openrouter", "OpenRouter"], ["ollama", "Ollama (runs on this computer)"], ["other", "Other OpenAI-compatible API"]],
    embedding: [["openrouter", "OpenRouter"], ["ollama", "Ollama (runs on this computer)"], ["other", "Other OpenAI-compatible API"],
      ["local", "sentence-transformers (inside HistFig)"]],
  };
  const MODEL_HINT = { // only where "Browse models…" needs a word of explanation
    ollama: { chat: "Browse shows the models installed in Ollama; “ollama pull <name>” adds more.",
      embedding: "Browse shows the models installed in Ollama; “ollama pull <name>” adds more." },
    local: { embedding: "Type a Hugging Face model name, e.g. owner/model-name. Needs “uv sync --extra local”." },
  };
  const serviceOf = (sec) => sec.provider === "ollama" ? "ollama" : sec.provider === "sentence_transformers" ? "local"
    : sec.base_url.replace(/\/+$/, "") === s.urls.openrouter ? "openrouter" : "other";
  const frow = (name, label, field, helpText = "") =>
    `<div class="frow" data-row="${name}"><label>${label}${helpText ? help(helpText) : ""}</label><div>${field}</div></div>`;
  const keyPlaceholder = (sec) => sec.api_key ? `Saved (${sec.api_key}) — type to replace`
    : sec.api_key_env ? `Read from $${sec.api_key_env}` : "Paste your API key";

  const modelForm = (which, title, sec, extra = "", advanced = "") => `
    <form class="card settings-card" data-section="${which}" autocomplete="off">
      <div class="row card-head"><h2>${title}</h2><span class="spacer"></span>
        <span class="status-pill" id="status-${which}">Not tested</span>
        <button type="button" class="btn small" data-test="${which}">Test</button></div>
      <div class="form-grid">
        ${frow("service", "Service", `<select name="service">${SERVICES[which].map(([v, l]) =>
          `<option value="${v}" ${serviceOf(sec) === v ? "selected" : ""}>${l}</option>`).join("")}</select>`)}
        ${frow("base_url", "Address", `<input name="base_url" value="${esc(serviceOf(sec) === "other" ? sec.base_url : "")}"
          placeholder="https://…/v1" spellcheck="false">`, "The API's base address, usually ending in /v1.")}
        ${which === "embedding" ? frow("same_key", "", `<label class="check plain"><input type="checkbox" name="same_key"
          ${s.same_key ? "checked" : ""}> Use the same API key as the chat model</label>`) : ""}
        ${frow("api_key", "API key", `<input name="api_key" type="password" placeholder="${esc(keyPlaceholder(sec))}"
          spellcheck="false">`, "Stored only on this computer, in the config file.")}
        ${which === "embedding" ? frow("model", "Model", `<input name="model" value="${esc(sec.model)}" placeholder="Model name" spellcheck="false" required>
          <div class="hint" data-hint></div>
          <button type="button" class="btn small" data-browse>Browse models…</button>
          <div class="model-browser hidden">
            <input type="search" class="model-filter" placeholder="Type to filter…" spellcheck="false">
            <ul class="model-list"></ul>
          </div>`) : ""}
        ${extra}
      </div>
      <details class="advanced"><summary>Advanced</summary><div class="form-grid">
        ${frow("api_key_env", "Key from environment variable", `<input name="api_key_env" value="${esc(sec.api_key_env)}"
          placeholder="e.g. OPENROUTER_API_KEY" spellcheck="false">`,
          "Instead of storing the key, read it from this environment variable (handy for Codespaces secrets). Used when no key is saved.")}
        ${advanced}
      </div></details>
      <div class="form-actions"><div class="test-detail small" id="detail-${which}"></div><span class="spacer"></span>
        <button class="btn small primary" disabled>Save</button></div>
    </form>`;

  const usage = usageText(s.embedding_usage.tokens, s.embedding_usage.cost);
  const r = c.retrieval, ch = c.chunking;
  app.innerHTML = `
    <div class="page" style="max-width:820px">
      <div class="row" style="margin-bottom:16px"><h1 style="margin:0">Settings</h1><span class="spacer"></span>
        <button class="primary" id="test-all">Test connections</button></div>
      ${s.problems.length ? `<div class="banner"><b>Welcome to HistFig!</b> Choose a chat model and an embedding
        model below and click Save. OpenRouter needs one API key for both; Ollama runs free models on your own computer.</div>` : ""}
      ${notes.map((n) => `<div class="banner">${esc(n)}</div>`).join("")}
      ${modelForm("chat", "Chat model", c.chat,
        frow("models", "Models", `<div class="tags" id="chat-models"></div>
          <button type="button" class="btn small" data-browse>Browse models…</button>
          <div class="model-browser hidden">
            <input type="search" class="model-filter" placeholder="Type to filter…" spellcheck="false">
            <ul class="model-list"></ul>
          </div>
          <div class="hint" data-hint></div>`, "The chat models you use. The default answers unless a conversation picks another one under ⚙ Options (visitors of a public server can pick too).") +
        frow("temperature", "Temperature", `<input name="temperature" type="number" min="0" max="2" step="0.1" value="${c.chat.temperature}">`,
          "Default for new messages. Lower = more focused, higher = more creative. Can be changed per conversation."))}
      ${modelForm("embedding", "Embedding model", c.embedding,
        frow("usage", "Used so far", `<span class="${usage ? "" : "muted"}">${usage || "nothing recorded yet"}</span>`,
          "Embedding usage for all figures, as reported by the provider."),
        frow("batch_size", "Batch size", `<input name="batch_size" type="number" min="1" max="512" value="${c.embedding.batch_size}">`,
          "Passages sent per request. Lower it if the provider complains about request size.") +
        frow("query_prefix", "Query prefix", `<textarea name="query_prefix" rows="2" spellcheck="false">${esc(c.embedding.query_prefix)}</textarea>`,
          "Text some models expect before each question. Filled in automatically for known models.") +
        frow("document_prefix", "Document prefix", `<textarea name="document_prefix" rows="2" spellcheck="false">${esc(c.embedding.document_prefix)}</textarea>`,
          "Text some models expect before each passage. Changing it requires rebuilding figures."))}
      <div class="card settings-card">
        <div class="row card-head"><h2>Prompts</h2>${help(
          "General prompts work for every figure. The default one is used unless a figure or a conversation picks another. Figures can also have their own prompts (on the figure's page).")}
          <span class="spacer"></span><button type="button" class="btn small" id="new-general-prompt">+ New prompt</button></div>
        <ul class="prompt-list" id="general-prompts"></ul>
      </div>
      <form class="card settings-card" data-section="passages" autocomplete="off">
        <h2>Passages &amp; retrieval</h2>
        <div class="form-grid">
          ${frow("chunk_size", "Passage size", `<input name="chunk_size" type="number" min="100" step="50" value="${ch.chunk_size}"> <span class="unit">characters</span>`,
            "Counted in Chinese characters; about three English letters count as one, so 1000 is ~1000 Chinese characters or ~500 English words. Applies to new uploads; “Rebuild index” applies it to existing ones.")}
          ${frow("overlap", "Overlap", `<input name="overlap" type="number" min="0" step="10" value="${ch.overlap}"> <span class="unit">characters</span>`,
            "How much consecutive passages share, so sentences at the edges aren't lost. Counted like the passage size, and less than half of it.")}
          ${frow("top_k", "Passages per question", `<input name="top_k" type="number" min="1" max="30" value="${r.top_k}">`,
            "Default number of passages given to the model. Can be changed per conversation.")}
          ${frow("candidates", "Candidates searched", `<input name="candidates" type="number" min="1" max="200" value="${r.candidates}">`,
            "How many passages each search method (meaning and keywords) proposes before they are combined.")}
          ${frow("min_similarity", "Minimum similarity", `<input name="min_similarity" type="number" min="0" max="1" step="0.05" value="${r.min_similarity}">`,
            "Passages less similar than this (0–1) are left out, unless they also match keywords.")}
          ${frow("history_messages", "Chat history sent", `<input name="history_messages" type="number" min="0" max="200" value="${r.history_messages}"> <span class="unit">messages</span>`,
            "How many earlier messages the model sees, so it remembers the conversation.")}
        </div>
        <div class="form-actions"><span class="spacer"></span><button class="btn small primary" disabled>Save</button></div>
      </form>
      <div class="card settings-card">
        <h2>Files</h2>
        <dl class="kv">
          <dt>Config file</dt><dd><code>${esc(s.config_path)}</code><br><span class="muted">Settings are saved here.
            You can also edit it by hand (then restart HistFig) or run <code>histfig setup</code> in a terminal.</span></dd>
          <dt>Data folder</dt><dd><code>${esc(s.data_dir)}</code><br><span class="muted">database, uploads and portraits — copy it to back up</span></dd>
        </dl>
      </div>
    </div>`;

  // ----- "Browse models…": a searchable list of the provider's models (used by both model cards)
  //   load()   → the model names        state(m) → "default", "added ✓", … or null if pickable
  //   pick(m)  → called on Add/Use       keepOpen → stay open after picking (to add several)
  function modelBrowser(root, form, initialService, { load, state, pick, keepOpen, pickLabel }) {
    const button = root.querySelector("[data-browse]"), browser = root.querySelector(".model-browser");
    const list = root.querySelector(".model-list"), filter = root.querySelector(".model-filter");
    let available = null, error = "";
    const render = () => {
      if (form.service.value !== initialService) {
        list.innerHTML = `<li class="muted small">Save the new service first, then browse its models.</li>`;
        return;
      }
      const typed = filter.value.trim(), q = typed.toLowerCase();
      const hits = (available || []).filter((m) => m.toLowerCase().includes(q));
      const row = (m) => `<li><span>${esc(m)}</span>${state(m) ? `<span class="muted small">${state(m)}</span>`
        : `<button type="button" class="btn small" data-pick="${esc(m)}">${pickLabel}</button>`}</li>`;
      list.innerHTML = available === null ? `<li class="muted small">Loading…</li>`
        : !available.length // no list from this provider: use the typed name as it is
          ? `<li class="muted small">The provider did not return a model list${error ? ` (${esc(error)})` : ""}. Type the exact name above.</li>` +
            (typed && !state(typed) ? row(typed) : "")
        : hits.slice(0, 200).map(row).join("") +
          (hits.length > 200 ? `<li class="muted small">${hits.length - 200} more — type to narrow down.</li>` : "") +
          (hits.length ? "" : `<li class="muted small">No model matches “${esc(typed)}”.</li>`);
    };
    button.onclick = async () => {
      browser.classList.toggle("hidden");
      if (browser.classList.contains("hidden")) return;
      filter.focus();
      if (available === null) {
        render();
        try { available = await load(); } catch (err) { available = []; error = err.message; }
      }
      render();
    };
    filter.oninput = (e) => { e.stopPropagation(); render(); };
    filter.onkeydown = (e) => {
      if (e.key === "Enter") e.preventDefault(); // don't submit the form
      if (e.key === "Escape") browser.classList.add("hidden");
    };
    list.onclick = (e) => {
      const b = e.target.closest("[data-pick]");
      if (!b) return;
      pick(b.dataset.pick);
      form.querySelector("button.primary").disabled = false;
      if (keepOpen) render(); else browser.classList.add("hidden");
    };
    // A click anywhere outside the list (or its button) closes it
    const closeOutside = (e) => {
      if (!browser.classList.contains("hidden") && document.body.contains(e.target) &&
          !browser.contains(e.target) && !button.contains(e.target)) browser.classList.add("hidden");
    };
    document.addEventListener("click", closeOutside);
    cleanup.push(() => document.removeEventListener("click", closeOutside));
    return { render, reset: () => { available = null; error = ""; render(); } };
  }

  // ----- chat "Models": one list, one of them the default (saved as chat.model + chat.allowed_models)
  let chatModels = [...new Set([c.chat.model, ...c.chat.allowed_models].filter(Boolean))];
  let defaultModel = c.chat.model || chatModels[0] || "";
  let resetChatModels = () => {};
  function wireChatModels(form, initialService) {
    const tags = document.getElementById("chat-models");
    const renderTags = () => {
      tags.innerHTML = chatModels.length ? chatModels.map((m) => `<span class="tag">${esc(m)}
          ${m === defaultModel ? `<span class="badge ready">default</span>`
            : `<button type="button" class="link small" data-make-default="${esc(m)}">make default</button>`}
          <button type="button" class="link icon" data-drop="${esc(m)}" title="Remove">✕</button></span>`).join("")
        : `<span class="muted small">No models yet — click “Browse models…” and add one.</span>`;
    };
    const browse = modelBrowser(form.querySelector('[data-row="models"]'), form, initialService, {
      load: async () => {
        const m = await getModels();
        if (!m.models.length && m.error) throw new Error(m.error);
        return m.models;
      },
      state: (m) => (chatModels.includes(m) ? (m === defaultModel ? "default" : "added ✓") : null),
      pick: (m) => { chatModels.push(m); if (!defaultModel) defaultModel = m; renderTags(); },
      keepOpen: true, pickLabel: "Add",
    });
    tags.onclick = (e) => {
      const drop = e.target.closest("[data-drop]"), def = e.target.closest("[data-make-default]");
      if (drop) {
        chatModels = chatModels.filter((m) => m !== drop.dataset.drop);
        if (defaultModel === drop.dataset.drop) defaultModel = chatModels[0] || "";
      }
      if (def) defaultModel = def.dataset.makeDefault;
      if (drop || def) { renderTags(); browse.render(); form.querySelector("button.primary").disabled = false; }
    };
    resetChatModels = () => { chatModels = []; defaultModel = ""; renderTags(); browse.reset(); };
    renderTags();
  }

  // ----- embedding "Model": one model; "Browse models…" fills in the field
  let resetEmbeddingBrowser = () => {};
  function wireEmbeddingModel(form, initialService) {
    const browse = modelBrowser(form.querySelector('[data-row="model"]'), form, initialService, {
      load: async () => {
        const r = await api("/settings/embedding-models");
        if (!r.models.length && r.error) throw new Error(r.error);
        return r.models;
      },
      state: (m) => (m === form.model.value.trim() ? "selected" : null),
      pick: (m) => { form.model.value = m; },
      keepOpen: false, pickLabel: "Use",
    });
    resetEmbeddingBrowser = browse.reset;
  }

  // ----- model forms: show the right fields for the chosen service; Save when something changed
  for (const which of ["chat", "embedding"]) {
    const form = app.querySelector(`form[data-section="${which}"]`);
    const initialService = form.service.value;
    const row = (name) => form.querySelector(`[data-row="${name}"]`);
    const sync = () => {
      const sv = form.service.value;
      const needsKey = sv === "openrouter" || sv === "other";
      const chatForm = app.querySelector('form[data-section="chat"]');
      const sameAvailable = which === "embedding" && needsKey && sv === chatForm.service.value &&
        (sv !== "other" || form.base_url.value.trim() === chatForm.base_url.value.trim());
      row("base_url").classList.toggle("hidden", sv !== "other");
      row("same_key")?.classList.toggle("hidden", !sameAvailable);
      const shared = sameAvailable && form.same_key?.checked;
      row("api_key").classList.toggle("hidden", !needsKey || shared);
      row("api_key_env").classList.toggle("hidden", !needsKey || shared);
      form.querySelector("[data-hint]").textContent = MODEL_HINT[sv]?.[which] || "";
    };
    form.service.onchange = () => {
      if (form.service.value !== initialService) {
        if (form.model) form.model.value = "";
        form.base_url.value = "";
        if (which === "chat") resetChatModels(); else resetEmbeddingBrowser(); // models belong to a service
      }
      sync();
    };
    if (which === "chat") wireChatModels(form, initialService); else wireEmbeddingModel(form, initialService);
    form.oninput = form.onchange = (e) => {
      if (e.target.name === "same_key" || e.target.name === "base_url") sync();
      form.querySelector("button.primary").disabled = false;
    };
    sync();
    form.onsubmit = async (e) => {
      e.preventDefault();
      const sv = form.service.value;
      const section = {
        provider: sv === "ollama" ? "ollama" : sv === "local" ? "sentence_transformers" : "openai_compatible",
        base_url: sv === "openrouter" ? s.urls.openrouter : sv === "ollama" ? s.urls.ollama : sv === "local" ? "" : form.base_url.value.trim(),
        model: which === "chat" ? defaultModel : form.model.value.trim(),
      };
      if (!section.model) return fail(new Error(which === "chat" ? "Add at least one chat model." : "Enter an embedding model."));
      const shared = which === "embedding" && !row("same_key").classList.contains("hidden") && form.same_key.checked;
      if (!shared) {
        const key = form.api_key.value.trim(), env = form.api_key_env.value.trim();
        if (key) { section.api_key = key; section.api_key_env = ""; }
        else section.api_key_env = env;
        if (sv !== initialService && !key) section.api_key = ""; // a different service never inherits the old key
      }
      if (which === "chat") {
        section.temperature = Number(form.temperature.value);
        section.allowed_models = chatModels.filter((m) => m !== defaultModel);
      }
      else {
        section.batch_size = Number(form.batch_size.value);
        section.query_prefix = form.query_prefix.value;
        section.document_prefix = form.document_prefix.value;
      }
      await save({ [which]: section, same_key_as_chat: shared }, form);
    };
  }

  // ----- passages & retrieval
  const pform = app.querySelector('form[data-section="passages"]');
  pform.oninput = () => (pform.querySelector("button.primary").disabled = false);
  pform.onsubmit = async (e) => {
    e.preventDefault();
    const n = (name) => Number(pform[name].value);
    await save({
      chunking: { chunk_size: n("chunk_size"), overlap: n("overlap") },
      retrieval: { top_k: n("top_k"), candidates: n("candidates"), min_similarity: n("min_similarity"), history_messages: n("history_messages") },
    }, pform);
  };

  async function save(body, form) {
    const button = form.querySelector("button.primary");
    button.disabled = true; button.textContent = "Saving…";
    try {
      const res = await api("/settings", { method: "PUT", json: body });
      modelsPromise = null; // the model list / defaults may have changed
      toast("Saved");
      await pageSettings(res.warnings || []);
    } catch (err) {
      fail(err);
      button.disabled = false; button.textContent = "Save";
    }
  }

  // ----- prompts
  let general = [];
  const loadGeneral = async () => {
    general = (await api("/prompts")).filter((p) => p.figure_id === null);
    document.getElementById("general-prompts").innerHTML =
      general.map((p) => promptRow(p, { isDefault: !!p.is_default, canDefault: true })).join("");
  };
  await loadGeneral();
  const generalList = document.getElementById("general-prompts");
  document.getElementById("new-general-prompt").onclick = () => editPrompt({ list: generalList, onDone: loadGeneral });
  generalList.onclick = async (e) => {
    const edit = e.target.closest("[data-edit]"), def = e.target.closest("[data-default]"), del = e.target.closest("[data-remove]");
    try {
      if (edit) editPrompt({ list: generalList, prompt: general.find((p) => p.id === Number(edit.dataset.edit)), onDone: loadGeneral });
      if (def) { await api(`/prompts/${def.dataset.default}/make-default`, { method: "POST" }); await loadGeneral(); }
      if (del && confirm("Delete this prompt? Conversations and figures using it switch to the default.")) {
        await api(`/prompts/${del.dataset.remove}`, { method: "DELETE" });
        await loadGeneral();
      }
    } catch (err) { fail(err); }
  };

  // ----- connection tests (of the saved settings)
  const runTest = async (which) => {
    const pill = document.getElementById(`status-${which}`), detail = document.getElementById(`detail-${which}`);
    pill.className = "status-pill testing"; pill.textContent = "Testing…"; detail.textContent = "";
    try {
      const r = await api(`/settings/test/${which}`, { method: "POST" });
      pill.className = `status-pill ${r.ok ? "ok" : "bad"}`;
      pill.textContent = r.ok ? "✓ Working" : "✗ Failed";
      detail.className = `test-detail small ${r.ok ? "status-ok" : "status-bad"}`;
      detail.textContent = r.detail;
    } catch (err) {
      pill.className = "status-pill bad"; pill.textContent = "✗ Failed"; detail.textContent = err.message;
    }
  };
  const buttons = () => document.querySelectorAll("#test-all, [data-test]");
  const locked = async (fn) => {
    const unsaved = [...app.querySelectorAll("form[data-section] button.primary")].some((b) => !b.disabled);
    if (unsaved) toast("Tests use the saved settings — click Save first to test your changes.");
    buttons().forEach((b) => (b.disabled = true));
    try { await fn(); } finally { buttons().forEach((b) => (b.disabled = false)); }
  };
  document.querySelectorAll("[data-test]").forEach((b) => (b.onclick = () => locked(() => runTest(b.dataset.test))));
  document.getElementById("test-all").onclick = () => locked(async () => {
    for (const which of ["chat", "embedding"]) {
      document.getElementById(`status-${which}`).className = "status-pill";
      document.getElementById(`status-${which}`).textContent = "Waiting…";
    }
    await runTest("chat");
    await runTest("embedding");
  });
}
