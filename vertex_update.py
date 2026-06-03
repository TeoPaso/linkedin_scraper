import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add get_gemini_client function after load_profile
helper_code = """
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
"""

if "def get_gemini_client():" not in content:
    content = content.replace("def generate_single_search_query(", helper_code + "\n\ndef generate_single_search_query(")

# Replace client instantiation in generate_single_search_query
old_init_1 = """    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        print("ERRORE: Variabile d'ambiente GEMINI_API_KEY non impostata.")
        return {"keywords": ""}

    client = genai.Client(api_key=gemini_key)"""
    
new_init_1 = """    try:
        client = get_gemini_client()
    except Exception as e:
        print(f"ERRORE Gemini Client: {e}")
        return {"keywords": ""}"""

content = content.replace(old_init_1, new_init_1)

# Replace client instantiation in evaluate_job_with_gemini
old_init_2 = """    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        print("[!] GEMINI_API_KEY mancante, non posso valutare il job.")
        return None

    client = genai.Client(api_key=gemini_key)"""
    
new_init_2 = """    try:
        client = get_gemini_client()
    except Exception as e:
        print(f"[!] Errore Gemini Client: {e}")
        return None"""

content = content.replace(old_init_2, new_init_2)

# Replace client instantiation in analyze_job_for_outreach
old_init_3 = """    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        print("[!] GEMINI_API_KEY mancante, skippo analisi outreach.")
        return None

    client = genai.Client(api_key=gemini_key)"""
    
new_init_3 = """    try:
        client = get_gemini_client()
    except Exception as e:
        print(f"[!] Errore Gemini Client: {e}")
        return None"""

content = content.replace(old_init_3, new_init_3)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(content)

print("SUCCESS")
