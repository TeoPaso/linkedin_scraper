import os
from dotenv import load_dotenv
load_dotenv('.env')
import db
import json
jobs = db.load_job_store()
if jobs:
    sorted_jobs = sorted(jobs.items(), key=lambda x: x[1].get('first_seen', x[1].get('date_seen', '')), reverse=True)
    for url, data in sorted_jobs[:5]:
        title = data.get('job_data', {}).get('title', data.get('title'))
        fs = data.get('fit_score')
        comp = data.get('compensation')
        reason = data.get('reasoning', '')[:30]
        print(f"Title: {title}, Score: {fs}, Comp: {comp}, Reason: {reason}")
