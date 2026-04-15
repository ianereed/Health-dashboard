#!/usr/bin/env python3
"""
update_contacts_columns.py — add Last Contacted, Notes, Location, Tags columns
and pre-fill with known data from Slack/session context.
"""

import gspread
from google.oauth2.service_account import Credentials

KEY_FILE = r"C:\Users\Ian Reed\Documents\Claude SQL\reference\production-plan-access-4e92a6c9086d.json"
SHEET_ID = "1z-8VGhT2Hh_KdWfHc2UX0Bkjyaukyinlpx0sJ5WelAA"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# email -> (last_contacted, notes, location, tags)
ENRICHMENT = {
    # ── LEADERSHIP ───────────────────────────────────────────────────────────
    "andrew@antora.energy": (
        "",
        "CEO & co-founder. Brought Ian into Antora at ground level to build manufacturing from scratch. MIT Technology Review Innovators Under 35 (2024). Agreed to Ian's contractor transition.",
        "San Jose, CA",
        "Leadership; Founder; Clean Energy"
    ),
    "stephen.sharratt@antora.energy": (
        "",
        "CTO. Originally hired Ian into Antora. Stanford-educated. Strong operator — led POET commissioning strategy and R&D direction. Passionate about reliability and compliance.",
        "San Jose, CA",
        "Leadership; Engineering; Clean Energy"
    ),
    "justin@antora.energy": (
        "2026-04-06",
        "Co-founder & COO. Close relationship — Ian consulted him on Colorado trip planning. Backcountry skier. In #skiing channel from day 1.",
        "San Jose, CA",
        "Leadership; Founder; Skiing"
    ),
    "david@antora.energy": (
        "",
        "Co-founder. David Bierman. Works on the technical/product side. Part of the original founding team with Andrew and Justin.",
        "San Jose, CA",
        "Leadership; Founder; Engineering"
    ),
    "emmett@antora.energy": (
        "",
        "Emmett Perl. Active in #ai-fun — thoughtful voice on AI security and governance. Pushed back on Claude Cowork adoption appropriately.",
        "San Jose, CA",
        "Leadership; AI/Tools"
    ),
    "julian.bishop@antora.energy": (
        "2026-04-14",
        "Strategy & Growth. DM'd Ian asking for Jessica Hills' cell. Oxford-educated; investment banking background. Friendly.",
        "San Jose, CA",
        "Leadership; Strategy; Growth"
    ),
    "david.bishop@antora.energy": (
        "",
        "Strategy & Growth. Ex-diplomat, MBA from Berkeley Haas. Thoughtful presence in #ai-fun discussions about AI reliability.",
        "San Jose, CA",
        "Leadership; Strategy; Growth"
    ),
    "leah@antora.energy": (
        "",
        "Head of Heat-to-Power Operations. Manages the POET Big Stone site operations team.",
        "Big Stone, MN",
        "Leadership; Field Ops; POET"
    ),

    # ── MANAGEMENT CHAIN ────────────────────────────────────────────────────
    "jerome.pereira@antora.energy": (
        "2026-04-15",
        "Ian's direct manager. 'Exceptional boss and mentor' per Ian's goodbye. Calm under pressure, great coach. Strong operational focus. Ian explicitly asked Antora vendors to redirect business to Jerome.",
        "San Jose, CA",
        "Management; Manufacturing Ops; Mentor"
    ),
    "ranjeet.mankikar@antora.energy": (
        "2026-04-13",
        "Supply chain lead who reports to Jerome. Ian called him 'an exceptional leader' for teaching how manufacturing systems interact with the real world. Managed Dan Park's departure gracefully.",
        "San Jose, CA",
        "Management; Supply Chain; Leadership"
    ),
    "david.haines@antora.energy": (
        "2026-04-15",
        "Director of Manufacturing Ops. Close working partner — 'building a manufacturing system alongside you has been one of the highlights of my time here' (Ian's goodbye). Very hands-on, fires daily messages about process plan issues.",
        "San Jose, CA",
        "Management; Manufacturing Ops; Leadership"
    ),
    "matthew.reyes@antora.energy": (
        "2026-04-15",
        "Production Planning & Fulfillment Manager. Works closely with Ian on supply forecast, production data, and module schedules. Part of the ops leads group.",
        "San Jose, CA",
        "Management; Production Planning; Supply Chain"
    ),
    "indigo.ramey-wright@antora.energy": (
        "2026-04-15",
        "OPM (Operations Program Manager). Jerome's direct report. Manages production readiness meetings, board deck slides, and cross-team coordination. Avoids Hwy 17 in bad weather — likely South Bay commuter.",
        "San Jose, CA",
        "Management; Production Ops; Program Management"
    ),

    # ── NPI TEAM ────────────────────────────────────────────────────────────
    "benjamin.wilson@antora.energy": (
        "2026-04-15",
        "Sr. NPI Engineer — Ian's direct report for 2+ years. Celebrated 2-year anniversary Apr 3. Deep expertise in GRI table, CNC gantry mill, carbon block handling. Very interested in AI/Claude for ECO review automation. Great attitude and sense of humor.",
        "San Jose, CA",
        "NPI; Engineering; AI/Tools"
    ),
    "montgomery.perry@antora.energy": (
        "2026-03-10",
        "Sr. NPI Engineer — Ian's direct report. 'Monty.' Expert on GRI, block staging, factory swap-over planning. Currently on parental leave (new baby). Ian texted him on last day.",
        "San Jose, CA",
        "NPI; Engineering"
    ),
    "mohammad.al-attiyeh@antora.energy": (
        "2026-04-15",
        "'Mo' — NPI Engineer, Ian's direct report. Electrical wiring and marshalling cabinet specialist. Process plan expert. Ian texted him on last day. Currently out sick.",
        "San Jose, CA",
        "NPI; Engineering; Electrical"
    ),
    "dan.freeman@antora.energy": (
        "2026-04-15",
        "NPI Manufacturing — Ian's direct report. Drove min-max rollout, GD&T improvements, GRI table proof testing. Built Slack notification tool independently. Ran lunch-and-learns for production team. One of Ian's most productive team members.",
        "San Jose, CA",
        "NPI; Manufacturing; Engineering; AI/Tools"
    ),
    "vishal.patel@antora.energy": (
        "2026-04-15",
        "Manufacturing — Ian's direct report. Led 10T crane installation, lineside material flow, subassembly moves to Zanker 2. Solid executer. Has young kids — frequently WFH for sick childcare.",
        "San Jose, CA",
        "NPI; Manufacturing; Facilities"
    ),
    "rj.fenton@antora.energy": (
        "2026-04-14",
        "NPI — Ian's direct report. Rigging and lifting expert, built Notion project tracker for the team. Active skier and snowboarder. Energetic and fast-moving.",
        "San Mateo, CA",
        "NPI; Engineering; Rigging; Skiing"
    ),

    # ── MODULE DESIGN / ENGINEERING ─────────────────────────────────────────
    "katelyn.work@antora.energy": (
        "2026-04-14",
        "TPM for Product Dev/Module Design. Organized leads lunch. Co-wrote product dev hiring philosophy with Ian and Anny. Runs subassembly meeting cadence. Thoughtful leader — frequently WFH due to illness/travel.",
        "San Jose, CA",
        "Module Design; TPM; Leadership; Leads Lunch"
    ),
    "tanner.devoe@antora.energy": (
        "2026-04-13",
        "Module engineering lead. Owned Gen1v6 system changes, heater arcing issues, POET commissioning support. Part of leads lunch group. Skier (skiing channel). Congratulated Ian on job change.",
        "San Jose, CA",
        "Module Design; Engineering; Skiing; Leads Lunch"
    ),
    "huck.dorn@antora.energy": (
        "2026-04-10",
        "Module design — HX and primary cooling. Part of leads lunch group. Has a daughter in soccer. WFH frequently. Thoughtful — raised valid concerns about AI reliability in #ai-fun.",
        "San Jose, CA",
        "Module Design; Engineering; Leads Lunch"
    ),
    "kevin.chan@antora.energy": (
        "2026-04-02",
        "Staff Mech Design Eng — blocks, insulation, throttle, shipping. Part of leads lunch group. Three kids, frequently managing childcare. Stanford-educated. Was NPI manager transition POC.",
        "Oakland, CA",
        "Module Design; Engineering; Leads Lunch"
    ),
    "hayden.hall@antora.energy": (
        "2026-04-06",
        "Sr. Mech Design Eng. Asked Ian to build the storage block mass dashboard — that became a major project. Interested in Claude Code. Also worked on module shipping/load constraints.",
        "San Jose, CA",
        "Module Design; Engineering; Dashboards"
    ),
    "jack.boes@antora.energy": (
        "2026-04-14",
        "Sr. Mech Eng. GE Aviation background (afterburner, turbine). Ohio State ME grad. Currently visiting Metalli supplier in China. Active in #ai-fun.",
        "San Jose, CA",
        "Module Design; Engineering"
    ),
    "nigel.myers@antora.energy": (
        "2026-04-07",
        "Sr. Mech Design Eng — electrode specialist. Works on heater components. Kate Work wanted to include him in engineering space planning. Part of leads lunch adjacent group.",
        "San Jose, CA",
        "Module Design; Engineering; Heater"
    ),
    "gabrielle.landess@antora.energy": (
        "2026-04-14",
        "Mech Design Eng. 'Gabby.' Owns the Antora ski/hiking trip cabin in Truckee. Organized 2026 skiing/hiking trip planning. Also works on GRI and HT insulation.",
        "San Jose, CA",
        "Module Design; Engineering; Skiing"
    ),
    "galilea.vonruden@antora.energy": (
        "2026-04-09",
        "Mech Design Eng II. Owns HX primary cooling and secondary cooling engineering. Took ownership from Anny Ning on departure. Tesla background.",
        "San Jose, CA",
        "Module Design; Engineering; HX"
    ),
    "luigi.celano@antora.energy": (
        "2026-04-08",
        "Staff Mech Eng. Quality/GRI specialist. Active in #ai-fun with thoughtful AI security commentary. Also in #antora-product-dev. Wrote GRI damage inspection SOP.",
        "San Jose, CA",
        "Module Design; Engineering; Quality"
    ),
    "ethan.ananny@antora.energy": (
        "2026-03-06",
        "Mech Eng. 'Glorified Plumber.' HX/JIC fittings/Resbond expert. Left Antora Mar 6 to start a new venture. Close relationship with Ian's team — attended early Antora builds.",
        "San Jose, CA",
        "Module Design; Engineering; HX; Alumni"
    ),
    "bharadwaja@antora.energy": (
        "2026-04-08",
        "Heater RE. ETH Zurich background. Leads heater v7 development. Assigned to ARI >80% of time in early 2026. Active in #ai-fun and tech discussions.",
        "San Jose, CA",
        "Module Design; Engineering; Heater; R&D"
    ),
    "anny.ning@antora.energy": (
        "2026-04-15",
        "Ian's partner. Manager of Mech Eng. Last day also 4/15. Owned HX, primary/secondary cooling engineering. Exceptional leader — built team from early Antora days. Personal email: annyning@gmail.com.",
        "San Jose, CA",
        "Module Design; Engineering; Leadership; Partner"
    ),
    "anders.laederich@antora.energy": (
        "2026-04-14",
        "Engineer. In leads lunch and skiing-adjacent group. Interested in Cursor/AI coding tools. Liked Ian's supply forecast dashboard.",
        "San Jose, CA",
        "Engineering; AI/Tools"
    ),
    "jasmine.chugh@antora.energy": (
        "2026-03-05",
        "Sr. Process Eng, Plant Engineering. Works on Paratherm HTF analysis and Pratt plant design. Part of #antora-product-dev. Active technical contributor.",
        "San Jose, CA",
        "Plant Engineering; Process Engineering"
    ),
    "davis.hoffman@antora.energy": (
        "",
        "Systems Eng — gas systems (N2, HTF). Works on module-level gas system design. Contributed to Gasmet analysis for R&D testing.",
        "San Jose, CA",
        "Engineering; Gas Systems; R&D"
    ),
    "devon.story@antora.energy": (
        "2026-04-08",
        "Sr. Mgr Plant Design Eng. Cornell/PE background. Owns BOP design, e-boiler, Pratt plant design. Promoted to Sr. Manager Sep 2025. Reports to Stephen Sharratt.",
        "Santa Clara, CA",
        "Plant Engineering; BOP; Leadership"
    ),
    "samantha.hudgens@antora.energy": (
        "2026-03-26",
        "'Sammy.' TPM. Joined #product_dev_leads_sync. Owns 8D process and issue tracking. Based in Chicago area (Central timezone).",
        "Chicago, IL",
        "Program Management; Quality; TPM"
    ),
    "jordan.leventhal@antora.energy": (
        "",
        "Project execution / finance. Works on transformer supply chain and project cost tracking. POET project team.",
        "San Jose, CA",
        "Project Execution; Finance"
    ),
    "tom.bence@antora.energy": (
        "2026-04-06",
        "Sr. Mgr Project Execution. PE + PMP credentials. Leads POET commissioning and project delivery. Based in Auburn, CA — near Tahoe. Active on product dev leads channel.",
        "Auburn, CA",
        "Project Execution; POET; Leadership"
    ),
    "alec.burns@antora.energy": (
        "",
        "Commissioning Manager. Moved to Big Stone site. Leads POET commissioning team after Brandon Lackey departure. Reports to Tom Bence.",
        "Big Stone, MN",
        "Commissioning; POET; Field Ops"
    ),
    "donald.haines@antora.energy": (
        "",
        "'Don Haines' — site operations at POET Big Stone. 'Lost in Big Stone' is his Slack title. Manages day-to-day module ops, O&M scheduling. Different person from Dave Haines.",
        "Big Stone, MN",
        "Field Ops; POET; Operations"
    ),
    "bijan.shiravi@antora.energy": (
        "2026-04-08",
        "Lead TPM. 5 years at Tesla (motor technology). Owns POET field work instructions, PTC testing roadmap, UL certification. Runs product dev all-hands (with pizza). Vacationing during Ian's last week.",
        "San Jose, CA",
        "Program Management; POET; Leadership"
    ),
    "scott.fife@antora.com": (
        "",
        "EHS&S Manager. Manages gas monitor safety, PPE compliance, safety protocols for R&D and production floor.",
        "San Jose, CA",
        "EHS; Safety; Compliance"
    ),

    # ── R&D / TEST ──────────────────────────────────────────────────────────
    "dustin@antora.energy": (
        "2026-04-08",
        "Director R&D Testing. ETH Zurich background. Owns R&D test infrastructure, POET commissioning support, hotter HTF testing. Led the interim commissioning effort. Very technically sharp.",
        "San Francisco, CA",
        "R&D; Testing; Leadership; POET"
    ),
    "tarun@antora.energy": (
        "2026-04-14",
        "Mgr Technology Development. Stanford-educated. Leads POET performance data analysis. Built operations metrics dashboard. 10 years since his last dentist visit (lol). Ian relied on his data frequently.",
        "Santa Clara, CA",
        "R&D; Data; Analytics; POET"
    ),
    "nick.azpiroz@antora.energy": (
        "2026-04-14",
        "R&D Test Automation Mgr. Stanford background. Built GrafTech DAQ system. Organized Gen1v5 EVT build as co-build owner. Helped Kate Work with schedule/test pad planning.",
        "San Francisco, CA",
        "R&D; Test Automation; Engineering"
    ),
    "connor.grady@antora.energy": (
        "2026-03-25",
        "R&D Test Eng. In #skiing channel — active skier. Organized MBB bracket league in #rnd_test_n_friends. Works with test pad infrastructure.",
        "San Jose, CA",
        "R&D; Testing; Skiing"
    ),
    "adam.ring@antora.energy": (
        "",
        "R&D Lead Test Operator. Manages gas monitor tracking (Despicable Tracker). Works on BOP and module test infrastructure at Zanker.",
        "San Jose, CA",
        "R&D; Testing; Operations"
    ),
    "rachel.lindley@antora.energy": (
        "2026-04-08",
        "R&D Test Operator. Works on Mod 5 test campaigns with Takeo Torrey. Built GrafTech DAQ #2.",
        "San Jose, CA",
        "R&D; Testing"
    ),
    "garun.arustamov@antora.energy": (
        "2026-04-07",
        "'Electrodes & Stuff.' Works on heater electrode development and R&D test support. Helped with cable tray system for power delivery roof removal.",
        "San Jose, CA",
        "R&D; Electrodes; Heater"
    ),
    "carson.townsend@antora.energy": (
        "2026-03-13",
        "Controls & Automation Eng. Built the 'Rainier Database' — a one-stop shop for aggregated module test cycle reports. Very useful tool Ian referenced. Active in #rnd_test_n_friends.",
        "San Jose, CA",
        "Controls; Software; R&D; Tools"
    ),
    "david.crudo@antora.energy": (
        "2026-03-11",
        "R&D team. Helped move Fresno HTF, manages R&D secondary storage. In #rnd_test_n_friends for equipment coordination.",
        "San Jose, CA",
        "R&D; Operations"
    ),
    "ian.spearing@antora.energy": (
        "2026-03-30",
        "In #ai-fun — active and thoughtful participant. Made the Guinness AI pricing joke. Works in strategy/international based on context.",
        "San Jose, CA",
        "Strategy; AI/Tools"
    ),
    "sean.gray@antora.energy": (
        "2026-04-08",
        "Controls & Software Eng Mgr. Manages throttle controls and module software. Raised concern about AI tools posting to Slack in production contexts. Alerted team to Amit Saini departure.",
        "San Jose, CA",
        "Controls; Software; Leadership"
    ),

    # ── PRODUCT / PM ────────────────────────────────────────────────────────
    "nicolas.robert@antora.energy": (
        "2026-04-08",
        "'Nico.' Product Manager. Ian helped onboard him to Claude Code and the Antora Analytics repo. Manages Gen1v6 product requirements in Notion. In #ai-fun — early adopter.",
        "San Jose, CA",
        "Product; Program Management; AI/Tools"
    ),
    "raghavendra.pai@antora.energy": (
        "2026-04-02",
        "'Raghavendra.' Product Manager. Works on Australia pipeline CRM and international business development. Active in #ai-fun — uses Claude for market analysis.",
        "San Jose, CA",
        "Product; Strategy; BD; AI/Tools"
    ),
    "sam.kortz@antora.com": (
        "2026-04-06",
        "Compliance and issue tracking. Managed UL field evaluation, GrafTech DAQ coordination, and POET spares tracking. Left primary compliance role when Andrew K departed.",
        "San Jose, CA",
        "Compliance; Program Management; POET"
    ),

    # ── SUPPLY CHAIN ────────────────────────────────────────────────────────
    "william.clark@antora.energy": (
        "2026-04-15",
        "Supplier Development. 'Will.' Handles vendor quality, NC RTV dispositions (Southco, etc.). Was part of Ian's NC dispo notifier project. In #npi-directs.",
        "San Jose, CA",
        "Supply Chain; Supplier Development; Quality"
    ),
    "tom.butler@antora.energy": (
        "2026-04-14",
        "Strategic Supply Chain — HX, Skid, Weather Cladding. Currently in China (Metalli supplier visit). Active in #ai-fun — uses ChatGPT for tariff/supply chain analysis. Great backpacker — discussed porter-free trips with Ian.",
        "San Jose, CA",
        "Supply Chain; Strategic Sourcing"
    ),
    "paula.loures@antora.energy": (
        "2026-04-06",
        "Strategic Supply Chain Mgr. Coordinates CNC machine installation (Selway Tool). Manages Haas-certified commissioning. Active in #manufacturing_engineering.",
        "San Jose, CA",
        "Supply Chain; Strategic Sourcing"
    ),
    "charles.su@antora.energy": (
        "2026-04-03",
        "Material Planning/Inventory. Ian ran supply forecast scenarios past Charles to validate output. Works closely with Dan Freeman and Ranjeet on inventory and MRP.",
        "San Jose, CA",
        "Supply Chain; Inventory; Planning"
    ),
    "jorge.pascual@antora.energy": (
        "2026-04-15",
        "Production Planning Analyst. Very active in #manufacturing_engineering — daily process plan updates, part number corrections, inventory discrepancies. Works alongside Mo and Phil Rutherford.",
        "San Jose, CA",
        "Supply Chain; Production Planning; Inventory"
    ),
    "miles.pereira@antora.energy": (
        "2026-04-06",
        "Buyer/Planner. Led pack density data collection for lineside tote sizing. Works under Daniel Park and Ranjeet on procurement.",
        "San Jose, CA",
        "Supply Chain; Procurement; Planning"
    ),

    # ── LOGISTICS / INVENTORY / WAREHOUSE ───────────────────────────────────
    "daniel.park@antora.energy": (
        "2026-04-02",
        "Director of Logistics & Inventory. Ian created #warehouse-projects channel specifically for Dan's projects. Led min-max rollout, lineside material flow design, receiving issue tracking. Departed Antora Dec 2025.",
        "San Jose, CA",
        "Logistics; Inventory; Leadership; Alumni"
    ),
    "kimbo.lorenzo@antora.energy": (
        "2026-04-06",
        "Inventory. Built the hot board kanban system and replenishment form/dashboard. Proactive and creative problem solver on the floor.",
        "San Jose, CA",
        "Inventory; Logistics; Operations"
    ),
    "akos.vesztergombi@antora.energy": (
        "2026-04-08",
        "Facilities/Warehouse. Managed Zanker 2 racking, asphalt repairs, fire sprinkler upgrades, roof repair. Also in #ops-leads. Key facilities point person.",
        "San Jose, CA",
        "Facilities; Warehouse; Operations"
    ),
    "nathaniel.chaffin-reed@antora.energy": (
        "2026-04-06",
        "'Nate.' Inventory tech. Interested in using AI for carbon block image classification. Ian pointed him to Gagan for guidance.",
        "San Jose, CA",
        "Inventory; Operations"
    ),

    # ── QUALITY / PRODUCTION FLOOR ──────────────────────────────────────────
    "oliver.paje@antora.energy": (
        "2026-04-15",
        "Inbound Quality Tech. Works on NC dispositions — RTV with vendors. Ian built the NC dispo Slack notifier partly to help Oliver's workflow.",
        "San Jose, CA",
        "Quality; Incoming Inspection"
    ),
    "gui.divanach@antora.energy": (
        "2026-04-08",
        "Quality/Supplier. Ian built the NC dispo notifier partly for Gui's team. Uses ChatGPT for dimensional inspection report templates. Currently vacationing. Ian worked with him on NC approval pings.",
        "San Jose, CA",
        "Quality; Supplier Quality; AI/Tools"
    ),
    "phillip.rutherford@antora.energy": (
        "2026-04-15",
        "'Phil.' Process plan updater — extremely active in #manufacturing_engineering, handles daily WO and PP corrections alongside Jorge Pascual. Reliable executer.",
        "San Jose, CA",
        "Production; Process Engineering; NPI Support"
    ),
    "aaron.sanchez@antora.energy": (
        "",
        "'AA_ron.' Production Supervisor. Celebrated Mod 100 milestone. Works on module assembly floor alongside LeAutry Bruner.",
        "San Jose, CA",
        "Production; Supervision"
    ),
    "leautry.bruner@antora.energy": (
        "",
        "Production Supervisor. Works alongside Aaron Sanchez on assembly floor. Responsible for block installation and crane operations.",
        "San Jose, CA",
        "Production; Supervision"
    ),
    "douglas.soga@antora.energy": (
        "",
        "'Doug.' Production Supervisor. Joined #manufacturing_engineering Mar 2026.",
        "San Jose, CA",
        "Production; Supervision"
    ),
    "edward.montejano@antora.energy": (
        "2026-02-12",
        "Production Lead. Works on toeboard installation and cladding wall assembly. Provides direct feedback on work instruction gaps.",
        "San Jose, CA",
        "Production; Manufacturing"
    ),
    "larry.madrid@antora.energy": (
        "2026-01-29",
        "Lead Production Tech. Raises process plan issues on the floor — proactive communicator in #manufacturing_engineering.",
        "San Jose, CA",
        "Production; Manufacturing"
    ),

    # ── PEOPLE / FACILITIES ──────────────────────────────────────────────────
    "becky.romero@antora.energy": (
        "2026-04-15",
        "People Partner. Handled Ian's transition from FT to contractor — set hourly rate, handled COBRA, badge return logistics. Very communicative and accommodating.",
        "San Jose, CA",
        "HR; People Ops; Transition"
    ),
    "kathleen.haynes@antora.energy": (
        "2026-04-13",
        "'Kat.' Sr. HR Manager. Ran Ian's final 1:1s and transition support. Worked with Ian on John Kelly interview panel.",
        "San Jose, CA",
        "HR; People Ops"
    ),
    "sebastien.lounis@antora.energy": (
        "2026-04-14",
        "'Seb.' Head of People & Culture. Co-founder of Cyclotron Road / Activate. Warm goodbye to Ian and Anny — 'stay in touch.' Active in #skiing.",
        "San Jose, CA",
        "HR; People Ops; Culture; Leadership; Skiing"
    ),
    "sherri.bhola@antora.energy": (
        "2026-04-14",
        "'Sherri Mills.' Executive Assistant. Helped Ian with scheduling and office logistics. Ian helped her think through an AI scheduling assistant project.",
        "San Jose, CA",
        "Admin; Executive Support"
    ),
    "john.perna@antora.energy": (
        "2026-04-07",
        "Director of Facilities & Equipment. Manages cranes, Dado facility, CNC machine installations, electrical power connections. Ian worked with him frequently on equipment projects.",
        "San Jose, CA",
        "Facilities; Equipment; Operations"
    ),

    # ── IT / ADMIN ──────────────────────────────────────────────────────────
    "gagan.malik@antora.energy": (
        "2026-04-13",
        "IT. Manages Claude/ChatGPT enterprise rollout and AI usage limits. Ian's go-to for bumping token limits. Posts weekly AI tips to #ai-fun. Very knowledgeable about AI tools.",
        "San Jose, CA",
        "IT; AI/Tools; Admin"
    ),
    "ben@antora.energy": (
        "2026-04-06",
        "'Ben Johnson.' IT/GitHub admin. Set up Ian's access to antora-energy GitHub org. Thoughtful about Claude Cowork security — provided good IT guardrails.",
        "San Jose, CA",
        "IT; GitHub; Security"
    ),
    "haley@antora.energy": (
        "2026-04-02",
        "'Haley Gilbert.' Head of Business Ops. Workspace admin. Partners with Gagan on AI tool vetting. Energetic and organized.",
        "Denver, CO",
        "Business Ops; Admin; AI/Tools"
    ),
    "annie.otfinoski@antora.energy": (
        "2026-04-01",
        "Business ops. Very active in #ai-fun — built Australia pipeline CRM using Claude projects. Enthusiastic AI adopter. Discovered a Notion page was accidentally trashed by AI.",
        "San Jose, CA",
        "Business Ops; AI/Tools; BD"
    ),

    # ── FINANCE / OTHER ─────────────────────────────────────────────────────
    "ben.bierman@antora.energy": (
        "2026-04-03",
        "Finance/operations. Ian asked Ben for consulting rate guidance when transitioning to contractor. Gave thoughtful, detailed advice. Long-tenured Antora employee.",
        "San Jose, CA",
        "Finance; Operations"
    ),
    "liz.theurer@antora.energy": (
        "2026-04-09",
        "NetSuite and IT systems. Ian's main contact for NetSuite TBA connector setup. Based in Eastern timezone. Has deep NS admin access. Ian worked with her on cloud hosting for automation.",
        "Remote (East Coast)",
        "IT; NetSuite; Systems; ERP"
    ),
    "julian.bishop@antora.energy": (
        "2026-04-14",
        "Strategy & Growth. LinkedIn: investment banking and renewable energy background.",
        "San Jose, CA",
        "Strategy; Growth; BD"
    ),

    # ── EXTERNAL — VENDORS ──────────────────────────────────────────────────
    "yaron@withmagenta.com": (
        "",
        "Co-founder of WithMagenta (MFO/Manufacturo partner). Yaron Alfi. Key contact for the Manufacturo system that powers Antora's production database.",
        "San Francisco, CA",
        "Vendor; Manufacturo; Software"
    ),
    "davide@withmagenta.com": (
        "",
        "WithMagenta team. Davide Semenzin. Involved in Manufacturo product development.",
        "San Francisco, CA",
        "Vendor; Manufacturo; Software"
    ),
    "mattselway@selwaytool.com": (
        "2026-02-11",
        "Matt Selway. Selway Machine Tool. Ian's contact for CNC machine commissioning (Haas gantry mill installation at Dado). Coordinated delivery and certification.",
        "Los Angeles, CA",
        "Vendor; CNC; Equipment"
    ),
    "zach@3laws.io": (
        "",
        "Zachary — 3Laws Robotics. Contacted Ian about robotics/automation safety solutions. In Ian's email thread.",
        "San Francisco, CA",
        "Vendor; Robotics; Safety"
    ),
    "kelly.darnell@cleanpower.org": (
        "",
        "Kelly Veney Darnell. COO, American Clean Power Association. Policy/regulatory contact in clean energy space.",
        "Washington, DC",
        "Clean Energy; Policy; External"
    ),
    "pwidziszewski@manufacturo.com": (
        "2026-04-08",
        "Manufacturo software team. Ian's direct contact for Manufacturo helpdesk tickets and platform issues.",
        "Remote (Poland)",
        "Vendor; Manufacturo; Software"
    ),
    "don.johnson@combilift.com": (
        "2026-04-14",
        "Combilift rep. Ian's contact for combi lift service records and capacity discussions. RJ asked Ian to forward email thread.",
        "Remote",
        "Vendor; Equipment; Forklift"
    ),
}

def main():
    creds = Credentials.from_service_account_file(KEY_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(SHEET_ID).sheet1

    rows = ws.get_all_values()
    headers = rows[0]
    email_col = headers.index("Professional Email")

    # Add new headers if not already present
    new_headers = ["Last Contacted", "Notes", "Location / City", "Tags"]
    col_offset = len(headers)
    existing = set(headers)
    headers_to_add = [h for h in new_headers if h not in existing]

    if headers_to_add:
        for i, h in enumerate(headers_to_add):
            col_letter = chr(ord("A") + col_offset + i)
            ws.update_cell(1, col_offset + i + 1, h)
            ws.format(f"{col_letter}1", {"textFormat": {"bold": True}})
        print(f"Added headers: {headers_to_add}")
        # Refresh
        rows = ws.get_all_values()
        headers = rows[0]

    lc_col  = headers.index("Last Contacted") + 1
    notes_col = headers.index("Notes") + 1
    loc_col = headers.index("Location / City") + 1
    tags_col = headers.index("Tags") + 1

    updates = []
    matched = 0
    for i, row in enumerate(rows[1:], start=2):
        email = row[email_col].lower()
        if email in ENRICHMENT:
            lc, notes, loc, tags = ENRICHMENT[email]
            updates.append({"range": f"{chr(ord('A') + lc_col - 1)}{i}", "values": [[lc]]})
            updates.append({"range": f"{chr(ord('A') + notes_col - 1)}{i}", "values": [[notes]]})
            updates.append({"range": f"{chr(ord('A') + loc_col - 1)}{i}", "values": [[loc]]})
            updates.append({"range": f"{chr(ord('A') + tags_col - 1)}{i}", "values": [[tags]]})
            matched += 1

    if updates:
        # Batch in chunks of 100
        for i in range(0, len(updates), 100):
            ws.batch_update(updates[i:i+100])
    print(f"Enriched {matched} contacts with notes, location, and tags.")

if __name__ == "__main__":
    main()
