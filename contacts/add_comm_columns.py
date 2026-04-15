#!/usr/bin/env python3
"""
add_comm_columns.py
1. Add "Last Digital Communication Date" column — queried live from Gmail.
2. Add "Worked On Together" column — pre-filled from session context.
"""

import time
import datetime
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

# email (lowercase) -> description of work done together
WORKED_ON = {
    # Leadership
    "andrew@antora.energy":                 "Manufacturing system strategy from ground up; supply forecast dashboards; contractor transition",
    "stephen.sharratt@antora.energy":        "POET commissioning strategy; product dev direction; brought Ian onto team",
    "justin@antora.energy":                  "Co-founder relationship; strategy alignment; board deck cycle time charts",
    "david@antora.energy":                   "Co-founder relationship; technical direction",
    "emmett@antora.energy":                  "AI tool governance discussions; company policy for Claude Cowork",
    "julian.bishop@antora.energy":           "Strategy discussions; general cross-functional coordination",
    "david.bishop@antora.energy":            "Strategy and growth discussions",
    "leah@antora.energy":                    "Heat-to-Power Ops at POET Big Stone; module operations",

    # Management chain
    "jerome.pereira@antora.energy":          "Direct manager 2+ years; NPI team strategy; ops leads meetings; supply forecast; process plan improvements; contractor transition",
    "ranjeet.mankikar@antora.energy":        "Supply chain ops; material flow; operations leads channel; inventory strategy",
    "david.haines@antora.energy":            "Production floor operations; process plans; module build issues; cycle time analysis; ops leads meetings; production schedule dashboards",
    "matthew.reyes@antora.energy":           "Production planning; supply forecast; module schedule tracking; ops leads meetings",
    "indigo.ramey-wright@antora.energy":     "Production readiness meetings; board deck updates; ops leads channel",

    # NPI team
    "benjamin.wilson@antora.energy":         "NPI direct report; GRI table design; CNC gantry mill; carbon block handling; AI/Claude ECO review tool; process plan QA",
    "montgomery.perry@antora.energy":        "NPI direct report; GRI/graphite block staging; factory swap planning; Gen1v5 production ramp",
    "mohammad.al-attiyeh@antora.energy":     "NPI direct report; wiring and marshalling cabinet specialist; process plan updates; electrical quality escapes",
    "dan.freeman@antora.energy":             "NPI direct report; min-max rollout; GD&T improvements; GRI proof testing; lunch-and-learns; Slack notification tools; NC dispo automation",
    "vishal.patel@antora.energy":            "NPI direct report; 10T crane installation; lineside material flow; subassembly layout; warehouse projects",
    "rj.fenton@antora.energy":              "NPI direct report; rigging and lifting documentation; Notion project tracker; block proof testing; GRI table wheels",

    # Module design
    "katelyn.work@antora.energy":            "Leads lunch group; product dev hiring philosophy; subassembly meeting cadence; Gen1v6 planning",
    "tanner.devoe@antora.energy":            "Gen1v6 system changes; heater arcing issues; POET commissioning support; product dev leads sync",
    "huck.dorn@antora.energy":               "Module design discussions; leads lunch; HX and primary cooling; product dev leads sync",
    "kevin.chan@antora.energy":              "Leads lunch; blocks, insulation, throttle engineering; Gen1v6 cost-down; NPI manager transition",
    "hayden.hall@antora.energy":             "Storage block mass dashboard (built on request); module shipping/loading constraints; Gen1v6 block design",
    "jack.boes@antora.energy":              "Manufacturing engineering discussions; GRI table; module-level quality checklist",
    "nigel.myers@antora.energy":             "Electrode and heater component work; leads lunch engineering space planning",
    "gabrielle.landess@antora.energy":       "GRI and HT insulation PDR; Gen1v5 EVT build; ski trip cabin organizer",
    "galilea.vonruden@antora.energy":        "HX primary and secondary cooling ownership (from Anny); Gen1v6 design",
    "luigi.celano@antora.energy":            "GRI damage inspection SOP; quality engineering; antora-product-dev discussions",
    "ethan.ananny@antora.energy":            "HX/JIC fittings/Resbond engineering; toeboard work instructions; early Antora module builds",
    "bharadwaja@antora.energy":              "Heater v7 development; ARI program; R&D test discussions; POET operations data",
    "anny.ning@antora.energy":              "Partner; Mech Eng Manager; HTF leak test revisions; Gen1v5 EVT build co-owner; product dev hiring",
    "anders.laederich@antora.energy":        "AI tools discussions; product dev engineering collaboration",
    "jasmine.chugh@antora.energy":           "Paratherm HTF analysis; Pratt plant design; process engineering",
    "devon.story@antora.energy":             "BOP design; Pratt project cost-down; e-boiler; plant engineering leadership",
    "samantha.hudgens@antora.energy":        "TPM for issue tracking and 8D process; product dev leads sync",
    "jordan.leventhal@antora.energy":        "Project execution; transformer supply chain; POET project financials",
    "tom.bence@antora.energy":              "POET project execution and commissioning leadership; product dev leads sync",
    "alec.burns@antora.energy":              "POET commissioning manager; module handoffs; Big Stone site operations",
    "donald.haines@antora.energy":           "POET Big Stone site operations; module O&M; steam production scheduling",
    "bijan.shiravi@antora.energy":           "TPM for POET field work instructions; PTC testing; UL certification; all-hands organizer",
    "scott.fife@antora.com":                "EHS safety protocols; gas monitor management; PPE compliance",
    "kai.caindec@antora.energy":             "Module design engineering; UL rain test; cladding and power delivery",
    "alyssa.higdon@antora.energy":           "Controls and software engineering collaboration",
    "davis.hoffman@antora.energy":           "Gas systems (N2, HTF) engineering; module-level gas system design",

    # R&D
    "dustin@antora.energy":                  "R&D testing leadership; POET commissioning; hotter HTF testing; module-level test campaigns",
    "tarun@antora.energy":                   "POET performance data analysis; ops metrics dashboard; supply forecast data validation",
    "nick.azpiroz@antora.energy":            "GrafTech DAQ system; Gen1v5 EVT build co-owner; test automation; schedule planning",
    "connor.grady@antora.energy":            "R&D test pad operations; AI/tool discussions",
    "rachel.lindley@antora.energy":          "Mod 5 test campaigns; GrafTech DAQ #2 build",
    "garun.arustamov@antora.energy":         "Electrode development; heater test support; R&D operations",
    "carson.townsend@antora.energy":         "Rainier Database (module test cycle reports); controls and automation",
    "david.crudo@antora.energy":             "R&D operations; HTF movement and storage; test equipment",
    "sean.gray@antora.energy":               "Controls and software engineering; module standard software updates",
    "saujan.sivaram@antora.energy":          "Materials process engineering; carbon block material work",
    "grace.yee@antora.energy":               "Reliability engineering; Exponent safety analysis discussions",
    "jacob.ng@antora.energy":               "R&D test operations; module test technician work",

    # Product / PM
    "nicolas.robert@antora.energy":         "Onboarding to Claude Code and Antora Analytics; product requirements in Notion; Gen1v6 product requirements",
    "raghavendra.pai@antora.energy":         "Product management; international pipeline; AI tool usage discussions",
    "bijan.shiravi@antora.energy":           "TPM; POET field WI process; PTC testing roadmap",
    "sam.kortz@antora.com":                 "Compliance and issue tracking; UL field evaluation; GrafTech DAQ coordination",

    # Supply chain
    "william.clark@antora.energy":           "Supplier development; NC RTV dispositions with vendors; npi-directs team",
    "tom.butler@antora.energy":              "Strategic supply chain for HX/Skid/Cladding; CNC machine procurement; Metalli China supplier",
    "paula.loures@antora.energy":            "CNC machine procurement coordination (Haas gantry mill); Selway Tool commissioning",
    "charles.su@antora.energy":             "Material planning; supply forecast validation; inventory data; MRP analysis",
    "jorge.pascual@antora.energy":           "Production planning; daily process plan updates; inventory discrepancies; VMI setup",
    "miles.pereira@antora.energy":           "Procurement; lineside tote sizing study; warehouse projects",
    "emily.wang@antora.energy":              "Supply chain coordination; GRI kit inventory",

    # Logistics
    "daniel.park@antora.energy":            "Created #warehouse-projects channel for Dan; material flow engineering; min-max design; receiving issue tracking system",
    "kimbo.lorenzo@antora.energy":          "Hot board kanban system; major component replenishment form and dashboard",
    "akos.vesztergombi@antora.energy":      "Zanker facility projects: racking, asphalt, fire sprinkler upgrade, roof repair; ops leads channel",
    "nathaniel.chaffin-reed@antora.energy": "Inventory operations; AI tools for block image classification",
    "jorge.pascual@antora.energy":          "Production planning; process plan corrections; inventory coordination",

    # Quality / Production
    "oliver.paje@antora.energy":            "NC dispo approval Slack notifier (built for his workflow); incoming quality inspection",
    "gui.divanach@antora.energy":           "NC dispo approval notifier; quality/SQE discussions; dimensional inspection AI tools",
    "ron.cuadro@antora.energy":             "Quality operations; NC dispo channel",
    "phillip.rutherford@antora.energy":      "Daily process plan updates and WO corrections alongside Jorge Pascual",
    "aaron.sanchez@antora.energy":          "Production supervision; Mod 100 milestone; assembly floor operations",
    "leautry.bruner@antora.energy":         "Production supervision; block installation; crane operations",
    "edward.montejano@antora.energy":       "Production lead; toeboard installation feedback; cladding wall assembly",
    "larry.madrid@antora.energy":           "Production floor; process plan issue identification",
    "jorge.pascual@antora.energy":          "Production planning analyst; process plan coordination",
    "douglas.soga@antora.energy":           "Production supervision",

    # People / Facilities
    "becky.romero@antora.energy":           "Contractor transition logistics: hourly rate, COBRA, badge return, UKG status change",
    "kathleen.haynes@antora.energy":        "HR support; Ian transition; interview panel for new hire",
    "sebastien.lounis@antora.energy":       "People and culture leadership; Home Week events; farewell",
    "sherri.bhola@antora.energy":           "Executive admin support; scheduling; AI scheduling assistant project discussion",
    "john.perna@antora.energy":             "Dado facility setup; crane/equipment projects; CNC machine installation; forklift and material handling",

    # IT / Admin
    "gagan.malik@antora.energy":            "Claude/ChatGPT enterprise rollout; API token limits; AI tool governance; Claude Cowork safety guidance",
    "ben@antora.energy":                    "GitHub org access setup; antora-energy/Antora-Analytics repo; IT/security guidance for Claude Cowork",
    "haley@antora.energy":                  "Business ops; workspace admin; AI tool vetting partnership with Gagan",
    "annie.otfinoski@antora.energy":        "AI tool discussions; Australia pipeline CRM project; business ops",
    "ben.bierman@antora.energy":            "Finance/ops; consulting rate guidance for Ian's contractor transition",
    "liz.theurer@antora.energy":            "NetSuite TBA connector setup; cloud hosting for automations; MFO replica DB access",
    "john.kelly@antora.energy":             "Operations discussions; MFO process questions",

    # External — Andea/Manufacturo
    "aschalke@manufacturo.com":             "Manufacturo platform — primary account contact; system upgrades, support tickets, feature requests",
    "rsulikowski@andea.com":                "Andea/Manufacturo implementation support",
    "jdabrowska@andea.com":                 "Andea/Manufacturo implementation support",
    "tlorens@andea.com":                    "Andea/Manufacturo — platform support and implementation",
    "jmontgomery@andea.com":                "Andea/Manufacturo support",
    "pmierzwa@andea.com":                   "Andea/Manufacturo support",
    "pmierzwa@manufacturo.com":             "Manufacturo support tickets and platform issues",
    "pwidziszewski@manufacturo.com":        "Manufacturo helpdesk; platform configuration; data collection migration",
    "ntrafimuk@manufacturo.com":            "Manufacturo support",
    "sgombervaux@manufacturo.com":          "Manufacturo support",
    "dkubala@manufacturo.com":              "Manufacturo support",
    "dclarke@manufacturo.com":              "Manufacturo support",

    # External — Kundel
    "elton@kundel.com":                     "Kundel workstation and overhead crane procurement for Zanker facility",
    "jennifer.b@kundel.com":                "Kundel crane procurement and support",
    "jima@kundel.com":                      "Kundel crane procurement and support",
    "andrew@kundel.com":                    "Kundel crane support",
    "annie@kundel.com":                     "Kundel crane support",

    # External — Combilift
    "don.johnson@combilift.com":            "Combilift forklift — service records, capacity limits, operational questions",
    "niall.crehan@combilift.com":           "Combilift — primary Bay Area sales/service contact; forklift procurement and support",
    "bret.hebenstreit@combilift.com":       "Combilift support",

    # External — LWD Advisors
    "jeff@lwdadvisors.com":                 "Outside legal counsel for Antora; startup contracts and corporate legal",
    "david@lwdadvisors.com":                "Outside legal counsel — most active LWD contact",
    "sandelin@lwdadvisors.com":             "LWD Advisors legal associate",
    "rory@lwdadvisors.com":                 "LWD Advisors legal support",

    # External — Selway Tool
    "mattselway@selwaytool.com":            "Haas CNC gantry mill procurement and commissioning coordination",
    "iruvalcaba@selwaytool.com":            "Selway Tool — CNC machine support",
    "hcuevas@selwaytool.com":               "Selway Tool — CNC machine support",
    "kpharis@selwaytool.com":               "Selway Tool — CNC machine support",

    # External — Pape MH
    "sgoud@papemh.com":                     "Pape Material Handling — forklift and material handling equipment",
    "tnolan@papemh.com":                    "Pape Material Handling — equipment support",
    "rbray@papemh.com":                     "Pape Material Handling — equipment support",

    # External — Allied Crane
    "jason@alliedcrane.us":                 "Allied Crane — overhead crane service and maintenance at Zanker",
    "sandy@alliedcrane.us":                 "Allied Crane — crane service support",

    # External — Cargo Modules
    "delano.melikian@cargomodules.com":     "Cargo Modules — module shipping and freight logistics",
    "reto.kaufmann@cargomodules.com":       "Cargo Modules — freight logistics",
    "mitch.gorge@cargomodules.com":         "Cargo Modules — freight logistics",

    # External — Bart Manufacturing
    "tweissbart@bartmanufacturing.com":     "Bart Manufacturing — aluminum welding and electromechanical fabrication (Santa Clara)",
    "lgarcia@bartmanufacturing.com":        "Bart Manufacturing — fabrication",

    # External — Math Mec
    "tmartinez@mathmec.com":                "Mathews Mechanical — CNC machining and fabrication vendor",

    # External — WithMagenta
    "yaron@withmagenta.com":                "WithMagenta (Manufacturo partner) — MES platform discussions",
    "davide@withmagenta.com":               "WithMagenta — Manufacturo implementation",
    "dave@withmagenta.com":                 "WithMagenta — platform support",

    # External — American Rigging
    "william@american-rigging.com":         "American Rigging — CNC machine delivery and rigging to Dado facility",
    "billjr@american-rigging.com":          "American Rigging — rigging support",

    # External — Thermtest
    "sdoiron@thermtest.com":                "Thermtest — thermal measurement equipment and calibration",
    "kpalmer@thermtest.com":                "Thermtest — thermal measurement support",
    "tcurtis@thermtest.com":                "Thermtest — thermal measurement support",

    # External — Rapid Axis
    "marc@rapidaxis.com":                   "Rapid Axis — CNC machining and rapid prototyping",
    "jared@rapidaxis.com":                  "Rapid Axis — machining and prototyping",

    # External — Fastenal
    "kjauregu@fastenal.com":                "Fastenal — industrial hardware and fastener supply for production floor",
    "devans@fastenal.com":                  "Fastenal — industrial supply",

    # External — Metalli China
    "edwin_zuo@metalli-china.com":          "Metalli China — carbon/graphite block material supplier; GRI furnace runs",
    "chris_qin@metalli-china.com":          "Metalli China — carbon material supplier",

    # External — PTC/Onshape
    "smoisan@ptc.com":                      "PTC/Onshape — CAD and PLM platform used for Arena integration and ECO workflow",

    # External — Transcend Technology
    "dpazdel@transcendtechnologyllc.com":   "Transcend Technology — technology vendor collaboration",
    "jling@transcendtechnologyllc.com":     "Transcend Technology — vendor support",

    # External — JL Precision
    "bgrizelj@jlprecision.com":             "JL Precision — CNC machining vendor",
    "mbince@jlprecision.com":               "JL Precision — machining support",

    # External — Real-Pak
    "iperez@real-pak.com":                  "Real-Pak — packaging and logistics vendor",
    "lperez@real-pak.com":                  "Real-Pak — packaging and logistics",
    "abeperez@real-pak.com":                "Real-Pak — packaging and logistics",

    # External — Lobo Systems
    "h.bokros@lobosystems.com":             "Lobo Systems — equipment vendor",
    "p.timson@lobosystems.com":             "Lobo Systems — equipment support",

    # External — Align Production Systems
    "jdresselhaus@alignprod.com":           "Align Production Systems — MES/manufacturing software",
    "bschmidt@alignprod.com":               "Align Production Systems — software support",

    # External — PASE
    "bwells@pase.com":                      "PASE — vendor collaboration",
    "rokano@pase.com":                      "PASE — vendor collaboration",

    # External — Anacapa
    "mark.heisler@anacapa.com":             "Anacapa — engineering firm collaboration",
    "marc.oberholzer@anacapa.com":          "Anacapa — engineering support",
    "stuart.heisler@anacapa.com":           "Anacapa — engineering support",

    # External — Haskell
    "patrick.ettorre@haskell.com":          "Haskell — engineering and construction firm; POET site work",

    # External — DHL
    "james.advincula@dhl.com":              "DHL — module freight and logistics",

    # External — Rexel
    "jarrod.levine@rexelusa.com":           "Rexel — electrical components distribution",

    # External — Fab.AI
    "michael@fabai.com":                    "Fab.AI — manufacturing AI software discussions",

    # External — Flexible Lifeline
    "kevin.courtney@flexiblelifeline.com":  "Flexible Lifeline Systems — fall protection and safety equipment for production floor",

    # External — Safety Net
    "davidb@safetynetinc.com":             "Safety Net Inc — safety equipment vendor",

    # External — Moody SE
    "joshua@moodyse.com":                   "Moody Structural Engineers — structural engineering support for facility projects",

    # External — Hex
    "charles@hex.tech":                     "Hex — analytics dashboard platform; support for Hex API and dashboard publishing",
    "nicole@hex.tech":                      "Hex — platform support",
    "alex@hex.tech":                        "Hex — platform support",

    # External — Breakthrough Energy / Sequoia
    "peter@breakthroughenergy.org":         "Breakthrough Energy — Antora investor; stakeholder reporting and demos",
    "ben.ruben@breakthroughenergy.org":     "Breakthrough Energy — investor contact",
    "jackie.brown@sequoia.com":             "Sequoia Capital — Antora investor; board-level reporting",
    "ashley.mckenzie@sequoia.com":          "Sequoia Capital — investor contact",

    # External — LNJ Bhilwara
    "mayank.saxena@lnjbhilwara.com":        "LNJ Bhilwara — Indian carbon/graphite material supplier",

    # External — Plastec Ventilation
    "contact@plastecventilation.com":       "Plastec Ventilation — HVAC/ventilation equipment for facility",
    "eduardo@plastecventilation.com":       "Plastec Ventilation — ventilation equipment support",

    # External — JZC Carbons
    "ella@jzc-carbons.com":                 "JZC Carbons — carbon material supplier",

    # External — 3Laws
    "zach@3laws.io":                        "3Laws Robotics — robotics safety solutions discussion",

    # External — Clean Power
    "kelly.darnell@cleanpower.org":         "American Clean Power Association — clean energy policy and regulatory discussions",

    # External — Pape MH extra
    "rbray@papemh.com":                     "Pape Material Handling — equipment support",
}


def get_gmail():
    creds = UserCredentials.from_authorized_user_file(GMAIL_TOKEN, GMAIL_SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def get_last_email_date(gmail, email_addr):
    """Return YYYY-MM-DD of most recent email from or to this address."""
    try:
        result = gmail.users().messages().list(
            userId="me",
            q=f"{email_addr}",
            maxResults=1,
            fields="messages(id)"
        ).execute()
        msgs = result.get("messages", [])
        if not msgs:
            return ""
        detail = gmail.users().messages().get(
            userId="me",
            id=msgs[0]["id"],
            format="metadata",
            metadataHeaders=["Date"]
        ).execute()
        headers = {h["name"]: h["value"]
                   for h in detail.get("payload", {}).get("headers", [])}
        date_str = headers.get("Date", "")
        if date_str:
            from email.utils import parsedate_to_datetime
            try:
                dt = parsedate_to_datetime(date_str)
                return dt.strftime("%Y-%m-%d")
            except Exception:
                pass
    except Exception as e:
        print(f"  Error {email_addr}: {e}")
    return ""


def main():
    sa_creds = SACredentials.from_service_account_file(SHEET_KEY, scopes=SHEET_SCOPES)
    gc = gspread.authorize(sa_creds)
    ws = gc.open_by_key(SHEET_ID).sheet1

    rows = ws.get_all_values()
    headers = rows[0]
    email_col = headers.index("Professional Email")

    # Add new column headers if missing
    new_cols = ["Last Digital Communication", "Worked On Together"]
    col_offset = len(headers)
    for i, col in enumerate(new_cols):
        if col not in headers:
            ws.update_cell(1, col_offset + i + 1, col)
            headers.append(col)

    # Re-read to get updated headers
    rows = ws.get_all_values()
    headers = rows[0]
    comm_col  = headers.index("Last Digital Communication") + 1  # 1-indexed for Sheets
    worked_col = headers.index("Worked On Together") + 1

    gmail = get_gmail()
    updates = []
    total = len(rows) - 1
    print(f"Processing {total} contacts...")

    for i, row in enumerate(rows[1:], start=2):
        if len(row) <= email_col:
            continue
        email = row[email_col].strip().lower()
        if not email:
            continue

        # Only query Gmail for external (non-Antora) contacts
        if (i - 1) % 10 == 0:
            print(f"  {i-1}/{total}...", end="\r")

        internal = email.endswith("@antora.energy") or email.endswith("@antora.com")
        date = "" if internal else get_last_email_date(gmail, email)
        worked = WORKED_ON.get(email, "")

        col_comm  = chr(ord("A") + comm_col - 1)
        col_work  = chr(ord("A") + worked_col - 1)
        updates.append({"range": f"{col_comm}{i}",  "values": [[date]]})
        updates.append({"range": f"{col_work}{i}",  "values": [[worked]]})

        # Rate limit
        if i % 50 == 0:
            time.sleep(0.5)

    print(f"\nWriting {len(updates)} updates to sheet...")
    for j in range(0, len(updates), 100):
        ws.batch_update(updates[j:j+100])

    print("Done.")


if __name__ == "__main__":
    main()
