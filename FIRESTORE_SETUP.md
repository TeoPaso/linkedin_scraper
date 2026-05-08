# Migrazione a Firebase Firestore & GitHub Pages

Questa guida ti accompagna passo-passo nella configurazione di Firebase per ospitare lo storage del tuo scraper e della nuova dashboard live su GitHub Pages.

## 1. Crea e configura il progetto Firebase

1. Vai alla [Firebase Console](https://console.firebase.google.com/).
2. Clicca su **Aggiungi progetto** e dagli un nome (es. `linkedin-scraper-db`).
3. (Opzionale) Disabilita Google Analytics, non ti servirà per questo progetto.
4. Clicca su **Crea progetto**.

## 2. Abilita Firestore Database

1. Nel menu a sinistra della console Firebase, sotto la sezione **Build**, clicca su **Firestore Database**.
2. Clicca su **Crea database**.
3. Scegli un ID e una Location per il database (es. `eur3 (Europe)`).
4. Seleziona **Avvia in modalità produzione** (imposteremo le regole corrette tra un attimo).

## 3. Imposta le Security Rules di Firestore

1. Sempre nella schermata di Firestore Database, vai nel tab **Regole** (Rules).
2. Sostituisci il contenuto esistente con le seguenti regole:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /jobs/{jobId} {
      allow read: if true;
      allow update: if request.resource.data.diff(resource.data).affectedKeys().hasOnly(['applied']);
      allow create, delete: if false;
    }
    match /search_memory/{docId} {
      allow read: if true;
      allow write: if false;
    }
    match /job_categories/{docId} {
      allow read: if true;
      allow write: if false;
    }
  }
}
```

3. Clicca su **Pubblica**.
> *Queste regole permettono a chiunque acceda alla Dashboard di leggere i dati (poiché è un sito statico senza login), ma limitano la scrittura UNICAMENTE al campo `applied` dei lavori, impedendo alterazioni malevole ai dati dello scraper.*

## 4. Genera il Service Account per GitHub Actions (Scrittura Backend)

Lo scraper che gira su GitHub Actions necessita di pieni privilegi per scrivere e sovrascrivere tutto il database. Per farlo usa l'Admin SDK.

1. In alto a sinistra nella console Firebase, clicca sull'icona a forma di **ingranaggio** (accanto a *Panoramica del progetto*) e scegli **Impostazioni progetto**.
2. Vai nel tab **Account di servizio**.
3. Assicurati che sia selezionato "Node.js" o "Python" e clicca sul pulsante **Genera nuova chiave privata**.
4. Ti verrà scaricato un file `.json` (es. `linkedin-scraper-firebase-adminsdk-xxxxx.json`). Apri questo file con un editor di testo: il suo contenuto è il tuo *Service Account*.

## 5. Aggiungi il Secret su GitHub

1. Vai nel tuo repository su GitHub.
2. Vai in **Settings** > **Secrets and variables** > **Actions**.
3. Clicca su **New repository secret**.
4. **Name**: `FIREBASE_SERVICE_ACCOUNT_JSON`
5. **Secret**: *(Incolla l'INTERO CONTENUTO del file `.json` scaricato al punto 4)*.
6. Clicca su **Add secret**.

## 6. Ottieni la Firebase Web Config e aggiorna la Dashboard

Ora dobbiamo dire alla tua dashboard in `docs/index.html` a quale database collegarsi per leggere i dati.

1. Ritorna in Firebase Console > **Impostazioni progetto** (icona ingranaggio).
2. Nel tab **Generale**, scorri in basso fino alla sezione "Le tue app".
3. Clicca sull'icona **</>** (Web) per aggiungere un'app web.
4. Scegli un nickname (es. `scraper-dashboard`) e clicca su **Registra app**.
5. Apparirà un blocco di codice contenente un oggetto `firebaseConfig`. Apparirà simile a questo:
   ```javascript
   const firebaseConfig = {
     apiKey: "AIzaSyB...",
     authDomain: "tuo-progetto.firebaseapp.com",
     projectId: "tuo-progetto",
     storageBucket: "tuo-progetto.firebasestorage.app",
     messagingSenderId: "1234567890",
     appId: "1:1234567890:web:abcd1234efgh"
   };
   ```
6. Copia questo oggetto.
7. Nel tuo repository in locale, apri il file **`docs/index.html`** e cerca la stringa `// REPLACE WITH YOUR FIREBASE CONFIG`.
8. Sostituisci l'oggetto fittizio `const firebaseConfig = { ... };` con quello reale che hai appena copiato.
> *È normale e sicuro mettere queste informazioni in un sito statico. Le regole di sicurezza configurate al Punto 3 impediscono alle persone di abusare del tuo database.*

## 7. Configura GitHub Pages

Tutto è pronto. Ora pubblichiamo la Dashboard.

1. Fai il commit e il push dei tuoi cambiamenti sul branch `main`.
2. Vai nel tuo repository su GitHub.
3. Vai in **Settings** > **Pages**.
4. Sotto **Build and deployment** > **Source**, seleziona **Deploy from a branch**.
5. Sotto **Branch**, seleziona `main` e dal menù a tendina adiacente (dove probabilmente c'è scritto `/ (root)`), seleziona `/docs`.
6. Clicca su **Save**.
7. Aspetta circa 1-2 minuti. In alto nella pagina Pages, o controllando la tab "Actions" di GitHub, vedrai l'URL della tua nuova Dashboard live!

## 🎉 Finito!

Ora il sistema salverà ogni iterazione direttamente nel cloud Firebase e la dashboard visualizzerà sempre i dati aggiornati in tempo reale all'apertura, senza mai più intasare il repository con file JSON che cambiano continuamente. E potrai cliccare su "Candidatura" per tenere traccia delle offerte a cui hai già risposto!
