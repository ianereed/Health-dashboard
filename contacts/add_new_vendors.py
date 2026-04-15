#!/usr/bin/env python3
"""Add all new vendor contacts found in full Gmail history scan."""

import gspread
from google.oauth2.service_account import Credentials

KEY_FILE = r"C:\Users\Ian Reed\Documents\Claude SQL\reference\production-plan-access-4e92a6c9086d.json"
SHEET_ID = "1z-8VGhT2Hh_KdWfHc2UX0Bkjyaukyinlpx0sJ5WelAA"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# First Last, Prof Email, Personal, Title, Phone, LinkedIn, LastContacted, Notes, Location, Tags
NEW_VENDORS = [
    # ANDEA / MANUFACTURO
    ("Adam","Schalke","aschalke@manufacturo.com","","","","","","Top Manufacturo/Andea contact at 93 emails. Key account manager for Antora. Andea and Manufacturo are sister companies.","Remote (Poland)","Vendor; Manufacturo; Andea; Software; MES"),
    ("","Sulikowski","rsulikowski@andea.com","","","","","","Andea team. 74 emails.","Remote (Poland)","Vendor; Andea; Software"),
    ("","Dabrowska","jdabrowska@andea.com","","","","","","Andea team. 71 emails.","Remote (Poland)","Vendor; Andea; Software"),
    ("Tomasz","Lorens","tlorens@andea.com","","","","","","Andea team. 49 emails.","Remote (Poland)","Vendor; Andea; Software"),
    ("","Montgomery","jmontgomery@andea.com","","","","","","Andea team. 16 emails.","Remote (Poland)","Vendor; Andea; Software"),
    ("Pawel","Mierzwa","pmierzwa@andea.com","","","","https://www.linkedin.com/in/pawelmierzwa/","","Andea/Manufacturo. Also has pmierzwa@manufacturo.com. 17 emails.","Remote (Poland)","Vendor; Andea; Manufacturo; Software"),
    ("","Warcholik","kwarcholik@andea.com","","","","","","Andea team. 3 emails.","Remote (Poland)","Vendor; Andea; Software"),
    ("","Clarke","dclarke@manufacturo.com","","","","","","Manufacturo team. 11 emails.","Remote (Poland)","Vendor; Manufacturo; Software"),
    ("","Niemiec","mniemiec@manufacturo.com","","","","","","Manufacturo team. 6 emails.","Remote (Poland)","Vendor; Manufacturo; Software"),
    ("Artur","Biernat","abiernat@manufacturo.com","","","","https://www.linkedin.com/in/artur-biernat-krk/","","Manufacturo team. 5 emails.","Remote (Poland)","Vendor; Manufacturo; Software"),
    ("","Rogan","krogan@manufacturo.com","","","","","","Manufacturo team. 5 emails.","Remote (Poland)","Vendor; Manufacturo; Software"),

    # KUNDEL INDUSTRIES
    ("Elton","Cervera","elton@kundel.com","","Business Development","","https://www.linkedin.com/in/elton-cervera-26000812/","","Kundel Industries - overhead/workstation crane manufacturer. Primary contact, 68 emails.","Vienna, OH","Vendor; Crane; Equipment; Facilities"),
    ("Jennifer","","jennifer.b@kundel.com","","","","","","Kundel Industries. 46 emails.","Vienna, OH","Vendor; Crane; Equipment"),
    ("Jim","","jima@kundel.com","","","","","","Kundel Industries. 40 emails.","Vienna, OH","Vendor; Crane; Equipment"),
    ("Andrew","","andrew@kundel.com","","","","","","Kundel Industries. 9 emails.","Vienna, OH","Vendor; Crane; Equipment"),
    ("Annie","","annie@kundel.com","","","","","","Kundel Industries. 2 emails.","Vienna, OH","Vendor; Crane; Equipment"),

    # COMBILIFT
    ("Niall","Crehan","niall.crehan@combilift.com","","Regional Manager","","https://www.linkedin.com/in/niall-crehan-5614a212a/","","Combilift Regional Manager - Bay Area. 64 emails. Primary Combilift sales contact.","San Francisco, CA","Vendor; Forklift; Equipment; Facilities"),
    ("Bret","Hebenstreit","bret.hebenstreit@combilift.com","","","","","","Combilift. 41 emails.","Remote","Vendor; Forklift; Equipment"),

    # LWD ADVISORS (legal counsel)
    ("Jeff","Hyman","jeff@lwdadvisors.com","","Founder / Outside Counsel","","https://www.linkedin.com/in/jeff-hyman-385a42/","","LWD Advisors - Antora outside legal counsel for startup contracts. 22 emails.","Menlo Park, CA","Legal; Counsel; Vendor"),
    ("David","","david@lwdadvisors.com","","Outside Counsel","","","","LWD Advisors. Most active LWD contact at 42 emails.","Menlo Park, CA","Legal; Counsel; Vendor"),
    ("Sandelin","Sikes","sandelin@lwdadvisors.com","","Associate","","https://www.linkedin.com/in/sandelin-sikes-b86b03208/","","LWD Advisors - Associate. 18 emails.","Menlo Park, CA","Legal; Counsel; Vendor"),
    ("Rory","","rory@lwdadvisors.com","","Outside Counsel","","","","LWD Advisors. 8 emails.","Menlo Park, CA","Legal; Counsel; Vendor"),

    # MATHEWS MECHANICAL / MATH MEC
    ("","Martinez","tmartinez@mathmec.com","","","","","","Mathews Mechanical (mathmec.com) - machining and fabrication vendor. 53 emails.","Fremont, CA","Vendor; Machining; Fabrication; CNC"),

    # TRANSCEND TECHNOLOGY
    ("","Pazdel","dpazdel@transcendtechnologyllc.com","","","","","","Transcend Technology LLC. 40 emails.","Remote","Vendor; Technology"),
    ("","Ling","jling@transcendtechnologyllc.com","","","","","","Transcend Technology LLC. 8 emails.","Remote","Vendor; Technology"),

    # CARGO MODULES
    ("Delano","Melikian","delano.melikian@cargomodules.com","","Supply Chain & Logistics Executive","","https://www.linkedin.com/in/delano-melikian-a1062a5/","","Cargo Modules LLC - freight and logistics. 18 emails.","Los Angeles, CA","Vendor; Logistics; Freight"),
    ("Reto","Kaufmann","reto.kaufmann@cargomodules.com","","","","https://www.linkedin.com/in/reto-kaufmann-7aa754103/","","Cargo Modules LLC. 12 emails.","Torrance, CA","Vendor; Logistics; Freight"),
    ("Mitch","Gorge","mitch.gorge@cargomodules.com","","","","","","Cargo Modules LLC. 10 emails.","Remote","Vendor; Logistics; Freight"),

    # BART MANUFACTURING
    ("","Weissbart","tweissbart@bartmanufacturing.com","","","","","","Bart Manufacturing - aluminum welding and electromechanical fabrication. Santa Clara. 30 emails.","Santa Clara, CA","Vendor; Fabrication; Welding; CNC"),
    ("","Garcia","lgarcia@bartmanufacturing.com","","","","","","Bart Manufacturing. 26 emails.","Santa Clara, CA","Vendor; Fabrication; Welding"),

    # LOBO SYSTEMS
    ("","Bokros","h.bokros@lobosystems.com","","","","","","Lobo Systems. 20 emails.","Remote","Vendor; Equipment"),
    ("","Timson","p.timson@lobosystems.com","","","","","","Lobo Systems. 10 emails.","Remote","Vendor; Equipment"),

    # ALIGN PRODUCTION SYSTEMS
    ("","Dresselhaus","jdresselhaus@alignprod.com","","","","","","Align Production Systems. 19 emails.","Remote","Vendor; Software; MES"),
    ("","Schmidt","bschmidt@alignprod.com","","","","","","Align Production Systems. 7 emails.","Remote","Vendor; Software; MES"),

    # PASE
    ("","Wells","bwells@pase.com","","","","","","PASE. 16 emails.","Remote","Vendor"),
    ("","Okano","rokano@pase.com","","","","","","PASE. 16 emails.","Remote","Vendor"),

    # JL PRECISION
    ("","Grizelj","bgrizelj@jlprecision.com","","","","","","JL Precision - machining vendor. 16 emails.","Remote","Vendor; Machining; CNC"),
    ("","Bince","mbince@jlprecision.com","","","","","","JL Precision. 8 emails.","Remote","Vendor; Machining"),

    # REAL-PAK
    ("","Perez","iperez@real-pak.com","","","","","","Real-Pak. 23 emails.","Remote","Vendor; Packaging; Logistics"),
    ("","Perez","lperez@real-pak.com","","","","","","Real-Pak. 18 emails.","Remote","Vendor; Packaging; Logistics"),
    ("","Perez","abeperez@real-pak.com","","","","","","Real-Pak. 11 emails.","Remote","Vendor; Packaging; Logistics"),

    # ALLIED CRANE
    ("Jason","","jason@alliedcrane.us","","","","","","Allied Crane - crane service and maintenance. 15 emails.","San Jose, CA","Vendor; Crane; Equipment; Facilities"),
    ("Sandy","","sandy@alliedcrane.us","","","","","","Allied Crane. 5 emails.","San Jose, CA","Vendor; Crane; Equipment"),

    # PTC / ONSHAPE
    ("","Moisan","smoisan@ptc.com","","","","","","PTC/Onshape - CAD and PLM platform contact. 23 emails.","Remote","Vendor; CAD; Software; PLM"),

    # FASTENAL
    ("","Jauregui","kjauregu@fastenal.com","","","","","","Fastenal - industrial supply distributor. Primary contact, 14 emails.","San Jose, CA","Vendor; Industrial Supply; Distributor"),
    ("","Evans","devans@fastenal.com","","","","","","Fastenal. 8 emails.","San Jose, CA","Vendor; Industrial Supply"),

    # METALLI CHINA
    ("Edwin","Zuo","edwin_zuo@metalli-china.com","","","","","","Metalli China - carbon and graphite material supplier. 3 emails.","China","Vendor; Materials; Carbon; Supplier"),
    ("Chris","Qin","chris_qin@metalli-china.com","","","","","","Metalli China. 3 emails.","China","Vendor; Materials; Carbon"),

    # ANACAPA
    ("Mark","Heisler","mark.heisler@anacapa.com","","","","","","Anacapa - engineering firm. 8 emails.","Remote","Vendor; Engineering"),
    ("Marc","Oberholzer","marc.oberholzer@anacapa.com","","","","","","Anacapa. 8 emails.","Remote","Vendor; Engineering"),
    ("Stuart","Heisler","stuart.heisler@anacapa.com","","","","","","Anacapa. 7 emails.","Remote","Vendor; Engineering"),

    # HASKELL
    ("Patrick","Ettorre","patrick.ettorre@haskell.com","","","","","","Haskell - engineering and construction firm. 9 emails.","Remote","Vendor; Engineering; Construction"),

    # DHL
    ("James","Advincula","james.advincula@dhl.com","","","","","","DHL - freight. 8 emails.","Remote","Vendor; Logistics; Freight"),

    # REXEL
    ("Jarrod","Levine","jarrod.levine@rexelusa.com","","","","","","Rexel - electrical distributor. 5 emails.","San Jose, CA","Vendor; Electrical; Distributor"),

    # RAPID AXIS (additional)
    ("Jared","","jared@rapidaxis.com","","","","","","Rapid Axis. 8 emails. Marc also at Rapid Axis already in sheet.","Remote","Vendor; CNC; Prototyping"),

    # FLEXIBLE LIFELINE SYSTEMS
    ("Kevin","Courtney","kevin.courtney@flexiblelifeline.com","","","","","","Flexible Lifeline Systems - fall protection and safety equipment. 6 emails.","Remote","Vendor; Safety; Fall Protection"),

    # FAB.AI
    ("Michael","","michael@fabai.com","","","","","","Fab.AI - manufacturing AI software. 15 emails.","Remote","Vendor; AI/Tools; Software; Manufacturing"),

    # SELWAY TOOL (additional contacts)
    ("","Pharis","kpharis@selwaytool.com","","","","","","Selway Tool. 6 emails. Matt Selway already in sheet.","Los Angeles, CA","Vendor; CNC; Equipment"),

    # BREAKTHROUGH ENERGY
    ("Peter","","peter@breakthroughenergy.org","","","","","","Breakthrough Energy - Bill Gates cleantech investor. Antora backer.","Remote","Investor; Clean Energy; Stakeholder"),
    ("Ben","Ruben","ben.ruben@breakthroughenergy.org","","","","","","Breakthrough Energy. 1 email.","Remote","Investor; Clean Energy; Stakeholder"),

    # SEQUOIA CAPITAL
    ("Jackie","Brown","jackie.brown@sequoia.com","","","","","","Sequoia Capital - Antora investor contact. 2 emails.","Menlo Park, CA","Investor; VC; Stakeholder"),
    ("Ashley","McKenzie","ashley.mckenzie@sequoia.com","","","","","","Sequoia Capital. 2 emails.","Menlo Park, CA","Investor; VC; Stakeholder"),

    # HEX
    ("Nicole","","nicole@hex.tech","","","","","","Hex - dashboard and analytics platform. Additional contact.","San Francisco, CA","Vendor; Software; Analytics; Dashboards"),
    ("Alex","","alex@hex.tech","","","","","","Hex. 2 emails.","San Francisco, CA","Vendor; Software; Analytics"),

    # LNJ BHILWARA
    ("Mayank","Saxena","mayank.saxena@lnjbhilwara.com","","","","","","LNJ Bhilwara Group - Indian carbon fiber and materials company. 8 emails.","India","Vendor; Materials; Carbon; Supplier"),

    # PLASTEC VENTILATION (additional)
    ("Eduardo","","eduardo@plastecventilation.com","","","","","","Plastec Ventilation. 3 emails. contact@ already in sheet.","Remote","Vendor; HVAC; Ventilation"),

    # SAFETY NET
    ("David","","davidb@safetynetinc.com","","","","","","Safety Net Inc - safety equipment vendor. 6 emails.","Remote","Vendor; Safety"),

    # PAPE MATERIAL HANDLING (additional)
    ("","Bray","rbray@papemh.com","","","","","","Pape Material Handling. 4 emails. sgoud and tnolan already in sheet.","San Jose, CA","Vendor; Material Handling; Equipment"),

    # MOODY STRUCTURAL ENGINEERS
    ("Joshua","","joshua@moodyse.com","","","","","","Moody Structural Engineers. 11 emails.","Remote","Vendor; Engineering; Structural"),
]


def main():
    creds = Credentials.from_service_account_file(KEY_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(SHEET_ID).sheet1

    rows = ws.get_all_values()
    existing = {r[2].lower() for r in rows[1:] if len(r) > 2}

    to_add = [list(r) for r in NEW_VENDORS if r[2].lower() not in existing]
    skipped = len(NEW_VENDORS) - len(to_add)

    if to_add:
        ws.append_rows(to_add, value_input_option="USER_ENTERED")
    print(f"Added {len(to_add)} vendors. Skipped {skipped} duplicates.")
    print(f"Sheet total: {len(rows) - 1 + len(to_add)} contacts.")


if __name__ == "__main__":
    main()
