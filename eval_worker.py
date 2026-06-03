import os
import time
import threading
from dotenv import load_dotenv
from google.cloud import firestore

load_dotenv()
import db
from main import load_config, load_profile, evaluate_job_with_gemini

# Carica configurazione e profilo in memoria
config = load_config("config.yaml")
profile = load_profile("my_profile.md")

def get_preferences():
    """Recupera la storia dei like/dislike aggiornata per influenzare il prompt."""
    job_store = db.load_job_store()
    liked_jobs = [data for url, data in job_store.items() if data.get("liked") is True]
    disliked_jobs = [data for url, data in job_store.items() if data.get("liked") is False]

    liked_history = ""
    for j in sorted(liked_jobs, key=lambda x: x.get("timestamp", ""), reverse=True)[:10]:
        t = j.get("job_data", {}).get("title", "")
        c = j.get("job_data", {}).get("companyName", "")
        d = j.get("job_data", {}).get("descriptionText", "")[:300]
        liked_history += f"- {t} presso {c}. (Snippet: {d}...)\n"

    disliked_history = ""
    for j in sorted(disliked_jobs, key=lambda x: x.get("timestamp", ""), reverse=True)[:10]:
        t = j.get("job_data", {}).get("title", "")
        c = j.get("job_data", {}).get("companyName", "")
        d = j.get("job_data", {}).get("descriptionText", "")[:300]
        disliked_history += f"- {t} presso {c}. (Snippet: {d}...)\n"
        
    return liked_history, disliked_history

def on_snapshot(col_snapshot, changes, read_time):
    """Callback richiamata da Firestore quando un documento cambia."""
    for change in changes:
        if change.type.name in ['ADDED', 'MODIFIED']:
            data = change.document.to_dict()
            if data.get("needs_evaluation") is True:
                title = data.get('job_data', {}).get('title', 'Unknown')
                print(f"[*] Richiesta valutazione intercettata per: {title}")
                # Esegue la valutazione in un thread separato per non bloccare il listener
                threading.Thread(target=process_evaluation, args=(change.document.id, data)).start()

def process_evaluation(doc_id, data):
    """Esegue la chiamata a Gemini e aggiorna il DB."""
    job_data = data.get("job_data", {})
    title = job_data.get("title", "Unknown Title")
    company = job_data.get("companyName", "Unknown Company")
    
    print(f"  [-] Avvio valutazione Gemini per: {title} @ {company}...")
    
    try:
        liked_history, disliked_history = get_preferences()
        evaluation = evaluate_job_with_gemini(job_data, profile, liked_history, disliked_history)
        
        # Aggiorna il documento rimuovendo il flag e inserendo i nuovi dati
        doc_ref = db.db.collection("jobs").document(doc_id)
        doc_ref.set({
            "fit_score": evaluation.fit_score,
            "reasoning": evaluation.reasoning,
            "highlighted_description": evaluation.highlighted_description,
            "compensation": evaluation.compensation,
            "needs_evaluation": firestore.DELETE_FIELD
        }, merge=True)
        
        print(f"  [v] Valutazione completata per '{title}'! Score: {evaluation.fit_score}/100")
    except Exception as e:
        print(f"  [!] Errore durante la valutazione di '{title}': {e}")
        # In caso di errore, disattiva il flag per evitare loop infiniti
        try:
            doc_ref = db.db.collection("jobs").document(doc_id)
            doc_ref.set({
                "needs_evaluation": firestore.DELETE_FIELD,
                "reasoning": f"Errore valutazione manuale: {e}"
            }, merge=True)
        except Exception as inner_e:
            pass

if __name__ == '__main__':
    print("[*] Avvio eval_worker.py in ascolto continuo...")
    print("[*] In attesa di richieste di valutazione dall'interfaccia UI...")
    
    # Crea una query che ascolta i cambiamenti sui documenti con needs_evaluation = True
    col_query = db.db.collection("jobs").where(filter=firestore.FieldFilter("needs_evaluation", "==", True))
    
    # Aggiungi il listener asincrono
    query_watch = col_query.on_snapshot(on_snapshot)
    
    try:
        # Tieni in vita il thread principale
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Uscita e spegnimento listener...")
