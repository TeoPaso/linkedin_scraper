# LinkedIn Job Scraper, Matcher & Email Reporter

Questo progetto è un'automazione avanzata che analizza il tuo profilo, delega all'Intelligenza Artificiale (Google Gemini) la creazione autonoma delle migliori ricerche di lavoro su LinkedIn, estrae le offerte tramite Apify, le valuta rigorosamente, e ti invia un report via Email solo per le posizioni ad alto "fit score".

## Componenti del Sistema

1. **`my_profile.md`**: Il cuore dell'applicazione. Contiene le tue esperienze, studi e interessi. Gemini lo legge per capire *chi sei* e formulare chiavi di ricerca mirate (Job Titles) e per valutare le offerte.
2. **`config.yaml`**: Il pannello di controllo operativo. Non contiene più chiavi di ricerca statiche, ma serve a definire i "limiti" per tenere sotto controllo i costi: numero massimo di ricerche da far generare a Gemini (`max_searches`), numero di risultati da scaricare per query (`max_jobs_per_search`), soglia minima di score (`min_fit_score`) e preferenza fissa di location.
3. **`main.py`**: L'orchestratore. 
    - **Fase 1 (Generazione Dinamica)**: Chiede a Gemini di generare X query di ricerca in formato JSON.
    - **Fase 2 (Scraping)**: Costruisce un URL LinkedIn dinamico in base alle keyword e alla location scelte dall'AI e avvia l'actor di Apify.
    - **Fase 3 (Valutazione)**: Passa la descrizione di ogni lavoro a Gemini, imponendo vincoli severi contro lavori fuori target (es. Marketing/HR o con troppa seniority richiesta).
    - **Fase 4 (Notifica)**: Formatta i risultati e i parametri di ricerca in HTML e li invia tramite email SMTP.
4. **`requirements.txt`**: Dipendenze necessarie (`apify-client`, `google-genai`, `pydantic`, `python-dotenv`, `pyyaml`).

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
*(Nota: il programma caricherà automaticamente queste variabili ad ogni esecuzione grazie alla libreria python-dotenv).*

### 3. Configurazione
- **Profilo**: Aggiorna `my_profile.md` ogni volta che aggiungi un'esperienza o vuoi cambiare il focus della tua ricerca (es. aggiungere interesse verso "Venture Capital").
- **Limiti Operativi**: Modifica `config.yaml` per scalare il numero di ricerche (`max_searches`) in base al tuo budget Apify.
- **Startup Outreach**: Sotto la chiave `outreach` in `config.yaml` puoi gestire la pipeline per le startup:
  - `run_discovery`: **Attenzione:** impostalo a `true` solo settimanalmente o quando avvii lo script manualmente per cercare nuove startup via Apify e Tavily. Lascialo a `false` durante l'esecuzione quotidiana del cron job in modo da aggiornare solo l'enrichment e non consumare inutilmente token e budget.

### 4. Esecuzione
Il processo principale su GitHub Actions o localmente eseguirà in sequenza:
```bash
python main.py
python startup_outreach.py
```
Riceverai un report per i match standard (tramite main.py) e un report separato per le startup (tramite startup_outreach.py) con relative cover letters salvate in locale.

