const API = window.localStorage.getItem("ragAgentApi") || "http://localhost:8000";

const state = {
  activeFileId: null,
  viewTitles: {
    chat: "Ask ForgeLens",
    upload: "Ingest files",
    corrections: "Review corrections",
    records: "Inspect records",
    audit: "Trace activity",
  },
};

const el = (id) => document.getElementById(id);

function setText(id, value) {
  el(id).textContent = value;
}

function renderIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

function showToast(message) {
  const toast = el("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2200);
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
  let data = {};
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  if (!res.ok) {
    throw new Error(data.detail || `Request failed with ${res.status}`);
  }
  return data;
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.tab === name);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("active", view.id === `tab-${name}`);
  });
  setText("view-title", state.viewTitles[name] || "ForgeLens");
  if (name === "audit") loadAudit();
  if (name === "records") loadRecords();
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
});

function formatRuntime(runtime) {
  if (runtime === "foundry_local") return "Foundry Local";
  if (runtime === "fallback") return "Local fallback";
  if (runtime === "not_loaded") return "Standby";
  return runtime || "unknown";
}

async function refreshHealth() {
  try {
    const data = await request("/health");
    setText("documents-count", data.documents_indexed ?? 0);
    setText("chunks-count", data.chunks_indexed ?? 0);
    setText("records-count", data.records_loaded ?? 0);
    setText("pending-count", data.corrections?.pending ?? 0);

    const runtime = data.runtime?.runtime || "unknown";
    setText("runtime-pill", formatRuntime(runtime));

    const dot = el("status-dot");
    dot.className = `status-dot ${runtime === "foundry_local" ? "good" : ""}`;
    state.activeFileId = data.active_records_file || state.activeFileId;
  } catch {
    setText("runtime-pill", "offline");
    el("status-dot").className = "status-dot offline";
  }
}

async function loadDocuments() {
  const container = el("document-list");
  try {
    const data = await request("/api/documents");
    container.replaceChildren();
    if (!data.documents.length) {
      container.textContent = "No documents indexed yet.";
      container.className = "list empty";
      return;
    }
    container.className = "list";
    data.documents.forEach((doc) => {
      container.appendChild(node("div", "list-item", doc));
    });
  } catch (err) {
    container.textContent = err.message;
    container.className = "list empty";
  }
}

function setBusy(button, busy, label) {
  if (!button) return;
  button.disabled = busy;
  if (label) {
    const span = button.querySelector("span");
    if (span) span.textContent = label;
  }
}

async function uploadFile(input, path, resultId, providedFile = null) {
  const file = providedFile || input.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append("file", file);
  setText(resultId, "Uploading...");

  try {
    const data = await request(path, { method: "POST", body: formData });
    if (path.includes("records")) {
      state.activeFileId = data.file_id;
      setText(resultId, `Loaded ${data.records} records from ${data.filename}`);
      renderRecords(data.preview || []);
      switchTab("corrections");
    } else {
      setText(resultId, `Indexed ${data.filename} with ${data.chunks} chunks`);
      await loadDocuments();
    }
    await refreshHealth();
    showToast("Upload complete");
  } catch (err) {
    setText(resultId, err.message);
  } finally {
    input.value = "";
  }
}

function setupUpload(inputId, apiPath, resultId) {
  const input = el(inputId);
  const zone = document.querySelector(`[data-drop-target="${inputId}"]`);

  input.addEventListener("change", (event) => {
    uploadFile(event.target, apiPath, resultId);
  });

  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("dragging");
  });

  zone.addEventListener("dragleave", () => {
    zone.classList.remove("dragging");
  });

  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("dragging");
    uploadFile(input, apiPath, resultId, event.dataTransfer.files[0]);
  });
}

setupUpload("document-upload", "/api/upload/document", "document-result");
setupUpload("records-upload", "/api/upload/records", "records-result");

el("refresh-docs").addEventListener("click", async () => {
  await loadDocuments();
  await refreshHealth();
  showToast("Workspace refreshed");
});

el("clear-documents").addEventListener("click", async () => {
  if (!window.confirm("Clear the local RAG index?")) return;
  await request("/api/documents", { method: "DELETE" });
  await loadDocuments();
  await refreshHealth();
  showToast("Document index cleared");
});

function appendMessage(role, text, sources = [], options = {}) {
  const log = el("chat-log");
  const item = node("div", `message ${role}${options.loading ? " loading" : ""}`);
  if (options.id) item.id = options.id;
  item.appendChild(node("div", "role", role === "user" ? "You" : "ForgeLens"));
  item.appendChild(node("div", "bubble", text));

  if (sources.length) {
    const sourceLine = node(
      "div",
      "sources",
      sources.map((source) => `${source.source} (${source.score})`).join(", ")
    );
    item.appendChild(sourceLine);
  }

  log.appendChild(item);
  log.scrollTop = log.scrollHeight;
  return item;
}

function removeNodeById(id) {
  const element = document.getElementById(id);
  if (element) element.remove();
}

async function submitChat(query) {
  const input = el("chat-input");
  const send = el("chat-send");
  const cleanQuery = query || input.value.trim();
  if (!cleanQuery) return;

  appendMessage("user", cleanQuery);
  input.value = "";
  setBusy(send, true, "Thinking");
  appendMessage("assistant", "Reading indexed context...", [], { id: "loading-message", loading: true });

  try {
    const data = await request("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: cleanQuery, top_k: 4 }),
    });
    removeNodeById("loading-message");
    appendMessage("assistant", data.answer, data.sources || []);
    await refreshHealth();
  } catch (err) {
    removeNodeById("loading-message");
    appendMessage("assistant", err.message);
  } finally {
    setBusy(send, false, "Send");
    renderIcons();
  }
}

el("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  submitChat();
});

document.querySelectorAll(".prompt-chip").forEach((chip) => {
  chip.addEventListener("click", () => submitChat(chip.dataset.prompt));
});

async function analyzeCorrections() {
  if (!state.activeFileId) {
    showToast("Upload a records file first");
    return;
  }
  const button = el("analyze-records");
  setBusy(button, true, "Analyzing");
  try {
    const data = await request("/api/correction/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_id: state.activeFileId || "latest", instructions: "Review all fields" }),
    });
    renderCorrectionSummary(data.summary || {});
    renderCorrections(data.corrections || []);
    await refreshHealth();
  } catch (err) {
    showToast(err.message);
  } finally {
    setBusy(button, false, "Analyze");
    renderIcons();
  }
}

function renderCorrectionSummary(summary) {
  const row = el("correction-summary");
  row.replaceChildren();
  ["pending", "approved", "rejected", "applied"].forEach((key) => {
    row.appendChild(node("span", "summary-chip", `${key}: ${summary[key] ?? 0}`));
  });
}

function renderCorrections(corrections) {
  const list = el("correction-list");
  list.replaceChildren();

  if (!corrections.length) {
    list.textContent = "No issues found.";
    list.className = "correction-list empty";
    return;
  }

  list.className = "correction-list";
  corrections.forEach((correction) => {
    const item = node("article", `correction-item ${correction.risk_level}`);
    const title = node("div", "correction-title");
    title.appendChild(
      node(
        "strong",
        "",
        `Record ${correction.record_index + 1} - ${correction.issue_type.replaceAll("_", " ")}`
      )
    );
    title.appendChild(node("span", `risk-pill ${correction.risk_level}`, correction.risk_level));
    item.appendChild(title);

    const diff = node("div", "diff");
    diff.appendChild(node("span", "old", `${correction.field}: ${correction.current_value || "[empty]"}`));
    diff.appendChild(node("span", "new", `${correction.field}: ${correction.proposed_value}`));
    item.appendChild(diff);

    item.appendChild(node("div", "meta", correction.reason));

    const confidence = node("div", "confidence");
    const confidenceFill = node("span");
    confidenceFill.style.width = `${Math.round((correction.confidence || 0) * 100)}%`;
    confidence.appendChild(confidenceFill);
    item.appendChild(confidence);

    const actions = node("div", "actions");
    const approve = node("button");
    approve.innerHTML = '<i data-lucide="check"></i><span>Approve</span>';
    approve.addEventListener("click", () => approveCorrection(correction.correction_id, true));
    const reject = node("button", "ghost-button danger");
    reject.innerHTML = '<i data-lucide="x"></i><span>Reject</span>';
    reject.addEventListener("click", () => approveCorrection(correction.correction_id, false));
    actions.append(approve, reject);
    item.appendChild(actions);
    list.appendChild(item);
  });
  renderIcons();
}

async function approveCorrection(id, approved) {
  try {
    await request("/api/correction/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ correction_id: id, approved, admin_note: approved ? "Approved in UI" : "Rejected in UI" }),
    });
    await analyzeCorrections();
    await loadRecords();
    showToast(approved ? "Correction approved" : "Correction rejected");
  } catch (err) {
    showToast(err.message);
  }
}

el("analyze-records").addEventListener("click", analyzeCorrections);

el("export-records").addEventListener("click", () => {
  if (!state.activeFileId) {
    showToast("Upload a records file first");
    return;
  }
  const fileId = state.activeFileId || "latest";
  window.location.href = `${API}/api/correction/export/${fileId}`;
});

async function loadRecords() {
  try {
    const data = await request(`/api/records/${state.activeFileId || "latest"}?limit=50`);
    renderRecords(data.records || []);
  } catch {
    renderRecords([]);
  }
}

function renderRecords(records) {
  const table = el("records-table");
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");
  thead.replaceChildren();
  tbody.replaceChildren();

  if (!records.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 1;
    cell.textContent = "No records loaded.";
    row.appendChild(cell);
    tbody.appendChild(row);
    return;
  }

  const columns = Array.from(new Set(records.flatMap((record) => Object.keys(record))));
  const headerRow = document.createElement("tr");
  columns.forEach((column) => headerRow.appendChild(node("th", "", column)));
  thead.appendChild(headerRow);

  records.forEach((record) => {
    const row = document.createElement("tr");
    columns.forEach((column) => {
      row.appendChild(node("td", "", record[column] ?? ""));
    });
    tbody.appendChild(row);
  });
}

el("refresh-records").addEventListener("click", loadRecords);

async function loadAudit() {
  const list = el("audit-list");
  try {
    const data = await request("/api/audit?limit=50");
    list.replaceChildren();
    if (!data.entries.length) {
      list.textContent = "No audit events yet.";
      list.className = "audit-list empty";
      return;
    }
    list.className = "audit-list";
    data.entries.forEach((entry) => {
      const item = node("div", "audit-item");
      item.appendChild(node("strong", "", entry.action));
      item.appendChild(node("div", "meta", `${entry.timestamp} - ${entry.target}`));
      list.appendChild(item);
    });
  } catch (err) {
    list.textContent = err.message;
  }
}

el("refresh-audit").addEventListener("click", loadAudit);

appendMessage("assistant", "ForgeLens is ready. Index a guide or student CSV, then ask a grounded question.");
refreshHealth();
loadDocuments();
renderIcons();
