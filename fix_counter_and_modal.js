const fs = require('fs');

let html = fs.readFileSync('docs/index.html', 'utf8');

// 1. Fix ApplyFilters
html = html.replace(/        let visibleCount = 0;\n            let show = true;/g, '            let show = true;');
html = html.replace('const applyFilters = () => {', 'const applyFilters = () => {\n        let visibleCount = 0;');

// 2. Add score modal
const newModals = `        <div class="modal-overlay" id="info-modal">
            <div class="modal-container">
                <div class="modal-header">
                    <h3 style="margin: 0; color: var(--accent);">Dettagli Offerta</h3>
                    <button class="modal-close" id="btn-close-modal">&times;</button>
                </div>
                <div class="modal-body">
                    <h4 style="margin-bottom: 10px;">Fit Reasoning</h4>
                    <div class="reasoning-box" id="modal-reasoning"></div>
                    
                    <h4 style="margin-bottom: 10px;">Description text</h4>
                    <div class="desc-box" id="modal-description"></div>
                </div>
            </div>
        </div>

        <div class="modal-overlay" id="score-modal">
            <div class="modal-container" style="max-width: 500px;">
                <div class="modal-header">
                    <h3 style="margin: 0; color: var(--accent);">Perché questo punteggio?</h3>
                    <button class="modal-close" id="btn-close-score-modal">&times;</button>
                </div>
                <div class="modal-body">
                    <ul style="padding-left: 20px; line-height: 1.8; color: var(--text-light);" id="score-reasoning-list">
                    </ul>
                </div>
            </div>
        </div>`;

html = html.replace(/<div class="modal-overlay" id="info-modal">[\s\S]*?<\/div>\n        <\/div>/m, newModals);

// 3. Make score clickable
const oldScoreTd = '<td class="metric" style="text-align: center;">${scoreHtml}</td>';
const newScoreTd = `<td class="metric" style="text-align: center;">
                    <a href="javascript:void(0)" class="score-link" data-target="\${descId}" style="text-decoration: none; border-bottom: 1px dashed var(--accent);" title="Mostra ragioni">
                        \${scoreHtml}
                    </a>
                </td>`;
html = html.replace(oldScoreTd, newScoreTd);

// 4. Add event listeners for score-link in attachEvents
const oldAttach = `    document.querySelectorAll('.btn-desc').forEach(btn => {`;
const newAttach = `    // Score click logic
    document.querySelectorAll('.score-link').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const targetId = e.currentTarget.getAttribute('data-target');
            const data = window[\`modalData_\${targetId}\`];
            const reasonText = data.reason || 'Nessuna informazione disponibile.';
            
            // Split reasoning into sentences for bullet points
            const sentences = reasonText.split(/\.\s+/).filter(s => s.trim().length > 0);
            const listHtml = sentences.map(s => \`<li>\${s}\${s.endsWith('.') ? '' : '.'}</li>\`).join('');
            
            const scoreList = document.getElementById('score-reasoning-list');
            if (scoreList) scoreList.innerHTML = listHtml;
            
            const scoreModal = document.getElementById('score-modal');
            if (scoreModal) scoreModal.classList.add('active');
        });
    });

    const scoreModal = document.getElementById('score-modal');
    const closeScoreBtn = document.getElementById('btn-close-score-modal');
    if (closeScoreBtn && scoreModal) {
        closeScoreBtn.addEventListener('click', () => scoreModal.classList.remove('active'));
        scoreModal.addEventListener('click', (e) => {
            if (e.target === scoreModal) scoreModal.classList.remove('active');
        });
    }

    document.querySelectorAll('.btn-desc').forEach(btn => {`;

html = html.replace(oldAttach, newAttach);

fs.writeFileSync('docs/index.html', html, 'utf8');
