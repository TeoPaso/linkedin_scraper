import sys

with open('docs/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update loadDataFromFirestore
content = content.replace(
    'if (!appData) appData = { execution_id: "N/A", job_store: {}, search_memory: [], job_categories: [], config: {} };',
    'if (!appData) appData = { execution_id: "N/A", job_store: {}, search_memory: [], job_categories: [], config: {}, uiState: { page: 1, limit: 10, sortCol: "date", sortDir: "desc", filters: { date: "", keyword: "", category: "", score: "", liked: "" } } };'
)

# 2. Update getScoreHtml
old_score_html = '''        function getScoreHtml(score) {
            if (score === null || score === undefined) return `<span class="score-grey" style="font-size: 0.9em;">Da valutare</span>`;
            if (score >= 85) return `<span class="score-green" style="font-weight: bold; font-size: 1.1em;">⭐ ${score} (Tier A)</span>`;
            if (score >= 70) return `<span class="score-orange" style="font-weight: bold; color: #ffaa00;">✓ ${score} (Tier B)</span>`;
            if (score >= 50) return `<span class="score-red" style="color: #ffaaaa;">${score} (Tier C)</span>`;
            return `<span class="score-red" style="color: #ff4444; font-weight: bold;">❌ ${score} (Tier D)</span>`;
        }'''
new_score_html = '''        function getScoreHtml(score) {
            if (score === null || score === undefined) return `<span class="score-grey" style="font-size: 0.9em;">Da valutare</span>`;
            if (score >= 90) return `<span class="score-green" style="font-weight: bold; font-size: 1.1em; color: #ffd700; text-shadow: 0 0 5px rgba(255, 215, 0, 0.5);">🏆 ${score} (Golden)</span>`;
            if (score >= 75) return `<span class="score-green" style="font-weight: bold;">⭐ ${score} (Tier A)</span>`;
            if (score >= 50) return `<span class="score-orange" style="font-weight: bold; color: #ffaa00;">✓ ${score} (Tier B)</span>`;
            return `<span class="score-red" style="color: #ff4444; font-weight: bold;">❌ ${score} (Scartato)</span>`;
        }'''
content = content.replace(old_score_html, new_score_html)

# 3. renderJobStore
start_idx = content.find('        function renderJobStore() {')
end_idx = content.find('        function renderModal() {')
if start_idx != -1 and end_idx != -1:
    old_render_store = content[start_idx:end_idx]
    
    new_render_store = """        function renderJobStore() {
            const jobs = appData.job_store || {};
            const urls = Object.keys(jobs);

            if (!urls.length) return '<div class="card">Nessuna offerta salvata.</div>';

            const uniqueDates = new Set();
            const uniqueKeywords = new Set();
            const uniqueCategories = new Set();

            let jobList = [];

            urls.forEach(url => {
                const j = jobs[url];
                const dateStr = j.first_seen || j.date_seen || '';
                if (dateStr) uniqueDates.add(dateStr.split('T')[0]);
                if (j.keyword) uniqueKeywords.add(j.keyword);
                if (j.category) uniqueCategories.add(j.category);
                
                // Determine UI score type for filtering
                let scoreType = 'non-valutato';
                if (j.fit_score !== null && typeof j.fit_score !== 'undefined') {
                    if (j.fit_score >= 90) scoreType = 'golden';
                    else if (j.fit_score >= 75) scoreType = 'tiera';
                    else if (j.fit_score >= 50) scoreType = 'tierb';
                    else scoreType = 'scartato';
                }

                let likedType = '';
                if (j.liked === true) likedType = 'liked';
                if (j.liked === false) likedType = 'disliked';

                jobList.push({
                    url: url,
                    j: j,
                    dateStr: dateStr ? dateStr.split('T')[0] : '',
                    keyword: j.keyword || '',
                    category: j.category || '',
                    scoreType: scoreType,
                    likedType: likedType,
                    rawDate: dateStr,
                    title: j.job_data ? j.job_data.title : j.title,
                    company: j.job_data ? j.job_data.companyName : j.company,
                    location: j.job_data ? j.job_data.location : j.location,
                    scoreVal: j.fit_score || -1
                });
            });

            if(!appData.uiState) appData.uiState = { page: 1, limit: 10, sortCol: 'date', sortDir: 'desc', filters: { date: '', keyword: '', category: '', score: '', liked: '' } };
            const state = appData.uiState;

            // --- FILTERING ---
            let filteredList = jobList.filter(item => {
                if (state.filters.date && item.dateStr !== state.filters.date) return false;
                if (state.filters.keyword && item.keyword !== state.filters.keyword) return false;
                if (state.filters.category && item.category !== state.filters.category) return false;
                if (state.filters.score && item.scoreType !== state.filters.score) return false;
                if (state.filters.liked && item.likedType !== state.filters.liked) return false;
                return true;
            });

            // --- SORTING ---
            filteredList.sort((a, b) => {
                let valA, valB;
                switch(state.sortCol) {
                    case 'title': valA = (a.title || '').toLowerCase(); valB = (b.title || '').toLowerCase(); break;
                    case 'company': valA = (a.company || '').toLowerCase(); valB = (b.company || '').toLowerCase(); break;
                    case 'location': valA = (a.location || '').toLowerCase(); valB = (b.location || '').toLowerCase(); break;
                    case 'score': valA = a.scoreVal; valB = b.scoreVal; break;
                    case 'category': valA = (a.category || '').toLowerCase(); valB = (b.category || '').toLowerCase(); break;
                    case 'date': valA = a.rawDate; valB = b.rawDate; break;
                    case 'liked': valA = a.likedType; valB = b.likedType; break;
                    case 'applied': valA = a.j.applied ? 1 : 0; valB = b.j.applied ? 1 : 0; break;
                    default: valA = a.rawDate; valB = b.rawDate; break;
                }
                if (valA < valB) return state.sortDir === 'asc' ? -1 : 1;
                if (valA > valB) return state.sortDir === 'asc' ? 1 : -1;
                return 0;
            });

            // --- PAGINATION ---
            const totalItems = filteredList.length;
            const totalPages = Math.max(1, Math.ceil(totalItems / state.limit));
            if (state.page > totalPages) state.page = totalPages;

            const startIndex = (state.page - 1) * state.limit;
            const paginatedList = filteredList.slice(startIndex, startIndex + state.limit);

            const dateOptions = Array.from(uniqueDates).sort().reverse().map(d => `<option value="${d}" ${state.filters.date === d ? 'selected' : ''}>${d}</option>`).join('');
            const keywordOptions = Array.from(uniqueKeywords).sort().map(k => `<option value="${escapeHtml(k)}" ${state.filters.keyword === k ? 'selected' : ''}>${escapeHtml(k)}</option>`).join('');
            const categoryOptions = Array.from(uniqueCategories).sort().map(c => `<option value="${escapeHtml(c)}" ${state.filters.category === c ? 'selected' : ''}>${escapeHtml(c)}</option>`).join('');

            const rows = paginatedList.map(item => {
                const j = item.j;
                const scoreHtml = getScoreHtml(j.fit_score);
                const descriptionText = j.job_data ? j.job_data.descriptionText : j.descriptionText;

                const descId = "desc_" + Math.random().toString(36).substr(2, 9);
                window[`modalData_${descId}`] = {
                    desc: descriptionText || '',
                    reason: j.reasoning || j.fit_reasoning || ''
                };

                let evalContent = '';
                if (j.needs_evaluation) {
                    evalContent = '<div style="font-size: 0.8em; color: var(--score-ok); margin-top: 5px;">⏳ In corso...</div>';
                } else {
                    evalContent = `<button class="btn-eval admin-only ${window.currentUser ? '' : 'hidden-auth'}" data-docid="${j._doc_id || ''}" data-url="${item.url}" style="margin-top: 5px; font-size: 0.75em; padding: 2px 6px; border: 1px solid var(--accent); background: transparent; color: var(--accent); border-radius: 4px; cursor: pointer;" title="Richiedi valutazione a Gemini">🔄 Valuta</button>`;
                }

                return `
            <tr class="job-row">
                <td>
                    <a href="javascript:void(0)" class="btn-desc" data-target="${descId}" style="text-decoration: none; border-bottom: 1px dashed var(--accent); color: var(--accent); font-weight: bold;" title="Mostra descrizione">
                        ${escapeHtml(item.title)}
                    </a>
                </td>
                <td>${escapeHtml(item.company)}</td>
                <td>${escapeHtml(item.location)}</td>
                <td class="metric" style="text-align: center;">
                    <a href="javascript:void(0)" class="score-link" data-target="${descId}" style="text-decoration: none; border-bottom: 1px dashed var(--accent); color: inherit;" title="Mostra ragioni">
                        ${scoreHtml}
                    </a>
                    <div style="display: flex; justify-content: center; margin-top: 4px;">
                        ${evalContent}
                    </div>
                </td>
                <td>${escapeHtml(item.category)}</td>
                <td style="color: var(--text-muted);">${formatDate(item.rawDate)}</td>
                <td><a href="${item.url}" target="_blank">Apri &nearr;</a></td>
                <td style="text-align: center;">
                    <div style="display: flex; gap: 5px; justify-content: center;">
                        <button class="btn-like" data-docid="${j._doc_id || ''}" data-like="true" data-current="${j.liked === true ? 'true' : 'false'}" style="background-color: ${j.liked === true ? '#2e7d32' : 'transparent'}; color: ${j.liked === true ? '#fff' : 'var(--text-muted)'}; border: 1px solid var(--border); padding: 4px 8px; border-radius: 4px; cursor: pointer; transition: all 0.2s;" title="Like">👍</button>
                        <button class="btn-like" data-docid="${j._doc_id || ''}" data-like="false" data-current="${j.liked === false ? 'true' : 'false'}" style="background-color: ${j.liked === false ? '#c62828' : 'transparent'}; color: ${j.liked === false ? '#fff' : 'var(--text-muted)'}; border: 1px solid var(--border); padding: 4px 8px; border-radius: 4px; cursor: pointer; transition: all 0.2s;" title="Dislike">👎</button>
                    </div>
                </td>
                <td>
                    <button class="btn-applied" data-docid="${j._doc_id || ''}" data-applied="${j.applied === true ? 'true' : 'false'}" style="background-color: ${j.applied === true ? '#2e7d32' : '#555'}; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer;">
                        ${j.applied === true ? 'Applicato ✓' : 'Non applicato'}
                    </button>
                </td>
            </tr>
        `;
            }).join('');

            return `
        <h2>Tutte le Offerte Salvate</h2>
        <div class="card" style="margin-bottom: 20px; display: flex; gap: 15px; flex-wrap: wrap;">
            <div>
                <label style="display:block; margin-bottom: 5px; font-size: 0.9em; color: var(--text-muted);">Data</label>
                <input type="date" id="filter-date" value="${state.filters.date}" style="padding: 5px; border-radius: 4px; background: #2c2c2c; color: #fff; border: 1px solid var(--border); min-width: 150px; box-sizing: border-box; height: 32px;" />
            </div>
            <div>
                <label style="display:block; margin-bottom: 5px; font-size: 0.9em; color: var(--text-muted);">Query</label>
                <select id="filter-keyword" style="padding: 6px; border-radius: 4px; background: #2c2c2c; color: #fff; border: 1px solid var(--border); min-width: 150px;">
                    <option value="">Tutte</option>
                    ${keywordOptions}
                </select>
            </div>
            <div>
                <label style="display:block; margin-bottom: 5px; font-size: 0.9em; color: var(--text-muted);">Categoria</label>
                <select id="filter-category" style="padding: 6px; border-radius: 4px; background: #2c2c2c; color: #fff; border: 1px solid var(--border); min-width: 150px;">
                    <option value="">Tutte</option>
                    ${categoryOptions}
                </select>
            </div>
            <div>
                <label style="display:block; margin-bottom: 5px; font-size: 0.9em; color: var(--text-muted);">Fit Score (Tier)</label>
                <select id="filter-score" style="padding: 6px; border-radius: 4px; background: #2c2c2c; color: #fff; border: 1px solid var(--border); min-width: 150px;">
                    <option value="" ${state.filters.score === '' ? 'selected' : ''}>Tutti</option>
                    <option value="golden" ${state.filters.score === 'golden' ? 'selected' : ''}>Golden Tier (90+)</option>
                    <option value="tiera" ${state.filters.score === 'tiera' ? 'selected' : ''}>Tier A (75-89)</option>
                    <option value="tierb" ${state.filters.score === 'tierb' ? 'selected' : ''}>Tier B (50-74)</option>
                    <option value="scartato" ${state.filters.score === 'scartato' ? 'selected' : ''}>Scartati (<50)</option>
                    <option value="non-valutato" ${state.filters.score === 'non-valutato' ? 'selected' : ''}>Non Valutati</option>
                </select>
            </div>
            <div>
                <label style="display:block; margin-bottom: 5px; font-size: 0.9em; color: var(--text-muted);">Preferenza</label>
                <select id="filter-liked" style="padding: 6px; border-radius: 4px; background: #2c2c2c; color: #fff; border: 1px solid var(--border); min-width: 150px;">
                    <option value="" ${state.filters.liked === '' ? 'selected' : ''}>Tutte</option>
                    <option value="liked" ${state.filters.liked === 'liked' ? 'selected' : ''}>👍</option>
                    <option value="disliked" ${state.filters.liked === 'disliked' ? 'selected' : ''}>👎</option>
                </select>
            </div>
            <div style="align-self: flex-end; padding-bottom: 5px;">
                <button id="btn-clear-filters" style="height: 32px; display: flex; align-items: center; padding: 0 15px; background: var(--bg-hover); color: var(--text-light); border: 1px solid var(--border); border-radius: 4px; cursor: pointer; transition: all 0.2s;">Pulisci Filtri</button>
            </div>
            <div style="margin-left: auto; align-self: flex-end; padding-bottom: 5px;">
                <span id="jobs-counter" class="metric" style="font-size: 1.1em;">${totalItems}</span> <span style="color: var(--text-muted); font-size: 0.9em;">offerte trovate</span>
            </div>
        </div>
        <div class="card table-responsive">
            <table>
                <thead>
                    <tr>
                        <th class="sortable" data-sort="title" style="cursor: pointer;">Titolo ${state.sortCol === 'title' ? (state.sortDir==='asc' ? '▲' : '▼') : ''}</th>
                        <th class="sortable" data-sort="company" style="cursor: pointer;">Azienda ${state.sortCol === 'company' ? (state.sortDir==='asc' ? '▲' : '▼') : ''}</th>
                        <th class="sortable" data-sort="location" style="cursor: pointer;">Luogo ${state.sortCol === 'location' ? (state.sortDir==='asc' ? '▲' : '▼') : ''}</th>
                        <th class="sortable" data-sort="score" style="cursor: pointer; text-align: center;">Score ${state.sortCol === 'score' ? (state.sortDir==='asc' ? '▲' : '▼') : ''}</th>
                        <th class="sortable" data-sort="category" style="cursor: pointer;">Categoria ${state.sortCol === 'category' ? (state.sortDir==='asc' ? '▲' : '▼') : ''}</th>
                        <th class="sortable" data-sort="date" style="cursor: pointer;">Date Seen ${state.sortCol === 'date' ? (state.sortDir==='asc' ? '▲' : '▼') : ''}</th>
                        <th>Link</th>
                        <th class="sortable" data-sort="liked" style="cursor: pointer; text-align: center;">Preferenza ${state.sortCol === 'liked' ? (state.sortDir==='asc' ? '▲' : '▼') : ''}</th>
                        <th class="sortable" data-sort="applied" style="cursor: pointer;">Candidatura ${state.sortCol === 'applied' ? (state.sortDir==='asc' ? '▲' : '▼') : ''}</th>
                    </tr>
                </thead>
                <tbody id="job-table-body">
                    ${rows.length ? rows : '<tr><td colspan="9" style="text-align:center; padding:20px;">Nessun risultato.</td></tr>'}
                </tbody>
            </table>
            
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 15px; border-top: 1px solid var(--border); padding-top: 15px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <button class="btn-page" data-page="${state.page - 1}" ${state.page <= 1 ? 'disabled' : ''} style="padding: 6px 12px; background: var(--bg-hover); color: var(--text-light); border: 1px solid var(--border); border-radius: 4px; cursor: pointer; ${state.page <= 1 ? 'opacity: 0.5' : ''}">&laquo; Prec</button>
                    <span>Pagina <strong>${state.page}</strong> di ${totalPages}</span>
                    <button class="btn-page" data-page="${state.page + 1}" ${state.page >= totalPages ? 'disabled' : ''} style="padding: 6px 12px; background: var(--bg-hover); color: var(--text-light); border: 1px solid var(--border); border-radius: 4px; cursor: pointer; ${state.page >= totalPages ? 'opacity: 0.5' : ''}">Succ &raquo;</button>
                </div>
                <div>
                    <label style="font-size: 0.9em; color: var(--text-muted); margin-right: 5px;">Righe per pagina:</label>
                    <select id="filter-limit" style="padding: 4px 8px; border-radius: 4px; background: #2c2c2c; color: #fff; border: 1px solid var(--border);">
                        <option value="10" ${state.limit === 10 ? 'selected' : ''}>10</option>
                        <option value="50" ${state.limit === 50 ? 'selected' : ''}>50</option>
                        <option value="100" ${state.limit === 100 ? 'selected' : ''}>100</option>
                    </select>
                </div>
            </div>
        </div>
    `;
        }
"""
    content = content.replace(old_render_store, new_render_store)

# 4. attachEvents
start_idx = content.find('        function attachEvents() {')
end_idx = content.find('            // Modal logic')
if start_idx != -1 and end_idx != -1:
    old_attach = content[start_idx:end_idx]
    
    new_attach = """        function attachEvents() {
            const updateFilters = () => {
                if(!appData.uiState) return;
                const fDate = document.getElementById('filter-date');
                const fKeyword = document.getElementById('filter-keyword');
                const fCat = document.getElementById('filter-category');
                const fScore = document.getElementById('filter-score');
                const fLiked = document.getElementById('filter-liked');
                const fLimit = document.getElementById('filter-limit');

                if(fDate) appData.uiState.filters.date = fDate.value;
                if(fKeyword) appData.uiState.filters.keyword = fKeyword.value;
                if(fCat) appData.uiState.filters.category = fCat.value;
                if(fScore) appData.uiState.filters.score = fScore.value;
                if(fLiked) appData.uiState.filters.liked = fLiked.value;
                
                if(fLimit) appData.uiState.limit = parseInt(fLimit.value) || 10;
                
                appData.uiState.page = 1;
                render();
            };

            ['filter-date', 'filter-keyword', 'filter-category', 'filter-score', 'filter-liked', 'filter-limit'].forEach(id => {
                const el = document.getElementById(id);
                if(el) el.addEventListener('change', updateFilters);
            });

            const btnClear = document.getElementById('btn-clear-filters');
            if (btnClear) {
                btnClear.addEventListener('click', () => {
                    if(!appData.uiState) return;
                    appData.uiState.filters = { date: '', keyword: '', category: '', score: '', liked: '' };
                    appData.uiState.page = 1;
                    render();
                });
            }

            document.querySelectorAll('.btn-page').forEach(btn => {
                btn.addEventListener('click', () => {
                    if (btn.disabled) return;
                    const newPage = parseInt(btn.getAttribute('data-page'));
                    if(!isNaN(newPage) && appData.uiState) {
                        appData.uiState.page = newPage;
                        render();
                    }
                });
            });

            document.querySelectorAll('.sortable').forEach(th => {
                th.addEventListener('click', () => {
                    const col = th.getAttribute('data-sort');
                    if(!appData.uiState) return;
                    
                    if (appData.uiState.sortCol === col) {
                        appData.uiState.sortDir = appData.uiState.sortDir === 'asc' ? 'desc' : 'asc';
                    } else {
                        appData.uiState.sortCol = col;
                        appData.uiState.sortDir = 'desc'; 
                    }
                    appData.uiState.page = 1; 
                    render();
                });
            });

            document.querySelectorAll('.btn-eval').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const docId = btn.getAttribute('data-docid');
                    if (!docId) return;
                    btn.disabled = true;
                    btn.textContent = '⏳...';
                    try {
                        await window.updateDoc(window.doc(window.db, "jobs", docId), {
                            needs_evaluation: true
                        });
                    } catch(err) {
                        console.error("Errore aggiornamento:", err);
                        alert("Errore nell'impostare la valutazione");
                        btn.disabled = false;
                        btn.textContent = '🔄 Valuta';
                    }
                });
            });

"""
    content = content.replace(old_attach, new_attach)

with open('docs/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("SUCCESS")
