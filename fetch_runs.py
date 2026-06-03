import urllib.request
import json
import ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
url = 'https://api.github.com/repos/TeoPaso/linkedin_scraper/actions/runs?per_page=10'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, context=ctx) as response:
        data = json.loads(response.read())
        for run in data.get('workflow_runs', []):
            print(f"Run ID: {run['id']}, Status: {run['status']}, Conclusion: {run['conclusion']}, Name: {run['name']}, Created: {run['created_at']}")
except Exception as e:
    print(f'Error: {e}')
