# LinkedIn Job Scraper, Matcher & Email Reporter

Questo progetto è un'automazione avanzata che analizza il tuo profilo, delega all'Intelligenza Artificiale (Google Gemini) la creazione autonoma delle migliori ricerche di lavoro su LinkedIn, estrae le offerte tramite Apify, le valuta rigorosamente, le categorizza e genera una dashboard locale e un report via Email per le posizioni ad alto "fit score".

## Componenti del Sistema

1. **`my_profile.md`**: Il cuore dell'applicazione. Contiene le tue esperienze, studi e interessi. Gemini lo legge per capire *chi sei* e formulare chiavi di ricerca mirate (Job Titles) e per valutare le offerte.
2. **`config.yaml`**: Il pannello di controllo operativo. Definisce il target di job post da raccogliere complessivamente (`jobs_target`), i tentativi massimi che Gemini può fare in un'esecuzione (`max_retries`), i risultati per ogni singola query (`count_per_search`), e la soglia minima di score (`min_fit_score`).
3. **`main.py`**: L'orchestratore iterativo. 
    - **Fase 1 (Generazione Dinamica & Scraping Iterativo)**: Legge lo storico delle ricerche (`search_memory.json`) e il totale dei lavori finora scaricati (`job_store.json`). Continua a generare nuove query con Gemini, esplorando titoli sempre nuovi e scaricando i risultati tramite Apify, finché non si raggiunge il target di `jobs_target`.
    - **Fase 2 (Valutazione)**: Passa a Gemini la descrizione di tutti i nuovi job scaricati per ottenere un punteggio di aderenza da 0 a 100 con relativo ragionamento.
    - **Fase 3 (Categorizzazione)**: Categorizza automaticamente le nuove offerte per facilitarne la consultazione (`job_categories.json`).
    - **Fase 4 (Dashboard e Notifica)**: Genera la `dashboard.html` visualizzabile localmente o via artefatto GitHub, ed invia un riepilogo tramite email SMTP con i ruoli migliori.
4. **File di Stato JSON**: `search_memory.json`, `job_store.json`, `job_categories.json` funzionano come una memoria permanente a lungo termine, rendendo il sistema più "intelligente" di run in run.
5. **`requirements.txt`**: Dipendenze necessarie.

## Istruzioni di Setup

### 1. Installazione Dipendenze
Per installare le librerie necessarie, apri un terminale nella cartella del progetto ed esegui:
```bash
pip install -r requirements.txt
```

### 2. Impostazione delle Variabili d'Ambiente (`.env`)
L'automazione richiede chiavi API esterne e credenziali per l'invio della posta.
Apri (o crea) il file `.env` nella directory principale e compila i campi:
```env
APIFY_API_TOKEN=il_tuo_token_apify_qui
GEMINI_API_KEY=la_tua_chiave_gemini_qui
EMAIL_SENDER=la_tua_email_mittente@gmail.com
EMAIL_PASSWORD=app_password_google_senza_spazi
EMAIL_RECIPIENT=matteo_pasini@outlook.com
```

### 3. Configurazione
- **Profilo**: Aggiorna `my_profile.md` ogni volta che aggiungi un'esperienza o vuoi cambiare il focus della tua ricerca (es. aggiungere interesse verso "Venture Capital").
- **Limiti Operativi**: Modifica `config.yaml` per cambiare la dimensione del batch quotidiano di job scaricati (`jobs_target`), ad esempio se vuoi estrarre 50 o 100 lavori nuovi per sessione.
- **Startup Outreach**: Sotto la chiave `outreach` in `config.yaml` puoi gestire la pipeline per le startup se prevista nel workflow secondario.

### 4. Esecuzione
Avvia lo script principal in locale o tramite action:
```bash
python main.py
```
A fine esecuzione verrà inviata un'email, e sarà aggiornata la **`dashboard.html`** da aprire per vedere i KPI, tutti i lavori filtrati e lo score di ciascuno.
