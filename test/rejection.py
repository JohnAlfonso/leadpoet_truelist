from Leadpoet.utils.cloud_db import get_rejection_feedback
import bittensor as bt
import requests
import json

url = "https://www.subnet71.com/api/lead-search"
params = {
    "uid": 13,
    "limit": 1000
}

response = requests.get(url, params=params)

# Check if request worked
response.raise_for_status()

data = response.json()

# print(json.dumps(data, indent=2))
# exit()

results = []
for lead in data['results']:
    email_hash = lead['emailHash']
    url = f"https://qplwoislplkcegvdmbim.supabase.co/rest/v1/transparency_log?select=*&email_hash=eq.{email_hash}&order=ts.asc"

    apikey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFwbHdvaXNscGxrY2VndmRtYmltIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQ4NDcwMDUsImV4cCI6MjA2MDQyMzAwNX0.5E0WjAthYDXaCWY6qjzXm2k20EhadWfigak9hleKZk8"

    headers = {
        "Authorization": f"Bearer {apikey}",
        "apikey": apikey,
        "Content-Type": "application/json"
    }

    # Use params instead of building URL manually
    response = requests.get(url, headers=headers, timeout=30)
    data = response.json() if response.text else []
    
    if data[-1]['event_type'] == "CONSENSUS_RESULT" and data[-1]['payload']['final_decision'] == 'deny':
        print (email_hash)
        print (json.loads(data[-1]['payload']['primary_rejection_reason']))
        
        results.append({
            "email_hash": email_hash,
            "reason": json.loads(data[-1]['payload']['primary_rejection_reason'])
        })
        
print (len(results))
with open("output.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
        