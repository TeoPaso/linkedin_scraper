import os
import json
import hashlib
import firebase_admin
from firebase_admin import credentials, firestore
from urllib.parse import urlparse, urlunparse

# Initialize Firebase only once
if not firebase_admin._apps:
    service_account_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not service_account_str:
        raise ValueError(
            "Environment variable FIREBASE_SERVICE_ACCOUNT_JSON is missing. Cannot connect to Firestore."
        )

    try:
        cred_dict = json.loads(service_account_str)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        raise ValueError(f"Failed to initialize Firebase Admin SDK: {e}")

db = firestore.client()


def normalize_linkedin_url(url: str) -> str:
    """Strip query params e fragment, tieni solo path del job."""
    if not url:
        return url
    parsed = urlparse(url)
    # Ricostruisce senza query string e fragment
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", "")
    )


def get_job_id(url: str) -> str:
    """Restituisce l'hash SHA1 dell'URL come ID documento."""
    clean_url = normalize_linkedin_url(url)
    return hashlib.sha1(clean_url.encode("utf-8")).hexdigest()


def get_category_id(label: str) -> str:
    """Restituisce lo slug della label per l'ID della categoria."""
    return "".join(c if c.isalnum() else "-" for c in label.lower()).strip("-")


def get_memory_id(entry: dict) -> str:
    """Restituisce un hash per la search_memory."""
    base_str = f"{entry.get('execution_id', '')}_{entry.get('keyword', '')}"
    return hashlib.sha1(base_str.encode("utf-8")).hexdigest()


def load_job_store() -> dict:
    """Legge tutti i job da Firestore e restituisce un dizionario {url: data}."""
    job_store = {}
    docs = db.collection("jobs").stream()
    for doc in docs:
        data = doc.to_dict()
        url = data.get("url")
        if url:
            clean_url = normalize_linkedin_url(url)
            data["url"] = clean_url  # Aggiorna il payload
            job_store[clean_url] = data
    return job_store


def save_single_job(url: str, data: dict):
    """Esegue l'upsert di un singolo job, utile per i thread in background."""
    doc_id = get_job_id(url)
    doc_ref = db.collection("jobs").document(doc_id)
    payload = data.copy()
    payload["url"] = url
    if "applied" not in payload:
        payload["applied"] = False
    doc_ref.set(payload, merge=True)

def save_job_store(job_store: dict):
    """Esegue un upsert di ogni job modificato. In batch."""
    batch = db.batch()
    count = 0

    # Per non inviare scritture inutili, se necessario potremmo implementare un controllo.
    # Usando Firestore .set(merge=True) ci garantiamo che non sovrascriva `applied` se l'utente l'ha cliccato nel frattempo.
    for url, data in job_store.items():
        doc_id = get_job_id(url)
        doc_ref = db.collection("jobs").document(doc_id)

        # Assicuriamoci che l'url sia dentro i dati e applicato di default se nuovo
        payload = data.copy()
        payload["url"] = url
        if "applied" not in payload:
            payload["applied"] = False

        batch.set(doc_ref, payload, merge=True)
        count += 1

        # Firestore batch supports up to 500 operations
        if count >= 450:
            batch.commit()
            batch = db.batch()
            count = 0

    if count > 0:
        batch.commit()


def load_search_memory() -> list:
    """Legge da search_memory, ordinata per timestamp."""
    memory = []
    # Attenzione: Firestore richiede un indice per ordinare lato server se query complesse.
    # Qui facciamo stream totale e ordiniamo in python per semplicità.
    docs = db.collection("search_memory").stream()
    for doc in docs:
        memory.append(doc.to_dict())

    # Ordina crescente per timestamp
    memory.sort(key=lambda x: x.get("timestamp", ""))
    return memory


def save_search_memory(memory: list):
    """Upsert su search_memory basato su execution_id+keyword."""
    batch = db.batch()
    count = 0
    for entry in memory:
        doc_id = get_memory_id(entry)
        doc_ref = db.collection("search_memory").document(doc_id)
        batch.set(doc_ref, entry, merge=True)
        count += 1
        if count >= 450:
            batch.commit()
            batch = db.batch()
            count = 0

    if count > 0:
        batch.commit()


def load_job_categories() -> list:
    """Legge job_categories."""
    categories = []
    docs = db.collection("job_categories").stream()
    for doc in docs:
        categories.append(doc.to_dict())
    return categories


def save_job_categories(categories: list):
    """Upsert su job_categories usando lo slug della label."""
    batch = db.batch()
    count = 0
    for cat in categories:
        if isinstance(cat, dict) and "label" in cat:
            doc_id = get_category_id(cat["label"])
            doc_ref = db.collection("job_categories").document(doc_id)
            batch.set(doc_ref, cat, merge=True)
            count += 1
            if count >= 450:
                batch.commit()
                batch = db.batch()
                count = 0
    if count > 0:
        batch.commit()


def load_cycle_state() -> dict:
    """Legge lo stato del ciclo round-robin delle keyword da Firestore."""
    doc = db.collection("app_state").document("keyword_cycle").get()
    if doc.exists:
        return doc.to_dict()
    return {"cycle_index": 0, "keyword_list": []}


def save_cycle_state(state: dict):
    """Salva lo stato del ciclo round-robin delle keyword su Firestore."""
    db.collection("app_state").document("keyword_cycle").set(state)


def load_config_from_db() -> dict:
    """Legge la configurazione da Firestore."""
    doc = db.collection("app_state").document("config").get()
    if doc.exists:
        return doc.to_dict()
    return {}


def save_config_to_db(config: dict):
    """Salva la configurazione su Firestore."""
    db.collection("app_state").document("config").set(config)

def get_trigger():
    """Controlla se c'è un trigger per avviare la ricerca."""
    doc = db.collection("app_state").document("trigger").get()
    if doc.exists:
        return doc.to_dict()
    return None

def set_trigger(status, execution_id=None, stop=False, current_query=None):
    """Imposta lo stato del trigger (es. 'pending', 'running', 'idle')."""
    data = {
        "status": status,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "stop": stop
    }
    if execution_id:
        data["execution_id"] = execution_id
    if current_query:
        data["current_query"] = current_query
    db.collection("app_state").document("trigger").set(data)

def is_stop_requested():
    """Controlla se è stato richiesto lo stop della ricerca."""
    doc = db.collection("app_state").document("trigger").get()
    if doc.exists:
        data = doc.to_dict()
        return data.get("stop") is True
    return False
