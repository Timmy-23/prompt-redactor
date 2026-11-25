// Front end for the local redactor. Talks only to the local Flask server.
const $ = (id) => document.getElementById(id);
const $$ = (sel) => [...document.querySelectorAll(sel)];

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

// Placeholder names produced by detector/transform.py (TAG_NAMES). Used only to flag
// placeholders the AI rewrote (e.g. "Person 2") so they can't be swapped back.
const FUZZY_PLACEHOLDER = String.raw`\[?\b(?:PERSON|EMAIL|PHONE|SIN|CARD|POSTAL[ _]?CODE|ADDRESS|ACCOUNT[ _]?ID|PLACE|REDACTED)[ _-]?\d+\b\]?`;

let state = { text: "", dets: [], mapping: {}, method: "", outText: "", restoredText: "" };

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
const escRe = (k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
// Whole values only, longest first (same rule as detector/transform.py), so a fake
// "Emily" inside "emily.clark@example.com" is not matched on its own.
function valuesPattern(keys) {
  return [...keys].sort((a, b) => b.length - a.length)
    .map((k) => (/^\w/.test(k) ? "(?<![\\w@.])" : "") + escRe(k) + (/\w$/.test(k) ? "(?![\\w@])" : "")).join("|");
}

function show(id, on = true) { $(id).classList.toggle("hidden", !on); }

// --- step slider ------------------------------------------------------------
const track = document.querySelector(".track");
const viewport = document.querySelector(".viewport");
const panels = [...track.children];
const steps = $$(".stepper button");
const ink = document.querySelector(".stepper .ink");
const workspace = document.querySelector(".workspace");
let cur = 0, reached = 0;   // reached = furthest step that has valid content

function fit() { viewport.style.height = panels[cur].offsetHeight + "px"; }
panels.forEach((p) => new ResizeObserver(fit).observe(p));
addEventListener("resize", fit);

function go(k) {
  if (k < 0 || k > reached) return;           // later steps stay locked until reached
  cur = k;
  track.style.transform = `translateX(-${cur * 100}%)`;
  ink.style.transform = `translateX(${cur * 100}%)`;
  panels.forEach((p, j) => { p.inert = j !== cur; });   // keep Tab inside the visible step
  steps.forEach((s, j) => {
    s.classList.toggle("on", j === cur);
    s.classList.toggle("done", j < cur);
    s.classList.toggle("locked", j > reached);
    s.setAttribute("aria-selected", j === cur);
    s.setAttribute("aria-disabled", j > reached);
    s.tabIndex = j > reached ? -1 : 0;
  });
  fit();
  if (workspace.getBoundingClientRect().top < 0) workspace.scrollIntoView({ behavior: "smooth", block: "start" });
}
function advance(k) { reached = Math.max(reached, k); go(k); }
function lockAfter(k) { reached = Math.min(reached, k); if (cur > reached) go(reached); else go(cur); }

function resetAfter(step) {
  if (step <= 1) lockAfter(0);
  if (step <= 2) {
    if (step === 2) lockAfter(1);
    state.mapping = {}; state.outText = ""; state.restoredText = "";
  }
}

// --- 1. check ---------------------------------------------------------------
async function check() {
  const text = $("input").value;
  if (!text.trim()) { $("input").focus(); return; }
  const btn = $("btn-check"), label = btn.textContent;
  btn.disabled = true; btn.textContent = "Checking…";
  try {
    const { detections } = await post("/api/analyze", {
      text, mode: $("mode").value, threshold: parseFloat($("threshold").value),
    });
    state = { ...state, text, dets: detections.map((d) => ({ ...d, on: true })) };
    resetAfter(2);
    renderReview();
    if (!window.STUDY) document.body.classList.add("compact");   // fold the hero away after first use
    advance(1);
    setTimeout(() => workspace.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  } catch (e) {
    alert("Check failed: " + e.message);
  } finally {
    btn.disabled = false; btn.textContent = label;
  }
}

// --- 2. review --------------------------------------------------------------
function renderReview() {
  const { text, dets } = state;
  const active = dets.filter((d) => d.on);
  const banner = $("banner");
  if (dets.length === 0) {
    banner.className = "alert ok";
    banner.textContent = "✓ No personal information detected. Still read it over before you share it.";
  } else {
    const types = [...new Set(dets.map((d) => LABELS[d.entity] || d.entity))].join(", ");
    const people = new Set(active.filter((d) => d.entity === "PERSON").map((d) => d.text.toLowerCase())).size;
    banner.className = "alert warn";
    banner.textContent = `⚠ ${dets.length} item${dets.length > 1 ? "s" : ""} of personal information found (${types}). `
      + `${active.length} will be replaced` + (people ? `, involving ${people} ${people === 1 ? "name" : "different names"}.` : ".");
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
    <li><label>
      <input type="checkbox" data-i="${i}" ${d.on ? "checked" : ""} aria-label="Protect ${esc(d.text)}">
      <span class="sw" style="background:var(--${d.entity})"></span>
      <div><div class="v">${esc(d.text)}</div>
      <div class="m">${esc(LABELS[d.entity] || d.entity)} · ${d.source === "user" ? "added by you" : esc(d.source.replace("Recognizer", "")) + " · " + d.score}</div></div>
    </label></li>`).join("");
}

function toggle(i) {
  state.dets[i].on = !state.dets[i].on;
  resetAfter(2);
  renderReview();
}

// adding a missed item by selecting text
let pending = null;
function offsetOf(node, off) {
  const el = node.nodeType === 3 ? node.parentElement : node;
  if (!el || el.dataset.start === undefined) return null;   // selection ended on a tag label or container
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

// --- 3. transform -----------------------------------------------------------
async function doRedact() {
  const checked = document.querySelector('input[name="method"]:checked');
  if (!checked) { alert("Please choose a method first."); return; }
  const method = checked.value;
  const btn = $("btn-redact"), label = btn.textContent;
  btn.disabled = true;
  try {
    const { text, mapping } = await post("/api/transform", { text: state.text, detections: state.dets.filter((d) => d.on), method });
    Object.assign(state, { mapping, method, outText: text, restoredText: "" });
  } catch (e) {
    alert("Could not create the safer prompt: " + e.message); return;
  } finally {
    btn.disabled = false; btn.textContent = label;
  }

  // Output with the replacements highlighted.
  const keys = method === "redact" ? ["[REDACTED]"] : Object.keys(state.mapping);
  const cls = method === "redact" ? "rd" : "ph";
  $("output").innerHTML = keys.length
    ? state.outText.split(new RegExp(`(${valuesPattern(keys)})`, "g")).map((part, i) => (i % 2 ? `<span class="${cls}">${esc(part)}</span>` : esc(part))).join("")
    : esc(state.outText);

  $("method-note").textContent = {
    pseudonymize: "Personal details were replaced with typed placeholders like [PERSON_1]. The same person or value always gets the same placeholder. The key stays in this tab so you can restore the AI's answer.",
    redact: "Personal details were replaced with [REDACTED]. The AI won't see what kind of data each item was or who is who, and the real details can't be put back into its answer.",
    surrogate: "Personal details were replaced with realistic fake values. None of them belong to a real person (reserved example.com emails, 555-01xx phone numbers, never-issued SINs, test card numbers).",
  }[method];

  const rows = Object.entries(state.mapping).filter(([k]) => k.includes(" ") || !Object.keys(state.mapping).some((o) => o !== k && o.includes(" ") && o.split(" ").includes(k)));
  $("mapping").innerHTML = "<tr><th>Sent to the AI</th><th>Real value</th></tr>"
    + rows.map(([k, v]) => `<tr><td><span class="ph">${esc(k)}</span></td><td>${esc(v)}</td></tr>`).join("");
  const restorable = method !== "redact" && rows.length > 0;
  show("key-wrap", restorable);
  $("out-grid").classList.toggle("single", !restorable);
  show("btn-to-restore", restorable);
  show("restore-on", restorable); show("restore-off", !restorable);

  $("reply").value = ""; renderRestored();
  advance(2);
}

async function copyText(text, toastId) {
  try { await navigator.clipboard.writeText(text); }
  catch {
    const t = document.createElement("textarea"); t.value = text; document.body.appendChild(t);
    t.select(); document.execCommand("copy"); t.remove();
  }
  if (toastId) { $(toastId).classList.add("on"); setTimeout(() => $(toastId).classList.remove("on"), 1500); }
}

// --- 4. restore -------------------------------------------------------------
function renderRestored() {
  const reply = $("reply").value;
  const status = $("restore-status");
  if (!reply.trim()) {
    state.restoredText = "";
    $("restored").innerHTML = '<span class="muted">Restored reply appears here</span>';
    show("restore-status", false); return;
  }
  const keys = Object.keys(state.mapping);
  const lower = Object.fromEntries(keys.map((k) => [k.toLowerCase(), state.mapping[k]]));   // "[person_1]" still restores
  const parts = [];
  if (keys.length) parts.push(`(${valuesPattern(keys)})`);
  if (state.method === "pseudonymize") parts.push(`(${FUZZY_PLACEHOLDER})`);
  let html = "", plain = "", last = 0, ok = 0, bad = 0;
  if (parts.length) {
    for (const m of reply.matchAll(new RegExp(parts.join("|"), "gi"))) {
      const before = reply.slice(last, m.index);
      html += esc(before); plain += before;
      const real = state.mapping[m[0]] ?? lower[m[0].toLowerCase()];
      if (real !== undefined) { html += `<span class="rest">${esc(real)}</span>`; plain += real; ok++; }
      else { html += `<span class="miss" title="Couldn't restore: the AI changed this placeholder">${esc(m[0])}</span>`; plain += m[0]; bad++; }
      last = m.index + m[0].length;
    }
  }
  html += esc(reply.slice(last)); plain += reply.slice(last);
  state.restoredText = plain;
  $("restored").innerHTML = html;

  show("restore-status");
  status.className = "status " + (bad ? "bad" : "good");
  status.textContent = bad
    ? `⚠ ${bad} placeholder${bad > 1 ? "s" : ""} couldn't be restored because the AI changed ${bad > 1 ? "them" : "it"}. Fix the highlighted part by hand.`
    : ok ? `✓ ${ok} item${ok === 1 ? "" : "s"} restored. Check the result before using it.`
         : "Nothing to restore was found in this reply. If the AI changed the placeholders or fake values, they can't be swapped back.";
}

function startOver() {
  $("input").value = "";
  state = { text: "", dets: [], mapping: {}, method: "", outText: "", restoredText: "" };
  reached = 0; go(0);
  $("input").focus({ preventScroll: true });
}

// --- wiring -----------------------------------------------------------------
$("btn-check").addEventListener("click", check);
$("btn-sample").addEventListener("click", () => { $("input").value = SAMPLE; resetAfter(1); });
$("input").addEventListener("input", () => resetAfter(1));
$$('input[name="method"]').forEach((r) => r.addEventListener("change", () => resetAfter(2)));
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
$("btn-copy").addEventListener("click", () => copyText(state.outText, "copied"));
$("btn-to-restore").addEventListener("click", () => advance(3));
$("reply").addEventListener("input", renderRestored);
$("btn-copy-restored").addEventListener("click", () => copyText(state.restoredText || $("reply").value));
$("btn-restart").addEventListener("click", startOver);
$$("[data-prev]").forEach((b) => b.addEventListener("click", () => go(cur - 1)));
steps.forEach((s, k) => s.addEventListener("click", () => go(k)));
$("brand").addEventListener("click", () => { document.body.classList.remove("compact"); scrollTo({ top: 0, behavior: "smooth" }); });

// theme toggle (choice remembered in this browser only)
$("theme").addEventListener("click", () => {
  const root = document.documentElement;
  root.dataset.theme = root.dataset.theme === "light" ? "dark" : "light";
  try { localStorage.setItem("pr-theme", root.dataset.theme); } catch (e) { /* storage blocked: theme just isn't remembered */ }
});

// hero slideshow
(() => {
  const slides = $$(".slide"), dots = $$(".dots button"), name = $("slide-name");
  if (!slides.length) return;
  const names = ["Original prompt", "Pseudonymized", "Fully redacted"];
  let i = 0, timer;
  const showSlide = (k) => {
    i = k;
    slides.forEach((s, j) => s.classList.toggle("on", j === k));
    dots.forEach((d, j) => d.classList.toggle("on", j === k));
    name.textContent = names[k];
  };
  const auto = () => { clearInterval(timer); timer = setInterval(() => showSlide((i + 1) % slides.length), 3800); };
  dots.forEach((d, k) => d.addEventListener("click", () => { showSlide(k); auto(); }));
  auto();
})();

// fade sections in as they scroll into view
(() => {
  const els = $$(".reveal");
  if (!("IntersectionObserver" in window)) { els.forEach((el) => el.classList.add("in")); return; }
  const io = new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }), { threshold: 0.12 });
  els.forEach((el) => io.observe(el));
})();

go(0);


// --- study mode (python app.py --study) ---------------------------------------
// Records counts, timings and choices only. The protected prompt is sent once so
// the server can count which known details are still visible; it is not stored.
if (window.STUDY) {
  const S = { task: null, t0: 0, tCheck: 0, tCreate: 0, checks: 0, copied: false, restore: false };
  $("btn-sample").classList.add("hidden");
  document.querySelector(".advanced").classList.add("hidden");
  document.querySelector(".extra").classList.add("hidden");

  async function loadTasks() {
    const pid = $("study-pid").value.trim() || "P01";
    const res = await fetch(`/api/study/tasks?participant=${encodeURIComponent(pid)}`);
    S.tasks = (await res.json()).tasks;
    const current = $("study-task").value;
    $("study-task").innerHTML = S.tasks.map((t) => `<option value="${t.id}">${t.id}: ${esc(t.title)}</option>`).join("");
    if (current) $("study-task").value = current;
  }
  $("study-pid").addEventListener("change", loadTasks);
  loadTasks();

  $("study-load").addEventListener("click", async () => {
    await loadTasks();
    const t = S.tasks.find((x) => x.id === $("study-task").value);
    Object.assign(S, { task: t, t0: performance.now(), tCheck: 0, tCreate: 0, checks: 0, copied: false, restore: false });
    $("input").value = t.prompt;
    state = { text: "", dets: [], mapping: {}, method: "", outText: "", restoredText: "" };
    $("reply").value = "";
    reached = 0; go(0);
    let instr = t.instructions;
    $$('input[name="method"]').forEach((r) => {
      const locked = t.method !== "choice" && r.value !== t.method;
      r.disabled = locked;
      r.closest(".mcard").classList.toggle("locked", locked);
      if (t.method !== "choice" && r.value === t.method) r.checked = true;
    });
    if (t.method === "choice") {
      $$('input[name="method"]').forEach((r) => (r.checked = false));
    } else {
      instr += ` For this task, use ${t.method === "redact" ? "Fully redact" : "Pseudonymize"}.`;
    }
    $("study-instr").textContent = instr;
    show("study-instr"); show("study-finish"); show("study-saved", false);
    $("study-done").disabled = false;
    workspace.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  $("btn-check").addEventListener("click", () => { S.checks += 1; S.tCheck = performance.now(); }, true);
  $("btn-redact").addEventListener("click", () => {
    if (document.querySelector('input[name="method"]:checked')) S.tCreate = performance.now();
  }, true);
  $("btn-copy").addEventListener("click", () => { S.copied = true; });
  $("reply").addEventListener("input", () => { if ($("reply").value.trim()) S.restore = true; });

  $("study-done").addEventListener("click", async () => {
    if (!S.task) return;
    const dets = state.dets || [];
    const body = {
      participant: $("study-pid").value.trim(), task: S.task.id,
      method_used: state.outText ? state.method : "none",
      seconds_total: (performance.now() - S.t0) / 1000,
      seconds_review: S.tCheck && S.tCreate ? (S.tCreate - S.tCheck) / 1000 : 0,
      checks: S.checks,
      n_detected: dets.filter((d) => d.source !== "user").length,
      n_unticked: dets.filter((d) => !d.on).length,
      n_added: dets.filter((d) => d.source === "user").length,
      added_types: dets.filter((d) => d.source === "user").map((d) => d.entity),
      final_text: state.outText || $("input").value,
      copied: S.copied, restore_used: S.restore,
    };
    await post("/api/study/record", body);
    $("study-done").disabled = true;
    show("study-saved");
    S.task = null;
  });
}
