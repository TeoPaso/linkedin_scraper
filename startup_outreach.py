import os
import sys
import yaml
import json
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

from apify_client import ApifyClient
from google import genai
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from tavily import TavilyClient

# --- Modelli Pydantic ---

class StartupFilterResult(BaseModel):
    is_vc_backed: bool
    has_growth_signals: bool
    founder_network_value: str
    profile_fit: str
    disqualified: bool
    disqualify_reason: str

# --- Funzioni di utilità ---

def load_config(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def load_profile(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path)

# --- FASE 1: DISCOVERY ---

def extract_startups_with_gemini(genai_client, text_content):
    """Usa Gemini per estrarre nomi e URL di startup dal testo (es. articoli, listicles)."""
    prompt = f"""
Estrai una lista di startup (preferibilmente milanesi/italiane) menzionate nel seguente testo.
Ignora grandi aziende corporate, concentrati su startup e scaleup.
Per ogni startup, prova a dedurre o fornire l'URL del suo sito web ufficiale, se menzionato o se puoi inferirlo (es. nomeazienda.com/it/io).
Se l'URL non è chiaro, metti una stringa vuota.
Restituisci ESATTAMENTE un array JSON puro, senza markdown, con questo formato:
[
  {{"name": "NomeStartup", "url": "https://nomesito.it"}}
]

Testo:
{text_content[:20000]}
"""
    try:
        response = genai_client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config={'response_mime_type': 'application/json', 'temperature': 0.1}
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"[!] Errore estrazione Gemini: {e}")
        return []

def run_discovery(tavily_client, apify_client, genai_client, config):
    print("\n[Fase 1] Avvio Discovery in parallelo...")
    startups = {}
    
    outreach_cfg = config.get('outreach', {})
    sources = outreach_cfg.get('sources', [])
    
    # 1.1 Prepara le query Tavily
    queries = [
        "top startup Milano 2025 seed serie A",
        "startupitalia startup milanesi fintech AI SaaS",
        "Italian Tech Alliance portfolio Milano"
    ]
    for source in sources:
        queries.append(f"startup portfolio {source} Milano")
        
    def process_tavily_query(q):
        print(f"  - Tavily Search in corso: '{q}'")
        found = []
        try:
            res = tavily_client.search(query=q, search_depth="advanced", max_results=3)
            combined_content = "\n".join([r.get('content', '') for r in res.get('results', [])])
            if combined_content:
                extracted = extract_startups_with_gemini(genai_client, combined_content)
                for s in extracted:
                    name = s.get('name', '').strip()
                    if name:
                        found.append({"name": name, "url": s.get('url', ''), "source": "Tavily Search"})
        except Exception as e:
            print(f"  [!] Errore durante la ricerca Tavily per '{q}': {e}")
        return found

    def process_apify_wellfound():
        print("  - Apify Search in corso: Wellfound")
        found = []
        try:
            run_input = {
                "role": "",
                "location": "Milan, Italy",
                "maxResults": 50
            }
            run = apify_client.actor("crawlerbros~wellfound-scraper").call(run_input=run_input)
            dataset_id = run["defaultDatasetId"]
            items = apify_client.dataset(dataset_id).list_items().items
            for item in items:
                company = item.get('company', {})
                name = company.get('name', '')
                if name:
                    url = company.get('websiteUrl', '')
                    if not url and company.get('twitterUrl'):
                        url = item.get('url', '')
                    found.append({"name": name, "url": url, "source": "Wellfound"})
        except Exception as e:
            print(f"  [!] Errore durante lo scraping Wellfound: {e}")
        return found

    # Esegui tutto in parallelo
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = []
        for q in queries:
            futures.append(executor.submit(process_tavily_query, q))
        futures.append(executor.submit(process_apify_wellfound))
        
        for future in as_completed(futures):
            results = future.result()
            for s in results:
                name = s['name']
                if name.lower() not in [k.lower() for k in startups.keys()]:
                    startups[name] = s

    return list(startups.values())

# --- FASE 2: ENRICHMENT ---

def enrich_startup(tavily_client, startup):
    name = startup['name']
    url = startup.get('url', '')
    
    enriched_data = {
        "name": name,
        "url": url,
        "description": "non disponibile",
        "founders": "non disponibile",
        "founder_background": "non disponibile",
        "recent_funding": "non disponibile",
        "careers_page": "non disponibile",
        "growth_signals": "non disponibile"
    }

    try:
        # Ricerca generale info business
        query_info = f"{name} startup Milano founders funding"
        if url:
            query_info += f" site:{urllib.parse.urlparse(url).netloc}"
        
        info_res = tavily_client.search(query=query_info, search_depth="basic", max_results=3)
        combined_info = "\n".join([r.get('content', '') for r in info_res.get('results', [])])
        
        # Chiediamo a Tavily (tramite la sua search che riassume) o usiamo i contenuti per mappare
        enriched_data["description"] = combined_info[:1000] if combined_info else "non disponibile"
        
        # Ricerca news/crescita
        query_news = f"{name} startup (finanziamento OR round OR assunzioni OR lancio) 2024 OR 2025"
        news_res = tavily_client.search(query=query_news, topic="news", max_results=2)
        combined_news = "\n".join([r.get('content', '') for r in news_res.get('results', [])])
        if combined_news:
             enriched_data["growth_signals"] = combined_news[:1000]
        
        # Ricerca careers
        if url:
            domain = urllib.parse.urlparse(url).netloc
            query_careers = f"site:{domain} (careers OR jobs OR \"lavora con noi\")"
            careers_res = tavily_client.search(query=query_careers, search_depth="basic", max_results=1)
            results = careers_res.get('results', [])
            if results:
                enriched_data["careers_page"] = results[0].get('url', 'non disponibile')
                
    except Exception as e:
        print(f"  [!] Errore arricchimento {name}: {e}")
        
    return enriched_data

# --- FASE 3: FILTERING ---

def filter_startup(genai_client, profile, enriched_data):
    prompt = f"""
Sei un analista di Venture Capital e un consulente di carriera.
Analizza i dati raccolti su questa startup e valuta se è un buon target per il candidato descritto, 
e se la startup stessa mostra segnali di qualità e crescita.

Profilo Candidato:
{profile}

Dati Startup:
- Nome: {enriched_data['name']}
- URL: {enriched_data['url']}
- Descrizione/Info trovate: {enriched_data['description']}
- News/Crescita: {enriched_data['growth_signals']}

Rispondi in JSON puro secondo questo formato, dove i valori stringa ammessi sono specificati:
{{
  "is_vc_backed": true/false, // ha backing da VC credibili o istituzionali? (se non lo sai con certezza e non ci sono tracce di round, false)
  "has_growth_signals": true/false, // segnali di crescita recente (round, hiring, lancio prodotto)?
  "founder_network_value": "high" | "medium" | "low", // il founder ha background interessante per costruire network VC? (se non ci sono info sui founder, "low")
  "profile_fit": "good" | "partial" | "none", // il profilo del candidato è spendibile lì?
  "disqualified": true/false, // pre-seed stagnante senza traction, settore morto, azienda >5 anni senza exit né crescita, team no info verificabili
  "disqualify_reason": "Motivazione breve (solo se disqualified: true, altrimenti stringa vuota \"\")"
}}
"""
    try:
        response = genai_client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': StartupFilterResult,
                'temperature': 0.1
            }
        )
        result = StartupFilterResult.model_validate_json(response.text)
        
        # Calcola punti
        score = 0
        if result.is_vc_backed: score += 1
        if result.has_growth_signals: score += 1
        
        if result.founder_network_value == "high": score += 2
        elif result.founder_network_value == "medium": score += 1
        
        if result.profile_fit == "good": score += 2
        elif result.profile_fit == "partial": score += 1
        
        return result, score
    except Exception as e:
        print(f"  [!] Errore filtering {enriched_data['name']}: {e}")
        return None, 0

# --- FASE 4: COVER LETTER ---

def generate_cover_letter(genai_client, profile, startup_data):
    prompt = f"""
Genera una cover letter (email di outreach proattivo) in ITALIANO (max 150 parole, prima persona) per questa startup.

Candidato:
{profile}

Startup:
{json.dumps(startup_data, ensure_ascii=False)}

VINCOLI TASSATIVI:
1. Prima frase: Cita qualcosa di SPECIFICO sulla startup (prodotto, round recente, founder, problema che risolvono). 
   VIETATO aprire con "Sono interessato alla vostra realtà", "Vi scrivo perché", "Con la presente" o formule generiche.
2. Seconda parte: Esattamente 2 righe su di te -> Polimi Finance Engineer, CFA winner Italy 2025, costruisci software AI autonomamente. 
   Cita ALMENO UN progetto (es. FinancialAnalyst_Agent, scraper, trascrizioni_gem) in base al settore della startup.
3. Terza parte: Una frase sul perché *questa* startup e il suo problema specifico ti interessano.
4. Chiusura: Call to action CONCRETA (offerta di demo o call di 15 minuti).
5. Tono: Diretto, competente, analitico. Niente entusiasmo performativo o esclamazioni eccessive. Niente formattazione markdown.
"""
    try:
        response = genai_client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config={'temperature': 0.2}
        )
        return response.text.strip()
    except Exception as e:
        print(f"  [!] Errore generazione cover letter per {startup_data['name']}: {e}")
        return "Errore nella generazione della cover letter."

# --- FASE 5: OUTPUT & EMAIL ---

def generate_summary_md(leads):
    lines = ["# Startup Outreach Report\n"]
    lines.append("| Nome | Stage/Segnali | VC Backed | Founder Network | Fit | Punteggio | Careers |")
    lines.append("|---|---|---|---|---|---|---|")
    
    for lead in leads:
        r = lead['filter_result']
        name = lead['name']
        signals = "Sì" if r.get('has_growth_signals') else "No"
        vc = "Sì" if r.get('is_vc_backed') else "No"
        network = r.get('founder_network_value', 'low')
        fit = r.get('profile_fit', 'none')
        score = lead['score']
        careers = lead.get('careers_page', 'N/D')
        
        lines.append(f"| {name} | Crescita: {signals} | {vc} | {network} | {fit} | {score} | {careers} |")
        
    return "\n".join(lines)

def send_outreach_email_report(leads):
    sender = os.environ.get("EMAIL_SENDER")
    password = os.environ.get("EMAIL_PASSWORD")
    recipient = os.environ.get("EMAIL_RECIPIENT")
    
    if not sender or not password or not recipient or password == "tua_app_password":
        print("[!] Credenziali email non configurate. Salto l'invio dell'email.")
        return
        
    today_str = datetime.now().strftime("%d/%m/%Y")
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Startup Outreach Report — {today_str}"
    msg["From"] = sender
    msg["To"] = recipient
    
    html_content = f"""
    <html>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; max-width: 800px; margin: auto;">
        <h2 style="color: #6a1b9a; border-bottom: 2px solid #6a1b9a; padding-bottom: 10px;">Startup Outreach Report</h2>
        <p>Ecco le startup analizzate in data <strong>{today_str}</strong> per il tuo piano di outreach proattivo.</p>
    """
    
    if not leads:
        html_content += "<p style='color: #666; font-style: italic;'>Nessuna startup ha superato i filtri in questa run.</p>"
    else:
        for lead in leads:
            name = lead["name"]
            url = lead.get("url", "#")
            score = lead["score"]
            careers = lead.get("careers_page", "outreach proattivo")
            cv_letter = lead.get("cover_letter", "").replace('\n', '<br>')
            filter_res = lead.get("filter_result", {})
            
            vc_backed = "✅ VC Backed" if filter_res.get("is_vc_backed") else "❌ No VC info"
            growth = "📈 Growth Signals" if filter_res.get("has_growth_signals") else "📉 No clear growth"
            network = f"Network: {filter_res.get('founder_network_value', 'low').upper()}"
            
            html_content += f"""
            <div style="margin-bottom: 25px; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <h3 style="margin-top: 0; margin-bottom: 8px; font-size: 18px;">
                    <a href="{url}" style="color: #6a1b9a; text-decoration: none;">{name}</a> 
                </h3>
                <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 15px;">
                    <span style="background-color: #f3f2ef; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; color: #4a148c;">
                        Punteggio Segnali: {score}
                    </span>
                    <span style="background-color: #f3f2ef; padding: 4px 8px; border-radius: 4px; font-size: 12px; color: #555;">
                        {vc_backed}
                    </span>
                    <span style="background-color: #f3f2ef; padding: 4px 8px; border-radius: 4px; font-size: 12px; color: #555;">
                        {growth}
                    </span>
                    <span style="background-color: #f3f2ef; padding: 4px 8px; border-radius: 4px; font-size: 12px; color: #555;">
                        {network}
                    </span>
                </div>
                <div style="margin-bottom: 15px; font-size: 14px;">
                    <strong>Careers/Jobs:</strong> <a href="{careers if careers != 'non disponibile' else '#'}" style="color: #0a66c2;">{careers}</a>
                </div>
                <div style="padding: 15px; border-left: 4px solid #6a1b9a; background-color: #f9f3fb; font-size: 14px; font-style: italic;">
                    {cv_letter}
                </div>
            </div>
            """
            
    html_content += """
        <p style="font-size: 12px; color: #888; text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #eaeaea;">
            Generato automaticamente da Startup Outreach Agent.
        </p>
    </body>
    </html>
    """
    
    msg.attach(MIMEText(html_content, "html"))
    
    try:
        print(f"[*] Invio email outreach a {recipient}...")
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
    outreach_cfg = config.get("outreach", {})
    min_signals = outreach_cfg.get("min_signals", 3)
    
    # Init Clients
    apify_token = os.environ.get("APIFY_API_TOKEN")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    tavily_key = os.environ.get("TAVILY_API_KEY")
    
    if not all([apify_token, gemini_key, tavily_key]):
        print("[!] Attenzione: Chiavi API mancanti (APIFY, GEMINI o TAVILY).")
        sys.exit(1)
        
    apify_client = ApifyClient(apify_token)
    genai_client = genai.Client(api_key=gemini_key)
    tavily_client = TavilyClient(api_key=tavily_key)
    
    # 1. DISCOVERY
    startups = []
    leads_file = "startup_leads.json"
    
    if outreach_cfg.get("run_discovery", False):
        startups = run_discovery(tavily_client, apify_client, genai_client, config)
        print(f"[*] Discovery completata. Trovate {len(startups)} potenziali startup.")
    else:
        print("\n[Fase 1] Salto Discovery (run_discovery: false). Caricamento da file locale...")
        if os.path.exists(leads_file):
            with open(leads_file, 'r', encoding='utf-8') as f:
                startups = json.load(f)
            print(f"[*] Caricate {len(startups)} startup dal file.")
        else:
            print("[!] File startup_leads.json non trovato e discovery disabilitata. Esco.")
            sys.exit(0)
            
    if not startups:
        print("[!] Nessuna startup da elaborare.")
        send_outreach_email_report([])
        sys.exit(0)

    # 2 & 3. ENRICHMENT e FILTERING
    print(f"\n[Fase 2 & 3] Enrichment e Filtering in parallelo su {len(startups)} startup...")
    valid_leads = []
    
    def process_startup(startup, idx, total):
        try:
            enriched = enrich_startup(tavily_client, startup)
            filter_res, score = filter_startup(genai_client, profile, enriched)
            
            if not filter_res:
                print(f"  [!] [{idx}/{total}] {startup['name']}: Errore filtro.")
                return None
                
            if filter_res.disqualified:
                print(f"  [X] [{idx}/{total}] Squalificata ({startup['name']}): {filter_res.disqualify_reason}")
                return None
                
            if score >= min_signals:
                print(f"  [V] [{idx}/{total}] SUPERATA! ({startup['name']}) - Segnali: {score}/{min_signals}")
                enriched['filter_result'] = filter_res.model_dump()
                enriched['score'] = score
                return enriched
            else:
                print(f"  [-] [{idx}/{total}] Scartata per score basso ({startup['name']}) - Segnali: {score}/{min_signals}")
                return None
        except Exception as e:
            print(f"  [!] [{idx}/{total}] Errore imprevisto su {startup['name']}: {e}")
            return None

    # Esegui in parallelo (max 5-8 workers per non incorrere in Rate Limit sulle API)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_startup, s, i+1, len(startups)): s for i, s in enumerate(startups)}
        for future in as_completed(futures):
            res = future.result()
            if res:
                valid_leads.append(res)

    # Ordina valid_leads
    valid_leads.sort(key=lambda x: x['score'], reverse=True)
    
    # 4. COVER LETTER
    print(f"\n[Fase 4] Generazione Cover Letter per {len(valid_leads)} startup...")
    ensure_dir("cover_letters")
    
    for lead in valid_leads:
        print(f"  - Generazione per {lead['name']}...")
        letter = generate_cover_letter(genai_client, profile, lead)
        lead['cover_letter'] = letter
        
        # Salva lettera in file txt
        safe_name = "".join(c for c in lead['name'] if c.isalnum() or c in (' ', '_')).replace(' ', '_').lower()
        with open(f"cover_letters/{safe_name}.txt", "w", encoding='utf-8') as f:
            f.write(letter)

    # 5. OUTPUT
    print("\n[Fase 5] Salvataggio dati e invio Email...")
    
    with open(leads_file, "w", encoding='utf-8') as f:
        json.dump(valid_leads, f, ensure_ascii=False, indent=2)
        
    summary_md = generate_summary_md(valid_leads)
    with open("OUTREACH_SUMMARY.md", "w", encoding='utf-8') as f:
        f.write(summary_md)
        
    send_outreach_email_report(valid_leads)
    print("\n[*] Processo di Outreach completato con successo!")

if __name__ == "__main__":
    main()
