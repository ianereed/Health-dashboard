#!/usr/bin/env python3
"""
fill_missing_names.py
For contacts missing first or last name, search Gmail for their emails,
extract name from the From: header display name, and update the sheet.
"""

import re
import time
import gspread
from google.oauth2.service_account import Credentials as SACredentials
from google.oauth2.credentials import Credentials as UserCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SHEET_KEY = r"C:\Users\Ian Reed\Documents\Claude SQL\reference\production-plan-access-4e92a6c9086d.json"
SHEET_ID  = "1z-8VGhT2Hh_KdWfHc2UX0Bkjyaukyinlpx0sJ5WelAA"
SHEET_SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

GMAIL_TOKEN  = "gmail_token.json"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail():
    creds = UserCredentials.from_authorized_user_file(GMAIL_TOKEN, GMAIL_SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def parse_display_name(from_header):
    """Extract display name from 'Display Name <email>' or just 'email'."""
    m = re.match(r'^"?([^"<]+?)"?\s*<', from_header)
    if m:
        return m.group(1).strip()
    return None


def split_name(display_name):
    """Split 'First Last' into (first, last). Handles multi-word names."""
    parts = display_name.strip().split()
    if len(parts) == 0:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    # Last word = last name, rest = first
    return " ".join(parts[:-1]), parts[-1]


def find_name_for_email(gmail, email_addr):
    """Search Gmail for messages from this address, return display name if found."""
    try:
        result = gmail.users().messages().list(
            userId="me",
            q=f"from:{email_addr}",
            maxResults=5,
            fields="messages(id)"
        ).execute()
        messages = result.get("messages", [])
        if not messages:
            # Try searching in To field too
            result = gmail.users().messages().list(
                userId="me",
                q=f"to:{email_addr}",
                maxResults=5,
                fields="messages(id)"
            ).execute()
            messages = result.get("messages", [])
        if not messages:
            return None, None

        for msg in messages:
            detail = gmail.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["From", "To", "Cc"]
            ).execute()
            headers = {h["name"]: h["value"]
                       for h in detail.get("payload", {}).get("headers", [])}

            # Check From header
            for field in ["From", "To", "Cc"]:
                val = headers.get(field, "")
                # Find our target email in this header
                if email_addr.lower() in val.lower():
                    # Extract just the part containing our email
                    for segment in val.split(","):
                        if email_addr.lower() in segment.lower():
                            name = parse_display_name(segment.strip())
                            if name and "@" not in name and len(name) > 1:
                                first, last = split_name(name)
                                return first, last
    except Exception as e:
        print(f"  Error for {email_addr}: {e}")
    return None, None


def main():
    # Connect to sheet
    sa_creds = SACredentials.from_service_account_file(SHEET_KEY, scopes=SHEET_SCOPES)
    gc = gspread.authorize(sa_creds)
    ws = gc.open_by_key(SHEET_ID).sheet1

    rows = ws.get_all_values()
    headers = rows[0]
    first_col = headers.index("First Name")   # 0-indexed
    last_col  = headers.index("Last Name")
    email_col = headers.index("Professional Email")

    # Find rows missing first or last name
    targets = []
    for i, row in enumerate(rows[1:], start=2):
        if len(row) <= max(first_col, last_col, email_col):
            continue
        first = row[first_col].strip()
        last  = row[last_col].strip()
        email = row[email_col].strip()
        if not email:
            continue
        if not first or not last:
            targets.append((i, row, first, last, email))

    print(f"Found {len(targets)} contacts missing first or last name.")

    gmail = get_gmail()
    updates = []
    found = 0

    for i, (row_num, row, cur_first, cur_last, email) in enumerate(targets):
        print(f"  [{i+1}/{len(targets)}] {email} (current: '{cur_first}' '{cur_last}')", end=" -> ")
        new_first, new_last = find_name_for_email(gmail, email)

        if new_first or new_last:
            apply_first = new_first if not cur_first and new_first else cur_first
            apply_last  = new_last  if not cur_last  and new_last  else cur_last
            print(f"'{apply_first}' '{apply_last}'")
            # Column letters (1-indexed)
            col_f = chr(ord("A") + first_col)
            col_l = chr(ord("A") + last_col)
            updates.append({"range": f"{col_f}{row_num}", "values": [[apply_first]]})
            updates.append({"range": f"{col_l}{row_num}", "values": [[apply_last]]})
            found += 1
        else:
            print("not found")

        # Be gentle with Gmail API rate limits
        if i % 20 == 19:
            time.sleep(1)

    if updates:
        for i in range(0, len(updates), 100):
            ws.batch_update(updates[i:i+100])
        print(f"\nUpdated names for {found}/{len(targets)} contacts.")
    else:
        print("No names found to update.")


if __name__ == "__main__":
    main()
