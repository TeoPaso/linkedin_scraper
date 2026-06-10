import os
import sys
from dotenv import load_dotenv

# Load env variables before importing db, since db.py initializes Firebase on import
load_dotenv()

import db
from main import evaluate_job_with_gemini, JobEvaluation

from firebase_admin import firestore

def get_preferences():
    liked_docs = db.db.collection("jobs").where(filter=firestore.FieldFilter("liked", "==", True)).limit(10).stream()
    disliked_docs = db.db.collection("jobs").where(filter=firestore.FieldFilter("liked", "==", False)).limit(10).stream()

    liked_history = ""
    for doc in liked_docs:
        d = doc.to_dict()
        t = d.get("job_data", {}).get("title", "")
        c = d.get("job_data", {}).get("companyName", "")
        desc = d.get("job_data", {}).get("descriptionText", "")[:300]
        liked_history += f"- {t} presso {c}. (Snippet: {desc}...)\n"

    disliked_history = ""
    for doc in disliked_docs:
        d = doc.to_dict()
        t = d.get("job_data", {}).get("title", "")
        c = d.get("job_data", {}).get("companyName", "")
        desc = d.get("job_data", {}).get("descriptionText", "")[:300]
        disliked_history += f"- {t} presso {c}. (Snippet: {desc}...)\n"
        
    return liked_history, disliked_history

def main():
    print("[*] Avvio valutazione job in sospeso...")
    
    # Identify pending jobs efficiently
    pending_docs = db.db.collection("jobs").where(filter=firestore.FieldFilter("needs_evaluation", "==", True)).limit(50).stream()
    pending_jobs = {}
    for doc in pending_docs:
        d = doc.to_dict()
        url = d.get("url")
        if url:
            pending_jobs[url] = d
    
    
    if not pending_jobs:
        print("[*] Nessun job in sospeso trovato.")
        return
        
    print(f"[*] Trovati {len(pending_jobs)} job da valutare.")
    
    profile = db.load_profile_from_db()
    if not profile:
        print("[!] Attenzione: Profilo non trovato su Firestore. I job verranno marcati con errore.")
        
    liked_history, disliked_history = get_preferences()
    
    count = 0
    
    for url, data in pending_jobs.items():
        job_data = data.get("job_data", {})
        title = job_data.get("title", "Unknown")
        print(f"  [{count+1}/{len(pending_jobs)}] Valutazione in corso per: {title}")
        
        try:
            if not profile:
                evaluation = JobEvaluation(
                    fit_score=0,
                    reasoning="Errore: Profilo non trovato su Firebase. Impossibile effettuare la valutazione.",
                    fit_score_reasoning="* [Errore Sistema]: Il profilo utente non è stato trovato su Firebase. Aggiungi il tuo profilo tramite la Dashboard per abilitare le valutazioni AI.",
                    highlighted_description=job_data.get("descriptionText", ""),
                    compensation=""
                )
            else:
                evaluation = evaluate_job_with_gemini(job_data, profile, liked_history, disliked_history)
            
            # Update payload
            data["fit_score"] = evaluation.fit_score
            data["reasoning"] = evaluation.reasoning
            data["fit_score_reasoning"] = evaluation.fit_score_reasoning
            data["highlighted_description"] = evaluation.highlighted_description
            data["compensation"] = evaluation.compensation
            data["needs_evaluation"] = firestore.DELETE_FIELD
            
            db.save_single_job(url, data)
            print(f"  [v] Completato '{title}' -> Score: {evaluation.fit_score}")
            
        except Exception as e:
            print(f"  [!] Errore durante la valutazione di '{title}': {e}")
            data["needs_evaluation"] = firestore.DELETE_FIELD
            data["reasoning"] = f"Errore script Python in background: {e}"
            db.save_single_job(url, data)
            
        count += 1
        
    print("[*] Valutazioni completate.")

if __name__ == "__main__":
    main()
