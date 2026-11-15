// Front end for the local redactor. Talks only to the local Flask server.
const $ = (id) => document.getElementById(id);

const LABELS = {
  PERSON: "Name", EMAIL_ADDRESS: "Email", PHONE_NUMBER: "Phone", CA_SIN: "SIN",
  CREDIT_CARD: "Card number", CA_POSTAL_CODE: "Postal code", STREET_ADDRESS: "Street address",
  ACCOUNT_ID: "Account / record ID", LOCATION: "City / place", OTHER: "Other sensitive detail",
};

const SAMPLE = `Hi, can you help me write a polite follow-up email to this customer and sort the records below by postal code?

Customer: Sarah Thompson (customer CUST-104882)
Email: sarah.thompson@example.com   Phone: (519) 824-4120
Address: 50 Stone Rd E, Guelph ON N1G 2W1
SIN on file: 130 692 544   Card used: 4532 0151 1283 0366

Other records:
- Daniel Okafor, d.okafor@example.org, 226-979-3311, 88 King St W, Kitchener ON N2G 1A1, CUST-118230
- Priya Raman, priya.r@example.com, +1 416 340 2211, 12 Elm Crescent, Toronto ON M4W 1N4, CUST-120511

Order 4471 shipped on March 2 for $129.99. Remind Sarah Thompson that returns close in 30 days.`;

let state = { text: "", dets: [], mapping: {} };

async function post(url, body) {
  const res = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json()).error || res.statusText);
  return res.json();
}

function esc(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function show(id, on = true) { $(id).classList.toggle("hidden", !on); }

function resetAfter(step) {
  if (step <= 1) show("step-review", false);
  if (step <= 2) { show("step-output", false); show("step-restore", false); state.mapping = {}; }
}

async function check() {
  const text = $("input").value;
  if (!text.trim()) return;
  const btn = $("btn-check");
  btn.disabled = true; btn.textContent = "Checking…";
  try {
    const { detections } = await post("/api/analyze", {
      text, mode: $("mode").value, threshold: parseFloat($("threshold").value),
    });
    state = { text, dets: detections.map((d) => ({ ...d, on: true })), mapping: {} };
    resetAfter(2);
    renderReview();
    show("step-review");
    $("step-review").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    alert("Check failed: " + e.message);
  } finally {
    btn.disabled = false; btn.textContent = "Check for personal information";
  }
}

function renderReview() {
  const { text, dets } = state;
  const active = dets.filter((d) => d.on).length;
  const banner = $("banner");
  if (dets.length === 0) {
    banner.className = "banner ok";
    banner.textContent = "No personal information detected. Still read it over before you share it.";
  } else {
    const types = [...new Set(dets.map((d) => LABELS[d.entity] || d.entity))].join(", ");
    banner.className = "banner warn";
    banner.textContent = `Warning: ${dets.length} item${dets.length > 1 ? "s" : ""} of personal information found (${types}). ${active} will be replaced.`;
  }

  // Highlighted text. Every text node sits in an element with data-start so a
  // selection can be mapped back to character offsets.
  let html = "", pos = 0;
  dets.forEach((d, i) => {
    if (d.start > pos) html += `<span data-start="${pos}">${esc(text.slice(pos, d.start))}</span>`;
    html += `<mark data-i="${i}" class="${d.on ? "" : "off"}" style="background:var(--${d.entity})" title="${esc(LABELS[d.entity] || d.entity)} · ${d.source} · score ${d.score}"><span data-start="${d.start}">${esc(text.slice(d.start, d.end))}</span><span class="tag">${esc(LABELS[d.entity] || d.entity)}</span></mark>`;
    pos = d.end;
  });
  if (pos < text.length) html += `<span data-start="${pos}">${esc(text.slice(pos))}</span>`;
  $("highlighted").innerHTML = html;

  $("det-list").innerHTML = dets.map((d, i) => `
    <li>
      <input type="checkbox" data-i="${i}" ${d.on ? "checked" : ""} aria-label="Redact ${esc(d.text)}">
      <span class="sw" style="background:var(--${d.entity})"></span>
      <div><div class="val">${esc(d.text)}</div>
      <div class="meta">${esc(LABELS[d.entity] || d.entity)} · ${d.source === "user" ? "added by you" : esc(d.source.replace("Recognizer", "")) + " · " + d.score}</div></div>
    </li>`).join("");
}

function toggle(i) {
  state.dets[i].on = !state.dets[i].on;
  resetAfter(2);
  renderReview();
}

// --- adding a missed item by selecting text --------------------------------
let pending = null;
function offsetOf(node, off) {
  let el = node.nodeType === 3 ? node.parentElement : node;
  if (!el || el.dataset.start === undefined) {
    // selection ended on a tag label or container; ignore
    return null;
  }
  return parseInt(el.dataset.start, 10) + (node.nodeType === 3 ? off : 0);
}
function onSelect() {
  const sel = window.getSelection();
  if (!sel.rangeCount || sel.isCollapsed || !$("highlighted").contains(sel.anchorNode)) return;
  const a = offsetOf(sel.anchorNode, sel.anchorOffset), b = offsetOf(sel.focusNode, sel.focusOffset);
  if (a === null || b === null) return;
  let start = Math.min(a, b), end = Math.max(a, b);
  while (start < end && /\s/.test(state.text[start])) start++;
  while (end > start && /\s/.test(state.text[end - 1])) end--;
  if (end <= start) return;
  pending = { start, end };
  $("sel-text").textContent = state.text.slice(start, end);
  show("add-bar");
}
function addPending() {
  if (!pending) return;
  const { start, end } = pending;
  state.dets = state.dets.filter((d) => d.end <= start || d.start >= end);
  state.dets.push({ entity: $("add-type").value, start, end, text: state.text.slice(start, end), score: 1, source: "user", on: true });
  state.dets.sort((x, y) => x.start - y.start);
  pending = null; show("add-bar", false); window.getSelection().removeAllRanges();
  resetAfter(2);
  renderReview();
}

// --- redact + restore -------------------------------------------------------
async function doRedact() {
  const chosen = state.dets.filter((d) => d.on);
  const method = document.querySelector('input[name="method"]:checked').value;
  const { text, mapping } = await post("/api/transform", { text: state.text, detections: chosen, method });
  state.mapping = mapping;
  $("output").value = text;
  $("method-note").textContent = {
    pseudonymize: "Personal details were replaced with typed placeholders like [PERSON_1]. The same person or value always gets the same placeholder.",
    redact: "Personal details were replaced with [REDACTED]. The AI won't see what kind of data each item was or who is who, and the real details can't be put back into its answer.",
    surrogate: "Personal details were replaced with realistic fake values. None of them belong to a real person (reserved example.com emails, 555-01xx phone numbers, never-issued SINs, test card numbers).",
  }[method];
  const rows = Object.entries(mapping).filter(([k, v]) => k.includes(" ") || !Object.keys(mapping).some((o) => o !== k && o.includes(" ") && o.split(" ").includes(k)));
  $("mapping").innerHTML = rows.length
    ? "<tr><th>Sent to the AI</th><th>Real value</th></tr>" + rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")
    : "<tr><td>Nothing to restore with full redaction.</td></tr>";
  $("reply").value = ""; $("restored").value = "";
  show("step-output"); show("step-restore", method !== "redact");
  $("step-output").scrollIntoView({ behavior: "smooth", block: "start" });
}

function restore() {
  // Same rule as detector/transform.py: longest first, and whole values only,
  // so a fake "Emily" inside "emily.clark@example.com" is not touched twice.
  const keys = Object.keys(state.mapping).sort((a, b) => b.length - a.length);
  if (!keys.length) { $("restored").value = $("reply").value; return; }
  const escRe = (k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(keys.map((k) => (/^\w/.test(k) ? "(?<![\\w@.])" : "") + escRe(k) + (/\w$/.test(k) ? "(?![\\w@])" : "")).join("|"), "g");
  $("restored").value = $("reply").value.replace(re, (m) => state.mapping[m] ?? m);
}

async function copyOut() {
  try { await navigator.clipboard.writeText($("output").value); }
  catch { $("output").select(); document.execCommand("copy"); }
  show("copied"); setTimeout(() => show("copied", false), 1500);
}

// --- wiring -----------------------------------------------------------------
$("btn-check").addEventListener("click", check);
$("btn-sample").addEventListener("click", () => { $("input").value = SAMPLE; resetAfter(1); });
$("input").addEventListener("input", () => resetAfter(1));
document.querySelectorAll('input[name="method"]').forEach((r) => r.addEventListener("change", () => resetAfter(2)));
$("threshold").addEventListener("input", (e) => { $("th-out").textContent = parseFloat(e.target.value).toFixed(2); });
$("highlighted").addEventListener("click", (e) => {
  const m = e.target.closest("mark");
  if (m && window.getSelection().isCollapsed) toggle(+m.dataset.i);
});
$("highlighted").addEventListener("mouseup", () => setTimeout(onSelect, 0));
$("det-list").addEventListener("change", (e) => { if (e.target.dataset.i) toggle(+e.target.dataset.i); });
$("btn-add").addEventListener("click", addPending);
$("btn-add-cancel").addEventListener("click", () => { pending = null; show("add-bar", false); });
$("btn-redact").addEventListener("click", doRedact);
$("btn-copy").addEventListener("click", copyOut);
$("reply").addEventListener("input", restore);


// --- study mode (python app.py --study) ---------------------------------------
// Records counts, timings and choices only. The protected prompt is sent once so
// the server can count which known details are still visible; it is not stored.
if (window.STUDY) {
  const S = { task: null, t0: 0, tCheck: 0, tCreate: 0, checks: 0, copied: false, restore: false };
  $("btn-sample").classList.add("hidden");
  document.querySelector(".advanced").classList.add("hidden");
  document.querySelector(".method .extra").classList.add("hidden");

  async function loadTasks() {
    const pid = $("study-pid").value.trim() || "P01";
    const res = await fetch(`/api/study/tasks?participant=${encodeURIComponent(pid)}`);
    S.tasks = (await res.json()).tasks;
    const cur = $("study-task").value;
    $("study-task").innerHTML = S.tasks.map((t) => `<option value="${t.id}">${t.id}: ${esc(t.title)}</option>`).join("");
    if (cur) $("study-task").value = cur;
  }
  $("study-pid").addEventListener("change", loadTasks);
  loadTasks();

  $("study-load").addEventListener("click", async () => {
    await loadTasks();
    const t = S.tasks.find((x) => x.id === $("study-task").value);
    Object.assign(S, { task: t, t0: performance.now(), tCheck: 0, tCreate: 0, checks: 0, copied: false, restore: false });
    $("input").value = t.prompt;
    resetAfter(1);
    let instr = t.instructions;
    document.querySelectorAll('input[name="method"]').forEach((r) => {
      const locked = t.method !== "choice" && r.value !== t.method;
      r.disabled = locked;
      r.closest(".opt").classList.toggle("locked", locked);
      if (t.method !== "choice" && r.value === t.method) r.checked = true;
    });
    if (t.method === "choice") {
      document.querySelectorAll('input[name="method"]').forEach((r) => (r.checked = false));
    } else {
      instr += ` For this task, use ${t.method === "redact" ? "Fully redact" : "Pseudonymize"}.`;
    }
    $("study-instr").textContent = instr;
    show("study-instr"); show("study-finish"); show("study-saved", false);
    $("study-done").disabled = false;
    $("step-input").scrollIntoView({ behavior: "smooth" });
  });

  $("btn-check").addEventListener("click", () => { S.checks += 1; S.tCheck = performance.now(); }, true);
  $("btn-redact").addEventListener("click", (e) => {
    if (!document.querySelector('input[name="method"]:checked')) {
      e.stopImmediatePropagation(); alert("Please choose a method first."); return;
    }
    S.tCreate = performance.now();
  }, true);
  $("btn-copy").addEventListener("click", () => { S.copied = true; });
  $("reply").addEventListener("input", () => { if ($("reply").value.trim()) S.restore = true; });

  $("study-done").addEventListener("click", async () => {
    if (!S.task) return;
    const method = document.querySelector('input[name="method"]:checked');
    const dets = state.dets || [];
    const body = {
      participant: $("study-pid").value.trim(), task: S.task.id,
      method_used: $("output").value ? (method ? method.value : "") : "none",
      seconds_total: (performance.now() - S.t0) / 1000,
      seconds_review: S.tCheck && S.tCreate ? (S.tCreate - S.tCheck) / 1000 : 0,
      checks: S.checks,
      n_detected: dets.filter((d) => d.source !== "user").length,
      n_unticked: dets.filter((d) => !d.on).length,
      n_added: dets.filter((d) => d.source === "user").length,
      added_types: dets.filter((d) => d.source === "user").map((d) => d.entity),
      final_text: $("output").value || $("input").value,
      copied: S.copied, restore_used: S.restore,
    };
    await post("/api/study/record", body);
    $("study-done").disabled = true;
    show("study-saved");
    S.task = null;
  });
}
