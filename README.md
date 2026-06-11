# LinkedIn Job Scraper, Matcher & Email Reporter

Benvenuto! Questo progetto è un sistema avanzato di automazione per la ricerca di lavoro su LinkedIn. Utilizza l'Intelligenza Artificiale (Google Gemini) per generare chiavi di ricerca dinamiche basate sul tuo profilo, effettua lo scraping dei job post tramite Apify distribuendo il carico su più account, valuta il "fit score" di ogni offerta in base alle tue esperienze e ti invia un report via email. Salva inoltre tutto lo storico su un database cloud Firebase Firestore.

> 🚀 **SEI UN UTENTE FINALE? (NON SERVE INSTALLARE NULLA!)**
> Se vuoi solo utilizzare il bot e consultare le offerte, **NON devi scaricare né installare nulla sul tuo computer**. 
> L'intero sistema gira automaticamente ogni giorno sui server di GitHub (tramite GitHub Actions). 
> **Tutto ciò che devi fare è visitare la [Dashboard Web](#) (il link ti verrà fornito dall'amministratore), fare login e gestire il tuo profilo da lì.**

> 🛠 **SEI UNO SVILUPPATORE/AMMINISTRATORE?**
> Se vuoi fare il setup iniziale del progetto, configurare Firebase, o far girare lo script dal tuo computer, segui le istruzioni tecniche qui sotto.

---

## 📋 Indice
1. [Prerequisiti](#1-prerequisiti)
2. [Installazione e Setup Locale](#2-installazione-e-setup-locale)
3. [Configurazione del Database Firebase](#3-configurazione-del-database-firebase)
4. [Configurazione dei Servizi e Variabili d'Ambiente (`.env`)](#4-configurazione-dei-servizi-e-variabili-dambiente-env)
5. [Configurazione della Dashboard Web (GitHub Pages)](#5-configurazione-della-dashboard-web-github-pages)
6. [Gestione del Profilo e dei Filtri via Dashboard](#6-gestione-del-profilo-e-dei-filtri-via-dashboard)
7. [Esecuzione del Bot](#7-esecuzione-del-bot)
8. [Automazione Quotidiana con GitHub Actions](#8-automazione-quotidiana-con-github-actions)

---

## 1. Prerequisiti
Assicurati di avere installato sul tuo computer:
* **Python** (versione 3.10 o superiore). Puoi scaricarlo da [python.org](https://www.python.org/).
* Un account **GitHub** (se desideri far girare l'automazione online in modo gratuito e automatico ogni giorno).
* Un progetto **Firebase** gratuito (necessario per memorizzare i dati e servire la Dashboard).

---

## 2. Installazione e Setup Locale

Apri il terminale del tuo computer ed esegui i seguenti comandi:

1. **Clona questo repository:**
   ```bash
   git clone <URL_DI_QUESTO_REPOSITORY>
   cd linkedin_scraper
   ```

2. **Crea un ambiente virtuale (consigliato per non interferire con altre librerie):**
   * **Windows:**
     ```bash
     python -m venv venv
     venv\Scripts\activate
     ```
   * **Mac/Linux:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Installa le dipendenze richieste:**
   ```bash
   pip install -r requirements.txt
   ```

---

## 3. Configurazione del Database Firebase

L'intero stato dell'applicazione (Lavori trovati, Memoria di ricerca, Configurazione, Profilo dell'utente) è conservato in modo sicuro sul cloud Firestore. I file locali non vengono più utilizzati per immagazzinare lo stato.

1. Crea un progetto gratuito su [Firebase Console](https://console.firebase.google.com/).
2. Nel menu laterale, clicca su **Build -> Firestore Database** e creane uno.
3. Vai in **Impostazioni Progetto** (icona a forma di ingranaggio in alto a sinistra) -> **Account di Servizio**.
4. Clicca su **Genera nuova chiave privata**. Verrà scaricato un file `.json` sul tuo computer. Ne avrai bisogno nel passaggio successivo.

---

## 4. Configurazione dei Servizi e Variabili d'Ambiente (`.env`)

Il progetto si appoggia a servizi esterni gratuiti. Copia il file modello `.env.example` e rinominalo in `.env`.

Compila le seguenti variabili:

```env
# Pool di account Apify (per distribuire le chiamate di scraping e rimanere nel limite gratuito)
APIFY_API_TOKEN_1=il_tuo_token_apify_qui
APIFY_API_TOKEN_2=... (fino a 7)

GEMINI_API_KEY=la_tua_chiave_gemini_qui
TAVILY_API_KEY=la_tua_chiave_tavily_qui

EMAIL_SENDER=tua_email_mittente@gmail.com
EMAIL_PASSWORD=tua_app_password_senza_spazi
EMAIL_RECIPIENT=tua_email_destinatario@gmail.com

FIREBASE_SERVICE_ACCOUNT_JSON={"type": "service_account", "project_id": "...", ...}
```

### Dettagli dei Servizi:
* **Apify (`APIFY_API_TOKEN_X`):** Crea uno o più account gratuiti su [Apify](https://apify.com/) ed estrai i loro token. L'automazione bilancia il carico e tiene traccia dei budget residui autonomamente.
* **Google Gemini (`GEMINI_API_KEY`):** Richiedi una chiave API gratuita accedendo a [Google AI Studio](https://aistudio.google.com/).
* **Firebase (`FIREBASE_SERVICE_ACCOUNT_JSON`):** Apri il file `.json` che hai scaricato al passaggio precedente, copia l'intero contenuto e incollalo **su una singola riga** (senza a capo) come valore.
* **Tavily (`TAVILY_API_KEY`):** *(Opzionale)* Necessario solo se utilizzi lo scouting di startup (`startup_outreach.py`). Registrati su [Tavily](https://tavily.com/).
* **Configurazione Email (SMTP):** Genera una Password per App (App Passwords) da Google se usi Gmail (Impostazioni di Sicurezza -> Verifica in 2 Passaggi -> App Passwords).

---

## 5. Configurazione della Dashboard Web (GitHub Pages)

Il progetto include una comoda dashboard interattiva ospitata nella cartella `docs/` che mostra grafici, statistiche e permette di gestire le preferenze.

Per utilizzare la tua dashboard:
1. Crea una "Web App" all'interno del tuo progetto Firebase (Impostazioni Progetto -> Generali -> Le tue app).
2. Copia l'oggetto di configurazione `firebaseConfig` che ti viene mostrato.
3. Apri il file `docs/index.html`, trova la riga `const firebaseConfig` (verso la riga 600) e sostituiscilo con i tuoi dati.
4. Su GitHub, vai in **Settings -> Pages** del tuo repository, seleziona come sorgente la cartella `/docs` dal branch `main` e salva. La tua dashboard sarà accessibile pubblicamente.

---

## 6. Gestione del Profilo e dei Filtri via Dashboard

A differenza del passato, **non è più necessario modificare manualmente i file di testo `my_profile.md` o i file JSON locali.**
Tutta la configurazione vive in the Cloud:

1. Visita la tua Dashboard appena pubblicata.
2. Vai nella sezione **Impostazioni**.
3. **Compila il tuo Profilo:** Incolla qui il tuo CV, descrivi le tue esperienze, definisci in modo esplicito le tue preferenze ("Cosa cerco", "Cosa evitare"). Gemini si baserà su questo per lo scraping.
4. **Parametri Operativi:** Regola dalla dashboard quanti job scaricare al giorno (`jobs_target`), la città di riferimento e la soglia minima (`min_fit_score`).

*(Nota: il file locale `config.yaml` agisce unicamente da fallback per il primo caricamento su database).*

---

## 7. Esecuzione del Bot

Una volta configurato il tutto, puoi avviare gli script:

* **Per avviare la ricerca di lavoro su LinkedIn:**
  ```bash
  python main.py
  ```
  *(Al termine dell'esecuzione riceverai un'email con il riassunto ed i dettagli saranno visibili nella Dashboard).*

* **Per avviare lo scouting e l'outreach delle Startup (usa `startup_outreach.py`):**
  ```bash
  python startup_outreach.py
  ```

---

## 8. Automazione Quotidiana (Zero Local Setup)

Se hai un setup locale (ad esempio per una terza persona) e vuoi migrarlo interamente nel cloud affinché giri da solo senza dover tenere acceso il PC, segui esattamente questi 4 passaggi:

### A. Creare un Repository Dedicato
1. Crea un account GitHub (se la persona non lo ha).
2. Crea un nuovo repository (anche privato).
3. Dal terminale locale, dove hai il codice, spingi il codice sul nuovo repository:
   ```bash
   git remote set-url origin https://github.com/NOME_UTENTE/NOME_REPO.git
   git push -u origin main
   ```

### B. Inserire le API Key (Secrets)
Tutte le credenziali `.env` locali devono essere salvate al sicuro su GitHub.
1. Vai su GitHub: **Settings -> Secrets and variables -> Actions**.
2. Clicca su **New repository secret** e crea un segreto per ciascuna variabile:
   * `APIFY_API_TOKEN_1`, `APIFY_API_TOKEN_2`, ecc.
   * `GEMINI_API_KEY`
   * `EMAIL_SENDER`, `EMAIL_PASSWORD`, `EMAIL_RECIPIENT`
   * `FIREBASE_SERVICE_ACCOUNT_JSON` (incolla qui l'intero contenuto del file JSON scaricato da Firebase, in una singola riga).

### C. Pubblicare la Dashboard (GitHub Pages)
1. In `docs/index.html` assicurati che il `firebaseConfig` punti al progetto Firebase corretto.
2. Vai su GitHub: **Settings -> Pages**.
3. Sotto "Build and deployment", scegli **Deploy from a branch**.
4. Scegli il branch `main` e la cartella `/docs`, poi salva.
5. In un paio di minuti la dashboard sarà raggiungibile a `https://nome_utente.github.io/nome_repo/`.

### D. Trigger Quotidiano (cron-job.org)
Il cron interno di GitHub spesso ritarda. Per spaccare il minuto usiamo il trigger `repository_dispatch`.
1. Da GitHub, genera un **Personal Access Token (Classic)** (*Settings -> Developer settings -> Personal access tokens*) abilitando lo scope `repo`.
2. Crea un account gratuito su [cron-job.org](https://cron-job.org/) e crea un nuovo "Cronjob".
3. **URL:** `https://api.github.com/repos/NOME_UTENTE/NOME_REPO/dispatches`
4. **Metodo HTTP:** `POST`
5. Abilita la sezione HTTP Headers e aggiungine due:
   * `Accept` : `application/vnd.github.v3+json`
   * `Authorization` : `Bearer <IL_TOKEN_GITHUB_CREATO_AL_PUNTO_1>`
6. Abilita la sezione HTTP Body e scrivi esattamente:
   ```json
   {"event_type": "trigger-daily-scrape"}
   ```
7. Imposta l'orario a cui far girare lo script (es. ogni giorno alle 8:00) e salva.

A questo punto la cartella locale può essere tranquillamente cancellata. L'intero bot è automatizzato nel Cloud!

