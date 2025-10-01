// ---------- Elements ----------
const form = document.getElementById('filmForm');
const msgDiv = document.getElementById('msg');
const progressSection = document.getElementById('progressSection');
const progressInner = document.getElementById('progressInner');
const progressText = document.getElementById('progressText');
const resultsDiv = document.getElementById('results');
const savePdfBtn = document.getElementById('savePdfBtn');

// Keep last result for PDF (so HTML == PDF)
let latestResult = null;

// ---------- Helpers ----------
function getPayloadFromForm() {
  const data = Object.fromEntries(new FormData(form));
  data.currency = form.currency.value;
  data.support_needed = Array.from(
    form.querySelectorAll('input[name="support_needed"]:checked')
  ).map(cb => cb.value);
  return data;
}

/* Make “Type/Support” human-readable in HTML (handles dicts/lists/strings) */
function formatSupport(s) {
  try {
    if (!s) return '';
    if (typeof s === 'string') return s;
    if (Array.isArray(s)) {
      return s.map(x => typeof x === 'object'
        ? [x.type, x.topic].filter(Boolean).join(' — ')
        : String(x)
      ).join('; ');
    }
    if (typeof s === 'object') {
      return [s.type, s.topic].filter(Boolean).join(' — ') || JSON.stringify(s);
    }
    return String(s);
  } catch { return String(s || ''); }
}

function renderResults(result) {
  // 1) LLM summary
  let summaryHtml = '';
  if (result.llm_summary) {
    summaryHtml = `
      <div class="ai-summary-box fade-in">
        <h3>AI Recommendation</h3>
        ${result.llm_summary.replace(/\n/g, '<br>')}
      </div>`;
  }

  // 2) Results table (colgroup mirrors PDF proportions)
  let tableHtml = '';
  if (Array.isArray(result.recommended_funds) && result.recommended_funds.length) {
    tableHtml = `
      <div class="results-table-box fade-in">
        <table>
          <colgroup>
            <col style="width: 4.5%;">   <!-- # -->
            <col style="width: 18%;">    <!-- Fund Name -->
            <col style="width: 18%;">    <!-- Organization -->
            <col style="width: 24%;">    <!-- Type/Support -->
            <col style="width: 12%;">    <!-- Location -->
            <col style="width: 10%;">    <!-- Status -->
            <col style="width: 10.5%;">  <!-- Amount -->
            <col style="width: 3%;">     <!-- Link -->
          </colgroup>
          <thead>
            <tr>
                <th>#</th>
                <th>Fund Name</th>
                <th>Organization</th>
                <th>Type / Support</th>
                <th>Location</th>
                <th>Status</th>
                <th>Amount</th>
                <th>Link</th>
            </tr>
          </thead>
          <tbody>
            ${result.recommended_funds.map((fund, i) => `
              <tr>
                <td>${i + 1}</td>
                <td>${fund.fund_name || ''}</td>
                <td>${fund.organization || ''}</td>
                <td>${formatSupport(fund.support_type_and_topic)}</td>
                <td>${fund.location || ''}</td>
                <td>${fund.status || ''}</td>
                <td>${(fund.amount && String(fund.amount).trim() !== '') ? fund.amount : 'N/A'}</td>
                <td>${fund.link ? `<a href="${fund.link}" target="_blank" aria-label="Open fund page">↗</a>` : ''}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>`;
  }

  resultsDiv.innerHTML = (summaryHtml || tableHtml)
    ? `<div class="results-flex">${summaryHtml}${tableHtml}</div>`
    : "<div class='error fade-in'>No results to display.</div>";

  savePdfBtn.style.display = (summaryHtml || tableHtml) ? 'block' : 'none';
}

// ---------- Submit handler: gets content from Python (/submit) ----------
form.onsubmit = async (e) => {
  e.preventDefault();
  msgDiv.textContent = '';
  msgDiv.className = '';
  resultsDiv.innerHTML = '';
  savePdfBtn.style.display = 'none';

  // progress UI
  progressSection.style.display = 'flex';
  progressInner.style.width = '0';
  progressText.textContent = 'Processing...';
  let progress = 0;
  const interval = setInterval(() => {
    progress = Math.min(99, progress + Math.random() * 4.3);
    progressInner.style.width = progress + '%';
    progressText.textContent = 'Matching: ' + Math.round(progress) + '%';
  }, 170);

  try {
    const payload = getPayloadFromForm();
    const res = await fetch('/submit', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });

    clearInterval(interval);
    progressInner.style.width = '100%';
    progressText.textContent = 'Done!';
    setTimeout(() => progressSection.style.display = 'none', 750);

    const result = await res.json();
    if (!res.ok) {
      msgDiv.textContent = result.error || 'Submission failed!';
      msgDiv.className = 'error fade-in';
      return;
    }

    latestResult = result; // keep what we showed on screen

    msgDiv.textContent = '✅ Successfully submitted!';
    msgDiv.className = 'success fade-in';
    renderResults(result);

  } catch (err) {
    clearInterval(interval);
    progressInner.style.width = '100%';
    progressText.textContent = 'Error';
    setTimeout(() => progressSection.style.display = 'none', 950);
    msgDiv.textContent = 'Server error!';
    msgDiv.className = 'error fade-in';
  }
};

// ---------- PDF button: asks Python to generate the PDF (/export_pdf) ----------
savePdfBtn.onclick = async () => {
  const payload = getPayloadFromForm();
  if (latestResult) {
    payload.llm_summary = latestResult.llm_summary || '';
    payload.recommended_funds = latestResult.recommended_funds || [];
  }

  try {
    const res = await fetch('/export_pdf', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      alert(`Could not generate PDF. ${errText || 'Check server logs.'}`);
      return;
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'funding_results.pdf';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error(e);
    alert('Network error while generating PDF.');
  }
};
