import re

# ============================
# 1. Update main.py
# ============================
with open('main.py', 'r', encoding='utf-8') as f:
    main_content = f.read()

# Add highlighted_description to JobEvaluation
old_job_eval = '''class JobEvaluation(BaseModel):
    fit_score: int
    reasoning: str'''
new_job_eval = '''class JobEvaluation(BaseModel):
    fit_score: int
    reasoning: str
    highlighted_description: str = ""'''
main_content = main_content.replace(old_job_eval, new_job_eval)

# Update evaluate_job_with_gemini prompt
old_prompt = '''1. Valuta l'aderenza del candidato per questo ruolo e assegna un 'fit_score' da 0 a 100 usando il seguente sistema a FASCE (Tier):
   - Fascia A (85-100): Match eccellente. Il core focus del lavoro e le skill principali corrispondono al profilo. Le mancanze sono secondarie.
   - Fascia B (70-84): Buon match. Esperienza pertinente ma ruolo leggermente diverso, o mancano un paio di requisiti importanti ma non bloccanti.
   - Fascia C (50-69): Match parziale o debole. Settore giusto ma seniority sbagliata (es. chiedono 10 anni e ne hai 2), oppure shift laterale non ideale.
   - Fascia D (0-49): Fuori scope. Dipartimento completamente errato (es. sei in Finance, cercano Sales o dev puro).
2. HARD RULE (CRITICO): Il candidato è disponibile a lavorare SOLO IN ITALIA (o fully remote). I viaggi per lavoro vanno bene, ma i trasferimenti definitivi all'estero (relocation) sono categoricamente esclusi. Se il lavoro richiede esplicitamente una relocation fuori dall'Italia, il punteggio DEVE essere 0.
3. Scrivi una 'reasoning' di 2-3 righe IN ITALIANO per giustificare il punteggio, spiegando chiaramente i pro e i contro rispetto al profilo.'''

new_prompt = '''1. Valuta l'aderenza del candidato per questo ruolo e assegna un 'fit_score' da 0 a 100 usando il seguente sistema a FASCE (Tier):
   - Fascia Golden (90-100): Ruolo perfetto, seniority esatta.
   - Fascia A (80-89): Match eccellente. Il core focus del lavoro e le skill principali corrispondono al profilo.
   - Fascia B (70-79): Buon match. Esperienza pertinente ma manca un requisito.
   - Fascia Scarto (0-69): Fuori scope, seniority sbagliata o ruolo errato.
2. HARD RULE (CRITICO): Lavora SOLO IN ITALIA o remote. Se richiesta relocation all'estero, punteggio = 0.
3. Scrivi una 'reasoning' discorsiva e diretta di 2-3 righe IN ITALIANO. NON ripetere il background del candidato (lo conosce già!). Invece, CONTESTUALIZZA: fagli capire esattamente cosa farebbe nel pratico in questo ruolo, "dandogli un assaggio" delle responsabilità principali.
4. Restituisci la 'highlighted_description' copiando il testo della "Descrizione" originale (senza tagliarlo), ma inserendo dei tag HTML <mark>testo</mark> attorno alle parti più rilevanti, le responsabilità chiave e i requisiti cruciali. Così leggerla sarà graficamente più agevole.'''
main_content = main_content.replace(old_prompt, new_prompt)

# Update job background task save logic
old_save_logic = '''    data["fit_score"] = evaluation.fit_score
    data["reasoning"] = evaluation.reasoning'''
new_save_logic = '''    data["fit_score"] = evaluation.fit_score
    data["reasoning"] = evaluation.reasoning
    data["highlighted_description"] = evaluation.highlighted_description'''
main_content = main_content.replace(old_save_logic, new_save_logic)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(main_content)


# ============================
# 2. Update docs/index.html
# ============================
with open('docs/index.html', 'r', encoding='utf-8') as f:
    html_content = f.read()

# Update getScoreHtml
old_score_html = '''        function getScoreHtml(score) {
            if (score === null || score === undefined) return `<span class="score-grey" style="font-size: 0.9em;">Da valutare</span>`;
            if (score >= 90) return `<span class="score-green" style="font-weight: bold; font-size: 1.1em; color: #ffd700; text-shadow: 0 0 5px rgba(255, 215, 0, 0.5);">🏆 ${score} (Golden)</span>`;
            if (score >= 75) return `<span class="score-green" style="font-weight: bold;">⭐ ${score} (Tier A)</span>`;
            if (score >= 50) return `<span class="score-orange" style="font-weight: bold; color: #ffaa00;">✓ ${score} (Tier B)</span>`;
            return `<span class="score-red" style="color: #ff4444; font-weight: bold;">❌ ${score} (Scartato)</span>`;
        }'''
new_score_html = '''        function getScoreHtml(score) {
            if (score === null || score === undefined) return `<span class="score-grey" style="font-size: 0.9em;">-</span>`;
            if (score >= 90) return `<span class="score-green" style="font-weight: bold; font-size: 1.1em; color: #ffd700; text-shadow: 0 0 5px rgba(255, 215, 0, 0.5);">${score}</span>`;
            if (score >= 80) return `<span class="score-green" style="font-weight: bold;">${score}</span>`;
            if (score >= 70) return `<span class="score-orange" style="font-weight: bold; color: #ffaa00;">${score}</span>`;
            return `<span class="score-red" style="color: #ff4444; font-weight: bold;">${score}</span>`;
        }'''
html_content = html_content.replace(old_score_html, new_score_html)

# Update score filtering logic & options in renderJobStore
old_score_logic = '''                let scoreType = 'non-valutato';
                if (j.fit_score !== null && typeof j.fit_score !== 'undefined') {
                    if (j.fit_score >= 90) scoreType = 'golden';
                    else if (j.fit_score >= 75) scoreType = 'tiera';
                    else if (j.fit_score >= 50) scoreType = 'tierb';
                    else scoreType = 'scartato';
                }'''
new_score_logic = '''                let scoreType = 'non-valutato';
                if (j.fit_score !== null && typeof j.fit_score !== 'undefined') {
                    if (j.fit_score >= 90) scoreType = 'golden';
                    else if (j.fit_score >= 80) scoreType = 'tiera';
                    else if (j.fit_score >= 70) scoreType = 'tierb';
                    else scoreType = 'scartato';
                }'''
html_content = html_content.replace(old_score_logic, new_score_logic)

old_options = '''                    <option value="" ${state.filters.score === '' ? 'selected' : ''}>Tutti</option>
                    <option value="golden" ${state.filters.score === 'golden' ? 'selected' : ''}>Golden Tier (90+)</option>
                    <option value="tiera" ${state.filters.score === 'tiera' ? 'selected' : ''}>Tier A (75-89)</option>
                    <option value="tierb" ${state.filters.score === 'tierb' ? 'selected' : ''}>Tier B (50-74)</option>
                    <option value="scartato" ${state.filters.score === 'scartato' ? 'selected' : ''}>Scartati (<50)</option>
                    <option value="non-valutato" ${state.filters.score === 'non-valutato' ? 'selected' : ''}>Non Valutati</option>'''
new_options = '''                    <option value="" ${state.filters.score === '' ? 'selected' : ''}>Tutti</option>
                    <option value="golden" ${state.filters.score === 'golden' ? 'selected' : ''}>Golden Tier (90+)</option>
                    <option value="tiera" ${state.filters.score === 'tiera' ? 'selected' : ''}>Tier A (80-89)</option>
                    <option value="tierb" ${state.filters.score === 'tierb' ? 'selected' : ''}>Tier B (70-79)</option>
                    <option value="scartato" ${state.filters.score === 'scartato' ? 'selected' : ''}>Scartati (<70)</option>
                    <option value="non-valutato" ${state.filters.score === 'non-valutato' ? 'selected' : ''}>Non Valutati</option>'''
html_content = html_content.replace(old_options, new_options)

# Update row generation for title color & highlighted text
old_row_gen = '''            const rows = paginatedList.map(item => {
                const j = item.j;
                const scoreHtml = getScoreHtml(j.fit_score);
                const descriptionText = j.job_data ? j.job_data.descriptionText : j.descriptionText;

                const descId = "desc_" + Math.random().toString(36).substr(2, 9);
                window[`modalData_${descId}`] = {
                    desc: descriptionText || '',
                    reason: j.reasoning || j.fit_reasoning || ''
                };

                return `
            <tr class="job-row">
                <td>
                    <a href="javascript:void(0)" class="btn-desc" data-target="${descId}" style="text-decoration: none; border-bottom: 1px dashed var(--accent); color: var(--accent); font-weight: bold;" title="Mostra descrizione">
                        ${escapeHtml(item.title)}
                    </a>
                </td>'''

new_row_gen = '''            const rows = paginatedList.map(item => {
                const j = item.j;
                const scoreHtml = getScoreHtml(j.fit_score);
                const descriptionText = j.highlighted_description || (j.job_data ? j.job_data.descriptionText : j.descriptionText);

                const descId = "desc_" + Math.random().toString(36).substr(2, 9);
                window[`modalData_${descId}`] = {
                    desc: descriptionText || '',
                    reason: j.reasoning || j.fit_reasoning || ''
                };
                
                let titleText = escapeHtml(item.title);
                let titleStyle = "text-decoration: none; border-bottom: 1px dashed var(--accent); color: var(--accent); font-weight: bold;";
                
                if (j.fit_score !== null && typeof j.fit_score !== 'undefined') {
                    if (j.fit_score >= 90) {
                        titleText = `🏆 ${titleText}`;
                        titleStyle = "text-decoration: none; border-bottom: 1px dashed #ffd700; color: #ffd700; font-weight: bold; text-shadow: 0 0 5px rgba(255, 215, 0, 0.5);";
                    } else if (j.fit_score >= 80) {
                        titleText = `⭐ ${titleText}`;
                        titleStyle = "text-decoration: none; border-bottom: 1px dashed var(--score-good); color: var(--score-good); font-weight: bold;";
                    } else if (j.fit_score >= 70) {
                        titleText = `✓ ${titleText}`;
                        titleStyle = "text-decoration: none; border-bottom: 1px dashed #ffaa00; color: #ffaa00; font-weight: bold;";
                    } else {
                        titleText = `❌ ${titleText}`;
                        titleStyle = "text-decoration: none; border-bottom: 1px dashed #ff4444; color: #ff4444; font-weight: bold;";
                    }
                }

                return `
            <tr class="job-row">
                <td>
                    <a href="javascript:void(0)" class="btn-desc" data-target="${descId}" style="${titleStyle}" title="Mostra descrizione">
                        ${titleText}
                    </a>
                </td>'''
html_content = html_content.replace(old_row_gen, new_row_gen)

with open('docs/index.html', 'w', encoding='utf-8') as f:
    f.write(html_content)

print("SUCCESS")
