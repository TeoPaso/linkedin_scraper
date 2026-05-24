# LinkedIn Job Scraper, Matcher & Email Reporter

Benvenuto! Questo progetto è un sistema avanzato di automazione per la ricerca di lavoro su LinkedIn. Utilizza l'Intelligenza Artificiale (Google Gemini) per generare chiavi di ricerca dinamiche basate sul tuo profilo, effettua lo scraping dei job post tramite Apify, valuta il "fit score" di ogni offerta in base alle tue esperienze e ti invia un report quotidiano via email con le posizioni migliori. Salva inoltre tutto lo storico su un database Firestore ed espone una comoda Dashboard web.

---

## 📋 Indice
1. [Prerequisiti](#1-prerequisiti)
2. [Installazione e Setup Locale](#2-installazione-e-setup-locale)
3. [Configurazione del Profilo e dei Filtri](#3-configurazione-del-profilo-e-dei-filtri)
4. [Configurazione dei Servizi e delle Variabili d'Ambiente (`.env`)](#4-configurazione-dei-servizi-e-delle-variabili-dambiente-env)
   * [Ottenere le Chiavi API](#ottenere-le-chiavi-api)
   * [Configurazione del Database Firebase](#configurazione-del-database-firebase)
   * [Configurazione Email (SMTP)](#configurazione-email-smtp)
5. [Esecuzione del Bot](#5-esecuzione-del-bot)
6. [Configurazione della Dashboard Web (GitHub Pages)](#6-configurazione-della-dashboard-web-github-pages)
7. [Automazione Quotidiana con GitHub Actions](#7-automazione-quotidiana-con-github-actions)

---

## 1. Prerequisiti
Assicurati di avere installato sul tuo computer:
* **Python** (versione 3.10 o superiore). Puoi scaricarlo da [python.org](https://www.python.org/).
* Un account **GitHub** (se desideri far girare l'automazione online in modo gratuito e automatico ogni giorno).

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

## 3. Configurazione del Profilo e dei Filtri

Prima di avviare il codice, devi spiegare all'AI chi sei e quali posizioni ti interessano:

1. **Il tuo Profilo (`my_profile.md`):**
   Apri il file [my_profile.md](my_profile.md) e sostituisci le informazioni esistenti con il tuo curriculum (esperienze, studi, competenze tecniche e soft skills) ed eventuali preferenze su settori ed aree geografiche. Gemini leggerà questo file per valutare la tua affinità con i lavori trovati.

2. **I Parametri Operativi (`config.yaml`):**
   Apri il file [config.yaml](config.yaml) e adatta le configurazioni alle tue necessità:
   * `preferences -> location`: La città o area di riferimento per le ricerche (es. `"Milan, Lombardy, Italy"`).
   * `scraper -> core_keywords`: Le parole chiave fisse che il bot controllerà ad ogni esecuzione prima di iniziare la ricerca dinamica.
   * `scraper -> jobs_target`: Numero totale di annunci che vuoi scaricare ed esaminare per sessione (es. 50 o 100).
   * `evaluation -> min_fit_score`: Il punteggio minimo (da 0 a 100) affinché un annuncio venga considerato valido ed incluso nel report email.

---

## 4. Configurazione dei Servizi e delle Variabili d'Ambiente (`.env`)

Il progetto si appoggia ad alcuni servizi esterni gratuiti (o con piani free generosi). Per farlo funzionare, devi creare un file chiamato `.env` nella cartella principale del progetto (puoi copiare il modello esistente rinominando `.env.example`).

Crea il file `.env` e compila le seguenti variabili:

```env
APIFY_API_TOKEN=il_tuo_token_apify_qui
GEMINI_API_KEY=la_tua_chiave_gemini_qui
TAVILY_API_KEY=la_tua_chiave_tavily_qui
EMAIL_SENDER=tua_email_mittente@gmail.com
EMAIL_PASSWORD=tua_app_password_senza_spazi
EMAIL_RECIPIENT=tua_email_destinatario@gmail.com
FIREBASE_SERVICE_ACCOUNT_JSON={"type": "service_account", "project_id": "...", ...}
```

### Ottenere le Chiavi API:
* **Apify (`APIFY_API_TOKEN`):** Crea un account gratuito su [Apify](https://apify.com/). Il bot utilizza l'Actor *LinkedIn Jobs Scraper* (ID: `hKByXkMQaC5Qt9UMN`). Il piano gratuito offre abbastanza crediti mensili per effettuare ricerche regolari.
* **Google Gemini (`GEMINI_API_KEY`):** Richiedi una chiave API gratuita accedendo a [Google AI Studio](https://aistudio.google.com/).
* **Tavily (`TAVILY_API_KEY`):** *(Opzionale)* Necessario solo se utilizzi lo scouting di startup (`startup_outreach.py`). Registrati gratuitamente su [Tavily](https://tavily.com/) per ottenere la chiave.

### Configurazione del Database Firebase:
I dati non vengono salvati localmente ma su un database cloud sicuro.
1. Crea un progetto gratuito su [Firebase Console](https://console.firebase.google.com/).
2. Nel menu laterale, clicca su **Build -> Firestore Database** e creane uno.
3. Vai in **Impostazioni Progetto** (icona a forma di ingranaggio in alto a sinistra) -> **Account di Servizio**.
4. Clicca su **Genera nuova chiave privata**. Verrà scaricato un file `.json` sul tuo computer.
5. Apri questo file `.json`, copia l'intero contenuto e incollalo **su una singola riga** (senza a capo) come valore di `FIREBASE_SERVICE_ACCOUNT_JSON` nel file `.env`.

### Configurazione Email (SMTP):
Il bot invia un riepilogo in formato HTML. 
* Se usi Gmail come `EMAIL_SENDER`:
  1. Vai sulle impostazioni di sicurezza del tuo account Google.
  2. Attiva la **Verifica in 2 passaggi**.
  3. Cerca **Password per le app** (App Passwords).
  4. Genera una nuova password temporanea, copiala e incollala in `EMAIL_PASSWORD` (senza spazi).

---

## 5. Esecuzione del Bot

Una volta configurato il file `.env`, puoi avviare gli script dal terminale:

* **Per avviare la ricerca di lavoro su LinkedIn:**
  ```bash
  python main.py
  ```
  *(Al termine dell'esecuzione riceverai un'email con le posizioni migliori sopra la soglia minima impostata).*

* **Per avviare lo scouting e l'outreach delle Startup:**
  ```bash
  python startup_outreach.py
  ```

---

## 6. Configurazione della Dashboard Web (GitHub Pages)

Il progetto include una comoda dashboard interattiva ospitata nella cartella `docs/` che mostra grafici, statistiche e tutti i lavori valutati.

Per utilizzare la tua dashboard:
1. Crea una "Web App" all'interno del tuo progetto Firebase (sempre da Impostazioni Progetto -> Generali -> Le tue app).
2. Copia l'oggetto di configurazione `firebaseConfig` che ti viene mostrato.
3. Apri il file [docs/index.html](docs/index.html), trova la riga `const firebaseConfig` (intorno alla riga 600) e sostituiscilo con i tuoi dati.
4. Su GitHub, vai in **Settings -> Pages** del tuo repository, seleziona come sorgente la cartella `/docs` dal branch `main` e salva. La tua dashboard sarà accessibile online pubblicamente all'indirizzo fornito da GitHub.

---

## 7. Automazione Quotidiana con GitHub Actions

Il file `.github/workflows/daily_scrape.yml` è già pronto per eseguire questa automazione in modo del tutto gratuito sui server di GitHub ogni mattina.

Per attivarlo sul tuo repository GitHub:
1. Vai su GitHub nelle impostazioni del tuo repository: **Settings -> Secrets and variables -> Actions**.
2. Clicca su **New repository secret** e crea un segreto per ciascuna delle variabili che hai configurato nel file `.env` locale:
   * `APIFY_API_TOKEN`
   * `GEMINI_API_KEY`
   * `TAVILY_API_KEY`
   * `EMAIL_SENDER`
   * `EMAIL_PASSWORD`
   * `EMAIL_RECIPIENT`
   * `FIREBASE_SERVICE_ACCOUNT_JSON` (incolla qui l'intero contenuto del file JSON scaricato da Firebase).
3. Il workflow si attiverà automaticamente ogni giorno alle ore 08:00 UTC (10:00 ora italiana). Puoi anche avviarlo manualmente in qualsiasi momento andando nella sezione **Actions** di GitHub, cliccando su "Daily LinkedIn Job Scraper" e premendo "Run workflow".
