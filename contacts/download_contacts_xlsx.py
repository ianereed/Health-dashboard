#!/usr/bin/env python3
"""Download the contacts Google Sheet as xlsx."""

import requests
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request

KEY_FILE = r"C:\Users\Ian Reed\Documents\Claude SQL\reference\production-plan-access-4e92a6c9086d.json"
SHEET_ID  = "1z-8VGhT2Hh_KdWfHc2UX0Bkjyaukyinlpx0sJ5WelAA"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
OUTPUT   = r"C:\Users\Ian Reed\Documents\GitHub\Home-Tools\contacts\antora_contacts.xlsx"

import os
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

creds = Credentials.from_service_account_file(KEY_FILE, scopes=SCOPES)
creds.refresh(Request())

url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"
resp = requests.get(url, headers={"Authorization": f"Bearer {creds.token}"})
resp.raise_for_status()

with open(OUTPUT, "wb") as f:
    f.write(resp.content)
print(f"Saved {len(resp.content):,} bytes to {OUTPUT}")
