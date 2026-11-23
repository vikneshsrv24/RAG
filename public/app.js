const state = {
  title: "Groww MF Facts Assistant",
  disclaimer: "Facts-only. No investment advice.",
  examples: [],
  sources: [],
  microcopy: "Grounding: 5 Approved AMC Indexes",
  lastQueryId: "",
  messages: loadMessages(),
};

const elements = {
  pageTitle: document.getElementById("page-title"),
  disclaimerBadge: document.getElementById("disclaimer-badge"),
  groundingText: document.getElementById("grounding-text"),
  verifiedBadge: document.getElementById("verified-badge"),
  microcopy: document.getElementById("microcopy"),
  sourceList: document.getElementById("source-list"),
  exampleList: document.getElementById("example-list"),
  chatStream: document.getElementById("chat-stream"),
  chatForm: document.getElementById("chat-form"),
  questionInput: document.getElementById("question-input"),
  sendButton: document.getElementById("send-button"),
  resetButton: document.getElementById("reset-button"),
  guidelinesButton: document.getElementById("guidelines-button"),
  guidelinesDialog: document.getElementById("guidelines-dialog"),
  guidelinesClose: document.getElementById("guidelines-close"),
  inspectorPanel: document.getElementById("inspector-panel"),
  inspectorQuery: document.getElementById("inspector-query"),
  inspectorQueryRow: document.getElementById("query-row"),
  inspectorRefresh: document.getElementById("inspector-refresh"),
  inspectorOutput: document.getElementById("inspector-output"),
};

function loadMessages() {
  try {
    const raw = localStorage.getItem("rag.messages");
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveMessages() {
  localStorage.setItem("rag.messages", JSON.stringify(state.messages));
  if (state.lastQueryId) {
    localStorage.setItem("rag.lastQueryId", state.lastQueryId);
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return payload;
}

function makeElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function renderSources() {
  elements.sourceList.replaceChildren();
  state.sources.forEach((source) => {
    const card = makeElement("div", `source-card${source.category === "amc" ? " active" : ""}`);
    const head = makeElement("div", "source-head");
    head.append(
      makeElement("div", "source-name", source.title),
      makeElement(
        "span",
        `source-badge${source.category === "amc" ? " active" : ""}`,
        source.category === "amc" ? "Active" : "Indexed"
      )
    );
    card.append(head, makeElement("div", "source-url", source.url), makeElement("div", "source-meta", source.scheme || source.category.toUpperCase()));
    elements.sourceList.append(card);
  });
}

function renderExamples() {
  elements.exampleList.replaceChildren();
  state.examples.forEach((example) => {
    const button = makeElement("button", "prompt-button", example);
    button.type = "button";
    button.addEventListener("click", () => ask(example));
    elements.exampleList.append(button);
  });
}

function renderUserMessage(text) {
  const row = makeElement("div", "user-row");
  row.append(makeElement("div", "user-bubble", text));
  elements.chatStream.append(row);
}

function safeCitation(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:") return null;
    if (!["groww.in", "www.groww.in"].includes(parsed.hostname)) return null;
    return url;
  } catch {
    return null;
  }
}

function renderAssistantMessage(result) {
  const card = makeElement("div", "answer-card");
  const head = makeElement("div", "answer-head");
  const isRefusal = result.outcome === "refused";
  head.append(
    makeElement("span", isRefusal ? "badge-refusal" : "badge-fact", isRefusal ? "● Refusal / Redirect" : "● Verified Scheme Fact"),
    makeElement("span", "answer-time", "Grounded Registry")
  );

  card.append(head);
  card.append(makeElement("p", "answer-body", result.body || ""));

  const citation = safeCitation(result.citation || "");
  const citationCard = makeElement("div", "citation-card");
  const citationText = makeElement("div");
  citationText.append(
    makeElement("div", "citation-title", result.citation_title || "Groww Mutual Funds"),
    makeElement("div", "citation-url", result.citation_path || result.citation || "")
  );
  citationCard.append(citationText);
  if (citation) {
    const link = makeElement("a", "citation-link", "Open Page ↗");
    link.href = citation;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    citationCard.append(link);
  }
  card.append(citationCard);
  card.append(makeElement("p", "caption", result.disclaimer || state.disclaimer));
  card.append(makeElement("p", "caption", result.footer || ""));

  const details = makeElement("details", "metadata-details");
  details.append(makeElement("summary", "", "View grounding metadata"));
  const pre = makeElement("pre");
  pre.textContent = JSON.stringify(
    {
      query_id: result.query_id,
      classification: result.classification,
      outcome: result.outcome,
      refusal_reason: result.refusal_reason,
      generation_mode: result.generation_mode,
      selected_chunk_ids: result.selected_chunk_ids,
      citation: result.citation,
      validation: result.validation,
    },
    null,
    2
  );
  details.append(pre);
  card.append(details);
  elements.chatStream.append(card);
}

function renderPending() {
  const card = makeElement("div", "pending-card", "Verifying against approved sources…");
  elements.chatStream.append(card);
  return card;
}

function renderError(message) {
  elements.chatStream.append(makeElement("div", "error-card", message));
}

function renderMessages() {
  elements.chatStream.replaceChildren();
  state.messages.forEach((message) => {
    if (message.role === "user") renderUserMessage(message.text);
    if (message.role === "assistant") renderAssistantMessage(message.result);
  });
}

function toggleQueryRow() {
  const panel = elements.inspectorPanel.value;
  const needsQuery = ["Retrieval", "Answer", "Generation", "Validation"].includes(panel);
  elements.inspectorQueryRow.classList.toggle("hidden", !needsQuery);
}

async function refreshInspector() {
  const panel = elements.inspectorPanel.value;
  const queryId = elements.inspectorQuery.value.trim() || state.lastQueryId || "";
  elements.inspectorOutput.textContent = "Loading artifact…";
  try {
    const params = new URLSearchParams({ panel });
    if (queryId) params.set("query_id", queryId);
    const payload = await api(`/api/inspect?${params.toString()}`);
    elements.inspectorOutput.textContent = JSON.stringify(payload, null, 2);
  } catch (error) {
    elements.inspectorOutput.textContent = `Could not load artifact: ${error.message}`;
  }
}

async function ask(rawQuestion) {
  const question = String(rawQuestion || "").trim();
  if (!question) return;

  elements.questionInput.value = "";
  elements.sendButton.disabled = true;
  const pending = renderPending();

  try {
    const result = await api("/api/answer", {
      method: "POST",
      body: JSON.stringify({ question }),
    });

    pending.remove();
    renderUserMessage(result.display_question || "[redacted]");
    renderAssistantMessage(result);
    state.messages.push({ role: "user", text: result.display_question || "[redacted]" });
    state.messages.push({ role: "assistant", result });
    state.lastQueryId = result.query_id || state.lastQueryId;
    saveMessages();
    await refreshInspector();
  } catch (error) {
    pending.remove();
    renderError(`Could not answer this question: ${error.message}`);
  } finally {
    elements.sendButton.disabled = false;
    elements.questionInput.focus();
  }
}

async function loadBootstrap() {
  try {
    const payload = await api("/api/sources");
    state.title = payload.title;
    state.disclaimer = payload.disclaimer;
    state.examples = payload.examples || [];
    state.sources = payload.sources || [];
    state.microcopy = payload.microcopy || state.microcopy;

    document.title = state.title;
    elements.pageTitle.textContent = state.title;
    elements.disclaimerBadge.textContent = `ⓘ ${state.disclaimer}`;
    elements.groundingText.textContent = payload.grounding_text || "Grounding Active";
    elements.verifiedBadge.textContent = `${payload.verified_count || 0} Verified`;
    elements.microcopy.textContent = state.microcopy;
    renderSources();
    renderExamples();
  } catch (error) {
    renderError(`Could not load app configuration: ${error.message}`);
  }
}

elements.chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  ask(elements.questionInput.value);
});

elements.resetButton.addEventListener("click", () => {
  state.messages = [];
  state.lastQueryId = "";
  localStorage.removeItem("rag.messages");
  localStorage.removeItem("rag.lastQueryId");
  elements.inspectorQuery.value = "";
  renderMessages();
  refreshInspector();
});

elements.guidelinesButton.addEventListener("click", () => elements.guidelinesDialog.showModal());
elements.guidelinesClose.addEventListener("click", () => elements.guidelinesDialog.close());
elements.inspectorPanel.addEventListener("change", () => {
  toggleQueryRow();
  refreshInspector();
});
elements.inspectorRefresh.addEventListener("click", refreshInspector);

(async function init() {
  const storedQueryId = localStorage.getItem("rag.lastQueryId");
  if (storedQueryId) state.lastQueryId = storedQueryId;
  elements.inspectorQuery.value = state.lastQueryId;
  toggleQueryRow();
  await loadBootstrap();
  renderMessages();
  await refreshInspector();
})();
