const state = { demo: null, result: null };

const $ = (selector) => document.querySelector(selector);
const formatTime = (value) => String(value).slice(0, 5);
const percent = (value) => `${Math.round(value * 100)}%`;
const averageCapacity = (slot) => {
  const values = Object.values(slot.capacity);
  return values.reduce((sum, value) => sum + value, 0) / values.length;
};
const escapeHtml = (value) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2600);
}

function bindRange(inputId, outputId, formatter) {
  const input = $(inputId);
  const output = $(outputId);
  const update = () => { output.value = formatter(Number(input.value)); };
  input.addEventListener("input", update);
  update();
}

async function loadDemo() {
  const response = await fetch("/api/demo");
  if (!response.ok) throw new Error("Could not load the demo scenario.");
  state.demo = await response.json();
  hydrateInputs();
  renderTasks();
  renderFixedSchedule();
}

function hydrateInputs() {
  const { user, signals, target_date: targetDate } = state.demo;
  $("#greeting").textContent = `Good morning, ${user.name}.`;
  $("#target-date").textContent = targetDate
    ? new Date(`${targetDate}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" })
    : "Today";
  $("#sleep-input").value = signals.sleep_hours;
  $("#energy-input").value = signals.energy;
  $("#focus-input").value = signals.focus;
  $("#creative-input").value = signals.creativity;
  ["sleep", "energy", "focus", "creative"].forEach((name) => {
    $("#" + name + "-input").dispatchEvent(new Event("input"));
  });
}

function renderTasks() {
  const tasks = state.demo.tasks;
  $("#task-count").textContent = `${tasks.length} tasks`;
  $("#tasks-placed").textContent = `0 / ${tasks.length}`;
  $("#task-list").innerHTML = tasks.map((task, index) => `
    <div class="task-item">
      <span class="task-index">${String(index + 1).padStart(2, "0")}</span>
      <div>
        <strong>${escapeHtml(task.title)}</strong>
        <small>${task.duration_minutes} min · Priority ${task.priority}</small>
      </div>
      <span class="priority-dots" aria-label="Priority ${task.priority}">
        ${[1, 2, 3, 4, 5].map((level) => `<i class="${level <= task.priority ? "active" : ""}"></i>`).join("")}
      </span>
    </div>
  `).join("");
}

function renderFixedSchedule() {
  $("#schedule-list").innerHTML = state.demo.calendar
    .slice()
    .sort((a, b) => a.start.localeCompare(b.start))
    .map((block) => scheduleRow(block.start, block.end, block.title, block.category, null, true))
    .join("");
}

function scheduleRow(start, end, title, category, fit, fixed = false) {
  return `
    <div class="schedule-item ${fixed ? "fixed" : ""}">
      <span class="schedule-time">${formatTime(start)}</span>
      <span class="schedule-color ${escapeHtml(category)}"></span>
      <div>
        <strong>${escapeHtml(title)}</strong>
        <small>${formatTime(start)}–${formatTime(end)} · ${fixed ? "Fixed calendar" : escapeHtml(category.replaceAll("_", " "))}</small>
      </div>
      ${fit == null ? '<span class="fit-badge">Fixed</span>' : `<span class="fit-badge">${percent(fit)} fit</span>`}
    </div>
  `;
}

function buildRequest() {
  return {
    ...state.demo,
    signals: {
      ...state.demo.signals,
      sleep_hours: Number($("#sleep-input").value),
      energy: Number($("#energy-input").value),
      focus: Number($("#focus-input").value),
      creativity: Number($("#creative-input").value),
    },
  };
}

async function optimize() {
  const button = $("#run-button");
  button.disabled = true;
  button.querySelector("span").textContent = "Running agents…";
  try {
    const response = await fetch("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildRequest()),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Optimization failed.");
    }
    state.result = await response.json();
    renderResult();
    showToast("Cognitive plan ready for your review.");
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "Optimize again";
  }
}

function renderResult() {
  const result = state.result;
  renderMetrics(result.forecast);
  renderForecast(result.forecast);
  renderSchedule(result);
  renderTrace(result);
  $("#coach-summary").textContent = result.coach_summary;
  $("#tasks-placed").textContent = `${result.schedule.recommendations.length} / ${state.demo.tasks.length}`;
  const fit = result.schedule.recommendations.reduce((sum, item) => sum + item.fit_score, 0)
    / Math.max(result.schedule.recommendations.length, 1);
  $("#average-fit").textContent = percent(fit);
  $("#review-confidence").textContent = `${percent(result.evaluation.confidence)} review confidence`;
}

function renderMetrics(forecast) {
  const peak = forecast.slice().sort((a, b) => averageCapacity(b) - averageCapacity(a))[0];
  ["executive", "attention", "creative", "social"].forEach((dimension) => {
    const value = peak.capacity[dimension];
    $("#metric-" + dimension).textContent = percent(value);
    $("#ring-" + dimension).style.setProperty("--value", `${value * 360}deg`);
  });
  const peakSlots = forecast.filter((slot) => slot.label === "peak");
  $("#peak-window").textContent = peakSlots.length
    ? `${formatTime(peakSlots[0].start)}–${formatTime(peakSlots.at(-1).end)}`
    : `${formatTime(peak.start)}–${formatTime(peak.end)}`;
}

function renderForecast(forecast) {
  $("#forecast-chart").innerHTML = forecast.map((slot, index) => {
    const value = averageCapacity(slot);
    const label = index % 2 === 0 ? formatTime(slot.start) : "";
    return `
      <div class="chart-column ${slot.label}" title="${formatTime(slot.start)} · ${percent(value)} average capacity">
        <div class="chart-bar-wrap"><div class="chart-bar" style="height:${Math.max(8, value * 100)}%"></div></div>
        <span class="chart-label">${label}</span>
      </div>
    `;
  }).join("");
}

function renderSchedule(result) {
  const flexible = result.schedule.recommendations.map((item) => ({ ...item, fixed: false }));
  const fixed = state.demo.calendar.map((item) => ({ ...item, fit_score: null, fixed: true }));
  $("#schedule-list").innerHTML = [...fixed, ...flexible]
    .sort((a, b) => a.start.localeCompare(b.start))
    .map((item) => scheduleRow(item.start, item.end, item.title, item.category, item.fit_score, item.fixed))
    .join("");

  const recovery = result.schedule.recovery_suggestions;
  $("#recovery-note").classList.toggle("hidden", !recovery.length);
  $("#recovery-note").textContent = recovery.length ? `Recovery note · ${recovery[0]}` : "";
  $("#approval-bar").classList.remove("hidden");
  updateApprovalStatus(result.status);
}

function renderTrace(result) {
  $("#trace-list").innerHTML = result.trace.map((step, index) => `
    <article class="trace-step">
      <span class="trace-number">STEP ${String(index + 1).padStart(2, "0")}</span>
      <h4>${escapeHtml(step.agent)}</h4>
      <p>${escapeHtml(step.summary)}</p>
      <small>${step.duration_ms} ms · ${escapeHtml(step.status)}</small>
    </article>
  `).join("");
}

function updateApprovalStatus(status) {
  const chip = $("#approval-status");
  chip.className = "pending-chip";
  if (status === "approved") {
    chip.textContent = "Approved locally";
    chip.classList.add("approved");
  } else if (status === "rejected") {
    chip.textContent = "Proposal rejected";
    chip.classList.add("rejected");
  } else {
    chip.textContent = "Approval required";
  }
}

async function decide(decision) {
  if (!state.result) return;
  const response = await fetch(`/api/runs/${state.result.run_id}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
  if (!response.ok) {
    showToast("Could not record the decision.");
    return;
  }
  state.result = await response.json();
  updateApprovalStatus(state.result.status);
  showToast(decision === "approve" ? "Plan approved locally. No external calendar was changed." : "Proposal rejected. Your calendar is unchanged.");
}

document.addEventListener("DOMContentLoaded", async () => {
  bindRange("#sleep-input", "#sleep-output", (value) => `${value.toFixed(1)} h`);
  bindRange("#energy-input", "#energy-output", percent);
  bindRange("#focus-input", "#focus-output", percent);
  bindRange("#creative-input", "#creative-output", percent);
  $("#run-button").addEventListener("click", optimize);
  $("#approve-button").addEventListener("click", () => decide("approve"));
  $("#reject-button").addEventListener("click", () => decide("reject"));
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((nav) => nav.classList.remove("active"));
      item.classList.add("active");
    });
  });
  try {
    await loadDemo();
  } catch (error) {
    showToast(error.message);
  }
});
