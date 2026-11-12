/*
 * VaaniOS frontend — app.js
 * Premium Fintech UI  |  v2.0
 * Keep Gnani API keys and provider calls on the backend only.
 */

const API_BASE_URL = "http://127.0.0.1:5000";
const API = {
  health:        "/api/health",
  summary:       "/api/summary/today",
  weeklySummary: "/api/summary/weekly",
  transactions:  "/api/transactions",
  undo:          "/api/transaction/undo",
  command:       "/api/voice/command",
  confirm:       "/api/voice/confirm"
};

const el = (id) => document.getElementById(id);

const state = {
  connected:       false,
  recording:       false,
  processing:      false,
  mediaRecorder:   null,
  stream:          null,
  chunks:          [],
  pendingActionId: null,
  latestAudioUrl:  null,
  weeklyChart:     null,
  selectedDate:    null,
  theme:           localStorage.getItem("vaanios_theme") || "dark",
  /* Last recorded summary for sharing */
  lastSales:       0,
  lastExpenses:    0,
};

/* ─────────────────────────────────────────────────────────────────
   SAMPLE DATA (preview mode)
───────────────────────────────────────────────────────────────── */
const sampleTransactions = [
  { id: "s1", description: "Counter sale",   note: "Sample preview record", type: "sale",    category: "general",  amount: 2500, time: "11:42 AM", status: "sample" },
  { id: "s2", description: "Stock purchase", note: "Sample preview record", type: "expense", category: "utility",  amount: 800,  time: "10:18 AM", status: "sample" },
  { id: "s3", description: "Morning sales",  note: "Sample preview record", type: "sale",    category: "food",     amount: 1250, time: "09:06 AM", status: "sample" },
];

/* ─────────────────────────────────────────────────────────────────
   UTILITIES
───────────────────────────────────────────────────────────────── */
function formatINR(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return "₹ " + n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function getTodayDateString() {
  const d = new Date();
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function updateDateDisplay(dateStr) {
  let targetDate;
  if (dateStr) {
    const parts = dateStr.split("-").map(Number);
    if (parts.length === 3 && !parts.some(isNaN)) {
      targetDate = new Date(parts[0], parts[1] - 1, parts[2]);
    } else {
      targetDate = new Date();
    }
  } else {
    targetDate = new Date();
  }
  const formatted = new Intl.DateTimeFormat("en-IN", {
    weekday: "short", day: "numeric", month: "short"
  }).format(targetDate);

  const displayEl = el("todayDate");
  if (displayEl) {
    displayEl.textContent = formatted;
  }
}

function formatToday() {
  const todayStr = getTodayDateString();
  state.selectedDate = todayStr;
  const picker = el("datePicker");
  if (picker) {
    picker.value = todayStr;
  }
  updateDateDisplay(todayStr);
}

function handleDateChange(e) {
  const newDate = e.target.value;
  state.selectedDate = newDate;
  updateDateDisplay(newDate);
  loadDashboard(newDate);
  addActivity("Date Filter Applied", `Viewing records for ${newDate}`, "info");
}

function categoryChipClass(category) {
  const map = {
    food:      "chip-food",
    utility:   "chip-utility",
    general:   "chip-general",
    transport: "chip-transport",
  };
  return map[String(category || "").toLowerCase()] || "chip-other";
}

function categoryLabel(category) {
  if (!category) return "General";
  return category.charAt(0).toUpperCase() + category.slice(1).toLowerCase();
}

/* ─────────────────────────────────────────────────────────────────
   TOAST  (Gmail-style, slides from bottom, has Undo)
───────────────────────────────────────────────────────────────── */
function showToast(message, { undoFn = null, duration = 4000 } = {}) {
  const container = el("toastContainer");

  const item = document.createElement("div");
  item.className = "toast-item";

  const msg = document.createElement("span");
  msg.className = "toast-msg";
  msg.textContent = message;
  item.append(msg);

  if (undoFn) {
    const undoBtn = document.createElement("button");
    undoBtn.className = "toast-undo";
    undoBtn.textContent = "Undo";
    undoBtn.addEventListener("click", () => {
      undoFn();
      dismiss();
    });
    item.append(undoBtn);
  }

  // Close button with Lucide icon
  const closeBtn = document.createElement("button");
  closeBtn.className = "toast-close";
  closeBtn.setAttribute("aria-label", "Dismiss");
  closeBtn.innerHTML = '<i data-lucide="x"></i>';
  closeBtn.addEventListener("click", () => dismiss());
  item.append(closeBtn);

  container.prepend(item);

  // Re-render Lucide icons for the new close button
  if (window.lucide) lucide.createIcons({ attrs: { class: "lucide" } });

  let timer = setTimeout(dismiss, duration);

  function dismiss() {
    clearTimeout(timer);
    item.classList.add("toast-exit");
    item.addEventListener("animationend", () => item.remove(), { once: true });
  }
}

/* ─────────────────────────────────────────────────────────────────
   ACTIVITY LOG
───────────────────────────────────────────────────────────────── */
function addActivity(title, message, kind = "info") {
  const row = document.createElement("div");
  row.className = "activity-item";

  const dot = document.createElement("span");
  dot.className = `activity-indicator ${kind}`;

  const copy = document.createElement("div");
  const strong = document.createElement("strong");
  strong.textContent = title;
  const p = document.createElement("p");
  p.textContent = message;
  copy.append(strong, p);

  const time = document.createElement("time");
  time.textContent = new Date()
    .toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
    .toUpperCase();

  row.append(dot, copy, time);
  el("activityList").prepend(row);
}

/* ─────────────────────────────────────────────────────────────────
   CONNECTION + MODE NOTICE
───────────────────────────────────────────────────────────────── */
function setConnection(connected) {
  state.connected = connected;
  const badge = el("connectionBadge");
  badge.classList.toggle("online", connected);
  badge.classList.toggle("offline", !connected);
  el("connectionText").textContent = connected ? "Backend connected" : "Backend not connected";

  const notice = el("modeNotice");
  if (connected) {
    notice.classList.add("connected");
    notice.innerHTML = '<span class="notice-icon"><i data-lucide="check-circle-2"></i></span><span><strong>Live mode</strong> — dashboard figures below are loaded from the backend.</span>';
  } else {
    notice.classList.remove("connected");
    notice.innerHTML = '<span class="notice-icon"><i data-lucide="info"></i></span><span><strong>Preview mode</strong> — sample figures are shown until the backend connects. They are not real business records.</span>';
  }
  if (window.lucide) lucide.createIcons({ attrs: { class: "lucide" } });
}

/* ─────────────────────────────────────────────────────────────────
   VOICE STATUS
───────────────────────────────────────────────────────────────── */
function setVoiceStatus(title, text) {
  el("voiceStatusTitle").textContent = title;
  el("voiceStatusText").textContent = text;
}

function setRecordingUI(recording) {
  state.recording = recording;
  el("voiceStage").classList.toggle("recording", recording);
  el("micButton").setAttribute("aria-label", recording ? "Stop recording" : "Start voice recording");

  const btn = el("mainVoiceButton");
  if (recording) {
    btn.innerHTML = '<i data-lucide="square" class="btn-icon"></i> Stop &amp; send';
  } else {
    btn.innerHTML = '<i data-lucide="mic" class="btn-icon"></i> Start speaking';
  }
  if (window.lucide) lucide.createIcons({ attrs: { class: "lucide" } });
}

function setProcessingUI(processing) {
  state.processing = processing;
  el("micButton").disabled = processing;
  el("mainVoiceButton").disabled = processing;
  if (processing) {
    setVoiceStatus("Understanding your request…", "Sending the recording to the VaaniOS backend.");
    el("transcriptStatus").textContent = "PROCESSING";
  }
}

/* ─────────────────────────────────────────────────────────────────
   FETCH HELPER
───────────────────────────────────────────────────────────────── */
async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { ...(options.headers || {}) }
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const message = typeof payload === "object"
      ? (payload.error || payload.message || JSON.stringify(payload))
      : payload;
    throw new Error(message || `HTTP ${response.status}`);
  }
  return payload;
}

/* ─────────────────────────────────────────────────────────────────
   DASHBOARD LOAD
───────────────────────────────────────────────────────────────── */
async function loadDashboard(dateStr = state.selectedDate) {
  try {
    await fetchJson(API.health);
    setConnection(true);

    const query = dateStr ? `?date=${encodeURIComponent(dateStr)}` : "";
    const [summaryResult, transactionResult, weeklyResult] = await Promise.allSettled([
      fetchJson(`${API.summary}${query}`),
      fetchJson(`${API.transactions}${query}`),
      fetchJson(API.weeklySummary)
    ]);

    if (summaryResult.status === "fulfilled") renderSummary(summaryResult.value);
    if (transactionResult.status === "fulfilled") renderTransactions(transactionResult.value);
    if (weeklyResult.status === "fulfilled") renderWeeklyChart(weeklyResult.value);

    if (summaryResult.status === "rejected" || transactionResult.status === "rejected") {
      const notice = el("modeNotice");
      notice.classList.remove("connected");
      notice.innerHTML = '<span class="notice-icon"><i data-lucide="alert-triangle"></i></span><span><strong>Backend partly connected</strong> — one or more data routes failed.</span>';
      if (window.lucide) lucide.createIcons({ attrs: { class: "lucide" } });
      addActivity("Dashboard partially loaded", "Check /api/summary/today and /api/transactions.", "warn");
    }
  } catch {
    setConnection(false);
  }
}

/* ─────────────────────────────────────────────────────────────────
   RENDER SUMMARY
───────────────────────────────────────────────────────────────── */
function renderSummary(data) {
  // Backend contract: { sales, expenses, net_balance }
  // Also accepts legacy aliases used by older API versions.
  const sales    = Number(data.sales_total    ?? data.sales    ?? 0);
  const expenses = Number(data.expense_total  ?? data.expenses ?? 0);
  const net      = Number(
    data.net_difference ?? data.net_balance ?? data.sales_minus_expenses ?? (sales - expenses)
  );

  el("salesTotal").textContent   = formatINR(sales);
  el("expenseTotal").textContent = formatINR(expenses);
  el("netTotal").textContent     = formatINR(net);

  // Persist for WhatsApp share button
  state.lastSales    = sales;
  state.lastExpenses = expenses;
}

/* ─────────────────────────────────────────────────────────────────
   RENDER TRANSACTIONS  (with Category Chips)
───────────────────────────────────────────────────────────────── */
function renderTransactions(payload) {
  const items = Array.isArray(payload)
    ? payload
    : (payload.items || payload.transactions || []);

  const tbody = el("transactionsBody");
  tbody.replaceChildren();

  if (!items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.textContent = "No transactions recorded yet. Speak a command to add your first one.";
    Object.assign(cell.style, { padding: "28px 18px", color: "#94a3b8", textAlign: "center" });
    row.append(cell);
    tbody.append(row);
    el("transactionCount").textContent = "0 transactions";
    return;
  }

  for (const item of items.slice(0, 8)) {
    const type   = String(item.type || item.kind || "unknown").toLowerCase();
    const isSale = type === "sale" || type === "income";
    const amount = Number(item.amount || 0);
    const cat    = item.category || (isSale ? "general" : "utility");

    // --- Row ---
    const row = document.createElement("tr");

    // Name cell
    const nameCell = document.createElement("td");
    const nameWrap = document.createElement("div");
    nameWrap.className = "transaction-name";
    const icon = document.createElement("span");
    icon.className = `transaction-icon ${isSale ? "sale" : "expense"}`;
    icon.innerHTML = isSale
      ? '<i data-lucide="trending-up"></i>'
      : '<i data-lucide="trending-down"></i>';
    const detail = document.createElement("span");
    const title  = document.createElement("strong");
    title.textContent = item.description || item.note || (isSale ? "Sale" : "Expense");
    const note   = document.createElement("small");
    note.textContent  = item.note || (item.created_at ? new Date(item.created_at).toLocaleDateString("en-IN") : "Saved transaction");
    detail.append(title, note);
    nameWrap.append(icon, detail);
    nameCell.append(nameWrap);

    // Type cell
    const typeCell = document.createElement("td");
    const typePill = document.createElement("span");
    typePill.className = `type-pill ${isSale ? "sale-type" : "expense-type"}`;
    typePill.textContent = isSale ? "Sale" : "Expense";
    typeCell.append(typePill);

    // Category chip cell
    const catCell  = document.createElement("td");
    const catChip  = document.createElement("span");
    catChip.className = `category-chip ${categoryChipClass(cat)}`;
    catChip.textContent = categoryLabel(cat);
    catCell.append(catChip);

    // Time cell
    const timeCell = document.createElement("td");
    const dateVal  = item.created_at || item.timestamp || item.time;
    timeCell.textContent = dateVal
      ? (Number.isNaN(Date.parse(dateVal)) ? String(dateVal) : new Date(dateVal).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }))
      : "—";

    // Amount cell
    const amountCell = document.createElement("td");
    amountCell.className = `align-right ${isSale ? "amount-positive" : "amount-negative"}`;
    amountCell.textContent = `${isSale ? "+" : "−"} ${formatINR(Math.abs(amount))}`;

    // Status cell
    const statusCell   = document.createElement("td");
    const statusBadge  = document.createElement("span");
    statusBadge.className = "status-pill saved";
    statusBadge.textContent = "SAVED";
    statusCell.append(statusBadge);

    row.append(nameCell, typeCell, catCell, timeCell, amountCell, statusCell);
    tbody.append(row);
  }

  el("transactionCount").textContent = `${items.length} transaction${items.length === 1 ? "" : "s"}`;

  // Re-render Lucide icons in table
  if (window.lucide) lucide.createIcons({ attrs: { class: "lucide" } });
}

/* ─────────────────────────────────────────────────────────────────
   TRANSCRIPT + INTENT PREVIEW
───────────────────────────────────────────────────────────────── */
function showTranscript(transcript) {
  const body = el("transcriptBody");
  body.replaceChildren();
  const quote = document.createElement("div");
  quote.className = "transcript-quote";
  quote.textContent = transcript || "No transcript was returned. Please try a shorter, clearer recording.";
  body.append(quote);
  el("transcriptStatus").textContent = transcript ? "TRANSCRIBED" : "NO TRANSCRIPT";
}

function showActionPreview(payload) {
  const preview = el("intentPreview");

  // ── Intent label ─────────────────────────────────────────────────────────────
  const intent     = payload.intent || payload.action || "Request interpreted";
  const normalized = String(intent).replaceAll("_", " ");
  el("intentTitle").textContent = normalized.charAt(0).toUpperCase() + normalized.slice(1);

  // ── Detail lines ─────────────────────────────────────────────────────────────
  // The backend may put action data at extracted_data, action_data, parameters,
  // OR inline in parsed.actions[0]. Check all locations.
  const data = payload.extracted_data
            || payload.action_data
            || payload.parameters
            || (payload.parsed?.actions?.[0])
            || {};
  const lines = [];
  if (data.type)                                       lines.push(`Type: ${data.type}`);
  if (data.amount !== undefined && data.amount !== null) lines.push(`Amount: ${formatINR(data.amount)}`);
  if (data.description)                                lines.push(`Description: ${data.description}`);
  if (payload.message)                                 lines.push(payload.message);
  if (!lines.length) lines.push("The backend returned an interpretation. Check the transcript before proceeding.");
  el("intentDetail").textContent = lines.join("\n");

  // ── Resolve action_id ────────────────────────────────────────────────────────
  // A valid action_id must be a non-empty string.
  const rawActionId =
       payload.action_id
    || payload.pending_id
    || payload.parsed?.action_id
    || null;

  const actionId = (typeof rawActionId === "string" && rawActionId.trim().length > 0)
    ? rawActionId.trim()
    : null;

  // ── Strict Confirmation & Button Visibility Rules ───────────────────────────
  // 1. If payload.transaction_saved is true (or result.saved), the transaction has
  //    already been committed. Buttons MUST be completely hidden.
  const alreadySaved = Boolean(payload.transaction_saved || payload.result?.saved || payload.saved);

  // 2. Confirmation is required ONLY if not already saved AND explicitly requested.
  const requiresConfirmation = !alreadySaved && Boolean(
    payload.requires_confirmation || payload.pending_confirmation
  );

  // 3. STRICTLY hide intentActions (Confirm/Cancel buttons) if a valid action_id is NOT present.
  const showButtons = requiresConfirmation && Boolean(actionId);

  // 4. Ensure state.pendingActionId is properly assigned ONLY when buttons show, else null.
  state.pendingActionId = showButtons ? actionId : null;

  if (requiresConfirmation && !actionId) {
    console.warn(
      "[VaaniOS] requires_confirmation is true but valid action_id is missing from response. Suppressing buttons.",
      payload
    );
  }

  // 5. Update DOM elements with both .hidden and .style.display for cross-browser safety.
  const confirmNote = el("confirmationNote");
  confirmNote.hidden = !requiresConfirmation;
  confirmNote.style.display = requiresConfirmation ? "block" : "none";

  const actionsEl = el("intentActions");
  actionsEl.hidden = !showButtons;
  actionsEl.style.display = showButtons ? "flex" : "none";

  preview.hidden = false;
  preview.style.display = "block";
}

function clearActionPreview() {
  const preview = el("intentPreview");
  preview.hidden = true;
  preview.style.display = "none";

  const confirmNote = el("confirmationNote");
  confirmNote.hidden = true;
  confirmNote.style.display = "none";

  const actionsEl = el("intentActions");
  actionsEl.hidden = true;
  actionsEl.style.display = "none";

  state.pendingActionId = null;
}

/* ─────────────────────────────────────────────────────────────────
   RECORDING LOGIC
───────────────────────────────────────────────────────────────── */
async function processRecording(blob) {
  if (!state.connected) {
    setProcessingUI(false);
    setVoiceStatus("Backend not connected yet", "Your recording is ready, but the Flask backend needs to be running.");
    el("transcriptStatus").textContent = "OFFLINE";
    addActivity("Recording captured locally", "Backend not connected; no transaction was sent.", "warn");
    showToast("Start the Flask backend before sending a live voice command.");
    return;
  }

  setProcessingUI(true);
  const form = new FormData();
  const mime = blob.type || "audio/webm";
  const ext  = mime.includes("wav") ? "wav" : mime.includes("mp4") ? "m4a" : "webm";
  form.append("audio_file", blob, `vaanios-recording.${ext}`);

  try {
    const payload    = await fetchJson(API.command, { method: "POST", body: form });
    const transcript = payload.transcript || payload.text || "";
    showTranscript(transcript);

    // ── Route the response to the correct UI state ───────────────────────────
    //
    // Priority order (highest → lowest):
    //  1. transaction_saved=true  → backend already committed; show info panel,
    //                               NEVER show Confirm/Cancel buttons.
    //  2. requires_confirmation=true + action_id present → genuine pending action;
    //                               show Confirm/Cancel buttons.
    //  3. Any intent / extracted data present, nothing to confirm → show info panel only.
    //  4. None of the above → hide the preview entirely.
    //
    // Passing `payload` to showActionPreview is always safe — that function
    // internally enforces the strict "action_id required" gate for the buttons.
    const alreadySaved   = Boolean(payload.transaction_saved || payload.result?.saved);
    const hasIntent      = payload.intent || payload.action;
    const hasData        = payload.extracted_data || payload.action_data || payload.parameters;
    const hasPendingId   = payload.action_id || payload.pending_id;
    const needsConfirm   = payload.requires_confirmation || payload.pending_confirmation;

    if (alreadySaved) {
      // Auto-committed: show the info card but guarantee no Confirm button leaks through.
      // We explicitly null the pending id before calling showActionPreview so that
      // even if a stale DOM state exists the buttons cannot appear.
      state.pendingActionId = null;
      showActionPreview(payload);            // renders intent + detail; buttons stay hidden
    } else if (hasIntent || hasData || needsConfirm || hasPendingId) {
      showActionPreview(payload);            // may show buttons only if action_id is valid
    } else {
      clearActionPreview();
    }

    const replyText = payload.reply_text || payload.response_text || payload.message || "Request processed.";
    el("replyCaption").textContent = replyText;

    if (payload.audio_url) {
      const audioUrl = payload.audio_url.startsWith("http")
        ? payload.audio_url
        : `${API_BASE_URL}${payload.audio_url}`;
      el("replyAudio").src = audioUrl;
      el("playReplyButton").disabled = false;
    } else {
      el("playReplyButton").disabled = true;
    }

    // Derive a clean flag: was this auto-saved by the backend?
    const wasAutoSaved = Boolean(payload.transaction_saved || payload.result?.saved);

    // Voice status line reflects the actual outcome, not just requires_confirmation.
    if (wasAutoSaved) {
      setVoiceStatus("Transaction saved", "The backend recorded this automatically. Check the ledger below.");
    } else if (payload.requires_confirmation && state.pendingActionId) {
      setVoiceStatus("Review before saving", "Confirm or cancel the detected action below.");
    } else {
      setVoiceStatus("Request received", "Check the transcript and result below.");
    }

    addActivity(
      "Voice request processed",
      wasAutoSaved
        ? "Transaction auto-saved by the backend."
        : payload.requires_confirmation && state.pendingActionId
          ? "An action is waiting for your confirmation."
          : "Backend returned a response.",
      wasAutoSaved ? "info" : payload.requires_confirmation && state.pendingActionId ? "warn" : "info"
    );

    if (wasAutoSaved) {
      await loadDashboard();
      showToast("✅ Transaction saved!", {
        undoFn: undoLastTransaction
      });
    }
  } catch (error) {
    setVoiceStatus("Couldn't process that recording", "Check your connection and try again.");
    el("transcriptStatus").textContent = "ERROR";
    addActivity("Voice request failed", error.message || "Unknown backend error", "error");
    showToast(`Voice request failed: ${error.message || "unknown error"}`);
  } finally {
    setProcessingUI(false);
  }
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    showToast("This browser does not support microphone recording. Try Chrome or Edge.");
    setVoiceStatus("Microphone not supported", "Open VaaniOS in a modern browser over localhost or HTTPS.");
    return;
  }
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const preferred = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]
      .find((t) => MediaRecorder.isTypeSupported(t));
    state.mediaRecorder = preferred
      ? new MediaRecorder(state.stream, { mimeType: preferred })
      : new MediaRecorder(state.stream);
    state.chunks = [];

    state.mediaRecorder.addEventListener("dataavailable", (e) => {
      if (e.data && e.data.size > 0) state.chunks.push(e.data);
    });
    state.mediaRecorder.addEventListener("stop", async () => {
      const blob = new Blob(state.chunks, { type: state.mediaRecorder.mimeType || "audio/webm" });
      state.stream?.getTracks().forEach((t) => t.stop());
      state.stream = null;
      setRecordingUI(false);
      if (!blob.size) {
        setVoiceStatus("No audio captured", "Please try again and speak for a few seconds.");
        return;
      }
      await processRecording(blob);
    }, { once: true });

    state.mediaRecorder.start();
    setRecordingUI(true);
    setVoiceStatus("Listening…", "Speak clearly, then tap Stop & send when you're finished.");
    el("transcriptStatus").textContent = "LISTENING";
    addActivity("Microphone recording started", "Recording locally until you stop and send.", "info");
  } catch (error) {
    setRecordingUI(false);
    setVoiceStatus("Microphone permission needed", "Allow microphone access in your browser, then try again.");
    addActivity("Microphone access failed", error.message || "Permission was denied", "error");
    showToast("VaaniOS needs microphone permission to record your command.");
  }
}

function stopRecording() {
  if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
    setVoiceStatus("Preparing your recording…", "Sending the clip to the backend next.");
    state.mediaRecorder.stop();
  }
}

async function handleMicClick() {
  if (state.processing) return;
  if (state.recording) stopRecording();
  else await startRecording();
}

/* ─────────────────────────────────────────────────────────────────
   CONFIRM / CANCEL ACTIONS
───────────────────────────────────────────────────────────────── */
async function confirmAction(confirmed) {
  if (!state.connected) {
    showToast("Connect the backend before confirming an action.");
    return;
  }
  if (!state.pendingActionId) {
    // This should not happen in normal flow — it means showActionPreview never
    // received a valid action_id from /api/voice/command. Surface the root cause
    // clearly rather than the old cryptic message.
    showToast("No pending action found. Please speak a command first, or check the backend logs for a missing action_id.", { duration: 5500 });
    console.error("[VaaniOS] confirmAction called but state.pendingActionId is null. The /api/voice/command response may be missing the action_id field.");
    return;
  }
  try {
    const payload = await fetchJson(API.confirm, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Send the exact field name the backend expects: "action_id"
      body: JSON.stringify({ action_id: state.pendingActionId, confirmed })
    });
    clearActionPreview();
    const text = payload.message || (confirmed ? "Action confirmed by the backend." : "Action cancelled.");
    setVoiceStatus(confirmed ? "Action confirmed" : "Action cancelled", text);
    addActivity(confirmed ? "Action confirmed" : "Action cancelled", text, confirmed ? "info" : "warn");
    if (confirmed && (payload.transaction_saved || payload.success)) await loadDashboard();
    if (confirmed && payload.transaction_saved) {
      showToast(`✅ ${text}`, { undoFn: undoLastTransaction });
    } else {
      showToast(confirmed ? `✅ ${text}` : text);
    }
  } catch (error) {
    addActivity("Action confirmation failed", error.message || "Unknown backend error", "error");
    showToast(`Could not update action: ${error.message || "unknown error"}`);
  }
}

async function undoLastTransaction() {
  if (!state.connected) {
    showToast("Connect the backend before undoing a transaction.");
    return;
  }
  try {
    const payload = await fetchJson(API.undo, { method: "POST" });
    if (payload.updated_summary) renderSummary(payload.updated_summary);
    await loadDashboard();
    const message = payload.message || "Last transaction undone.";
    addActivity("Transaction undone", message, "warn");
    showToast(message);
  } catch (error) {
    addActivity("Undo failed", error.message || "Unknown backend error", "error");
    showToast(`Could not undo transaction: ${error.message || "unknown error"}`);
  }
}

function renderWeeklyChart(data) {
  if (!state.weeklyChart || !data) return;
  if (Array.isArray(data.labels) && Array.isArray(data.sales) && Array.isArray(data.expenses)) {
    state.weeklyChart.data.labels = data.labels;
    state.weeklyChart.data.datasets[0].data = data.sales;
    state.weeklyChart.data.datasets[1].data = data.expenses;
    if (state.weeklyChart.data.datasets[2]) {
      state.weeklyChart.data.datasets[2].data = data.sales.map((s, i) => s - (data.expenses[i] || 0));
    }
    state.weeklyChart.update();
  }
}

/* ─────────────────────────────────────────────────────────────────
   WEEKLY CHART  (Complex Multi-Colored Neon Area Chart)
───────────────────────────────────────────────────────────────── */
function initWeeklyChart() {
  const canvas = document.getElementById("weeklyChart");
  if (!canvas || !window.Chart) return;

  const isLight = state.theme === "light";
  const ptBorderColor = isLight ? "#ffffff" : "#06080d";

  const labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const salesData    = [8200,  11400, 9700, 14300, 12800, 18500, 12450];
  const expenseData  = [2100,  3800,  2900,  4100,  3600,  5200,  4280];

  const ctx = canvas.getContext("2d");

  // Create glowing vertical neon area gradients
  const salesGrad = ctx.createLinearGradient(0, 0, 0, 220);
  salesGrad.addColorStop(0, "rgba(0, 245, 212, 0.38)");
  salesGrad.addColorStop(0.55, "rgba(0, 245, 212, 0.10)");
  salesGrad.addColorStop(1, "rgba(0, 245, 212, 0.0)");

  const expGrad = ctx.createLinearGradient(0, 0, 0, 220);
  expGrad.addColorStop(0, "rgba(255, 42, 133, 0.32)");
  expGrad.addColorStop(0.55, "rgba(255, 42, 133, 0.08)");
  expGrad.addColorStop(1, "rgba(255, 42, 133, 0.0)");

  const netGrad = ctx.createLinearGradient(0, 0, 0, 220);
  netGrad.addColorStop(0, "rgba(168, 85, 247, 0.25)");
  netGrad.addColorStop(0.6, "rgba(168, 85, 247, 0.04)");
  netGrad.addColorStop(1, "rgba(168, 85, 247, 0.0)");

  state.weeklyChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Sales Revenue",
          data: salesData,
          borderColor: "#00f5d4",
          borderWidth: 2.5,
          backgroundColor: salesGrad,
          fill: true,
          tension: 0.42,
          pointBackgroundColor: "#00f5d4",
          pointBorderColor: ptBorderColor,
          pointBorderWidth: 2,
          pointRadius: 3.5,
          pointHoverRadius: 6,
          pointHoverBackgroundColor: "#ffffff",
          pointHoverBorderColor: "#00f5d4",
          pointHoverBorderWidth: 3,
        },
        {
          label: "Expenses",
          data: expenseData,
          borderColor: "#ff2a85",
          borderWidth: 2.5,
          backgroundColor: expGrad,
          fill: true,
          tension: 0.42,
          pointBackgroundColor: "#ff2a85",
          pointBorderColor: ptBorderColor,
          pointBorderWidth: 2,
          pointRadius: 3.5,
          pointHoverRadius: 6,
          pointHoverBackgroundColor: "#ffffff",
          pointHoverBorderColor: "#ff2a85",
          pointHoverBorderWidth: 3,
        },
        {
          label: "Net Trajectory",
          data: salesData.map((s, i) => s - expenseData[i]),
          borderColor: "#a855f7",
          borderWidth: 2,
          borderDash: [5, 4],
          backgroundColor: netGrad,
          fill: true,
          tension: 0.42,
          pointBackgroundColor: "#a855f7",
          pointBorderColor: ptBorderColor,
          pointBorderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          pointHoverBackgroundColor: "#ffffff",
          pointHoverBorderColor: "#a855f7",
          pointHoverBorderWidth: 2,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: isLight ? "rgba(255, 255, 255, 0.96)" : "rgba(11, 14, 23, 0.94)",
          titleColor: isLight ? "#0f172a" : "#ffffff",
          bodyColor: isLight ? "#334155" : "#cbd5e1",
          borderColor: "rgba(0, 245, 212, 0.35)",
          borderWidth: 1,
          cornerRadius: 8,
          padding: 10,
          boxPadding: 4,
          usePointStyle: true,
          titleFont: { family: "'Plus Jakarta Sans', sans-serif", size: 11, weight: "700" },
          bodyFont:  { family: "'JetBrains Mono', monospace", size: 11 },
          callbacks: {
            label: (ctx) => ` ${ctx.dataset.label}: ${formatINR(ctx.parsed.y)}`
          }
        }
      },
      scales: {
        x: {
          grid: {
            color: isLight ? "rgba(0, 0, 0, 0.05)" : "rgba(255, 255, 255, 0.04)",
            drawTicks: false,
          },
          border: { display: false },
          ticks: {
            font: { family: "'Plus Jakarta Sans', sans-serif", size: 11, weight: "500" },
            color: "#64748b",
            padding: 8,
          }
        },
        y: {
          grid: {
            color: isLight ? "rgba(0, 0, 0, 0.06)" : "rgba(255, 255, 255, 0.05)",
            lineWidth: 1
          },
          border: { dash: [4, 4], display: false },
          ticks: {
            font: { family: "'JetBrains Mono', monospace", size: 10 },
            color: "#64748b",
            padding: 10,
            callback: (val) => "₹" + (val >= 1000 ? (val / 1000).toFixed(0) + "k" : val),
          }
        }
      }
    }
  });
}

/* ─────────────────────────────────────────────────────────────────
   THEME SWITCHER  (Dark / Light Mode)
───────────────────────────────────────────────────────────────── */
function updateChartTheme(isLight) {
  if (!state.weeklyChart) return;
  const gridColorX = isLight ? "rgba(0, 0, 0, 0.05)" : "rgba(255, 255, 255, 0.04)";
  const gridColorY = isLight ? "rgba(0, 0, 0, 0.06)" : "rgba(255, 255, 255, 0.05)";
  const ptBorderColor = isLight ? "#ffffff" : "#06080d";

  if (state.weeklyChart.options.scales?.x?.grid) {
    state.weeklyChart.options.scales.x.grid.color = gridColorX;
  }
  if (state.weeklyChart.options.scales?.y?.grid) {
    state.weeklyChart.options.scales.y.grid.color = gridColorY;
  }
  if (state.weeklyChart.options.plugins?.tooltip) {
    state.weeklyChart.options.plugins.tooltip.backgroundColor = isLight ? "rgba(255, 255, 255, 0.96)" : "rgba(11, 14, 23, 0.94)";
    state.weeklyChart.options.plugins.tooltip.titleColor = isLight ? "#0f172a" : "#ffffff";
    state.weeklyChart.options.plugins.tooltip.bodyColor = isLight ? "#334155" : "#cbd5e1";
  }
  state.weeklyChart.data.datasets.forEach((ds) => {
    ds.pointBorderColor = ptBorderColor;
  });
  state.weeklyChart.update();
}

function applyTheme(theme) {
  state.theme = theme;
  try {
    localStorage.setItem("vaanios_theme", theme);
  } catch {
    // Ignore private browsing storage errors
  }

  const isLight = theme === "light";
  document.body.classList.toggle("light-theme", isLight);

  const icon = el("themeIcon");
  if (icon) {
    icon.setAttribute("data-lucide", isLight ? "moon" : "sun");
    if (window.lucide) {
      lucide.createIcons({ attrs: { class: "lucide" } });
    }
  }

  updateChartTheme(isLight);
}

function toggleTheme() {
  const nextTheme = state.theme === "light" ? "dark" : "light";
  applyTheme(nextTheme);
  showToast(nextTheme === "light" ? "Light theme enabled" : "Dark theme enabled");
}

/* ─────────────────────────────────────────────────────────────────
   PDF DOWNLOAD  (html2pdf.js)
───────────────────────────────────────────────────────────────── */
function downloadPDF() {
  if (!window.html2pdf) {
    showToast("PDF library is still loading. Please try again in a moment.");
    return;
  }
  const element = el("dashboardContent");
  const opt = {
    margin:       [8, 8, 8, 8],
    filename:     `VaaniOS-Dashboard-${new Date().toISOString().slice(0, 10)}.pdf`,
    image:        { type: "jpeg", quality: 0.96 },
    html2canvas:  { scale: 2, useCORS: true, logging: false },
    jsPDF:        { unit: "mm", format: "a4", orientation: "portrait" }
  };
  showToast("Generating PDF… please wait.");
  html2pdf().set(opt).from(element).save()
    .then(() => showToast("PDF downloaded successfully!"))
    .catch(() => showToast("PDF export failed. Try again."));
}

/* ─────────────────────────────────────────────────────────────────
   WHATSAPP SHARE
───────────────────────────────────────────────────────────────── */
function shareWhatsApp() {
  const sales    = formatINR(state.lastSales);
  const expenses = formatINR(state.lastExpenses);
  const net      = formatINR(state.lastSales - state.lastExpenses);
  
  let dateFormatted;
  if (state.selectedDate) {
    const parts = state.selectedDate.split("-").map(Number);
    if (parts.length === 3 && !parts.some(isNaN)) {
      dateFormatted = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long" }).format(new Date(parts[0], parts[1] - 1, parts[2]));
    }
  }
  if (!dateFormatted) {
    dateFormatted = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long" }).format(new Date());
  }

  const text = [
    `📊 *VaaniOS Daily Report — ${dateFormatted}*`,
    ``,
    `✅ Sales:    ${sales}`,
    `🔴 Expenses: ${expenses}`,
    `💰 Net Flow: ${net}`,
    ``,
    `_Sent via VaaniOS Voice Business Assistant_`
  ].join("\n");

  const url = `https://wa.me/?text=${encodeURIComponent(text)}`;
  window.open(url, "_blank", "noopener,noreferrer");
}

/* ─────────────────────────────────────────────────────────────────
   PLAY REPLY
───────────────────────────────────────────────────────────────── */
function playReply() {
  const audio = el("replyAudio");
  if (!audio.src) return;
  audio.play().catch(() => showToast("Couldn't play the reply audio. Check the audio URL and browser permissions."));
}

/* ─────────────────────────────────────────────────────────────────
   PROMPT CHIPS
───────────────────────────────────────────────────────────────── */
function connectPromptChips() {
  document.querySelectorAll("[data-prompt]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const prompt = btn.dataset.prompt;
      try {
        await navigator.clipboard.writeText(prompt);
        showToast("Example phrase copied! Read it aloud after starting the microphone.");
      } catch {
        showToast(`Try saying: ${prompt}`);
      }
    });
  });
}

/* ─────────────────────────────────────────────────────────────────
   NAVIGATION
───────────────────────────────────────────────────────────────── */
function connectNavigation() {
  document.querySelectorAll(".nav-link").forEach((link) => {
    link.addEventListener("click", () => {
      document.querySelectorAll(".nav-link").forEach((l) => l.classList.remove("active"));
      link.classList.add("active");
    });
  });
}

/* ─────────────────────────────────────────────────────────────────
   INIT
───────────────────────────────────────────────────────────────── */
function init() {
  // 1. Initialize Theme (from localStorage)
  applyTheme(state.theme);
  const themeToggle = el("themeToggleBtn");
  if (themeToggle) {
    themeToggle.addEventListener("click", toggleTheme);
  }

  // 2. Render Lucide icons
  if (window.lucide) lucide.createIcons({ attrs: { class: "lucide" } });

  // 3. Set today's date & date picker listener
  formatToday();
  const datePicker = el("datePicker");
  if (datePicker) {
    datePicker.addEventListener("change", handleDateChange);
  }
  clearActionPreview();

  // 4. Wire mic & action buttons
  el("micButton").addEventListener("click", handleMicClick);
  el("mainVoiceButton").addEventListener("click", handleMicClick);
  el("refreshButton").addEventListener("click", () => loadDashboard(state.selectedDate));
  el("playReplyButton").addEventListener("click", playReply);
  el("confirmAction").addEventListener("click", () => confirmAction(true));
  el("cancelAction").addEventListener("click", () => confirmAction(false));

  // 5. PDF + WhatsApp buttons
  el("pdfButton").addEventListener("click", downloadPDF);
  el("waButton").addEventListener("click", shareWhatsApp);

  // 6. Activity + view-all
  el("clearActivityButton").addEventListener("click", () => {
    el("activityList").replaceChildren();
    addActivity("Activity log cleared", "New session events will appear here.", "info");
  });
  el("viewAllButton").addEventListener("click", () =>
    el("voice-activity").scrollIntoView({ behavior: "smooth" })
  );

  // 7. Prompt chips + navigation
  connectPromptChips();
  connectNavigation();

  // 8. Weekly chart
  initWeeklyChart();

  // 9. Load live data from backend
  loadDashboard(state.selectedDate);
}

document.addEventListener("DOMContentLoaded", init);
