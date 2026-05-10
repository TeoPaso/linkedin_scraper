import os
import sys
from dotenv import load_dotenv

# Carica le variabili d'ambiente PRIMA di importare db
load_dotenv()

# Aggiunge la root del progetto al path per importare db.py correttamente
sys.path.append(os.getcwd())

import db

def clear_collection(collection_name):
    """Cancella tutti i documenti in una specifica collezione di Firestore."""
    print(f"Cancellazione collezione: {collection_name}...")
    docs = db.db.collection(collection_name).stream()
    count = 0
    batch = db.db.batch()
    for doc in docs:
        batch.delete(doc.reference)
        count += 1
        # Firestore accetta massimo 500 operazioni per batch
        if count % 400 == 0:
            batch.commit()
            batch = db.db.batch()
    if count % 400 != 0:
        batch.commit()
    print(f"Fatto! Eliminati {count} documenti.")

def main():
    load_dotenv()
    print("\n--- LinkedIn Scraper DB Cleaner ---")
    print("Questo script pulirà i dati dal tuo database Firestore.")
    print("-----------------------------------")
    print("1. Cancella solo Cronologia Ricerche (search_memory) e Reset Ciclo")
    print("2. Cancella TUTTO (Jobs, Categorie, Ricerche, Ciclo)")
    print("3. Annulla")
    
    choice = input("\nScegli un'opzione (1/2/3): ")
    
    if choice == "1":
        confirm = input("Vuoi resettare la cronologia? Le statistiche della dashboard torneranno a zero. (SÌ/No): ")
        if confirm.upper() == "SÌ":
            clear_collection("search_memory")
            print("Reset stato ciclo keyword...")
            db.db.collection("app_state").document("keyword_cycle").delete()
            print("\nCronologia e ciclo resettati correttamente.")
        else:
            print("Operazione annullata.")
            
    elif choice == "2":
        print("\nATTENZIONE: Questa opzione cancellerà TUTTI i lavori salvati, le categorie e le ricerche.")
        confirm = input("Sei SICURO di voler procedere? Scrivi 'SÌ' per confermare: ")
        if confirm.upper() == "SÌ":
            clear_collection("search_memory")
            clear_collection("job_categories")
            clear_collection("jobs")
            print("Reset stato ciclo keyword...")
            db.db.collection("app_state").document("keyword_cycle").delete()
            print("\nDatabase completamente svuotato.")
        else:
            print("Operazione annullata.")
    else:
        print("Operazione annullata.")

if __name__ == "__main__":
    main()
