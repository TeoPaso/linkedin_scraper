import os
import sys
import json
import yaml
import argparse
import urllib.parse
from datetime import datetime, timezone
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import concurrent.futures
import copy

from google import genai
from pydantic import BaseModel, field_validator
import time
from dotenv import load_dotenv

load_dotenv()
import db


class JobEvaluation(BaseModel):
    fit_score: int
    reasoning: str
    fit_score_reasoning: str = ""
    highlighted_description: str = ""
    compensation: str = ""

    @field_validator("compensation", mode="before")
    @classmethod
    def coerce_none_to_empty(cls, v):
        return v if v is not None else ""


def load_config(path: str) -> dict:
    """Carica la configurazione yaml."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_profile(path: str) -> str:
    """Carica il profilo markdown del candidato."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()



def get_gemini_client():
    use_vertex = os.environ.get("USE_VERTEX_AI", "false").lower() == "true"
    if use_vertex:
        sa_json_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        if sa_json_str:
            import tempfile, json
            cred_dict = json.loads(sa_json_str)
            project_id = cred_dict.get("project_id")
            
            # Scrivi un file temporaneo per le credenziali ADC se non esiste già
            if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
                fd, path = tempfile.mkstemp(suffix=".json")
                with os.fdopen(fd, 'w') as temp_f:
                    temp_f.write(sa_json_str)
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
                
            location = os.environ.get("VERTEX_LOCATION", "us-central1")
            return genai.Client(vertexai=True, project=project_id, location=location)
        else:
            raise ValueError("FIREBASE_SERVICE_ACCOUNT_JSON mancante per l'autenticazione a Vertex AI")
    else:
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if not gemini_key:
            raise ValueError("GEMINI_API_KEY mancante.")
        return genai.Client(api_key=gemini_key)


def generate_single_search_query(
    profile: str, config: dict, search_memory: list
) -> dict:
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        print("ERRORE: Variabile d'ambiente GEMINI_API_KEY non impostata.")
        sys.exit(1)

    client = genai.Client(api_key=gemini_key)

    memory_summary = ""
    if search_memory:
        memory_summary = "Ricerche precedenti (con risultati):\n"
        for mem in search_memory[-40:]:
            avg = mem.get("avg_fit_score")
            avg_str = f"{avg}/100" if avg is not None else "non valutato"
            memory_summary += (
                f'- "{mem.get("keyword")}" → '
                f"{mem.get('jobs_new_unique', 0)} job unici, "
                f"fit score medio: {avg_str}, "
                f"titoli trovati: {mem.get('top_titles', [])}\n"
            )

    prompt = f"""
Sei un recruiter specializzato che aiuta candidati a trovare posizioni ad alto fit.
Il tuo obiettivo è generare UNA SOLA keyword di ricerca LinkedIn estremamente precisa e mirata.

Profilo del candidato:
{profile}

Ricerche già effettuate (NON ripetere nessuna di queste, né variazioni simili):
{memory_summary}

REGOLE OBBLIGATORIE per la keyword:
1. DEVI generare SEMPRE UN SOLO job title preciso. NON USARE MAI l'operatore "OR" o le doppie virgolette.
   La query deve essere una singola stringa pulita.
   CORRETTO: Venture Capital Analyst
   CORRETTO: FP&A Analyst
   SBAGLIATO: "Venture Capital Analyst"
   SBAGLIATO: Strategic Finance Analyst OR Corporate Development
2. Scegli titoli il più specifici possibile per il profilo del candidato. Titoli generici come
   "Business Analyst" o "Financial Analyst" da soli producono risultati troppo eterogenei — evitali
   a meno che non siano accompagnati da un modificatore (es. "Junior Financial Analyst", "Strategy Analyst").
3. NON usare mai nomi di tecnologie, linguaggi o tool (no "Python", "Power BI", "Excel").
4. Guarda i top_titles delle ricerche precedenti: se una keyword ha prodotto titoli lontani
   dal profilo (es. "Regional Sales Manager", "Customer Marketing"), quella direzione è da evitare.
5. Ogni nuova keyword deve esplorare un'area DIVERSA da quelle già coperte.

DEVI RESTITUIRE SOLO questo JSON, senza testo aggiuntivo:
{{
  "keywords": "un singolo job title preciso",
  "reasoning": "una frase in italiano che spiega perché questa keyword è mirata per questo profilo"
}}
"""
    try:
        time.sleep(4.5)  # Limit to 15 RPM
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0.2},
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"[!] ERRORE durante la generazione della query con Gemini: {e}")
        return {"keywords": "", "reasoning": ""}


def construct_linkedin_url(
    params: dict, location: str, time_filter: str = "r604800"
) -> str:
    """Costruisce un URL di ricerca per LinkedIn basandosi sui parametri."""
    base_url = "https://www.linkedin.com/jobs/search/?"
    query_params = {}
    if params.get("keywords"):
        query_params["keywords"] = params["keywords"]

    if location:
        query_params["location"] = location

    if time_filter:
        query_params["f_TPR"] = time_filter

    return base_url + urllib.parse.urlencode(query_params)


def scrape_jobs(query_params: dict, config: dict, apify_usage: dict) -> list:
    """Lancia l'Actor di Apify per lo scraping dei job post usando il pool di chiavi."""
    from apify_pool import get_next_client, report_usage, report_error
    
    try:
        client, account_id = get_next_client(apify_usage)
    except RuntimeError as e:
        print(f"[!] ERRORE FATALE: {e}")
        return []

    time_filter = config.get("scraper", {}).get("time_filter", "r604800")
    location = config.get("preferences", {}).get("location", "Milan, Lombardy, Italy")
    url = construct_linkedin_url(query_params, location, time_filter)
    print(f"[*] Avvio scraper su URL: {url} (usando Account #{account_id})")

    run_input = {
        "urls": [url],
        "count": config.get("scraper", {}).get("count_per_search", 25),
        "scrapeCompany": config.get("scraper", {}).get("scrape_company", False),
    }

    try:
        run = client.actor("hKByXkMQaC5Qt9UMN").call(run_input=run_input)
        dataset_id = run["defaultDatasetId"]

        items = client.dataset(dataset_id).list_items().items
        jobs_returned = len(items)
        
        # Registra l'utilizzo per fatturazione
        report_usage(account_id, jobs_returned, apify_usage)
        
        print(
            f"[*] Scraper completato. Trovati {jobs_returned} job post per la query corrente. "
            f"Account #{account_id} totale consumato: {apify_usage['accounts'][account_id]['total_jobs_returned']}"
        )
        return items
    except Exception as e:
        print(f"[!] ERRORE durante l'esecuzione di Apify: {e}")
        report_error(account_id, apify_usage)
        return []


def evaluate_job_with_gemini(
    job: dict, profile: str, liked_history: str = "", disliked_history: str = ""
) -> JobEvaluation:
    """Valuta il fit tra l'offerta di lavoro e il profilo del candidato usando Gemini."""
    gemini_key = os.environ.get("GEMINI_API_KEY")
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
Se l'intera offerta di lavoro (incluso Titolo, Azienda, Location o Descrizione) viola una di queste regole, applica la direttiva indicata nel profilo per quella categoria:
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
  * 🚨 [HARD RULES]: [OBBLIGATORIO: scrivi "Nessuna violazione" oppure "Violazione rilevata: {motivo} -> applico {conseguenza}"]
  * [Nome fattore dal profilo]: motivazione (+X come da profilo)
  * [Nome fattore dal profilo]: motivazione (-Y come da profilo)
  * Subtotale profilo: 70 base + X - Y = ZZ
  * 💡 Mio giudizio: [spiegazione sintetica di cosa ti ha convinto o preoccupato] (+/-N)
  * Punteggio finale: ZZ + N = XX
- highlighted_description: RISCRIVI E PRESERVA INTEGRALMENTE TUTTO il contenuto della "Descrizione" originale. È ASSOLUTAMENTE VIETATO RIASSUMERE O OMETTERE PARTI DI TESTO. Se ci sono lunghi paragrafi, devi riportarli tutti per intero senza tagliare nulla. Migliorane SOLO la formattazione per la MASSIMA LEGGIBILITÀ: aggiungi la punteggiatura mancante, usa ESCLUSIVAMENTE il simbolo '•' per gli elenchi puntati e usa il grassetto (tag HTML <b> o <strong>) per i titoli delle sezioni. È FONDAMENTALE che ogni titoletto in grassetto (es. <b>Descrizione:</b>) sia PRECEDUTO da due "a capo" (\n\n) e SEGUITO da un "a capo" (\n) in modo che non sia mai attaccato al testo adiacente. Infine, usa il tag HTML <mark> per evidenziare i passaggi specifici della descrizione che ritieni possano interessare di più al candidato (basandoti sul suo profilo).
- compensation: se la JD contiene info su stipendio (RAL, compensation, hourly rate), estraile. Altrimenti lascia vuoto.
"""
    try:
        time.sleep(4.5)  # Limit to 15 RPM
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
        return JobEvaluation(fit_score=0, reasoning=f"Errore di valutazione: {str(e)}")

def process_and_evaluate_job(url: str, job_store: dict, profile: str, liked_history: str, disliked_history: str):
    """Esegue la valutazione in background e salva su db."""
    data = job_store.get(url)
    if not data or data.get("fit_score") is not None:
        return
    
    job_data = data["job_data"]
    title = job_data.get("title", "Unknown Title")
    company = job_data.get("companyName", "Unknown Company")
    
    print(f"  [Background] Valutazione: {title} @ {company}...")
    evaluation = evaluate_job_with_gemini(job_data, profile, liked_history, disliked_history)
    
    data["fit_score"] = evaluation.fit_score
    data["reasoning"] = evaluation.reasoning
    data["fit_score_reasoning"] = evaluation.fit_score_reasoning
    data["highlighted_description"] = evaluation.highlighted_description
    data["compensation"] = evaluation.compensation
    
    db.save_single_job(url, data)
    print(f"  [Background] -> Score {evaluation.fit_score} ({title})")

def categorize_jobs_with_gemini(
    uncategorized_jobs: dict, current_categories: list
) -> dict:
    if not uncategorized_jobs:
        return {"job_labels": {}, "new_categories": []}

    gemini_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=gemini_key)

    jobs_text = ""
    for i, (url, job) in enumerate(uncategorized_jobs.items()):
        title = job.get("title", "Unknown")
        company = job.get("companyName", "Unknown")
        desc = job.get("descriptionText", "")[:300]
        jobs_text += f"URL: {url}\nTitolo: {title}\nAzienda: {company}\nSnippet Descrizione: {desc}...\n---\n"

    # Convert current categories to list of labels for prompt
    cat_labels = [
        c["label"] for c in current_categories if isinstance(c, dict) and "label" in c
    ]

    prompt = f"""
Sei un HR esperto nel categorizzare le offerte di lavoro.
Hai a disposizione le seguenti categorie attuali (labels): {cat_labels}

Ecco una lista di offerte di lavoro non ancora categorizzate:
{jobs_text}

Istruzioni:
1. Assegna ogni lavoro a una delle categorie attuali, se pertinente.
2. Se nessuna delle categorie attuali è pertinente per un lavoro, crea una NUOVA categoria. Evita di creare troppe categorie specifiche; raggruppa in macro-aree (es. "Data Analytics", "Finance", "Marketing & Sales", "Operations").
3. Restituisci una mappa "job_labels" dove le chiavi sono gli URL dei lavori e i valori le categorie (stringhe).
4. Restituisci una lista "new_categories" contenente OGGETTI JSON per le nuove categorie create (con "label" e "description"). Non includere categorie che esistevano già.

DEVI RESTITUIRE UN OGGETTO JSON ESATTAMENTE CON QUESTA STRUTTURA:
{{
  "job_labels": {{"URL_DEL_LAVORO": "NOME CATEGORIA"}},
  "new_categories": [
    {{"label": "NOME NUOVA CATEGORIA", "description": "Breve descrizione di 1 frase"}}
  ]
}}
"""
    try:
        time.sleep(4.5)  # Limit to 15 RPM
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0.1},
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"[!] ERRORE durante la categorizzazione con Gemini: {e}")
        return {"job_labels": {}, "new_categories": []}


def send_email_report(matched_jobs: list, metrics: dict, config: dict, apify_usage: dict = None):
    """Invia un'email di recap se ci sono offerte interessanti."""
    if not config.get("email", {}).get("send_email", True):
        return

    sender = os.environ.get("EMAIL_SENDER")
    password = os.environ.get("EMAIL_PASSWORD")
    recipient = os.environ.get("EMAIL_RECIPIENT")

    if not sender or not password or not recipient:
        print("[!] Credenziali email mancanti, salto invio email.")
        return

    today_str = datetime.now().strftime("%d/%m/%Y")

    total_matched = metrics.get("total_above_threshold", 0)
    total_found = metrics.get("total_found", 0)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"LinkedIn Job Report — {today_str} — {total_matched} job matched/{total_found} trovati"
    )
    msg["From"] = sender
    msg["To"] = recipient

    html_content = f"""
    <html>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; max-width: 800px; margin: auto;">
        <h2 style="color: #0a66c2; border-bottom: 2px solid #0a66c2; padding-bottom: 10px;">LinkedIn Job Report</h2>
        
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #0a66c2;">
            <table style="width: 100%; border-collapse: collapse;">
                <tr><td style="padding: 4px 0; width: 60%;"><strong>Totale offerte passate al setaccio (inclusi duplicati passati):</strong></td><td>{total_found}</td></tr>
                <tr><td style="padding: 4px 0;"><strong>Nuovi job effettivamente analizzati oggi (il tuo Target):</strong></td><td>{metrics.get("new_jobs_today", "N/A")}</td></tr>
                <tr><td style="padding: 4px 0;"><strong>Nuovi job promossi (Sopra la soglia Min Fit):</strong></td><td>{total_matched}</td></tr>
                <tr><td style="padding: 4px 0;"><strong>Iterazioni effettuate:</strong></td><td>{metrics.get("iterations", 0)}</td></tr>
                <tr><td style="padding: 4px 0;"><strong>Keyword migliore:</strong></td><td><code>{metrics.get("best_keyword", "N/A")}</code></td></tr>
                <tr><td style="padding: 4px 0;"><strong>Fit score medio:</strong></td><td>{round(metrics.get("avg_fit_score", 0), 1)}/100</td></tr>
            </table>
        </div>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
    """

    if not matched_jobs:
        html_content += "<p style='color: #666; font-style: italic;'>Nessuna nuova offerta ha superato la soglia minima per oggi.</p>"
    else:
        top_picks = [j for j in matched_jobs if j["score"] >= 80]
        other_valid = [j for j in matched_jobs if j["score"] < 80]

        def generate_job_html(item):
            job = item["job"]
            title = job.get("title", "Titolo Sconosciuto")
            company = job.get("companyName", "Azienda Sconosciuta")
            url = job.get("link", "#")
            score = item["score"]
            reasoning = item["reasoning"]

            if score >= 90:
                icon = "🏆"
                color = "#b8860b" # dark gold for text
                border_color = "#ffd700"
                bg_color = "#fffdf0"
            elif score >= 80:
                icon = "⭐"
                color = "#2e7d32"
                border_color = "#2e7d32"
                bg_color = "#f2fcf3"
            elif score >= 70:
                icon = "✓"
                color = "#f57c00"
                border_color = "#e0e0e0"
                bg_color = "#ffffff"
            else:
                icon = "❌"
                color = "#d32f2f"
                border_color = "#e0e0e0"
                bg_color = "#ffffff"

            return f"""
            <div style="margin-bottom: 25px; padding: 20px; border: 1px solid {border_color}; border-radius: 8px; background-color: {bg_color}; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <h3 style="margin-top: 0; margin-bottom: 8px; font-size: 18px;">
                    <span style="margin-right: 5px;">{icon}</span>
                    <a href="{url}" style="color: #0a66c2; text-decoration: none;">{title}</a> 
                    <span style="color: #666; font-weight: normal; font-size: 16px;">presso {company}</span>
                    <span style="float: right; font-size: 14px; font-weight: 600; color: {color};">Score: {score}/100</span>
                </h3>
                <div style="padding-top: 8px;">
                    <span style="color: #555; font-size: 14px; line-height: 1.5;">{reasoning}</span>
                </div>
            </div>
            """

        if top_picks:
            html_content += "<h3>🏆 Top Picks (Fascia A & Golden)</h3><div style='margin-top: 20px;'>"
            for item in top_picks:
                html_content += generate_job_html(item)
            html_content += "</div>"
        
        if other_valid:
            html_content += "<hr style='border: 0; border-top: 1px dashed #ccc; margin: 30px 0;'>"
            html_content += "<h3>✓ Altre Posizioni Valide (Fascia B)</h3><div style='margin-top: 20px;'>"
            for item in other_valid:
                html_content += generate_job_html(item)
            html_content += "</div>"

    dashboard_url = os.environ.get("DASHBOARD_URL", "https://teopaso.github.io/linkedin_scraper/")

    html_content += f"""
        <p style="font-size: 14px; color: #888; text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #eaeaea;">
            Report completo e stato API disponibili nella <a href="{dashboard_url}" style="color: #0a66c2; text-decoration: none; font-weight: bold;">Dashboard</a>.
        </p>
    """

    html_content += """
    </body>
    </html>
    """


    msg.attach(MIMEText(html_content, "html"))

    try:
        print(f"[*] Invio email a {recipient}...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        print("[*] Email inviata con successo!")
    except Exception as e:
        print(f"[!] ERRORE durante l'invio dell'email: {e}")


def deep_merge(base: dict, update: dict) -> dict:
    """Esegue un merge ricorsivo di due dizionari."""
    for key, value in update.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def main():
    load_dotenv()

    if not os.path.exists("config.yaml"):
        print("ERRORE: File config.yaml mancante.")
        sys.exit(1)

    config = load_config("config.yaml")

    # Carica il profilo dal cloud (Firestore)
    profile = db.load_profile_from_db()
    if profile:
        print("[*] Profilo caricato da Firestore.")
    else:
        print("ERRORE: Profilo non trovato su Firestore.")
        sys.exit(1)

    # Salva la configurazione locale come "factory_config" per permettere il reset dalla dashboard
    try:
        db.db.collection("app_state").document("factory_config").set(config)
    except Exception as e:
        print(f"[!] Errore durante il salvataggio della factory_config: {e}")

    # Carica la configurazione dal DB e fai il merge con quella locale
    print("[*] Controllo configurazione cloud su Firestore...")
    cloud_config = db.load_config_from_db()
    if cloud_config:
        print("[*] Configurazione cloud rilevata. Applicazione merge...")
        config = deep_merge(config, cloud_config)
    else:
        print("[*] Nessuna configurazione cloud trovata. Sincronizzazione locale -> cloud...")
        db.save_config_to_db(config)

    # Inizializza stato trigger
    db.set_trigger("running", stop=False)

    try:
        _run_scraper(config, profile)
    finally:
        # SEMPRE resettare a idle, anche in caso di crash
        db.set_trigger("idle", stop=False)
        print("[*] Stato bot resettato a IDLE.")


def _run_scraper(config, profile):
    """Corpo principale dello scraping, estratto per poter essere wrappato in try/finally."""
    search_memory = db.load_search_memory()
    job_store = db.load_job_store()
    job_categories = db.load_job_categories()
    cycle_state = db.load_cycle_state()
    apify_usage = db.load_apify_usage()

    execution_id = datetime.now(timezone.utc).isoformat()
    
    # Controllo reset mensile account Apify
    from apify_pool import check_and_apply_resets
    if check_and_apply_resets(apify_usage):
        db.save_apify_usage(apify_usage)

    jobs_target = config.get("scraper", {}).get("jobs_target", 50)
    max_retries = config.get("scraper", {}).get("max_retries", 10)

    iteration = 0
    queries_run = []

    core_keywords = config.get("scraper", {}).get("core_keywords", [])
    core_time_filter = config.get("scraper", {}).get("core_time_filter", "r86400")

    unique_keyword_threshold = config.get("scraper", {}).get(
        "unique_keyword_threshold", 40
    )

    # Calcola le keyword uniche già scoperte dalla memoria
    all_discovered_keywords = list(
        dict.fromkeys(
            m.get("keyword") for m in search_memory if m.get("keyword")
        )
    )

    # Determina se siamo in modalità ciclaggio
    is_cycling_mode = len(all_discovered_keywords) >= unique_keyword_threshold

    if is_cycling_mode:
        # Sincronizza la lista nel cycle_state con le keyword effettivamente scoperte
        cycle_state["keyword_list"] = all_discovered_keywords
        cycle_index = cycle_state.get("cycle_index", 0)
        # Se l'indice è oltre la lista (es. keyword rimosse), resetta
        if cycle_index >= len(all_discovered_keywords):
            cycle_index = 0
        print(
            f"[*] Modalità CICLAGGIO attiva ({len(all_discovered_keywords)} keyword). "
            f"Riparto dall'indice {cycle_index}."
        )
    else:
        cycle_index = 0
        print(
            f"[*] Modalità ESPLORAZIONE attiva "
            f"({len(all_discovered_keywords)}/{unique_keyword_threshold} keyword scoperte)."
        )

    print("[*] Recupero storico valutazioni per personalizzare i risultati...")
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

    print("[*] Avvio scraping iterativo con valutazione in background...")
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    jobs_scraped_this_run = 0
    keywords_cycled_this_run = 0

    while jobs_scraped_this_run < jobs_target and iteration < max_retries:
        if db.is_stop_requested():
            print("\n[!] STOP ricevuto dalla dashboard. Interruzione scraping...")
            break
        
        # Check se abbiamo ancora budget Apify
        eligible = [a for a in apify_usage.get("accounts", {}).values() if a.get("enabled") and a.get("total_jobs_returned", 0) < a.get("budget_jobs", 5000)]
        if not eligible:
            print("\n[!] TUTTI GLI ACCOUNT APIFY HANNO ESAURITO IL BUDGET O SONO DISABILITATI. Interruzione scraping...")
            break

        print(
            f"\n--- Iterazione {iteration + 1}/{max_retries} | "
            f"Lavori estratti: {jobs_scraped_this_run}/{jobs_target} ---"
        )

        is_core_iteration = iteration < len(core_keywords)

        if is_core_iteration:
            # Fase 1: Core keywords
            keyword = core_keywords[iteration]
            db.set_trigger("running", stop=False, current_query=f"Scraping: {keyword}")
            print(f"[*] Keyword CORE predefinita: {keyword}")
            query = {
                "keywords": keyword,
                "reasoning": "Keyword predefinita dal config",
                "is_core": True,
            }
        elif is_cycling_mode:
            # Fase 3: Ciclaggio round-robin
            if keywords_cycled_this_run >= len(all_discovered_keywords):
                print("[*] Tutte le keyword del ciclo sono state esaurite. Stop.")
                break

            keyword = all_discovered_keywords[cycle_index]
            db.set_trigger("running", stop=False, current_query=f"Scraping: {keyword}")
            print(
                f"[*] Keyword CICLAGGIO [{cycle_index + 1}/{len(all_discovered_keywords)}]: {keyword}"
            )
            query = {
                "keywords": keyword,
                "reasoning": "Ciclaggio round-robin",
                "is_core": False,
            }

            # Avanza l'indice circolarmente
            cycle_index = (cycle_index + 1) % len(all_discovered_keywords)
            keywords_cycled_this_run += 1
        else:
            # Fase 2: Esplorazione con Gemini
            query = generate_single_search_query(
                profile, config, search_memory
            )
            keyword = query.get("keywords", "")
            if keyword:
                print(
                    f"[*] Keyword generata da Gemini 3.1 flash lite: {keyword} "
                    f"(Reasoning: {query.get('reasoning', '')})"
                )
                # Aggiorna la lista di keyword scoperte
                if keyword not in all_discovered_keywords:
                    all_discovered_keywords.append(keyword)
                    # Controlla se abbiamo appena raggiunto la soglia
                    if len(all_discovered_keywords) >= unique_keyword_threshold:
                        is_cycling_mode = True
                        cycle_state["keyword_list"] = all_discovered_keywords
                        cycle_index = 0
                        print(
                            f"[*] Soglia di {unique_keyword_threshold} keyword raggiunta! "
                            f"Passo alla modalità CICLAGGIO dalla prossima iterazione."
                        )

        if not keyword:
            print("[!] Keyword non generata o errore. Riprovo...")
            iteration += 1
            continue

        queries_run.append(query)

        # Modifica il time_filter temporaneamente se stiamo facendo una query core
        current_config = copy.deepcopy(config)
        if is_core_iteration:
            current_config["scraper"]["time_filter"] = core_time_filter

        jobs = scrape_jobs(query, current_config, apify_usage)
        # Salva usage dopo ogni iterazione in caso di crash
        db.save_apify_usage(apify_usage)

        new_jobs_count = 0
        top_titles = []
        for job in jobs:
            raw_url = job.get("link", job.get("url", ""))
            if not raw_url:
                continue

            job_url = db.normalize_linkedin_url(raw_url)
            job["link"] = job_url
            job["url"] = job_url

            title = job.get("title", "Unknown Title")
            if len(top_titles) < 5 and title not in top_titles:
                top_titles.append(title)

            if job_url not in job_store:
                if db.is_stop_requested():
                    break
                
                new_data = {
                    "job_data": job,
                    "fit_score": None,
                    "reasoning": None,
                    "category": None,
                    "first_seen": execution_id,
                    "execution_id": execution_id,
                    "keyword": keyword,
                }
                job_store[job_url] = new_data
                
                # Invia il lavoro alla coda per la valutazione in background
                executor.submit(
                    process_and_evaluate_job, 
                    job_url, job_store, profile, liked_history, disliked_history
                )
                
                new_jobs_count += 1
                jobs_scraped_this_run += 1

        fruitful = new_jobs_count > 0

        memory_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "execution_id": execution_id,
            "keyword": keyword,
            "jobs_found_total": len(jobs),
            "jobs_new_unique": new_jobs_count,
            "fruitful": fruitful,
            "top_titles": top_titles,
            "avg_fit_score": None,
        }
        search_memory.append(memory_entry)

        db.save_search_memory(search_memory)

        iteration += 1

    # Salva lo stato del ciclo per la prossima run
    cycle_state["cycle_index"] = cycle_index
    cycle_state["keyword_list"] = all_discovered_keywords
    db.save_cycle_state(cycle_state)

    print("\n[*] Attendo il completamento delle valutazioni in background...")
    executor.shutdown(wait=True)
    print("[*] Valutazioni in background completate.")

    for mem_entry in search_memory:
        if (
            mem_entry.get("execution_id") == execution_id
            and mem_entry.get("avg_fit_score") is None
        ):
            kw = mem_entry.get("keyword")

            scores = []
            for url, data in job_store.items():
                if (
                    data.get("execution_id") == execution_id
                    and data.get("keyword") == kw
                ):
                    score = data.get("fit_score")
                    if score is not None:
                        scores.append(score)

            if scores:
                mem_entry["avg_fit_score"] = round(sum(scores) / len(scores), 1)
            else:
                mem_entry["avg_fit_score"] = 0

    db.save_search_memory(search_memory)

    print("\n[*] Categorizzazione dei lavori non categorizzati...")
    jobs_to_categorize = {
        url: data["job_data"]
        for url, data in job_store.items()
        if data.get("category") is None
    }

    if jobs_to_categorize:
        # Preveniamo timeout processando in blocchi di 50 job alla volta
        urls_list = list(jobs_to_categorize.keys())
        chunk_size = 50

        job_labels_total = {}
        new_cats_total = []

        for i in range(0, len(urls_list), chunk_size):
            chunk_urls = urls_list[i : i + chunk_size]
            chunk_jobs = {u: jobs_to_categorize[u] for u in chunk_urls}

            print(
                f"  [-] Categorizzazione blocco {i // chunk_size + 1} ({len(chunk_urls)} jobs)..."
            )
            cat_result = categorize_jobs_with_gemini(chunk_jobs, job_categories)
            job_labels_total.update(cat_result.get("job_labels", {}))
            new_cats_total.extend(cat_result.get("new_categories", []))

        # Estrai le vecchie categorie come set per il confronto
        cat_labels_set = {
            c["label"].lower()
            for c in job_categories
            if isinstance(c, dict) and "label" in c
        }

        # Aggiungi le nuove categorie all'elenco se non esistono
        for nc in new_cats_total:
            if isinstance(nc, dict) and "label" in nc and "description" in nc:
                if nc["label"].lower() not in cat_labels_set:
                    nc["job_urls"] = []
                    job_categories.append(nc)
                    cat_labels_set.add(nc["label"].lower())

        # Mappa i nomi delle categorie restituiti da Gemini ai nomi esatti nel config (se ignorando case combaciano)
        # Questo previene discrepanze di case-sensitivity (es. "Data analytics" vs "Data Analytics")
        label_mapping = {
            c["label"].lower(): c["label"]
            for c in job_categories
            if isinstance(c, dict) and "label" in c
        }

        for url, category in job_labels_total.items():
            if url in job_store:
                normalized_cat = category.lower() if category else None
                if normalized_cat in label_mapping:
                    job_store[url]["category"] = label_mapping[normalized_cat]
                else:
                    job_store[url]["category"] = category

        # Popola/aggiorna le associazioni job_urls all'interno delle job_categories (utili per l'UI)
        for i, cat in enumerate(job_categories):
            if isinstance(cat, str):
                job_categories[i] = {
                    "label": cat,
                    "description": "Legacy category",
                    "job_urls": [],
                }
                cat = job_categories[i]

            cat["job_urls"] = []
            for url, data in job_store.items():
                if data.get("category") == cat["label"]:
                    cat["job_urls"].append(url)

        print(
            f"  [-] Trovate/assegnate categorie. Nuove categorie aggiunte: {len(new_cats_total)}"
        )
    else:
        print("  [-] Nessun lavoro da categorizzare.")

    db.save_search_memory(search_memory)
    db.save_job_store(job_store)
    db.save_job_categories(job_categories)

    print("\n[*] Dati salvati con successo. Invio report via email...")

    min_fit_score = config.get("evaluation", {}).get("min_fit_score", 75)
    matched_jobs = []

    today_prefix = execution_id.split("T")[0]

    for url, data in job_store.items():
        # Include jobs scraped today
        if data.get("first_seen", "").startswith(today_prefix) or data.get(
            "execution_id", ""
        ).startswith(today_prefix):
            score = data.get("fit_score")
            if score is not None and score >= min_fit_score:
                matched_jobs.append(
                    {
                        "job": data["job_data"],
                        "score": score,
                        "reasoning": data.get("reasoning", ""),
                    }
                )

    matched_jobs.sort(key=lambda x: x["score"], reverse=True)

    total_found = 0
    max_new_unique = -1
    best_keyword = "N/A"
    all_scores = []

    loops_today = 0

    for mem in search_memory:
        if mem.get("timestamp", "").startswith(today_prefix) or mem.get(
            "execution_id", ""
        ).startswith(today_prefix):
            loops_today += 1
            total_found += mem.get("jobs_found_total", 0)
            if mem.get("jobs_new_unique", 0) >= max_new_unique:
                max_new_unique = mem.get("jobs_new_unique", 0)
                best_keyword = mem.get("keyword", "N/A")

    for url, data in job_store.items():
        if data.get("first_seen", "").startswith(today_prefix) or data.get(
            "execution_id", ""
        ).startswith(today_prefix):
            score = data.get("fit_score")
            if score is not None:
                all_scores.append(score)

    avg_fit_score = sum(all_scores) / len(all_scores) if all_scores else 0.0

    metrics_dict = {
        "total_found": total_found,
        "new_jobs_today": jobs_scraped_this_run,
        "total_above_threshold": len(matched_jobs),
        "iterations": loops_today,
        "best_keyword": best_keyword,
        "avg_fit_score": avg_fit_score,
    }

    send_email_report(matched_jobs, metrics_dict, config, apify_usage)

    print("[*] Esecuzione completata con successo.")




if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", action="store_true", help="Resta in attesa di un trigger dalla dashboard")
    args = parser.parse_args()

    def categorize_existing():
        """Categorizza i job già in DB che non hanno ancora una categoria."""
        load_dotenv()
        print("[*] Controllo job non categorizzati nel database...")
        job_store = db.load_job_store()
        job_categories = db.load_job_categories()

        jobs_to_categorize = {
            url: data["job_data"]
            for url, data in job_store.items()
            if data.get("category") is None and data.get("job_data")
        }

        if not jobs_to_categorize:
            print("  [-] Tutti i job sono già categorizzati.")
            return

        print(f"  [-] Trovati {len(jobs_to_categorize)} job da categorizzare.")

        urls_list = list(jobs_to_categorize.keys())
        chunk_size = 50
        job_labels_total = {}
        new_cats_total = []

        for i in range(0, len(urls_list), chunk_size):
            chunk_urls = urls_list[i : i + chunk_size]
            chunk_jobs = {u: jobs_to_categorize[u] for u in chunk_urls}
            print(f"  [-] Categorizzazione blocco {i // chunk_size + 1} ({len(chunk_urls)} jobs)...")
            cat_result = categorize_jobs_with_gemini(chunk_jobs, job_categories)
            job_labels_total.update(cat_result.get("job_labels", {}))
            new_cats_total.extend(cat_result.get("new_categories", []))

        cat_labels_set = {
            c["label"].lower()
            for c in job_categories
            if isinstance(c, dict) and "label" in c
        }

        for nc in new_cats_total:
            if isinstance(nc, dict) and "label" in nc and "description" in nc:
                if nc["label"].lower() not in cat_labels_set:
                    nc["job_urls"] = []
                    job_categories.append(nc)
                    cat_labels_set.add(nc["label"].lower())

        label_mapping = {
            c["label"].lower(): c["label"]
            for c in job_categories
            if isinstance(c, dict) and "label" in c
        }

        for url, category in job_labels_total.items():
            if url in job_store:
                normalized_cat = category.lower() if category else None
                if normalized_cat in label_mapping:
                    job_store[url]["category"] = label_mapping[normalized_cat]
                else:
                    job_store[url]["category"] = category

        for i, cat in enumerate(job_categories):
            if isinstance(cat, str):
                job_categories[i] = {"label": cat, "description": "Legacy category", "job_urls": []}
                cat = job_categories[i]
            cat["job_urls"] = []
            for url, data in job_store.items():
                if data.get("category") == cat["label"]:
                    cat["job_urls"].append(url)

        db.save_job_store(job_store)
        db.save_job_categories(job_categories)
        print(f"  [-] Categorizzazione completata! Nuove categorie: {len(new_cats_total)}")

    if args.listen:
        print("[*] Modalità ASCOLTO attiva. In attesa di trigger dalla dashboard...")
        categorize_existing()
        db.set_trigger("idle")
        while True:
            trigger = db.get_trigger()
            if trigger and trigger.get("status") == "pending":
                print("[!] Trigger ricevuto! Avvio ricerca...")
                try:
                    main()
                except Exception as e:
                    print(f"[!] Errore durante l'esecuzione: {e}")
                finally:
                    db.set_trigger("idle", stop=False)
                print("\n[*] Ricerca completata. In attesa del prossimo trigger...")
            time.sleep(5)
    else:
        main()
