import os
from firebase_admin import initialize_app, firestore
from firebase_functions import scheduler_fn
from google import genai
from pydantic import BaseModel, field_validator
import firebase_admin
import time

# Lazy initialization for Firebase Admin to prevent deployment timeouts
def get_db():
    if not firebase_admin._apps:
        initialize_app()
    return firestore.client()

class JobEvaluation(BaseModel):
    fit_score: int
    reasoning: str
    fit_score_reasoning: str = ""
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

═══ PROCESSO DI VALUTAZIONE ═══

STEP 1 — HARD RULES & SBARRAMENTI
Controlla scrupolosamente le categorie "Not interested in" nel Profilo Candidato (es. 🚫 ZERO, ⛔ BOCCIATURA).
Se la job description viola una di queste regole, applica la direttiva indicata nel profilo per quella categoria:
- Es. Se rientra in una categoria "ZERO", lo score finale è 0 (ferma la valutazione).
- Es. Se rientra in "BOCCIATURA", lo score finale non può superare il massimo indicato (es. 50).
ATTENZIONE: QUESTE REGOLI SONO INVIOLABILI. Non puoi ignorarle né applicare bonus extra per "salvare" un'offerta che viola una hard rule.

STEP 2 — CALCOLO DEI PUNTI DAL PROFILO (Base 70)
Se la job non è stata scartata allo step 1, parti da una base di 70 punti.
Leggi attentamente il Profilo Candidato e cerca match nella Job Description per TUTTE le preferenze indicate (es. "Interested in", seniority, contratto, skills).
- Per ogni match positivo, aggiungi il punteggio ESATTO indicato nel profilo per quella categoria (es. +10, +5, +2).
- Per ogni match negativo (es. MALUS, PENALITÀ), sottrai il punteggio ESATTO indicato nel profilo.
IMPORTANTE: NON inventare o applicare punteggi (es. +15, +3, -5) se non sono scritti nel testo del profilo. Il tuo compito è solo leggere i punti dal profilo e sommarli.
Calcola il subtotale: base 70 + bonus - malus = SUBTOTALE PROFILO.

STEP 3 — TUO GIUDIZIO PERSONALE (da -20 a +20)
Ora esprimi il TUO giudizio personale sulla job, al di là dei criteri espliciti nel profilo.
Assegna un punteggio intero compreso tra -20 e +20 basato sulla tua analisi complessiva. È ASSOLUTAMENTE VIETATO ASSEGNARE UN PUNTEGGIO FUORI DA QUESTO RANGE (es. +60 o -50 sono VIETATI).
Considera fattori come: red flag nascoste nella JD, tono dell'annuncio, opportunità di crescita, qualità dell'azienda, potenziale formativo, coerenza del ruolo, segnali positivi o negativi non catturati dai criteri del profilo.
Questo punteggio deve riflettere la tua opinione indipendente come recruiter esperto, MA NEL RISPETTO DEI LIMITI MATEMATICI.

STEP 4 — PUNTEGGIO FINALE (CALCOLO MATEMATICO E CAPPING)
1. Calcola il punteggio provvisorio: SUBTOTALE PROFILO (step 2) + TUO GIUDIZIO (step 3) = SCORE PROVVISORIO.
2. Applica i "cap" (sbarramenti) dello Step 1, se l'offerta ha violato qualche regola:
   - Se c'è una violazione "ZERO", il fit_score DEVE ESSERE 0.
   - Se c'è una "BOCCIATURA" (punteggio massimo 50), e lo SCORE PROVVISORIO è > 50, il fit_score DEVE ESSERE RIDOTTO A 50.
   - Altrimenti, fit_score = SCORE PROVVISORIO.
   
Esempio: Se lo score provvisorio è 80 ma c'è "Bending Spoons" (Bocciatura, max 50), il punteggio finale SARÀ 50. Non 80 e non 77. 50 esatto.
Verifica la fascia:
- Golden (90+): eccelle
- Fascia A (80-89): molto buono
- Fascia B (70-79): discreto
- Scarto (50-69): debole
- Bocciatura (0-40): non in target

═══ FORMATO OUTPUT (4 campi) ═══
- fit_score: intero (il punteggio finale dello step 4).
- reasoning: IN ITALIANO, testo DISCORSIVO (NO bullet points). Spiega brevemente di cosa si tratta questo ruolo.
- fit_score_reasoning: IN ITALIANO, ELENCO PUNTATO strutturato. Elenca i singoli fattori che hanno determinato il punteggio, SEPARANDO chiaramente i criteri del profilo dal tuo giudizio personale:
  * [Nome fattore dal profilo]: motivazione (+X come da profilo)
  * [Nome fattore dal profilo]: motivazione (-Y come da profilo)
  * Subtotale profilo: 70 base + X - Y = ZZ
  * 💡 Mio giudizio: [spiegazione sintetica di cosa ti ha convinto o preoccupato] (+/-N)
  * Punteggio finale: ZZ + N = XX
- highlighted_description: RISCRIVI E PRESERVA INTEGRALMENTE TUTTO il contenuto della "Descrizione" originale. È ASSOLUTAMENTE VIETATO RIASSUMERE O OMETTERE PARTI DI TESTO. Se ci sono lunghi paragrafi, devi riportarli tutti per intero senza tagliare nulla. Migliorane SOLO la formattazione per la MASSIMA LEGGIBILITÀ: aggiungi la punteggiatura mancante, usa ESCLUSIVAMENTE il simbolo '•' per gli elenchi puntati e usa il grassetto (tag HTML <b> o <strong>) per i titoli delle sezioni. È FONDAMENTALE che ogni titoletto in grassetto (es. <b>Descrizione:</b>) sia PRECEDUTO da due "a capo" (\n\n) e SEGUITO da un "a capo" (\n) in modo che non sia mai attaccato al testo adiacente. Infine, usa il tag HTML <mark> per evidenziare i passaggi specifici della descrizione che ritieni possano interessare di più al candidato (basandoti sul suo profilo).
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
                    "fit_score_reasoning": {"type": "STRING"},
                    "highlighted_description": {"type": "STRING"},
                    "compensation": {"type": "STRING", "nullable": True}
                },
                "required": ["fit_score", "reasoning", "fit_score_reasoning", "highlighted_description"]
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
        return JobEvaluation(fit_score=0, reasoning=f"Errore HTTP API: {str(e)}", fit_score_reasoning="", highlighted_description="", compensation="")

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

@scheduler_fn.on_schedule(schedule="* * * * *", region="europe-west1", timeout_sec=180)
def eval_pending_jobs(event: scheduler_fn.ScheduledEvent) -> None:
    db = get_db()
    
    # Prendi un batch di massimo 5 job che necessitano di valutazione (ridotto da 10 per evitare timeout)
    jobs_ref = db.collection("jobs").where(filter=firestore.FieldFilter("needs_evaluation", "==", True)).limit(5).stream()
    
    jobs_to_evaluate = list(jobs_ref)
    
    if not jobs_to_evaluate:
        return
        
    print(f"[*] Trovati {len(jobs_to_evaluate)} job da valutare. Inizio elaborazione batch...")
    
    # Carica il profilo e le preferenze una sola volta per il batch
    profile = ""
    profile_doc = db.collection("app_state").document("profile").get()
    if profile_doc.exists:
        profile = profile_doc.to_dict().get("content", "")
    else:
        print("[-] Profilo non trovato su Firestore (app_state/profile), la valutazione potrebbe essere inaccurata.")
    
    try:
        liked_history, disliked_history = get_preferences()
    except Exception as e:
        print(f"[-] Errore nel caricare le preferenze: {e}")
        liked_history, disliked_history = "", ""
    
    for idx, doc in enumerate(jobs_to_evaluate):
        data = doc.to_dict()
        job_data = data.get("job_data", {})
        title = job_data.get("title", "Unknown Title")
        
        print(f"  [{idx+1}/{len(jobs_to_evaluate)}] Valutazione in corso per: {title}")
        
        try:
            evaluation = evaluate_job_with_gemini(job_data, profile, liked_history, disliked_history)
            
            # Update del documento
            doc.reference.set({
                "fit_score": evaluation.fit_score,
                "reasoning": evaluation.reasoning,
                "fit_score_reasoning": evaluation.fit_score_reasoning,
                "highlighted_description": evaluation.highlighted_description,
                "compensation": evaluation.compensation,
                "needs_evaluation": firestore.DELETE_FIELD
            }, merge=True)
            
            print(f"  [v] Completato '{title}' -> Score: {evaluation.fit_score}")
            
        except Exception as e:
            print(f"  [!] Errore durante la valutazione di '{title}': {e}")
            doc.reference.set({
                "needs_evaluation": firestore.DELETE_FIELD,
                "reasoning": f"Errore valutazione in Cloud Function: {e}"
            }, merge=True)
            
        # Rate limiting pausa tra le chiamate (tranne l'ultima)
        if idx < len(jobs_to_evaluate) - 1:
            time.sleep(4.5)
            
    print("[*] Batch di valutazioni completato.")
