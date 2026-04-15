#!/usr/bin/env python3
"""
gmail_all_vendors.py — find every external vendor Ian has emailed across all time.
Reads ALL email (no date filter), extracts unique external addresses,
filters out bots/notifications, outputs ranked by frequency.
"""

import os
import re
from collections import defaultdict

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_FILE = "gmail_token.json"
CREDS_FILE = "credentials.json"

INTERNAL_DOMAINS = {"antora.energy", "antora.com", "antoraenergy.com"}
MY_EMAIL = "ian.reed@antora.energy"

# Patterns that indicate automated/bot senders — skip these
BOT_PATTERNS = re.compile(
    r"(noreply|no-reply|donotreply|do-not-reply|notifications?|mailer|"
    r"bounce|postmaster|daemon|auto.?reply|newsletter|alerts?|support@|"
    r"billing@|invoices?@|calendar-notification|notify@|info@|admin@|"
    r"updates?@|feedback@|hello@|team@|help@|accounts?@|"
    r"github|slack|atlassian|jira|confluence|greenhouse|linkedin|"
    r"expensify|saashr|anthropic|claude|openai|chatgpt|notion|"
    r"google|stripe|quickbooks|zoom|calendly|dropbox|docusign|"
    r"wexhealth|anthem|cobra|carta|"
    r"manufacturo\.atlassian|antora-energy\.atlassian|"
    r"arena\.solutions|bom\.com|"
    r"campaign|em\d+\.|phx\d+\.|send\.|mail\.|bounce@|"
    r"\.bounces\.|docos\.bounces|"
    r"\d{8,}@|reply-[a-z0-9]+@)",
    re.IGNORECASE
)


def get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def extract_emails(header_value):
    return re.findall(r"[\w.+\-]+@[\w.\-]+\.\w+", header_value or "")


def is_internal(email):
    domain = email.split("@")[-1].lower()
    return domain in INTERNAL_DOMAINS


def is_bot(email):
    return bool(BOT_PATTERNS.search(email))


def main():
    service = get_service()

    print("Fetching all message IDs (no date filter — this may take a while)...")
    all_ids = []
    page_token = None
    page = 0
    while True:
        kwargs = {"userId": "me", "maxResults": 500,
                  "fields": "messages(id),nextPageToken"}
        if page_token:
            kwargs["pageToken"] = page_token
        result = service.users().messages().list(**kwargs).execute()
        msgs = result.get("messages", [])
        all_ids.extend(m["id"] for m in msgs)
        page += 1
        print(f"  Page {page}: {len(all_ids)} messages so far...", end="\r")
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    print(f"\nTotal messages: {len(all_ids)}. Now extracting headers...")

    contacts = defaultdict(int)
    HEADER_FIELDS = ["From", "To", "Cc"]

    def handle(request_id, response, exception):
        if exception:
            return
        headers = {h["name"]: h["value"]
                   for h in response.get("payload", {}).get("headers", [])}
        for field in HEADER_FIELDS:
            for email in extract_emails(headers.get(field, "")):
                email = email.lower()
                if email == MY_EMAIL.lower():
                    continue
                if is_internal(email):
                    continue
                if is_bot(email):
                    continue
                contacts[email] += 1

    batch_size = 100
    for i in range(0, len(all_ids), batch_size):
        batch = all_ids[i:i + batch_size]
        batch_req = service.new_batch_http_request(callback=handle)
        for mid in batch:
            batch_req.add(service.users().messages().get(
                userId="me", id=mid, format="metadata",
                metadataHeaders=HEADER_FIELDS))
        batch_req.execute()
        if (i // batch_size) % 10 == 0:
            print(f"  Processed {i + len(batch)}/{len(all_ids)} messages, "
                  f"{len(contacts)} unique vendors so far...", end="\r")

    print(f"\nDone. {len(contacts)} unique external addresses found.")

    # Sort by frequency
    sorted_contacts = sorted(contacts.items(), key=lambda x: -x[1])

    with open("gmail_all_vendors.txt", "w", encoding="utf-8") as f:
        f.write(f"ALL EXTERNAL VENDOR CONTACTS — Ian Reed @ Antora Energy\n")
        f.write(f"Total unique addresses: {len(sorted_contacts)}\n")
        f.write("=" * 60 + "\n")
        for email, count in sorted_contacts:
            f.write(f"{count:>5}  {email}\n")

    print(f"Written to gmail_all_vendors.txt")
    print(f"\nTop 30:")
    for email, count in sorted_contacts[:30]:
        print(f"  {count:>4}  {email}")


if __name__ == "__main__":
    main()
