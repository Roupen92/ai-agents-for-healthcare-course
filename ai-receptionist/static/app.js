// Polls the dashboard API every 3 seconds. No WebSockets on purpose —
// this is a teaching project, and polling is a much shorter lesson than
// explaining a persistent connection.

let selectedCallSid = null;

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");
  });
});

function statusLabel(status) {
  return status.replace("_", " ");
}

async function refreshStats() {
  const r = await fetch("/api/stats");
  const s = await r.json();
  document.getElementById("stat-total").textContent = s.total_calls;
  document.getElementById("stat-active").textContent = s.active_calls;
  document.getElementById("stat-emergency").textContent = s.emergency_calls;
  document.getElementById("stat-appts").textContent = s.appointments_captured;
}

async function refreshCallList() {
  const r = await fetch("/api/calls");
  const calls = await r.json();
  const list = document.getElementById("call-list");
  list.innerHTML = "";
  if (calls.length === 0) {
    list.innerHTML = '<li class="empty">No calls yet. Run test_local.py or call the Twilio number.</li>';
    return;
  }
  for (const c of calls) {
    const li = document.createElement("li");
    li.dataset.callSid = c.call_sid;
    if (c.call_sid === selectedCallSid) li.classList.add("selected");
    li.innerHTML = `<span class="call-status ${c.status}">${statusLabel(c.status)}</span>${c.call_sid}
      <span class="preview">${c.preview || "(no messages yet)"}</span>`;
    li.addEventListener("click", () => {
      selectedCallSid = c.call_sid;
      refreshCallList();
      refreshTranscript();
    });
    list.appendChild(li);
  }
}

async function refreshTranscript() {
  const title = document.getElementById("transcript-title");
  const hint = document.getElementById("transcript-hint");
  const box = document.getElementById("transcript-messages");
  if (!selectedCallSid) {
    title.textContent = "Transcript";
    hint.style.display = "block";
    box.innerHTML = "";
    return;
  }
  hint.style.display = "none";
  const r = await fetch(`/api/calls/${selectedCallSid}/transcript`);
  const data = await r.json();
  title.textContent = `Transcript — ${selectedCallSid} (${statusLabel(data.status)})`;
  box.innerHTML = "";
  for (const m of data.messages) {
    const div = document.createElement("div");
    div.className = `msg ${m.role}`;
    div.innerHTML = `<span class="role">${m.role}</span>${m.content}`;
    box.appendChild(div);
  }
}

async function refreshScheduler() {
  const r = await fetch("/api/appointments");
  const appts = await r.json();
  const rows = document.getElementById("appt-rows");
  rows.innerHTML = "";
  for (const a of appts) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${a.intent}</td><td>${a.caller_name || "—"}</td>
      <td>${a.callback_number || "—"}</td><td>${a.requested_time || "—"}</td>
      <td>${a.reason || "—"}</td><td>${new Date(a.updated_at).toLocaleTimeString()}</td>`;
    rows.appendChild(tr);
  }
}

async function tick() {
  await Promise.all([refreshStats(), refreshCallList(), refreshTranscript(), refreshScheduler()]);
}

tick();
setInterval(tick, 3000);
