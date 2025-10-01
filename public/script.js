// public/script.js

// ---------- Config: dynamic API base ----------
// In production your app is mounted at /predictions; in dev it's at /.
const APP_PREFIX = "/predictions";
const onPredictionsPath =
  window.location.pathname === APP_PREFIX ||
  window.location.pathname.startsWith(`${APP_PREFIX}/`);
const API_BASE = onPredictionsPath ? `${APP_PREFIX}/api` : "/api";

// ---------- DOM ----------
const form = document.getElementById("filmForm");
const resultsDiv = document.getElementById("results");
const msg = document.getElementById("msg");
const savePdfBtn = document.getElementById("savePdfBtn");
const progressSection = document.getElementById("progressSection");
const progressInner = document.getElementById("progressInner");
const progressText = document.getElementById("progressText");

let lastResponse = null;

// ---------- UI helpers ----------
function setProgress(p, text) {
  progressSection.style.display = "block";
  progressInner.style.width = `${p}%`;
  progressText.textContent = text || "";
}

function showError(e) {
  const text =
    (e && e.message) ||
    (typeof e === "string" ? e : "Something went wrong. Please try again.");
  msg.textContent = text;
}

// Defensive JSON parser: if server returns HTML (e.g., index.html), show snippet
async function parseJsonOrThrow(resp) {
  const ct = resp.headers.get("content-type") || "";
  const raw = await resp.text();
  if (!ct.includes("application/json")) {
    const snippet = raw.slice(0, 200);
    throw new Error(
      `Non-JSON from server (status ${resp.status}). First 200 chars:\n${snippet}`
    );
  }
  try {
    return JSON.parse(raw);
  } catch {
    throw new Error("Server returned invalid JSON.");
  }
}

// ---------- Form data ----------
function buildPayloadFromForm() {
  const data = new FormData(form);

  // Validate amount early on the client
  const amtStr = data.get("amount_requested");
  const amt = Number(amtStr);
  if (!Number.isFinite(amt) || amt < 0) {
    throw new Error("Please enter a valid non-negative budget amount.");
  }

  const support = Array.from(
    document.querySelectorAll('input[name="support_needed"]:checked')
  ).map((cb) => cb.value);

  return {
    project_title: data.get("project_title"),
    project_location: data.get("project_location"),
    project_type: data.get("project_type"),
    project_desc: data.get("project_desc"),
    project_stage: data.get("project_stage"),
    currency: data.get("currency"),
    amount_requested: amt,
    support_needed: support,
  };
}

// ---------- Event: Submit (recommendations) ----------
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.textContent = "";
  resultsDiv.innerHTML = "";
  savePdfBtn.style.display = "none";
  setProgress(8, "Preparing…");

  let payload;
  try {
    payload = buildPayloadFromForm();
  } catch (err) {
    showError(err);
    progressSection.style.display = "none";
    return;
  }

  try {
    setProgress(25, "Matching funds…");
    const r = await fetch(`${API_BASE}/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const j = await parseJsonOrThrow(r);
    if (!r.ok) throw new Error(j.error || "Failed to fetch recommendations.");
    lastResponse = j;

    // Render results
    const list = j.recommended_funds || [];
    let html = `<div class="summary"><h3>AI Recommendation</h3><p>${(j.llm_summary || "")
      .replace(/\n/g, "<br/>")}</p></div>`;

    html += `<table class="results"><thead><tr>
              <th>#</th><th>Fund</th><th>Organization</th><th>Type / Support</th>
              <th>Location</th><th>Status</th><th>Amount</th><th>Link</th></tr></thead><tbody>`;

    list.forEach((f, i) => {
      html += `<tr>
        <td>${i + 1}</td>
        <td>${f.fund_name || ""}</td>
        <td>${f.organization || ""}</td>
        <td>${f.support_type_and_topic || ""}</td>
        <td>${f.location || ""}</td>
        <td>${f.status || ""}</td>
        <td>${f.amount || "N/A"}</td>
        <td>${f.link ? `<a href="${f.link}" target="_blank" rel="noopener">Open</a>` : ""}</td>
      </tr>`;
    });
    html += `</tbody></table>`;
    resultsDiv.innerHTML = html;

    setProgress(90, "Ready");
    savePdfBtn.style.display = "inline-block";
  } catch (err) {
    console.error(err);
    showError(err);
    setProgress(100, "Error");
  } finally {
    setTimeout(() => (progressSection.style.display = "none"), 800);
  }
});

// ---------- Event: Save PDF ----------
savePdfBtn.addEventListener("click", async () => {
  if (!lastResponse) return;

  let payload;
  try {
    payload = buildPayloadFromForm();
  } catch (err) {
    showError(err);
    return;
  }
  payload.recommended_funds = lastResponse.recommended_funds || [];
  payload.llm_summary = lastResponse.llm_summary || "";

  try {
    const r = await fetch(`${API_BASE}/export_pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    // Expect a PDF; if not, surface the HTML/text
    const ct = r.headers.get("content-type") || "";
    if (!r.ok) {
      const raw = await r.text().catch(() => "");
      throw new Error(
        raw || `PDF export failed (status ${r.status}). Please try again.`
      );
    }
    if (!ct.includes("application/pdf")) {
      const raw = await r.text().catch(() => "");
      throw new Error(
        `Server did not return a PDF. First 200 chars:\n${raw.slice(0, 200)}`
      );
    }

    const blob = await r.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "funding_results.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  } catch (e) {
    console.error(e);
    showError(e);
  }
});
