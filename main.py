import os
import sys
import yaml
import urllib.parse
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from apify_client import ApifyClient
from google import genai
from pydantic import BaseModel
from dotenv import load_dotenv

class JobEvaluation(BaseModel):
    fit_score: int
    reasoning: str

class SearchQuery(BaseModel):
    keywords: str
    location: str
    contract_type: str
    reasoning: str
    
class SearchPlan(BaseModel):
    queries: list[SearchQuery]

def load_config(path: str) -> dict:
    """Carica la configurazione yaml."""
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def load_profile(path: str) -> str:
    """Carica il profilo markdown del candidato."""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

import json

def generate_search_queries(profile: str, config: dict) -> list[dict]:
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        print("ERRORE: Variabile d'ambiente GEMINI_API_KEY non impostata.")
        sys.exit(1)
        
    client = genai.Client(api_key=gemini_key)
    
    max_searches = config.get("scraper", {}).get("max_searches", 1)
    location_pref = config.get("preferences", {}).get("location", "Milan, Italy")
    
    prompt = f"""
Sei un technical recruiter esperto e un career coach.
Leggi il seguente profilo del candidato e genera esattamente {max_searches} ricerche di lavoro altamente mirate e adatte alle competenze, esperienze, aspirazioni e interessi del candidato.

Profilo Candidato:
{profile}

Istruzioni:
1. Fornisci 'keywords' precise basate ESCLUSIVAMENTE sui JOB TITLE. Esempi validi: "Analyst", "Associate", "Consultant", "Specialist", "Graduate", "Graduate Program", "Trainee", "Intern", "Researcher", "Business Partner", "Business Development", "Junior Associate", "Junior Consultant", "Strategic". Puoi usare operatori logici (e.g. "Analyst OR Associate OR Graduate"). NON inserire MAI nomi di tecnologie, linguaggi o competenze (e.g. NON usare "Python" o "Power BI") per evitare che LinkedIn filtri via troppi annunci.
2. Le diverse ricerche che generi devono avere 'keywords' DIVERSE e COMPLEMENTARI tra loro in modo da non sovrapporsi nei risultati, coprendo le varie sfumature del profilo (es. una per ambiti data, una per ambiti strategy, ecc.).
3. Scrivi in ITALIANO una breve 'reasoning' sul perché hai scelto questa combinazione di parametri.

DEVI RESTITUIRE UN OGGETTO JSON ESATTAMENTE CON QUESTA STRUTTURA:
{{
  "queries": [
    {{
      "keywords": "la stringa con le keywords",
      "reasoning": "la motivazione in italiano"
    }}
  ]
}}
Non aggiungere nessun altro testo fuori dal JSON.
"""
    try:
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'temperature': 0.2
            },
        )
        plan_dict = json.loads(response.text)
        return plan_dict.get("queries", [])
    except Exception as e:
        print(f"[!] ERRORE durante la generazione delle query con Gemini: {e}")
        return []

def construct_linkedin_url(params: dict, location: str, time_filter: str = "r604800") -> str:
    """Costruisce un URL di ricerca per LinkedIn basandosi sui parametri."""
    base_url = "https://www.linkedin.com/jobs/search/?"
    query_params = {}
    if params.get("keywords"):
        query_params["keywords"] = params["keywords"]
    
    if location:
        query_params["location"] = location
    
    # Filtro temporale configurabile (default past month)
    if time_filter:
        query_params["f_TPR"] = time_filter
    
    return base_url + urllib.parse.urlencode(query_params)

def scrape_jobs(query_params: dict, config: dict) -> list:
    """Lancia l'Actor di Apify per lo scraping dei job post."""
    apify_token = os.environ.get("APIFY_API_TOKEN")
    if not apify_token:
        print("ERRORE: Variabile d'ambiente APIFY_API_TOKEN non impostata.")
        sys.exit(1)
        
    client = ApifyClient(apify_token)
    
    time_filter = config.get("scraper", {}).get("time_filter", "r604800")
    location = config.get("preferences", {}).get("location", "Milan, Lombardy, Italy")
    url = construct_linkedin_url(query_params, location, time_filter)
    print(f"[*] Avvio scraper su URL: {url}")
    
    run_input = {
        "urls": [url],
        "count": config.get("scraper", {}).get("max_jobs_per_search", 10),
        "scrapeCompany": config.get("scraper", {}).get("scrape_company", False),
    }
    
    try:
        # Chiamata all'Actor Curious Coder per LinkedIn Jobs
        run = client.actor("hKByXkMQaC5Qt9UMN").call(run_input=run_input)
        dataset_id = run["defaultDatasetId"]
        
        items = client.dataset(dataset_id).list_items().items
        print(f"[*] Scraper completato. Trovati {len(items)} job post per la query corrente.")
        return items
    except Exception as e:
        print(f"[!] ERRORE durante l'esecuzione di Apify: {e}")
        return []

def evaluate_job_with_gemini(job: dict, profile: str) -> JobEvaluation:
    """Valuta il fit tra l'offerta di lavoro e il profilo del candidato usando Gemini."""
    gemini_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=gemini_key)
    
    prompt = f"""
Sei un technical recruiter esperto e un career coach.
Valuta l'aderenza del candidato alla seguente offerta di lavoro.

Profilo Candidato:
{profile}

Descrizione Lavoro:
Titolo: {job.get('title', 'Unknown')}
Azienda: {job.get('companyName', 'Unknown')}
Descrizione: {job.get('descriptionText', '')}

Istruzioni:
1. Valuta l'aderenza del candidato per questo ruolo e assegna un 'fit_score' da 0 a 100.
2. Scrivi una 'reasoning' di 2-3 righe IN ITALIANO per giustificare il punteggio.
3. CRITICO: Non inventare competenze. Se il ruolo richiede skill tecniche o esperienze specifiche che mancano, il punteggio non deve superare i 60 punti.
4. CRITICO: Se il dipartimento/focus del lavoro (es. Marketing, HR, Customer Service) è totalmente estraneo all'obiettivo del candidato (Finance, AI, Engineering, Data), il punteggio DEVE essere inferiore a 50, anche se il candidato ha buone skill analitiche. Solo i fatti espliciti valgono.
"""
    try:
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': JobEvaluation,
                'temperature': 0.1
            },
        )
        return JobEvaluation.model_validate_json(response.text)
    except Exception as e:
        print(f"[!] ERRORE durante la valutazione con Gemini: {e}")
        return JobEvaluation(fit_score=0, reasoning=f"Errore di valutazione: {str(e)}")

def send_email_report(matched_jobs: list, queries: list):
    """Genera e invia il report in formato HTML via Email."""
    sender = os.environ.get("EMAIL_SENDER")
    password = os.environ.get("EMAIL_PASSWORD")
    recipient = os.environ.get("EMAIL_RECIPIENT")
    
    if not sender or not password or not recipient or password == "tua_app_password":
        print("[!] Credenziali email non configurate nel file .env (o password di default). Salto l'invio dell'email.")
        return
        
    today_str = datetime.now().strftime("%d/%m/%Y")
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"LinkedIn Job Matches - {today_str}"
    msg["From"] = sender
    msg["To"] = recipient
    
    html_content = f"""
    <html>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; max-width: 800px; margin: auto;">
        <h2 style="color: #0a66c2; border-bottom: 2px solid #0a66c2; padding-bottom: 10px;">LinkedIn Job Matches</h2>
        <p>Ecco le offerte di lavoro altamente in target analizzate per te in data <strong>{today_str}</strong>.</p>
        
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #0a66c2;">
            <h4 style="margin-top: 0; margin-bottom: 10px; color: #444;">Ricerca effettuata da Gemini:</h4>
            <ul style="margin-bottom: 0; padding-left: 20px;">
    """
    
    for q in queries:
        html_content += f"""
                <li style="margin-bottom: 10px;">
                    <strong>Keywords:</strong> <code>{q.get('keywords', 'N/A')}</code><br>
                    <em style="color: #666; font-size: 0.9em;">Motivazione Ricerca: {q.get('reasoning', 'N/A')}</em>
                </li>
        """
        
    html_content += """
            </ul>
        </div>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
        <div style="margin-top: 20px;">
    """
    
    if not matched_jobs:
        html_content += "<p style='color: #666; font-style: italic;'>Nessuna offerta ha superato la soglia minima specificata per oggi.</p>"
    else:
        for item in matched_jobs:
            job = item["job"]
            title = job.get("title", "Titolo Sconosciuto")
            company = job.get("companyName", "Azienda Sconosciuta")
            location = job.get("location", "N/A")
            url = job.get("link", "#")
            score = item["score"]
            reasoning = item["reasoning"]
            
            color = "#2e7d32" if score >= 85 else "#d32f2f" if score < 75 else "#f57c00"
            
            html_content += f"""
            <div style="margin-bottom: 25px; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <h3 style="margin-top: 0; margin-bottom: 8px; font-size: 18px;">
                    <a href="{url}" style="color: #0a66c2; text-decoration: none;">{title}</a> 
                    <span style="color: #666; font-weight: normal; font-size: 16px;">presso {company}</span>
                </h3>
                <div style="display: flex; gap: 20px; margin-bottom: 15px;">
                    <span style="background-color: #f3f2ef; padding: 4px 8px; border-radius: 4px; font-size: 14px; font-weight: 600; color: {color};">
                        Fit Score: {score}/100
                    </span>
                    <span style="background-color: #f3f2ef; padding: 4px 8px; border-radius: 4px; font-size: 14px; color: #555;">
                        📍 {location}
                    </span>
                </div>
                <div style="padding-top: 12px; border-top: 1px solid #eaeaea;">
                    <strong style="color: #444; font-size: 14px;">Perché questo ruolo:</strong><br>
                    <span style="color: #555; font-size: 14px;">{reasoning}</span>
                </div>
            </div>
            """
            
    html_content += """
        </div>
        <p style="font-size: 12px; color: #888; text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #eaeaea;">
            Generato automaticamente da LinkedIn Job Scraper Agent.
        </p>
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

def main():
    load_dotenv()
    
    if not os.path.exists("config.yaml") or not os.path.exists("my_profile.md"):
        print("ERRORE: File config.yaml o my_profile.md mancanti.")
        sys.exit(1)
        
    config = load_config("config.yaml")
    profile = load_profile("my_profile.md")
    
    print("[*] Generazione parametri di ricerca tramite Gemini in base al profilo...")
    queries = generate_search_queries(profile, config)
    
    if not queries:
        print("[!] Nessuna query generata. Esco.")
        sys.exit(1)
        
    print(f"[*] Generate {len(queries)} query di ricerca. Avvio scraping...")
    
    all_unique_jobs = {}
    for i, query in enumerate(queries):
        print(f"\n--- Ricerca {i+1}/{len(queries)} ---")
        print(f"Keywords: {query['keywords']}")
        print(f"Location: {config.get('preferences', {}).get('location', 'N/A')}")
        
        jobs = scrape_jobs(query, config)
        for job in jobs:
            job_url = job.get('link', job.get('url', ''))
            if job_url and job_url not in all_unique_jobs:
                all_unique_jobs[job_url] = job
                
    unique_jobs_list = list(all_unique_jobs.values())
    print(f"\n[*] Scraping completato. Trovati {len(unique_jobs_list)} job post unici in totale.")
    
    if not unique_jobs_list:
        print("[!] Nessun job trovato. Invio email vuota.")
        send_email_report([], queries)
        sys.exit(0)
        
    min_fit_score = config.get("evaluation", {}).get("min_fit_score", 75)
    matched_jobs = []
    
    print(f"\n[*] Inizio valutazione delle offerte tramite Gemini (Soglia: {min_fit_score})...")
    for i, job in enumerate(unique_jobs_list):
        title = job.get("title", "Unknown Title")
        company = job.get("companyName", "Unknown Company")
        print(f"  [{i+1}/{len(unique_jobs_list)}] Analisi: {title} @ {company}...")
        
        evaluation = evaluate_job_with_gemini(job, profile)
        print(f"      -> Score: {evaluation.fit_score}")
        
        if evaluation.fit_score >= min_fit_score:
            matched_jobs.append({
                "job": job,
                "score": evaluation.fit_score,
                "reasoning": evaluation.reasoning
            })
            
    # Ordiniamo i job dal punteggio più alto a quello più basso
    matched_jobs.sort(key=lambda x: x["score"], reverse=True)
    
    print(f"\n[*] Trovate {len(matched_jobs)} offerte con score >= {min_fit_score}. Invio report via email...")
    send_email_report(matched_jobs, queries)

if __name__ == "__main__":
    main()
