import os
from firebase_admin import initialize_app, firestore
from firebase_functions import firestore_fn
from google import genai
from pydantic import BaseModel, field_validator
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
    compensation: str = ""

    @field_validator("compensation", mode="before")
    @classmethod
    def coerce_none_to_empty(cls, v):
        return v if v is not None else ""

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

    prompt = f"""Sei un technical recruiter esperto. Valuta l'aderenza del candidato all'offerta seguendo un processo RIGOROSO a 4 step.

Profilo Candidato:
{profile}
{preferences_section}
Offerta di Lavoro:
Titolo: {job.get("title", "Unknown")}
Azienda: {job.get("companyName", "Unknown")}
Location: {job.get("location", "Unknown")}
Descrizione: {job.get("descriptionText", "")}

═══ PROCESSO DI VALUTAZIONE (segui questi 4 step IN ORDINE) ═══

STEP 1 — HARD RULES CHECK
Il profilo contiene "Interested in" (tier: 🏆 GOLDEN BOOST, ⭐ BONUS FORTE, ✓ BONUS MODERATO) e "Not interested in" (tier: 🚫 ZERO, ⛔ BOCCIATURA, ⚠️ PENALITÀ, 📉 MALUS LEGGERO).
Controlla se il lavoro rientra in un elemento di "Not interested in":
- Se rientra nella fascia 🚫 ZERO → fit_score = 0, STOP.
- Se rientra nella fascia ⛔ BOCCIATURA → fit_score = massimo 40.
- Se rientra nella fascia ⚠️ PENALITÀ → annota la penalità (-15/-20 punti) da applicare dopo.
- Se rientra nella fascia 📉 MALUS LEGGERO → annota il malus (-5/-10 punti) da applicare dopo.

STEP 2 — SENIORITY & LOCATION
- Il lavoro deve essere in Lombardia (o ibrido/remote con sede in Lombardia). Se fuori Lombardia o estero → fit_score = 0.
- Esperienza richiesta:
  - 0-1 anni obbligatori → OK
  - Fino a 2 anni "preferibili" (NON obbligatori) → OK, score inalterato
  - 2+ anni OBBLIGATORI → fit_score = massimo 40 (bocciatura seniority)
  - 5+ anni anche solo preferibili → fit_score = massimo 40 (bocciatura seniority)

STEP 3 — VALUTAZIONE DIMENSIONALE (solo se superati step 1-2, parti da un base di 70)
Valuta queste 5 dimensioni IN ORDINE DI IMPORTANZA:

a) SENIORITY FIT (peso 30%): Il ruolo è adatto a un neolaureato magistrale con ~8 mesi di esperienza (6 mesi CFA Research Challenge + 2 mesi stage)?
   Entry-level/junior/neolaureato → +15 punti | Non specificato ma compatibile → +10 | Leggermente sopra → +5

b) SETTORE & AZIENDA (peso 25%): Controlla i tier in "Interested in":
   Match 🏆 GOLDEN BOOST → +12 | Match ⭐ BONUS FORTE → +8 | Match ✓ BONUS MODERATO → +5 | Neutro → +0

c) CULTURAL FIT (peso 20%): Cerca segnali nella job description:
   Team piccolo, ownership, autonomia, varietà → fino a +10 | Struttura rigida, ruolo esecutivo → fino a -5

d) CONTRATTO (peso 15%): Se indicato nella JD:
   Indeterminato → +5 | Apprendistato → +3 | Stage → +0 | Non specificato → +2

e) SKILL MATCH (peso 10%): Le competenze richieste corrispondono al profilo?
   Forte corrispondenza → +5 | Parziale → +2 | Nessuna → +0

STEP 4 — PUNTEGGIO FINALE
Somma: base 70 + bonus step 3 - eventuali penalità/malus step 1.
Verifica la fascia:
- Golden (90-100): eccelle su tutte le dimensioni
- Fascia A (80-89): eccelle su almeno 3/5 dimensioni
- Fascia B (70-79): buono ma 1-2 debolezze
- Scarto (50-69): 2+ debolezze importanti
- Bocciatura (0-40): hard rule o mismatch grave

═══ FORMATO OUTPUT ═══
- fit_score: intero 0-100
- reasoning: 2-3 righe IN ITALIANO, discorsive e dirette. NON ripetere il background del candidato (lo conosce già!). CONTESTUALIZZA: descrivi cosa farebbe nel pratico in questo ruolo. Se bocciato o penalizzato, spiega QUALE regola specifica ha causato la bocciatura/penalità.
- highlighted_description: copia il testo della "Descrizione" originale INTEGRALE (senza tagliarlo), inserendo tag HTML <mark>testo</mark> attorno alle parti più rilevanti, responsabilità chiave e requisiti cruciali.
- compensation: se la JD contiene info su stipendio (RAL, compensation, hourly rate), estraile. Altrimenti lascia vuoto.
"""
    import requests
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={gemini_key}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "fit_score": {"type": "INTEGER"},
                    "reasoning": {"type": "STRING"},
                    "highlighted_description": {"type": "STRING"},
                    "compensation": {"type": "STRING", "nullable": True}
                },
                "required": ["fit_score", "reasoning", "highlighted_description"]
            },
            "temperature": 0.1
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code != 200:
            raise Exception(f"API Error {resp.status_code}: {resp.text}")
        data = resp.json()
        text_response = data['candidates'][0]['content']['parts'][0]['text']
        return JobEvaluation.model_validate_json(text_response)
    except Exception as e:
        print(f"[!] ERRORE durante la valutazione con Gemini: {e}")
        return JobEvaluation(fit_score=0, reasoning=f"Errore HTTP API: {str(e)}", highlighted_description="", compensation="")

def get_preferences():
    # Ottieni i like/dislike dalla collezione jobs per preparare le preferenze
    db = get_db()
    jobs_ref = db.collection("jobs")
    liked_docs = jobs_ref.where(filter=firestore.FieldFilter("liked", "==", True)).limit(10).stream()
    disliked_docs = jobs_ref.where(filter=firestore.FieldFilter("liked", "==", False)).limit(10).stream()

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
            # Carica il profilo da Firestore
            profile = ""
            db = get_db()
            profile_doc = db.collection("app_state").document("profile").get()
            if profile_doc.exists:
                profile = profile_doc.to_dict().get("content", "")
            else:
                print("[-] Profilo non trovato su Firestore (app_state/profile), la valutazione potrebbe essere inaccurata.")
            
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
