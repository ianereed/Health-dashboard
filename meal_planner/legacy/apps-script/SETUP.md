# Apps Script Setup

## ARCHIVED

This Apps Script frontend was decommissioned in Phase 18 (2026-05-08).
The Google Sheet is now **read-only**. Do not add or edit recipes here.

**Use instead:** `http://homeserver:8503/?tab=recipes` — the web edit UI
added in Phase 18 A2 is the canonical way to create, edit, and delete recipes.

---

## One-time setup

### 1. Create the Google Sheet

Create a new blank Google Sheet. Note the sheet ID from the URL:
```
https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit
```

The tab name defaults to "Sheet1" — rename it if you like (you'll set it as a Script Property below).

### 2. Copy the script into the Sheet

1. In the Sheet, open **Extensions → Apps Script**
2. Delete the default `myFunction` code
3. Create two files:
   - Rename `Code.gs` to `Code.gs` and paste the contents of `Code.gs` from this repo
   - Click **+** → **HTML** → name it `PhotoCapture` → paste the contents of `PhotoCapture.html`
4. Click **Save** (floppy disk icon)

### 3. Create the `meal-planner` label in Todoist

In Todoist: **Filters & Labels → Add label → `meal-planner`**

This label is applied to every task the script creates, so `consolidate.py` can find and replace them safely without touching manual tasks.

### 4. Set Script Properties

In the Apps Script editor: **Project Settings (gear icon) → Script properties → Add property**

| Property | Value |
|---|---|
| `TODOIST_API_TOKEN` | Your Todoist API token |
| `TODOIST_PROJECT_ID` | `6CrcwVR2PPQ9QWJr` |
| `TODOIST_SECTIONS` | `{"Fruits + Veggies":"67V8V83649hw7fmJ","Dairy + cold items":"67V87Gc83hmQRP9r","Frozen":"67V87Gc83hmQRP9r","Meats":"67V8WqMfpV7vmCjr","Shelf-stable":"67V8RX3xVmgqMfHr","Home/Pharmacy":"67V8596jQ7hR62rr","Asian market":"68RWF3hxgmMf3H6J"}` |
| `GEMINI_API_KEY` | Free key from **aistudio.google.com** → Get API key |
| `SHEET_NAME` | Sheet tab name (e.g. `Sheet1`) |

### 5. Authorize the script

1. Close and reopen the Google Sheet
2. A **Grocery** menu will appear — click it
3. The first time, Google will ask you to authorize the script
4. Click **Review permissions → Allow**

You only need to do this once.

---

## Adding recipes

**By hand:** Type the recipe name in Row 1 of the next empty column. Add ingredients in Row 2 downward, one per cell, formatted as `quantity unit ingredient` (e.g. `2 cups flour`, `1 lb chicken thighs`). Close and reopen the sheet — the recipe appears in the Grocery menu.

**From a photo:** Click **Grocery → Add Recipe from Photo…**, select a photo or take one. Claude extracts the recipe and adds it to the sheet automatically.

---

## Limits

- Supports up to 20 recipes (columns A–T). This covers most home recipe rotations; add more stubs to `Code.gs` if needed.
- Apps Script has a 6-minute execution timeout, which is well above the typical ~10-second Claude API call.

---

## Bulk photo import (`bulk_import.py`)

Use this to load recipes in bulk from a folder of photos. Python handles all
the Gemini vision calls and POSTs the results to an Apps Script web app.

### 1. Add optional secret (recommended)

In the Apps Script editor: **Project Settings → Script properties → Add property**

| Property | Value |
|---|---|
| `BULK_IMPORT_SECRET` | Any random string (e.g. `openssl rand -hex 16`). Leave blank to skip auth. |

### 2. Deploy as web app

1. In the Apps Script editor, click **Deploy → New deployment**
2. Click the gear icon next to "Select type" → choose **Web app**
3. Set **Execute as:** Me (your Google account)
4. Set **Who has access:** Anyone
5. Click **Deploy** → copy the **Web app URL**

### 3. Add to `.env`

```
APPS_SCRIPT_WEBAPP_URL=https://script.google.com/macros/s/YOUR_ID/exec
BULK_IMPORT_SECRET=your_random_secret   # must match Script Property value
```

### 4. Verify & run

```bash
# Verify the web app is live
python bulk_import.py --check

# Dry run (Gemini extracts recipes, nothing written to sheet)
python bulk_import.py ~/Desktop/recipe-photos/ --dry-run

# Full run (extracts + writes to sheet)
python bulk_import.py ~/Desktop/recipe-photos/ --yes
```

### Re-deploying after Code.gs changes

Each time you update `Code.gs`, you must create a **new deployment version**:
**Deploy → Manage deployments → Edit → "New version" → Deploy**.
The web app URL stays the same; only the live version changes.
