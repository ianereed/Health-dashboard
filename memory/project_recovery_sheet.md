---
name: Project — Recovery Google Sheet
description: Google Sheet for Ian's shoulder surgery recovery tracking — Sheet ID, tabs, service account, scripts
type: project
originSessionId: c9fea4f9-d5be-425c-9794-af0e07140cdb
---
## Sheet
- **URL**: https://docs.google.com/spreadsheets/d/1p-QC3nujdwFbbNNatsoXD1V0YIyW81TByY7Bd8ZlfQA/edit
- **Sheet ID**: `1p-QC3nujdwFbbNNatsoXD1V0YIyW81TByY7Bd8ZlfQA`

## Service account
- **Email**: claude-sheets@noted-branch-492500-c7.iam.gserviceaccount.com
- **Key file**: `C:\Users\Ian Reed\Downloads\noted-branch-492500-c7-192242227131.json`
- **GCP project**: noted-branch-492500-c7

## Python access
- `gspread` 6.2.1 and `google-auth` already installed
- Scripts saved in `C:\Users\Ian Reed\Documents\GitHub\Home-Tools\`
  - `add_recovery_tab.py` — original tab creation
  - `update_sheets.py` — full rebuild with all 4 tabs + PDF renames

## Tabs (as of Apr 14, 2026)
1. **pre-hab** — pre-existing
2. **weekly checklist** — pre-existing
3. **Month 1 Recovery** — Apr 16–May 13 daily schedule, guiding principles, appointment anchors inline, accomplishments
4. **Appointments** — all 10 confirmed appointments (screenshot-authoritative), conflict flags
5. **Surgery Day** — pre-op checklist, fasting, transport, medications to hold, auth info
6. **Recovery Roadmap** — Apr–Sep phases, sports return timeline, Alaska/NM wedding milestones

## Why
Ian is recovering from right shoulder arthroscopy (labral repair, Apr 16 2026) and uses this sheet as a recovery command center.

## How to apply
When adding to the sheet, always use the service account key file above. The screenshot from Apr 14 (`2026-04-14 16_03_34-.png` in Downloads) is the authoritative appointment source — it includes Jul 17 which is missing from all PDFs.
