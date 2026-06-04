import os
from datetime import datetime, timezone
from apify_client import ApifyClient

def get_next_client(usage: dict) -> tuple[ApifyClient, str]:
    """
    Seleziona l'account Apify con il minor numero di `total_jobs_returned`
    tra quelli attivi e con budget disponibile.
    """
    if "accounts" not in usage:
        raise ValueError("Invalid usage data: missing 'accounts' key")

    eligible = []
    for account_id, data in usage["accounts"].items():
        if data.get("enabled", False) and data.get("total_jobs_returned", 0) < data.get("budget_jobs", 5000):
            eligible.append((account_id, data))

    if not eligible:
        raise RuntimeError("Tutti gli account Apify hanno esaurito il budget o sono disabilitati!")

    # Least-used-first
    best_account = min(eligible, key=lambda x: x[1].get("total_jobs_returned", 0))
    account_id = best_account[0]
    
    # Recupera il token dall'ambiente
    token = os.environ.get(f"APIFY_API_TOKEN_{account_id}")
    if not token:
        # Fallback se le env vars non sono impostate correttamente ma il file c'è
        raise ValueError(f"APIFY_API_TOKEN_{account_id} mancante nelle variabili d'ambiente.")

    # Aggiorna il timestamp di ultimo utilizzo (solo in memoria per ora)
    usage["accounts"][account_id]["last_used"] = datetime.now(timezone.utc).isoformat()

    return ApifyClient(token), account_id

def report_usage(account_id: str, jobs_returned: int, usage: dict):
    """
    Aggiorna i contatori di utilizzo dopo una chiamata all'actor.
    """
    if account_id in usage["accounts"]:
        acc = usage["accounts"][account_id]
        acc["total_jobs_returned"] += jobs_returned
        acc["total_searches"] += 1
        
        usage["grand_total_jobs_returned"] = usage.get("grand_total_jobs_returned", 0) + jobs_returned
        usage["grand_total_searches"] = usage.get("grand_total_searches", 0) + 1
        
        # Se ha superato il budget, disabilitalo per il futuro
        if acc["total_jobs_returned"] >= acc.get("budget_jobs", 5000):
            acc["enabled"] = False

def report_error(account_id: str, usage: dict, max_errors: int = 3):
    """
    Registra un errore per un account e lo disabilita se supera la soglia.
    """
    if account_id in usage["accounts"]:
        acc = usage["accounts"][account_id]
        acc["errors"] = acc.get("errors", 0) + 1
        if acc["errors"] >= max_errors:
            acc["enabled"] = False
