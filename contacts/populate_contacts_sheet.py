#!/usr/bin/env python3
"""
populate_contacts_sheet.py — write professional contacts to Google Sheet.
Sheet: https://docs.google.com/spreadsheets/d/1z-8VGhT2Hh_KdWfHc2UX0Bkjyaukyinlpx0sJ5WelAA
"""

import gspread
from google.oauth2.service_account import Credentials

KEY_FILE = r"C:\Users\Ian Reed\Documents\Claude SQL\reference\production-plan-access-4e92a6c9086d.json"
SHEET_ID = "1z-8VGhT2Hh_KdWfHc2UX0Bkjyaukyinlpx0sJ5WelAA"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# fmt: First, Last, Prof Email, Personal Email, Job Title, Phone, LinkedIn
# Personal email / LinkedIn left blank where unknown — fill in manually or via search
CONTACTS = [
    # ── LEADERSHIP ──────────────────────────────────────────────────────────
    ("Andrew",      "Ponec",           "andrew@antora.energy",                 "", "",                                                    "503-602-2371", ""),
    ("Stephen",     "Sharratt",        "stephen.sharratt@antora.energy",       "", "",                                                    "510-295-3923", ""),
    ("Justin",      "Briggs",          "justin@antora.energy",                 "", "",                                                    "", ""),
    ("Emmett",      "Perl",            "emmett@antora.energy",                 "", "",                                                    "", ""),
    ("Julian",      "Bishop",          "julian.bishop@antora.energy",          "", "Strategy & Growth",                                   "+1 978-944-6207", ""),
    ("David",       "Bishop",          "david.bishop@antora.energy",           "", "Strategy & Growth",                                   "", ""),
    ("David",       "Bierman",         "david@antora.energy",                  "", "",                                                    "", ""),
    ("Leah",        "Kuritzky",        "leah@antora.energy",                   "", "Head of Heat-to-Power Operations",                    "", ""),

    # ── MANAGEMENT CHAIN ────────────────────────────────────────────────────
    ("Jerome",      "Pereira",         "jerome.pereira@antora.energy",         "", "",                                                    "408-398-0136", ""),
    ("Ranjeet",     "Mankikar",        "ranjeet.mankikar@antora.energy",       "", "",                                                    "408-667-2463", ""),
    ("Dave",        "Haines",          "david.haines@antora.energy",           "", "Director of Manufacturing Operations",                "510-780-6055", ""),
    ("Matt",        "Reyes",           "matthew.reyes@antora.energy",          "", "Production Planning & Fulfillment Manager",           "510-424-9210", ""),
    ("Indigo",      "Ramey-Wright",    "indigo.ramey-wright@antora.energy",    "", "OPM",                                                 "831-325-8452", ""),

    # ── NPI TEAM ────────────────────────────────────────────────────────────
    ("Ben",         "Wilson",          "benjamin.wilson@antora.energy",        "", "Sr. NPI Engineer",                                    "", ""),
    ("Montgomery",  "Perry",           "montgomery.perry@antora.energy",       "", "Sr. NPI Engineer",                                    "408-603-0803", ""),
    ("Mohammad",    "Al-Attiyeh",      "mohammad.al-attiyeh@antora.energy",    "", "NPI Engineer",                                        "530-739-9390", ""),
    ("Dan",         "Freeman",         "dan.freeman@antora.energy",            "", "NPI Manufacturing",                                   "805-914-3498", ""),
    ("Vishal",      "Patel",           "vishal.patel@antora.energy",           "", "Manufacturing",                                       "408-859-7111", ""),
    ("RJ",          "Fenton",          "rj.fenton@antora.energy",              "", "NPI",                                                 "231-714-7261", ""),

    # ── MODULE DESIGN / ENGINEERING ─────────────────────────────────────────
    ("Kate",        "Work",            "katelyn.work@antora.energy",           "", "TPM - Product Development / Module Design",           "419-304-6497", ""),
    ("Tanner",      "DeVoe",           "tanner.devoe@antora.energy",           "", "",                                                    "503-729-1553", ""),
    ("Huck",        "Dorn",            "huck.dorn@antora.energy",              "", "",                                                    "617-270-6414", ""),
    ("Kevin",       "Chan",            "kevin.chan@antora.energy",              "", "Staff Mechanical Design Engineer",                    "650-815-6095", ""),
    ("Hayden",      "Hall",            "hayden.hall@antora.energy",            "", "Sr. Mechanical Design Engineer",                      "714-812-3001", ""),
    ("Jack",        "Boes",            "jack.boes@antora.energy",              "", "Senior Mechanical Engineer",                          "406-231-9002", ""),
    ("Nigel",       "Myers",           "nigel.myers@antora.energy",            "", "Sr. Mechanical Design Engineer",                      "650-898-9760", ""),
    ("Gabby",       "Landess",         "gabrielle.landess@antora.energy",      "", "Mechanical Design Engineer",                          "408-832-0872", ""),
    ("Galilea",     "von Ruden",       "galilea.vonruden@antora.energy",       "", "Mechanical Design Engineer II",                       "650-924-6041", ""),
    ("Jodie",       "Prudhomme",       "jodie.prudhomme@antora.energy",        "", "",                                                    "", ""),
    ("Luigi",       "Celano",          "luigi.celano@antora.energy",           "", "Staff Mechanical Engineer",                           "650-224-3998", ""),
    ("Ethan",       "Ananny",          "ethan.ananny@antora.energy",           "ethan.ananny@gmail.com", "",                             "617-418-9243", ""),
    ("Bharadwaja",  "Ryali",           "bharadwaja@antora.energy",             "", "",                                                    "408-334-1917", ""),
    ("Anny",        "Ning",            "anny.ning@antora.energy",              "annyning@gmail.com", "Manager, Mechanical Engineering",   "", ""),
    ("Anders",      "Laederich",       "anders.laederich@antora.energy",       "", "",                                                    "", ""),
    ("Maggie",      "Graupera",        "maggie.graupera@antora.energy",        "", "",                                                    "", ""),
    ("Jasmine",     "Chugh",           "jasmine.chugh@antora.energy",          "", "Sr. Process Engineer, Plant Engineering",             "", ""),
    ("Davis",       "Hoffman",         "davis.hoffman@antora.energy",          "", "Systems Engineer - Gas Systems",                      "706-691-9218", ""),
    ("Devon",       "Story",           "devon.story@antora.energy",            "", "Plant Design Engineering",                            "650-468-3942", ""),
    ("Sammy",       "Hudgens",         "samantha.hudgens@antora.energy",       "", "TPM",                                                 "630-696-6328", ""),
    ("Jordan",      "Leventhal",       "jordan.leventhal@antora.energy",       "", "",                                                    "", ""),
    ("Tom",         "Bence",           "tom.bence@antora.energy",              "", "Sr. Manager, Project Execution",                      "248-497-2883", ""),
    ("Alec",        "Burns",           "alec.burns@antora.energy",             "", "Commissioning Manager",                               "", ""),
    ("Donald",      "Haines",          "donald.haines@antora.energy",          "", "Site Operations - Big Stone",                         "559-960-5620", ""),
    ("Kai",         "Caindec",         "kai.caindec@antora.energy",            "", "",                                                    "415-686-3928", ""),
    ("John",        "Kosanovich",      "john.kosanovich@antora.energy",        "", "",                                                    "", ""),
    ("Scott",       "Merrick",         "scott.merrick@antora.energy",          "", "",                                                    "530-613-5511", ""),
    ("Saujan",      "Sivaram",         "saujan.sivaram@antora.energy",         "", "Manager, Materials Process Engineering",              "734-546-9121", ""),
    ("Grace",       "Yee",             "grace.yee@antora.energy",              "", "Staff Reliability Engineer",                          "", ""),
    ("Alyssa",      "Higdon",          "alyssa.higdon@antora.energy",          "", "Controls & Software Engineer",                        "510-402-1865", ""),
    ("Bijan",       "Shiravi",         "bijan.shiravi@antora.energy",          "", "",                                                    "949-525-7707", ""),
    ("Scott",       "Fife",            "scott.fife@antora.com",                "", "EHS&S",                                               "", ""),
    ("Oren",        "Lawit",           "oren.lawit@antora.com",                "", "",                                                    "", ""),

    # ── R&D / TEST ──────────────────────────────────────────────────────────
    ("Dustin",      "Nizamian",        "dustin@antora.energy",                 "", "Director, R&D Testing",                               "650-666-7522", ""),
    ("Tarun",       "Narayan",         "tarun@antora.energy",                  "", "Manager, Technology Development",                     "408-608-4983", ""),
    ("Nick",        "Azpiroz",         "nick.azpiroz@antora.energy",           "", "R&D Test Automation Manager",                         "972-762-9381", ""),
    ("Connor",      "Grady",           "connor.grady@antora.energy",           "", "R&D Test Engineer",                                   "206-641-5087", ""),
    ("Adam",        "Ring",            "adam.ring@antora.energy",              "", "R&D Lead Test Operator",                              "", ""),
    ("Takeo",       "Torrey",          "takeo.torrey@antora.energy",           "", "R&D Test Operator",                                   "669-208-8183", ""),
    ("Rachel",      "Lindley",         "rachel.lindley@antora.energy",         "", "",                                                    "", ""),
    ("Garun",       "Arustamov",       "garun.arustamov@antora.energy",        "", "",                                                    "408-821-0891", ""),
    ("Jacob",       "Ng",              "jacob.ng@antora.energy",               "", "Photovoltaic Module Test Technician",                 "+1 414-477-1257", ""),
    ("Carson",      "Townsend",        "carson.townsend@antora.energy",        "", "Controls & Automation Engineer",                      "541-671-3943", ""),
    ("David",       "Crudo",           "david.crudo@antora.energy",            "", "",                                                    "", ""),
    ("Ian",         "Spearing",        "ian.spearing@antora.energy",           "", "",                                                    "", ""),
    ("Stuart",      "Robinson",        "stuart.robinson@antora.energy",        "", "",                                                    "", ""),
    ("Sean",        "Gray",            "sean.gray@antora.energy",              "", "Controls & Software Engineering Manager",             "", ""),
    ("Kai",         "Liu",             "kai.liu@antora.energy",                "", "Controls Engineer",                                   "", ""),

    # ── PRODUCT / PROGRAM MANAGEMENT ────────────────────────────────────────
    ("Nico",        "Robert",          "nicolas.robert@antora.energy",         "", "Product Manager",                                     "", ""),
    ("Raghavendra", "Pai",             "raghavendra.pai@antora.energy",        "", "Product Manager",                                     "", ""),
    ("Sam",         "Kortz",           "sam.kortz@antora.com",                 "", "",                                                    "", ""),

    # ── SUPPLY CHAIN / PROCUREMENT ──────────────────────────────────────────
    ("Will",        "Clark",           "william.clark@antora.energy",          "", "Supplier Development",                                "408-707-0258", ""),
    ("Tom",         "Butler",          "tom.butler@antora.energy",             "", "Strategic Supply Chain Manager",                      "724-309-5437", ""),
    ("Paula",       "Loures",          "paula.loures@antora.energy",           "", "Strategic Supply Chain Manager",                      "", ""),
    ("Charles",     "Su",              "charles.su@antora.energy",             "", "Material Planning / Inventory",                       "214-674-1560", ""),
    ("Jorge",       "Pascual",         "jorge.pascual@antora.energy",          "", "Production Planning Analyst",                         "209-470-0990", ""),
    ("Miles",       "Pereira",         "miles.pereira@antora.energy",          "", "Buyer/Planner",                                       "408-781-6064", ""),
    ("Emily",       "Wang",            "emily.wang@antora.energy",             "", "",                                                    "", ""),
    ("Gene",        "Gonzales",        "gene.gonzales@antora.com",             "", "",                                                    "", ""),
    ("Mugdha",      "Thakur",          "mugdha.thakur@antora.com",             "", "",                                                    "", ""),
    ("Sahika",      "Vatan",           "sahika.vatan@antora.com",              "", "",                                                    "", ""),
    ("Vincent",     "Calianno",        "vincent.calianno@antora.com",          "", "",                                                    "", ""),
    ("Victoria",    "Mapar",           "victoria.mapar@antora.com",            "", "",                                                    "", ""),

    # ── LOGISTICS / INVENTORY / WAREHOUSE ───────────────────────────────────
    ("Daniel",      "Park",            "daniel.park@antora.energy",            "", "Director of Logistics & Inventory",                   "", ""),
    ("Kimbo",       "Lorenzo",         "kimbo.lorenzo@antora.energy",          "", "Inventory",                                           "", ""),
    ("Jose",        "Padilla",         "jose.padilla@antora.energy",           "", "Inventory Swing Shift Lead",                          "", ""),
    ("Serena",      "Pallib",          "serena.pallib@antora.energy",          "", "Warehouse Lead",                                      "", ""),
    ("Ta",          "Pulu",            "tata.pulu@antora.energy",              "", "Supervisor",                                          "408-775-0078", ""),
    ("Nate",        "Chaffin-Reed",    "nathaniel.chaffin-reed@antora.energy", "", "Inventory",                                           "", ""),
    ("Akos",        "Vesztergombi",    "akos.vesztergombi@antora.energy",      "", "",                                                    "408-650-9262", ""),

    # ── QUALITY / PRODUCTION FLOOR ──────────────────────────────────────────
    ("Oliver",      "Paje",            "oliver.paje@antora.energy",            "", "Inbound Quality Technician",                          "", ""),
    ("Gui",         "Divanach",        "gui.divanach@antora.energy",           "", "",                                                    "916-837-6023", ""),
    ("Ronnie",      "Cuadro",          "ron.cuadro@antora.energy",             "", "",                                                    "", ""),
    ("Aaron",       "Sanchez",         "aaron.sanchez@antora.energy",          "", "Production Supervisor",                               "669-288-9801", ""),
    ("LeAutry",     "Bruner",          "leautry.bruner@antora.energy",         "", "Production Supervisor",                               "415-825-2913", ""),
    ("Doug",        "Soga",            "douglas.soga@antora.energy",           "", "Production Supervisor",                               "650-892-2459", ""),
    ("Edward",      "Montejano",       "edward.montejano@antora.energy",       "", "Production Lead",                                     "", ""),
    ("Larry",       "Madrid",          "larry.madrid@antora.energy",           "", "Lead Production Technician",                          "", ""),
    ("Abelardo",    "Olivas",          "abelardo.olivas@antora.energy",        "", "Lead Production Technician",                          "", ""),
    ("Sam",         "Torres",          "samuel.torres@antora.energy",          "", "",                                                    "", ""),
    ("Phil",        "Rutherford",      "phillip.rutherford@antora.energy",     "", "",                                                    "408-916-8456", ""),
    ("Jose",        "Martinez",        "jose.martinez@antora.energy",          "", "",                                                    "408-515-8533", ""),
    ("Alan",        "Wirkkala",        "alan.wirkkala@antora.energy",          "", "",                                                    "", ""),
    ("Robert",      "Paez",            "robert.paez@antora.energy",            "", "Incoming Quality Technician",                         "", ""),
    ("Joan",        "Santillanez",     "joan.santillanez@antora.energy",       "", "Plant Maintenance Technician",                        "209-857-1605", ""),
    ("Jamal",       "Lorta",           "jamal.lorta@antora.energy",            "", "Power Plant Operator",                                "559-593-8025", ""),
    ("Jose",        "Aguilar",         "jose.aguilar.martinez@antora.energy",  "", "",                                                    "", ""),
    ("Kia",         "White",           "kia.white@antora.energy",              "", "",                                                    "", ""),
    ("Stephanie",   "Caacbay",         "stephanie.caacbay@antora.energy",      "", "",                                                    "510-925-5516", ""),
    ("Rechie",      "de Ramos",        "rechie.de.ramos@antora.energy",        "", "",                                                    "", ""),
    ("Jacob",       "Martinez",        "jacob.martinez@antora.energy",         "", "",                                                    "", ""),

    # ── PEOPLE / FACILITIES / EHS ────────────────────────────────────────────
    ("Becky",       "Romero",          "becky.romero@antora.energy",           "", "People Partner",                                      "650-889-0366", ""),
    ("Kat",         "Haynes",          "kathleen.haynes@antora.energy",        "", "Sr. HR/People Manager",                               "408-209-9417", ""),
    ("Seb",         "Lounis",          "sebastien.lounis@antora.energy",       "", "Head of People & Culture",                            "510-507-1498", ""),
    ("Sherri",      "Mills",           "sherri.bhola@antora.energy",           "", "Executive Assistant",                                 "", ""),
    ("John",        "Perna",           "john.perna@antora.energy",             "", "Director of Facilities & Equipment",                  "", ""),

    # ── IT / ADMIN ──────────────────────────────────────────────────────────
    ("Gagan",       "Malik",           "gagan.malik@antora.energy",            "", "",                                                    "", ""),
    ("Ben",         "Johnson",         "ben@antora.energy",                    "", "",                                                    "", ""),
    ("Haley",       "Gilbert",         "haley@antora.energy",                  "", "",                                                    "919-414-0521", ""),
    ("Annie",       "Otfinoski",       "annie.otfinoski@antora.energy",        "", "",                                                    "860-510-1413", ""),

    # ── FINANCE / OTHER ─────────────────────────────────────────────────────
    ("Ben",         "Bierman",         "ben.bierman@antora.energy",            "", "",                                                    "", ""),
    ("Liz",         "Theurer",         "liz.theurer@antora.energy",            "", "",                                                    "352-672-0860", ""),
    ("John",        "Kelly",           "john.kelly@antora.energy",             "", "",                                                    "", ""),
    ("Dan",         "Tran",            "dan.tran@antora.energy",               "", "",                                                    "", ""),
    ("John",        "LaPorga",         "john.laporga@antora.energy",           "", "Sr. R&D Tech",                                        "", ""),

    # ── EXTERNAL — VENDORS / SUPPLIERS ──────────────────────────────────────
    ("Matt",        "Selway",          "mattselway@selwaytool.com",            "", "Selway Tool",                                         "", "https://www.linkedin.com/in/mark-selway-006a9814/"),
    ("",            "Iruvalcaba",      "iruvalcaba@selwaytool.com",            "", "Selway Tool",                                         "", ""),
    ("",            "Hcuevas",         "hcuevas@selwaytool.com",               "", "Selway Tool",                                         "", ""),
    ("Yaron",       "Alfi",            "yaron@withmagenta.com",                "", "WithMagenta",                                         "", "https://www.linkedin.com/in/yaronalfi/"),
    ("Davide",      "Semenzin",        "davide@withmagenta.com",               "", "WithMagenta",                                         "", "https://www.linkedin.com/in/davidesemenzin/"),
    ("Dave",        "",                "dave@withmagenta.com",                 "", "WithMagenta",                                         "", ""),
    ("Don",         "Johnson",         "don.johnson@combilift.com",            "", "Combilift",                                           "", ""),
    ("",            "Goud",            "sgoud@papemh.com",                     "", "Pape Material Handling",                              "", ""),
    ("",            "Nolan",           "tnolan@papemh.com",                    "", "Pape Material Handling",                              "", ""),
    ("William",     "",                "william@american-rigging.com",         "", "American Rigging",                                    "", ""),
    ("Bill Jr",     "",                "billjr@american-rigging.com",          "", "American Rigging",                                    "", ""),
    ("",            "Chiruvella",      "nchiruvella@reliable.co",              "", "Reliable",                                            "", ""),
    ("Ella",        "",                "ella@jzc-carbons.com",                 "", "JZC Carbons",                                         "", ""),
    ("",            "Dye",             "bdye@zaxisinc.com",                    "", "Zaxis Inc",                                           "", ""),
    ("Marc",        "",                "marc@rapidaxis.com",                   "", "Rapid Axis",                                          "", ""),
    ("Zachary",     "",                "zach@3laws.io",                        "", "3Laws Robotics",                                      "", "https://www.linkedin.com/in/zdrake2013/"),
    ("Kelly",       "Darnell",         "kelly.darnell@cleanpower.org",         "", "Clean Power",                                         "", ""),
    ("Mike",        "",                "mike@actnanoglobal.com",               "", "Actna Nano",                                          "", ""),
    ("Dylan",       "G.",              "dylan.g@myjerneesolutions.com",        "", "Jerney Solutions",                                    "", ""),
    ("Betty",       "",                "betty@jtgraphite.com",                 "", "JT Graphite",                                         "", ""),
    ("",            "Widziszewski",    "pwidziszewski@manufacturo.com",        "", "Manufacturo",                                         "", ""),
    ("",            "Mierzwa",         "pmierzwa@manufacturo.com",             "", "Manufacturo",                                         "", ""),
    ("",            "Trafimuk",        "ntrafimuk@manufacturo.com",            "", "Manufacturo",                                         "", ""),
    ("",            "Gombervaux",      "sgombervaux@manufacturo.com",          "", "Manufacturo",                                         "", ""),
    ("",            "Kubala",          "dkubala@manufacturo.com",              "", "Manufacturo",                                         "", ""),
]

HEADERS = ["First Name", "Last Name", "Professional Email", "Personal Email", "Job Title", "Phone", "LinkedIn"]


def main():
    creds = Credentials.from_service_account_file(KEY_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.sheet1

    ws.clear()

    # Write header row
    ws.append_row(HEADERS)

    # Write all contacts in one batch
    rows = [list(c) for c in CONTACTS]
    ws.append_rows(rows, value_input_option="USER_ENTERED")

    # Bold the header
    ws.format("A1:G1", {
        "textFormat": {"bold": True},
        "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
    })

    print(f"Done. {len(rows)} contacts written to sheet.")
    print(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}")


if __name__ == "__main__":
    main()
