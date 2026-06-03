import os
from firebase_admin import initialize_app, firestore
from firebase_functions import firestore_fn
from google import genai
from pydantic import BaseModel
import firebase_admin

# Lazy initialization for Firebase Admin to prevent deployment timeouts
def get_db():
    if not firebase_admin._apps:
        initialize_app()
    return firestore.client()

class JobEvaluation(BaseModel):
    fit_score: int
    reasoning: str
    highlighted_description: str
    compensation: str

def evaluate_job_with_gemini(job: dict, profile: str, liked_history: str = "", disliked_history: str = "") -> JobEvaluation:
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        raise ValueError("GEMINI_API_KEY non trovata nelle variabili d'ambiente (.env)")
        
    client = genai.Client(api_key=gemini_key)

    preferences_section = ""
    if liked_history or disliked_history:
        preferences_section = "\nPreferenze del candidato (basate sui feedback precedenti):\n"
        if liked_history:
            preferences_section += f"Lavori apprezzati (LIKE):\n{liked_history}\n"
        if disliked_history:
            preferences_section += f"Lavori scartati (DISLIKE):\n{disliked_history}\n"
        preferences_section += "Usa queste preferenze per influenzare il punteggio: alza il punteggio per lavori molto simili a quelli apprezzati e abbassalo drasticamente per lavori simili a quelli scartati.\n"

    prompt = f"""
Sei un technical recruiter esperto e un career coach.
Valuta l'aderenza del candidato alla seguente offerta di lavoro.

Profilo Candidato:
{profile}
{preferences_section}
Descrizione Lavoro:
Titolo: {job.get("title", "Unknown")}
Azienda: {job.get("companyName", "Unknown")}
Location: {job.get("location", "Unknown")}
Descrizione: {job.get("descriptionText", "")}

Istruzioni:
1. Valuta l'aderenza del candidato per questo ruolo e assegna un 'fit_score' da 0 a 100 usando il seguente sistema a FASCE (Tier):
   - Fascia Golden (90-100): Ruolo perfetto, seniority esatta.
   - Fascia A (80-89): Match eccellente. Il core focus del lavoro e le skill principali corrispondono al profilo.
   - Fascia B (70-79): Buon match. Esperienza pertinente ma manca un requisito.
   - Fascia Scarto (0-69): Fuori scope, seniority sbagliata o ruolo errato.
2. HARD RULE (CRITICO): Lavora SOLO IN ITALIA o remote. Se richiesta relocation all'estero, punteggio = 0.
3. Scrivi una 'reasoning' discorsiva e diretta di 2-3 righe IN ITALIANO. NON ripetere il background del candidato (lo conosce già!). Invece, CONTESTUALIZZA: fagli capire esattamente cosa farebbe nel pratico in questo ruolo, "dandogli un assaggio" delle responsabilità principali.
4. Restituisci la 'highlighted_description' copiando il testo della "Descrizione" originale (senza tagliarlo), ma inserendo dei tag HTML <mark>testo</mark> attorno alle parti più rilevanti, le responsabilità chiave e i requisiti cruciali.
5. Se la job description contiene informazioni sullo stipendio (es. RAL, compensation, hourly rate), estraile e inseriscile nel campo 'compensation', altrimenti lascialo vuoto.
"""
    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": JobEvaluation,
                "temperature": 0.1,
            },
        )
        return JobEvaluation.model_validate_json(response.text)
    except Exception as e:
        print(f"[!] ERRORE durante la valutazione con Gemini: {e}")
        return JobEvaluation(fit_score=0, reasoning=f"Errore di valutazione: {str(e)}", highlighted_description="", compensation="")

def get_preferences():
    # Ottieni i like/dislike dalla collezione jobs per preparare le preferenze
    db = get_db()
    jobs_ref = db.collection("jobs")
    liked_docs = jobs_ref.where(filter=firestore.FieldFilter("liked", "==", True)).order_by("timestamp", direction=firestore.Query.DESCENDING).limit(10).stream()
    disliked_docs = jobs_ref.where(filter=firestore.FieldFilter("liked", "==", False)).order_by("timestamp", direction=firestore.Query.DESCENDING).limit(10).stream()

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

@firestore_fn.on_document_updated(document="jobs/{jobId}", region="europe-west1")
def eval_job_on_demand(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot | None]]) -> None:
    if event.data is None or event.data.after is None:
        return

    after_data = event.data.after.to_dict()
    before_data = event.data.before.to_dict() if event.data.before else {}

    needs_eval_before = before_data.get("needs_evaluation", False)
    needs_eval_after = after_data.get("needs_evaluation", False)

    # Scatta solo se needs_evaluation passa da False/NonEsistente a True
    if needs_eval_after and not needs_eval_before:
        job_data = after_data.get("job_data", {})
        title = job_data.get("title", "Unknown Title")
        
        print(f"[*] Inizio valutazione on-demand per: {title}")
        
        try:
            # Carica il profilo da my_profile.md
            profile = ""
            profile_path = os.path.join(os.path.dirname(__file__), "my_profile.md")
            if os.path.exists(profile_path):
                with open(profile_path, "r", encoding="utf-8") as f:
                    profile = f.read()
            else:
                print("[-] my_profile.md non trovato, la valutazione potrebbe essere inaccurata.")
            
            liked_history, disliked_history = get_preferences()
            
            evaluation = evaluate_job_with_gemini(job_data, profile, liked_history, disliked_history)
            
            # Update
            event.data.after.reference.set({
                "fit_score": evaluation.fit_score,
                "reasoning": evaluation.reasoning,
                "highlighted_description": evaluation.highlighted_description,
                "compensation": evaluation.compensation,
                "needs_evaluation": firestore.DELETE_FIELD
            }, merge=True)
            
            print(f"[v] Valutazione completata per '{title}'. Fit Score: {evaluation.fit_score}")
            
        except Exception as e:
            print(f"[!] Errore durante eval_job_on_demand: {e}")
            event.data.after.reference.set({
                "needs_evaluation": firestore.DELETE_FIELD,
                "reasoning": f"Errore valutazione in Cloud Function: {e}"
            }, merge=True)
