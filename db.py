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


def get_user_col(collection_name: str, user_id: str = None):
    if user_id:
        return db.collection("users").document(user_id).collection(collection_name)
    return db.collection(collection_name)


def get_user_app_state_doc(doc_name: str, user_id: str = None):
    if user_id:
        return db.collection("users").document(user_id).collection("app_state").document(doc_name)
    return db.collection("app_state").document(doc_name)


def load_known_urls(user_id: str = None) -> set:
    """Legge l'indice degli URL noti da Firestore."""
    doc = get_user_app_state_doc("url_index", user_id).get()
    if doc.exists:
        data = doc.to_dict()
        return set(data.get("urls", []))
    if user_id:
        root_doc = db.collection("app_state").document("url_index").get()
        if root_doc.exists:
            return set(root_doc.to_dict().get("urls", []))
    return set()


def save_known_urls(urls: list, user_id: str = None):
    """Aggiunge in batch nuovi URL all'indice."""
    if not urls:
        return
    get_user_app_state_doc("url_index", user_id).set(
        {"urls": firestore.ArrayUnion(urls)}, merge=True
    )


def save_single_job(url: str, data: dict, user_id: str = None):
    """Esegue l'upsert di un singolo job per uno specifico utente."""
    doc_id = get_job_id(url)
    doc_ref = get_user_col("jobs", user_id).document(doc_id)
    payload = data.copy()
    payload["url"] = url
    if "applied" not in payload:
        payload["applied"] = False
    doc_ref.set(payload, merge=True)


def save_jobs_batch(jobs_dict: dict, user_id: str = None):
    """Esegue un upsert dei job passati nel dizionario per uno specifico utente."""
    if not jobs_dict:
        return
    batch = db.batch()
    count = 0
    col_ref = get_user_col("jobs", user_id)
    for url, data in jobs_dict.items():
        doc_id = get_job_id(url)
        doc_ref = col_ref.document(doc_id)

        payload = data.copy()
        payload["url"] = url
        if "applied" not in payload:
            payload["applied"] = False

        batch.set(doc_ref, payload, merge=True)
        count += 1

        if count >= 450:
            batch.commit()
            batch = db.batch()
            count = 0

    if count > 0:
        batch.commit()


def get_liked_jobs(user_id: str = None) -> list:
    """Recupera i job apprezzati per un utente."""
    docs = list(get_user_col("jobs", user_id).where("liked", "==", True).stream())
    if not docs and user_id:
        docs = list(db.collection("jobs").where("liked", "==", True).stream())
    return [doc.to_dict() for doc in docs]


def get_disliked_jobs(user_id: str = None) -> list:
    """Recupera i job scartati per un utente."""
    docs = list(get_user_col("jobs", user_id).where("liked", "==", False).stream())
    if not docs and user_id:
        docs = list(db.collection("jobs").where("liked", "==", False).stream())
    return [doc.to_dict() for doc in docs]


def load_search_memory(user_id: str = None) -> list:
    """Legge da search_memory dell'utente, ordinata per timestamp."""
    memory = []
    docs = list(get_user_col("search_memory", user_id).stream())
    if not docs and user_id:
        docs = list(db.collection("search_memory").stream())

    for doc in docs:
        memory.append(doc.to_dict())

    # Ordina crescente per timestamp
    memory.sort(key=lambda x: x.get("timestamp", ""))
    return memory


def save_search_memory(memory: list, user_id: str = None):
    """Upsert su search_memory dell'utente basato su execution_id+keyword."""
    batch = db.batch()
    count = 0
    col_ref = get_user_col("search_memory", user_id)
    for entry in memory:
        doc_id = get_memory_id(entry)
        doc_ref = col_ref.document(doc_id)
        batch.set(doc_ref, entry, merge=True)
        count += 1
        if count >= 450:
            batch.commit()
            batch = db.batch()
            count = 0

    if count > 0:
        batch.commit()


def load_job_categories(user_id: str = None) -> list:
    """Legge job_categories per l'utente."""
    categories = []
    docs = list(get_user_col("job_categories", user_id).stream())
    if not docs and user_id:
        docs = list(db.collection("job_categories").stream())

    for doc in docs:
        categories.append(doc.to_dict())
    return categories


def save_job_categories(categories: list, user_id: str = None):
    """Upsert su job_categories per l'utente usando lo slug della label."""
    batch = db.batch()
    count = 0
    col_ref = get_user_col("job_categories", user_id)
    for cat in categories:
        if isinstance(cat, dict) and "label" in cat:
            doc_id = get_category_id(cat["label"])
            doc_ref = col_ref.document(doc_id)
            batch.set(doc_ref, cat, merge=True)
            count += 1
            if count >= 450:
                batch.commit()
                batch = db.batch()
                count = 0
    if count > 0:
        batch.commit()


def load_cycle_state(user_id: str = None) -> dict:
    """Legge lo stato del ciclo round-robin delle keyword dell'utente."""
    doc = get_user_app_state_doc("keyword_cycle", user_id).get()
    if doc.exists:
        return doc.to_dict()
    if user_id:
        root_doc = db.collection("app_state").document("keyword_cycle").get()
        if root_doc.exists:
            return root_doc.to_dict()
    return {"cycle_index": 0, "keyword_list": []}


def save_cycle_state(state: dict, user_id: str = None):
    """Salva lo stato del ciclo round-robin delle keyword per l'utente."""
    get_user_app_state_doc("keyword_cycle", user_id).set(state)


def load_config_from_db() -> dict:
    """Legge la configurazione condivisa da Firestore."""
    doc = db.collection("app_state").document("config").get()
    if doc.exists:
        return doc.to_dict()
    return {}


def save_config_to_db(config: dict):
    """Salva la configurazione condivisa su Firestore."""
    db.collection("app_state").document("config").set(config)


def load_apify_usage() -> dict:
    """Legge lo stato di utilizzo condiviso degli account Apify da Firestore."""
    doc = db.collection("app_state").document("apify_usage").get()
    if doc.exists:
        return doc.to_dict()
    
    # Inizializza nuovo se non esiste
    usage = {
        "accounts": {},
        "grand_total_jobs_returned": 0,
        "grand_total_searches": 0
    }
    
    # Mapping iniziale dei prossimi reset e consumi
    initial_states = {
        "1": {"next_reset_date": "2026-06-24", "total_jobs_returned": 5000},
        "2": {"next_reset_date": "2026-06-18", "total_jobs_returned": 0},
        "3": {"next_reset_date": "2026-07-04", "total_jobs_returned": 0},
        "4": {"next_reset_date": "2026-07-04", "total_jobs_returned": 0},
        "5": {"next_reset_date": "2026-06-09", "total_jobs_returned": 0},
        "6": {"next_reset_date": "2026-06-09", "total_jobs_returned": 0},
        "7": {"next_reset_date": "2026-06-09", "total_jobs_returned": 0},
    }
    
    for i in range(1, 8):
        acc_id = str(i)
        usage["accounts"][acc_id] = {
            "label": f"Account {i}",
            "total_jobs_returned": initial_states[acc_id]["total_jobs_returned"],
            "total_searches": 0,
            "budget_jobs": 5000,
            "next_reset_date": initial_states[acc_id]["next_reset_date"],
            "enabled": True,
            "errors": 0,
            "last_used": None
        }
    return usage


def save_apify_usage(usage: dict):
    """Salva lo stato di utilizzo degli account Apify su Firestore."""
    db.collection("app_state").document("apify_usage").set(usage)


def get_trigger(user_id: str = None):
    """Controlla se c'è un trigger per avviare la ricerca."""
    if user_id:
        doc = get_user_app_state_doc("trigger", user_id).get()
        if doc.exists:
            data = doc.to_dict()
            data["_user_id"] = user_id
            return data
        return None

    # Controlla prima il trigger root
    root_doc = db.collection("app_state").document("trigger").get()
    if root_doc.exists:
        data = root_doc.to_dict()
        if data.get("status") in ["pending", "running"]:
            data["_user_id"] = None
            return data

    # Se il root non ha trigger attivi, scansiona le subcollection utenti
    users = db.collection("users").stream()
    for u in users:
        t_doc = db.collection("users").document(u.id).collection("app_state").document("trigger").get()
        if t_doc.exists:
            data = t_doc.to_dict()
            if data.get("status") in ["pending", "running"]:
                data["_user_id"] = u.id
                return data
    return None


def set_trigger(status, execution_id=None, stop=False, current_query=None, user_id: str = None):
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
    get_user_app_state_doc("trigger", user_id).set(data)


def load_profile_from_db(user_id: str = None) -> str:
    """Legge il profilo del candidato dell'utente da Firestore (con fallback su root)."""
    doc = get_user_app_state_doc("profile", user_id).get()
    if doc.exists:
        return doc.to_dict().get("content", "")
    if user_id:
        root_doc = db.collection("app_state").document("profile").get()
        if root_doc.exists:
            return root_doc.to_dict().get("content", "")
    return ""


def save_profile_to_db(content: str, user_id: str = None):
    """Salva il profilo del candidato dell'utente su Firestore."""
    get_user_app_state_doc("profile", user_id).set({
        "content": content,
        "updated_at": firestore.SERVER_TIMESTAMP
    })


def is_stop_requested(user_id: str = None):
    """Controlla se è stato richiesto lo stop della ricerca per l'utente."""
    doc = get_user_app_state_doc("trigger", user_id).get()
    if doc.exists:
        data = doc.to_dict()
        return data.get("stop") is True
    return False
