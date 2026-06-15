// main.js — NeuroScan Edge Frontend (Production Build)
// Handles: Command Center, Queue, Dossier, Landing

// ─── Helpers ──────────────────────────────────────────────────────────
function timeAgo(iso) {
    if (!iso) return '--';
    const diff = Date.now() - new Date(iso).getTime();
    const s = Math.floor(diff / 1000);
    if (s < 60) return s + 's ago';
    const m = Math.floor(s / 60);
    if (m < 60) return m + 'm ago';
    const h = Math.floor(m / 60);
    if (h < 24) return h + 'h ago';
    return Math.floor(h / 24) + 'd ago';
}

function urgencyColors(u) {
    const up = (u || '').toUpperCase();
    if (up.includes('HIGH') || up.includes('CRITICAL'))
        return { bg: 'bg-error/20', border: 'border-error/50', text: 'text-error', bar: 'bg-error', icon: 'emergency', pulse: 'critical-pulse' };
    if (up.includes('MEDIUM'))
        return { bg: 'bg-secondary-container/20', border: 'border-secondary-container/50', text: 'text-secondary', bar: 'bg-secondary', icon: 'psychology', pulse: '' };
    return { bg: 'bg-white/5', border: 'border-white/10', text: 'text-on-surface-variant', bar: 'bg-primary-fixed-dim/40', icon: 'person', pulse: '' };
}

function urgencyLabel(u) {
    const up = (u || '').toUpperCase();
    if (up.includes('HIGH')) return 'CRITICAL';
    if (up.includes('MEDIUM')) return 'PRIORITY';
    return 'ROUTINE';
}

function setEl(id, val) {
    const e = document.getElementById(id);
    if (e) e.textContent = val || 'N/A';
}

// ─── Command Center: Upload ──────────────────────────────────────────
async function uploadXRay(file) {
    const formData = new FormData();
    formData.append('file', file);

    // Append patient metadata if user provided it
    const ageInput = document.getElementById('input-age');
    const genderInput = document.getElementById('input-gender');
    const viewInput = document.getElementById('input-view');
    if (ageInput && ageInput.value) formData.append('age', ageInput.value);
    if (genderInput && genderInput.value) formData.append('gender', genderInput.value);
    if (viewInput && viewInput.value) formData.append('view_position', viewInput.value);

    const btn = document.getElementById('upload-btn');
    if (btn) {
        btn.innerHTML = '<span class="material-symbols-outlined animate-spin">sync</span> ANALYZING...';
        btn.classList.add('opacity-50', 'pointer-events-none');
    }

    const startTime = performance.now();

    try {
        const res = await fetch('/api/analyze', { method: 'POST', body: formData });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || res.statusText);
        }
        const data = await res.json();
        const elapsed = Math.round(performance.now() - startTime);

        updateCommandCenterUI(data, elapsed);

        // Persist for dossier page
        try { localStorage.setItem('lastScanData', JSON.stringify(data)); } catch(_) {}
        window.lastScanData = data;

    } catch (e) {
        console.error('Upload error:', e);
        alert('Analysis failed: ' + e.message);
    } finally {
        if (btn) {
            btn.innerHTML = '<span class="material-symbols-outlined">upload</span> UPLOAD X-RAY';
            btn.classList.remove('opacity-50', 'pointer-events-none');
        }
    }
}

// ─── Command Center: UI Update ───────────────────────────────────────
function updateCommandCenterUI(d, elapsedMs) {
    // Images
    const orig = document.getElementById('original-image');
    if (orig) orig.src = d.original_base64;
    const heat = document.getElementById('heatmap-image');
    if (heat) { heat.src = d.heatmap_base64; heat.style.display = 'block'; }
    const simGrad = document.getElementById('simulated-gradient');
    if (simGrad) simGrad.style.display = 'none';

    // Patient Profile
    setEl('patient-id', d.patient_id || d.filename);
    setEl('patient-age', d.age ? d.age + ' yrs' : null);
    setEl('patient-gender', d.gender === 'M' ? 'Male' : d.gender === 'F' ? 'Female' : d.gender);
    setEl('patient-view', d.view_position);

    // Risk Score + SVG ring
    const rs = document.getElementById('risk-score');
    const riskPct = Math.min(Math.round(d.risk_score || 0), 100);
    if (rs) rs.textContent = riskPct + '%';
    const ring = document.getElementById('risk-ring');
    if (ring) {
        const offset = (351.85 * (1 - riskPct / 100)).toFixed(1);
        ring.setAttribute('stroke-dashoffset', offset);
        // Color the ring based on risk
        if (riskPct >= 60) ring.setAttribute('stroke', '#ffb4ab'); // error color
        else if (riskPct >= 30) ring.setAttribute('stroke', '#b3c5ff'); // secondary
        else ring.setAttribute('stroke', '#00f2ff'); // primary
    }

    // Urgency badge
    const urg = document.getElementById('urgency-level');
    if (urg) {
        urg.textContent = d.urgency;
        urg.className = 'mt-6 px-8 py-2 rounded-full font-status-sm text-status-sm uppercase tracking-[0.3em]';
        const up = (d.urgency || '').toUpperCase();
        if (up.includes('HIGH')) urg.classList.add('bg-error-container', 'text-on-error-container', 'pulse-red');
        else if (up.includes('MEDIUM')) urg.classList.add('bg-primary-container', 'text-on-primary-container');
        else urg.classList.add('bg-on-surface-variant/20', 'text-on-surface-variant');
    }

    // Findings
    const fc = document.getElementById('findings-container');
    if (fc && d.selected_scores) {
        fc.innerHTML = '';
        if (d.selected_scores.length === 0) {
            fc.innerHTML = '<div class="glass-panel p-5 rounded-xl border-l-4 border-primary-container/50 floating-module"><div class="flex items-start justify-between mb-2"><span class="font-data-label text-data-label text-on-surface-variant uppercase">No Significant Findings</span></div><div class="font-headline-lg text-[22px] text-primary">Clear</div></div>';
        } else {
            d.selected_scores.forEach(item => {
                const name = item[0], conf = (item[1] * 100).toFixed(1);
                const clr = conf > 80 ? 'error' : (conf > 50 ? 'primary-container' : 'on-surface-variant');
                fc.insertAdjacentHTML('beforeend', `
                <div class="glass-panel p-5 rounded-xl border-l-4 border-${clr}/50 floating-module">
                    <div class="flex items-start justify-between mb-2">
                        <span class="font-data-label text-data-label text-on-surface-variant uppercase">${name}</span>
                    </div>
                    <div class="flex items-end justify-between">
                        <span class="font-headline-lg text-[22px] text-on-surface">${conf}%</span>
                        <div class="w-1/2 h-1 bg-white/10 rounded-full overflow-hidden">
                            <div class="h-full bg-${clr}" style="width:${conf}%"></div>
                        </div>
                    </div>
                </div>`);
            });
        }
    }

    // Reasoning flow conclusion
    const topConf = d.top_score ? (d.top_score * 100).toFixed(1) : '0';
    setEl('reasoning-conclusion', `Conclusion: ${d.top_finding} (${topConf}% confidence)`);

    // Data readout overlay
    const readout = document.getElementById('data-readout');
    if (readout) {
        readout.innerHTML = `SCAN: ${d.scan_id || '--'}<br>FINDING: ${d.top_finding}<br>RISK: ${riskPct}%`;
    }

    // HUD latency
    const hud = document.getElementById('hud-latency');
    if (hud && elapsedMs) hud.textContent = `LATENCY: ${elapsedMs}MS`;
}

// ─── Queue Page ──────────────────────────────────────────────────────
async function loadQueue() {
    const list = document.getElementById('queue-list');
    if (!list) return;

    try {
        const res = await fetch('/api/queue');
        if (!res.ok) throw new Error('Failed to load queue');
        const data = await res.json();

        setEl('critical-count', data.critical_count || 0);
        setEl('priority-count', data.priority_count || 0);
        setEl('routine-count', data.routine_count || 0);

        list.innerHTML = '';
        if (!data.scans || data.scans.length === 0) {
            list.innerHTML = `<div class="glass-panel rounded-xl p-8 text-center text-on-surface-variant font-data-label text-data-label">
                No scans in queue yet. Upload X-rays from the <a href="/command_center" class="text-primary-container underline hover:brightness-125">Command Center</a>.
            </div>`;
            return;
        }

        data.scans.forEach(s => {
            const uc = urgencyColors(s.urgency);
            const label = urgencyLabel(s.urgency);
            const conf = s.top_score ? (s.top_score * 100).toFixed(1) : '0.0';
            list.insertAdjacentHTML('beforeend', `
            <div class="glass-panel rounded-xl p-1 ${uc.pulse} group transition-transform duration-300 hover:scale-[1.01] cursor-pointer" onclick="window.location.href='/dossier?scan_id=${s.scan_id}'">
                <div class="bg-surface-container/20 rounded-[10px] p-5 grid grid-cols-12 items-center gap-4">
                    <div class="col-span-4 flex items-center gap-4">
                        <div class="w-12 h-12 rounded-lg ${uc.bg} border ${uc.border} flex items-center justify-center">
                            <span class="material-symbols-outlined ${uc.text}" style="font-variation-settings: 'FILL' 1;">${uc.icon}</span>
                        </div>
                        <div>
                            <h3 class="font-headline-lg text-[18px] text-on-surface tracking-wide">${s.patient_id || s.filename}</h3>
                            <p class="font-data-label text-[10px] text-on-surface-variant">ID: ${s.scan_id} &bull; ${s.top_finding}</p>
                        </div>
                    </div>
                    <div class="col-span-3">
                        <div class="flex flex-col items-center gap-2">
                            <div class="w-full bg-white/5 h-2 rounded-full overflow-hidden border border-white/10">
                                <div class="h-full ${uc.bar}" style="width:${conf}%"></div>
                            </div>
                            <span class="font-data-label text-[10px] ${uc.text}">${conf}% ${s.top_finding}</span>
                        </div>
                    </div>
                    <div class="col-span-2 flex justify-center">
                        <span class="px-3 py-1 rounded-full ${uc.bg} border ${uc.border} ${uc.text} font-data-label text-[10px] uppercase tracking-widest">${label}</span>
                    </div>
                    <div class="col-span-2 text-center">
                        <p class="font-data-label text-[14px] text-on-surface-variant">${timeAgo(s.timestamp)}</p>
                    </div>
                    <div class="col-span-1 flex justify-end">
                        <span class="w-10 h-10 rounded-full border border-white/10 flex items-center justify-center hover:bg-primary-container hover:text-on-primary transition-all">
                            <span class="material-symbols-outlined text-[20px]">open_in_new</span>
                        </span>
                    </div>
                </div>
            </div>`);
        });
    } catch (e) {
        console.error('Queue load error:', e);
        list.innerHTML = '<div class="glass-panel rounded-xl p-8 text-center text-error font-data-label">Failed to load queue data.</div>';
    }
}

// ─── Dossier Page ────────────────────────────────────────────────────
async function loadDossier() {
    const caseIdEl = document.getElementById('dossier-case-id');
    if (!caseIdEl) return;

    const params = new URLSearchParams(window.location.search);
    const scanId = params.get('scan_id');
    let data = null;

    if (scanId) {
        try {
            const res = await fetch(`/api/scan/${scanId}`);
            if (res.ok) data = await res.json();
        } catch (_) {}
    }

    if (!data) {
        try { data = JSON.parse(localStorage.getItem('lastScanData')); } catch(_) {}
    }

    if (!data) {
        caseIdEl.textContent = 'NO SCAN DATA — Upload from Command Center';
        return;
    }

    // Populate fields
    setEl('dossier-case-id', 'CASE ID: ' + (data.scan_id || data.patient_id || '--'));
    setEl('dossier-patient-name', data.patient_id || data.filename || '--');
    setEl('dossier-patient-age', data.age ? `Age: ${data.age}` : 'Age: N/A');
    setEl('dossier-patient-gender', data.gender === 'M' ? 'Male' : data.gender === 'F' ? 'Female' : (data.gender || 'N/A'));
    setEl('dossier-top-finding', data.top_finding || '--');

    // Status badge
    const status = document.getElementById('dossier-status');
    if (status) {
        const up = (data.urgency || '').toUpperCase();
        status.textContent = data.urgency || '--';
        status.className = 'font-data-label text-data-label';
        if (up.includes('HIGH')) status.classList.add('text-error');
        else if (up.includes('MEDIUM')) status.classList.add('text-secondary');
        else status.classList.add('text-primary-container');
    }

    // Risk gauge
    const riskVal = Math.round(data.risk_score || 0);
    setEl('dossier-risk-gauge', riskVal);
    const ring = document.getElementById('dossier-risk-ring');
    if (ring) {
        const pct = Math.min(riskVal, 100) / 100;
        ring.setAttribute('stroke-dashoffset', (440 * (1 - pct)).toFixed(1));
    }

    // Images
    const origImg = document.getElementById('dossier-original-img');
    if (origImg && data.original_base64) origImg.src = data.original_base64;
    const heatImg = document.getElementById('dossier-heatmap-img');
    if (heatImg && data.heatmap_base64) heatImg.src = data.heatmap_base64;

    // Findings
    const fc = document.getElementById('dossier-findings');
    if (fc && data.selected_scores) {
        fc.innerHTML = '';
        if (data.selected_scores.length === 0) {
            fc.innerHTML = '<div class="flex gap-4"><div class="flex-none w-10 h-10 rounded-full bg-primary-container/20 flex items-center justify-center"><span class="material-symbols-outlined text-primary-container">check_circle</span></div><div><div class="font-data-label text-data-label text-primary-container mb-1">NO SIGNIFICANT FINDINGS</div><p class="text-on-surface-variant text-body-md">The AI analysis did not detect any pathological findings above the confidence threshold.</p></div></div>';
        } else {
            data.selected_scores.forEach((item, i) => {
                const name = item[0], conf = (item[1] * 100).toFixed(1);
                const colors = ['primary-container', 'tertiary-container', 'error', 'secondary'];
                const clr = colors[i % colors.length];
                fc.insertAdjacentHTML('beforeend', `
                <div class="flex gap-4">
                    <div class="flex-none w-10 h-10 rounded-full bg-${clr}/20 flex items-center justify-center">
                        <span class="material-symbols-outlined text-${clr}">psychology</span>
                    </div>
                    <div>
                        <div class="font-data-label text-data-label text-${clr} mb-1">FINDING ${String(i+1).padStart(2,'0')}: ${name.toUpperCase()}</div>
                        <p class="text-on-surface-variant text-body-md">AI detected ${name} with ${conf}% confidence.</p>
                    </div>
                </div>`);
            });
        }
    }

    // Risk bars
    const barsContainer = document.getElementById('dossier-risk-bars');
    if (barsContainer && data.selected_scores) {
        barsContainer.innerHTML = '';
        if (data.selected_scores.length === 0) {
            barsContainer.innerHTML = '<div class="text-on-surface-variant font-data-label text-data-label opacity-60">No risk factors detected.</div>';
        } else {
            data.selected_scores.forEach(item => {
                const name = item[0], conf = (item[1] * 100).toFixed(1);
                const clr = conf > 60 ? 'error' : (conf > 30 ? 'tertiary-container' : 'primary-container');
                barsContainer.insertAdjacentHTML('beforeend', `
                <div class="space-y-2">
                    <div class="flex justify-between font-data-label text-data-label">
                        <span>${name.toUpperCase()}</span>
                        <span class="text-${clr}">${conf}%</span>
                    </div>
                    <div class="h-1 bg-surface-container-highest rounded-full overflow-hidden">
                        <div class="h-full bg-${clr}" style="width:${conf}%"></div>
                    </div>
                </div>`);
            });
        }
    }

    // Reason log
    const reasonEl = document.getElementById('dossier-reason');
    if (reasonEl) reasonEl.textContent = data.reason || 'No risk factors identified.';

    // Timestamp
    setEl('dossier-timestamp', data.timestamp ? 'Generated: ' + new Date(data.timestamp).toLocaleString() : '');
}

// ─── Page Router ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Upload handler (command center)
    const uploadInput = document.getElementById('xray-upload-input');
    if (uploadInput) {
        uploadInput.addEventListener('change', e => {
            if (e.target.files[0]) uploadXRay(e.target.files[0]);
        });
    }

    // Queue page auto-load
    if (document.getElementById('queue-list')) loadQueue();

    // Dossier page auto-load
    if (document.getElementById('dossier-case-id')) loadDossier();
});
