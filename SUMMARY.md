# LinkedIn Job Scraper, Matcher & Email Reporter

Questo progetto è un'automazione avanzata che analizza il tuo profilo, delega all'Intelligenza Artificiale (Google Gemini) la creazione autonoma delle migliori ricerche di lavoro su LinkedIn, estrae le offerte tramite Apify, le valuta rigorosamente, le categorizza e salva tutto in modo persistente e sicuro su un database in cloud (Firebase Firestore). Il tutto è governabile da una Dashboard web.

## Componenti del Sistema

1. **Il tuo Profilo**: Il cuore dell'applicazione. Contiene le tue esperienze, studi e interessi. Viene salvato su Firestore e gestito tramite la Dashboard. Gemini lo legge per capire *chi sei* e formulare chiavi di ricerca mirate (Job Titles) e per valutare le offerte.
2. **La Configurazione**: Il pannello di controllo operativo. Definisce il target di job post da raccogliere complessivamente, le strategie di ricerca e la soglia minima di score. Anche questa è salvata su Firestore e modificabile da Dashboard (il file `config.yaml` funge da setup iniziale / factory fallback).
3. **`main.py`**: L'orchestratore iterativo. 
    - **Fase 1 (Generazione Dinamica & Scraping Iterativo)**: Legge lo storico delle ricerche (`search_memory` su DB). Continua a generare nuove query con Gemini, esplorando titoli sempre nuovi e scaricando i risultati distribuendo il carico su un pool di account Apify (`apify_pool.py`), finché non si raggiunge il target.
    - **Fase 2 (Valutazione)**: Invia a Gemini la descrizione di tutti i nuovi job scaricati per ottenere un punteggio di aderenza da 0 a 100 con relativo ragionamento. Il tutto è processato asincronamente.
    - **Fase 3 (Categorizzazione)**: Categorizza automaticamente le nuove offerte per facilitarne la consultazione.
    - **Fase 4 (Notifica)**: Invia un riepilogo tramite email SMTP con i ruoli migliori.
4. **Firebase Firestore (DB Cloud)**: Il database cloud sostituisce completamente i vecchi file JSON. Le collezioni `jobs`, `search_memory`, `job_categories` e `app_state` funzionano come memoria permanente, permettendo al sistema di essere più "intelligente" ed evitare duplicati tra una run e l'altra.
5. **Dashboard Web**: Un'interfaccia interattiva da cui monitorare i KPI, leggere i lavori trovati e modificare Profilo e Configurazioni senza toccare il codice.

## Istruzioni di Setup

### 1. Installazione Dipendenze
Per installare le librerie necessarie, apri un terminale nella cartella del progetto ed esegui:
```bash
pip install -r requirements.txt
```

### 2. Impostazione delle Variabili d'Ambiente (`.env`)
L'automazione richiede chiavi API esterne e credenziali per l'invio della posta.
Copia il file `.env.example` in `.env` nella directory principale e compila i campi (tra cui il pool di token Apify, le chiavi Gemini, credenziali SMTP e il Service Account di Firebase).

### 3. Configurazione via Dashboard
- **Profilo e Limiti Operativi**: Non è più necessario modificare file locali. Accedi alla tua Dashboard connessa al progetto Firebase, e usa le sezioni apposite per aggiornare il tuo CV, i tuoi interessi, o i parametri di scraping (numero di offerte target, soglie, ecc.).
- **Startup Outreach**: Lo script `startup_outreach.py` utilizza Tavily e Gemini per trovare e qualificare startup attive, generando cover letter personalizzate. Anche in questo caso fa affidamento al profilo caricato su DB.

### 4. Esecuzione
Avvia lo script principal in locale o tramite action:
```bash
python main.py
```
A fine esecuzione verrà inviata un'email, e la tua Dashboard online si popolerà in tempo reale con i nuovi lavori scaricati e valutati.
