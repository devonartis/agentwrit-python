/* MedAssist AI — Interactive AgentAuth Demo */

function syncPatientInput() {
    const sel = document.getElementById('patient-select');
    const inp = document.getElementById('patient-input');
    if (sel.value) inp.value = sel.value;
}

function getPatientId() {
    const inp = document.getElementById('patient-input');
    const sel = document.getElementById('patient-select');
    return inp.value.trim() || sel.value || '';
}

function setRequest(text) {
    document.getElementById('request-input').value = text;
}

function setPatientAndRequest(pid, text) {
    document.getElementById('patient-input').value = pid;
    document.getElementById('patient-select').value = '';
    document.getElementById('request-input').value = text;
}

async function submitRequest() {
    const patientId = getPatientId();
    const requestText = document.getElementById('request-input').value.trim();
    const btn = document.getElementById('submit-btn');

    if (!patientId || !requestText) return;

    // Reset UI
    document.getElementById('trace-container').innerHTML = '';
    document.getElementById('agents-container').innerHTML = '';
    updateFinalAnswerPanel('');
    btn.disabled = true;
    btn.textContent = 'Processing...';

    // Show loading
    addTraceStep({step_type: 'loading', label: 'Sending request to LLM...', detail: {}, status: 'info'});

    try {
        const resp = await fetch('/api/request', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({patient_id: patientId, request: requestText}),
        });

        const data = await resp.json();

        // Clear loading
        document.getElementById('trace-container').innerHTML = '';

        let lastLlmContent = '';
        if (data.trace) {
            for (const step of data.trace) {
                if (step.step_type === 'llm_response' && step.detail && step.detail.content) {
                    lastLlmContent = step.detail.content;
                }
                addTraceStep(step);
                if (step.step_type === 'agent_created') {
                    addAgentCard(step.detail);
                }
            }
        }
        updateFinalAnswerPanel(lastLlmContent);
    } catch (err) {
        document.getElementById('trace-container').innerHTML = '';
        addTraceStep({
            step_type: 'error',
            label: 'Request failed: ' + err.message,
            detail: {error: err.message},
            status: 'error',
        });
    } finally {
        btn.disabled = false;
        btn.textContent = 'Submit';
    }
}

function addTraceStep(step) {
    const container = document.getElementById('trace-container');
    const el = document.createElement('div');
    el.className = 'trace-step trace-' + step.status;

    const icon = {
        success: '\u2705', denied: '\u26D4', error: '\u274C',
        warning: '\u26A0\uFE0F', info: '\u2139\uFE0F',
    }[step.status] || '\u25CF';

    let body = '';
    const d = step.detail || {};

    switch (step.step_type) {
        case 'agent_created':
            body = `<div class="trace-detail">
                <div class="trace-field"><span class="trace-key">SPIFFE ID</span><span class="trace-val spiffe">${d.spiffe_id || ''}</span></div>
                <div class="trace-field"><span class="trace-key">Task</span><span class="trace-val">${d.task_id || ''}</span></div>
                <div class="trace-field"><span class="trace-key">Trigger</span><span class="trace-val">${d.trigger || ''}</span></div>
                <div class="trace-field"><span class="trace-key">TTL</span><span class="trace-val">${d.expires_in || ''}s</span></div>
                <div class="trace-field"><span class="trace-key">Token</span><span class="trace-val mono">${d.token_preview || ''}</span></div>
                <div class="trace-field"><span class="trace-key">Scopes</span><div class="scope-list">${(d.scope || []).map(s => '<span class="scope-tag ' + scopeCat(s) + '">' + s + '</span>').join('')}</div></div>
                <div class="trace-field"><span class="trace-key">Tools</span><span class="trace-val">${(d.tools || []).join(', ')}</span></div>
            </div>`;
            break;

        case 'token_validated':
            body = `<div class="trace-detail">
                <div class="trace-field"><span class="trace-key">SUB</span><span class="trace-val spiffe">${d.sub || ''}</span></div>
                <div class="trace-field"><span class="trace-key">JTI</span><span class="trace-val mono">${d.jti || ''}</span></div>
                <div class="trace-field"><span class="trace-key">Scope</span><div class="scope-list">${(d.scope || []).map(s => '<span class="scope-tag ' + scopeCat(s) + '">' + s + '</span>').join('')}</div></div>
            </div>`;
            break;

        case 'tool_call':
            body = `<div class="trace-detail">
                <div class="trace-field"><span class="trace-key">Tool</span><span class="trace-val">${d.tool || ''}</span></div>
                <div class="trace-field"><span class="trace-key">Patient</span><span class="trace-val">${d.patient_id || ''}</span></div>
                <div class="trace-field"><span class="trace-key">Required</span><div class="scope-list">${(d.required_scope || []).map(s => '<span class="scope-tag scope-ok">' + s + '</span>').join('')}</div></div>
                <div class="trace-field"><span class="trace-key">Agent</span><span class="trace-val mono">${truncate(d.agent_id || '', 60)}</span></div>
                <div class="trace-output"><pre>${JSON.stringify(d.output || {}, null, 2).substring(0, 500)}</pre></div>
            </div>`;
            break;

        case 'scope_denied':
            body = `<div class="trace-detail">
                <div class="trace-field"><span class="trace-key">Tool</span><span class="trace-val">${d.tool || ''}</span></div>
                <div class="trace-field"><span class="trace-key">Patient</span><span class="trace-val">${d.patient_id || ''}</span></div>
                <div class="trace-field"><span class="trace-key">Required</span><div class="scope-list">${(d.required_scope || []).map(s => '<span class="scope-tag scope-bad">' + s + '</span>').join('')}</div></div>
                <div class="trace-field"><span class="trace-key">Held</span><div class="scope-list">${(d.held_scope || []).map(s => '<span class="scope-tag ' + scopeCat(s) + '">' + s + '</span>').join('')}</div></div>
                <div class="trace-field"><span class="trace-key">Agent</span><span class="trace-val mono">${truncate(d.agent_id || '', 60)}</span></div>
                <div class="trace-reason">${d.reason || ''}</div>
            </div>`;
            break;

        case 'delegation':
            body = `<div class="trace-detail">
                <div class="trace-field"><span class="trace-key">From</span><span class="trace-val spiffe">${truncate(d.delegator_id || '', 60)}</span></div>
                <div class="trace-field"><span class="trace-key">To</span><span class="trace-val spiffe">${truncate(d.delegate_id || '', 60)}</span></div>
                <div class="trace-field"><span class="trace-key">Scope</span><div class="scope-list">${(d.delegated_scope || []).map(s => '<span class="scope-tag scope-deleg">' + s + '</span>').join('')}</div></div>
                <div class="trace-field"><span class="trace-key">TTL</span><span class="trace-val">${d.expires_in || ''}s</span></div>
            </div>`;
            break;

        case 'token_renewed':
            body = `<div class="trace-detail">
                <div class="trace-field"><span class="trace-key">Old</span><span class="trace-val mono">${d.old_preview || ''} (now dead)</span></div>
                <div class="trace-field"><span class="trace-key">New</span><span class="trace-val mono">${d.new_preview || ''}</span></div>
                <div class="trace-field"><span class="trace-key">TTL</span><span class="trace-val">${d.new_expires_in || ''}s</span></div>
            </div>`;
            break;

        case 'llm_response':
            body = `<div class="trace-detail"><div class="llm-prose llm-prose-inline"></div></div>`;
            break;

        case 'patient_lookup':
            if (!d.found) {
                body = `<div class="trace-detail"><div class="trace-field"><span class="trace-key">Known patients</span><span class="trace-val">${(d.known_patients || []).join(', ')}</span></div></div>`;
            }
            break;

        case 'routing':
            body = `<div class="trace-detail">
                <div class="trace-field"><span class="trace-key">Categories</span><span class="trace-val">${(d.categories || []).join(', ')}</span></div>
            </div>`;
            break;

        default:
            if (d.error) body = `<div class="trace-detail"><div class="trace-reason">${escapeHtml(d.error)}</div></div>`;
            else if (d.message) body = `<div class="trace-detail"><span class="trace-val">${escapeHtml(d.message)}</span></div>`;
            break;
    }

    el.innerHTML = `
        <div class="trace-header">
            <span class="trace-icon">${icon}</span>
            <span class="trace-type">${step.step_type}</span>
            <span class="trace-label">${step.label}</span>
        </div>
        ${body}
    `;

    if (step.step_type === 'llm_response') {
        const prose = el.querySelector('.llm-prose-inline');
        if (prose) {
            prose.innerHTML = renderMarkdown(d.content || '');
        }
    }

    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
}

function addAgentCard(d) {
    const container = document.getElementById('agents-container');
    const empty = container.querySelector('.empty-state');
    if (empty) empty.remove();

    const cat = d.category || 'unknown';
    const card = document.createElement('div');
    card.className = 'agent-card agent-' + cat;
    card.innerHTML = `
        <div class="agent-header">
            <span class="agent-cat">${cat.toUpperCase()}</span>
            <span class="agent-ttl">${d.expires_in || '?'}s</span>
        </div>
        <div class="agent-body">
            <div class="agent-field"><span class="agent-key">SPIFFE</span><span class="agent-val spiffe">${d.spiffe_id || ''}</span></div>
            <div class="agent-field"><span class="agent-key">Task</span><span class="agent-val">${d.task_id || ''}</span></div>
            <div class="agent-field"><span class="agent-key">Token</span><span class="agent-val mono">${d.token_preview || ''}</span></div>
            <div class="agent-scopes">${(d.scope || []).map(s => '<span class="scope-tag ' + scopeCat(s) + '">' + s + '</span>').join('')}</div>
        </div>
    `;
    container.appendChild(card);
}

function scopeCat(scope) {
    if (scope.match(/records|labs/)) return 'scope-clinical';
    if (scope.match(/prescriptions|formulary/)) return 'scope-rx';
    if (scope.match(/billing|insurance/)) return 'scope-billing';
    return '';
}

function truncate(s, n) { return s.length > n ? s.substring(0, n) + '...' : s; }
function escapeHtml(t) { const d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML; }

/** Turn model markdown into safe HTML (bold, lists, headings). */
function renderMarkdown(text) {
    if (!text) return '';
    let html = '';
    if (typeof marked !== 'undefined' && typeof marked.parse === 'function') {
        try {
            html = marked.parse(text, { async: false, breaks: true, gfm: true });
        } catch (_e) {
            html = escapeHtml(text).replace(/\n/g, '<br>');
        }
    } else {
        html = escapeHtml(text).replace(/\n/g, '<br>');
    }
    if (typeof DOMPurify !== 'undefined' && typeof DOMPurify.sanitize === 'function') {
        // Drop inline styles — model HTML can include position:absolute etc., which
        // caused overlapping “garbled” text in some browsers.
        return DOMPurify.sanitize(html, {
            USE_PROFILES: { html: true },
            FORBID_ATTR: ['style'],
        });
    }
    return html;
}

function updateFinalAnswerPanel(markdownText) {
    const section = document.getElementById('llm-answer-section');
    const panel = document.getElementById('llm-final-answer');
    if (!section || !panel) return;
    if (!markdownText || !markdownText.trim()) {
        section.classList.add('hidden');
        panel.innerHTML = '';
        return;
    }
    panel.innerHTML = renderMarkdown(markdownText);
    section.classList.remove('hidden');
    section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function filterAudit() {
    const type = document.getElementById('audit-filter-type')?.value;
    document.querySelectorAll('.audit-row').forEach(row => {
        if (!type) { row.style.display = ''; return; }
        const badge = row.querySelector('.event-type-badge');
        row.style.display = (badge && badge.textContent.trim() === type) ? '' : 'none';
    });
}
