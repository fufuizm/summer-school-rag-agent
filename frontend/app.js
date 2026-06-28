const API = window.localStorage.getItem("ragAgentApi") || "http://localhost:8000";

const state = {
  activeFileId: null,
};

const el = (id) => document.getElementById(id);

function setText(id, value) {
  el(id).textContent = value;
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
  if (name === "audit") loadAudit();
  if (name === "records") loadRecords();
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
});

async function refreshHealth() {
  try {
    const data = await request("/health");
    setText("documents-count", data.documents_indexed ?? 0);
    setText("chunks-count", data.chunks_indexed ?? 0);
    setText("records-count", data.records_loaded ?? 0);
    setText("pending-count", data.corrections?.pending ?? 0);

    const runtime = data.runtime?.runtime || "unknown";
    const pill = el("runtime-pill");
    pill.textContent = `Runtime: ${runtime}`;
    pill.className = `runtime-pill ${runtime === "foundry_local" ? "good" : "warn"}`;

    state.activeFileId = data.active_records_file || state.activeFileId;
  } catch {
    const pill = el("runtime-pill");
    pill.textContent = "Runtime: offline";
    pill.className = "runtime-pill warn";
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

async function uploadFile(input, path, resultId) {
  const file = input.files[0];
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

el("document-upload").addEventListener("change", (event) => {
  uploadFile(event.target, "/api/upload/document", "document-result");
});

el("records-upload").addEventListener("change", (event) => {
  uploadFile(event.target, "/api/upload/records", "records-result");
});

el("refresh-docs").addEventListener("click", async () => {
  await loadDocuments();
  await refreshHealth();
});

el("clear-documents").addEventListener("click", async () => {
  if (!window.confirm("Clear the local RAG index?")) return;
  await request("/api/documents", { method: "DELETE" });
  await loadDocuments();
  await refreshHealth();
  showToast("Document index cleared");
});

function appendMessage(role, text, sources = []) {
  const log = el("chat-log");
  const item = node("div", `message ${role}`);
  item.appendChild(node("div", "role", role === "user" ? "You" : "Agent"));
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
}

el("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = el("chat-input");
  const query = input.value.trim();
  if (!query) return;

  appendMessage("user", query);
  input.value = "";

  try {
    const data = await request("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: 4 }),
    });
    appendMessage("assistant", data.answer, data.sources || []);
    await refreshHealth();
  } catch (err) {
    appendMessage("assistant", err.message);
  }
});

async function analyzeCorrections() {
  if (!state.activeFileId) {
    showToast("Upload a records file first");
    return;
  }
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
    item.appendChild(
      node(
        "strong",
        "",
        `Record ${correction.record_index + 1} - ${correction.issue_type.replaceAll("_", " ")}`
      )
    );

    const diff = node("div", "diff");
    diff.appendChild(node("span", "old", `${correction.field}: ${correction.current_value || "[empty]"}`));
    diff.appendChild(node("span", "new", `${correction.field}: ${correction.proposed_value}`));
    item.appendChild(diff);

    item.appendChild(
      node(
        "div",
        "meta",
        `${correction.reason} Confidence: ${Math.round((correction.confidence || 0) * 100)}%`
      )
    );

    const actions = node("div", "actions");
    const approve = node("button", "", "Approve");
    approve.addEventListener("click", () => approveCorrection(correction.correction_id, true));
    const reject = node("button", "ghost danger", "Reject");
    reject.addEventListener("click", () => approveCorrection(correction.correction_id, false));
    actions.append(approve, reject);
    item.appendChild(actions);
    list.appendChild(item);
  });
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

appendMessage("assistant", "Upload the sample guide or student CSV, then ask a grounded question.");
refreshHealth();
loadDocuments();
