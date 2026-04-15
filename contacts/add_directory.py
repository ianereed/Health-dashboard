#!/usr/bin/env python3
"""
add_directory.py
Merges Antora internal directory into the contacts sheet.
- Updates existing records (phone, location, pronouns, etc.)
- Adds new contacts not already in sheet
- Adds columns: Pronouns, Contact Method, Work Location
"""

import gspread
from google.oauth2.service_account import Credentials

KEY_FILE = r"C:\Users\Ian Reed\Documents\Claude SQL\reference\production-plan-access-4e92a6c9086d.json"
SHEET_ID  = "1z-8VGhT2Hh_KdWfHc2UX0Bkjyaukyinlpx0sJ5WelAA"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

# Parsed + cleaned directory data
# (first, last, pronouns, contact_method, email, phone, work_location, home_city, notes_extra)
DIRECTORY = [
    ("Aaron",       "Sanchez",              "he/him",   "Slack, Text",                  "aaron.sanchez@antora.energy",          "669-288-9801",  "Onsite (Zanker)",   "Milpitas, CA",         ""),
    ("Adam",        "Frankel",              "he/him",   "Urgent: Text/call; Typical: Slack/Email", "adam.frankel@antora.energy", "202-365-8087", "Remote",           "",                     ""),
    ("Alan",        "Wirkkala",             "he/him",   "Text, Email",                  "alan.wirkkala@antora.energy",           "408-910-1232",  "Onsite (Zanker)",   "Tracy, CA",            ""),
    ("Alec",        "Burns",                "he/him",   "Slack, email, call, text",     "alec.burns@antora.energy",              "909-262-6688",  "Onsite (Fresno)",   "Fresno, CA",           ""),
    ("Alice",       "Tsai",                 "she/her",  "Slack, email",                 "alice.tsai@antora.energy",              "607-592-2907",  "Hybrid (Zanker)",   "Berkeley, CA",         ""),
    ("Alyssa",      "Higdon",               "she/her",  "Slack",                        "alyssa.higdon@antora.energy",           "650-544-1626",  "Onsite (Zanker)",   "San Carlos, CA",       ""),
    ("Amit",        "Kumar Gupta",          "he/him",   "Best: Slack/Text/Whatsapp",    "amit.gupta@antora.energy",              "765-404-5141",  "Onsite (Reamwood)", "Fremont, CA",          ""),
    ("Amit",        "Saini",                "he/him",   "Slack, text, email, call",     "amit.saini@antora.energy",              "860-960-3346",  "Onsite (Zanker)",   "San Jose, CA",         "Left Antora March 2026"),
    ("Anders",      "Laederich",            "he/him",   "Phone/Slack/Email",            "anders.laederich@antora.energy",        "408-387-4215",  "Onsite (Zanker)",   "",                     ""),
    ("Andrew",      "Ponec",                "he/him",   "",                             "andrew@antora.energy",                  "503-602-2371",  "Onsite (Reamwood)", "Linden, CA",           "CEO & Co-founder"),
    ("Annie",       "Otfinoski",            "she/her",  "Slack, email, call",           "annie.otfinoski@antora.energy",         "860-510-1413",  "Hybrid (Zanker)",   "",                     ""),
    ("Antonio",     "Carrillo",             "he/him",   "Slack, text, email, call",     "antonio.carrillo@antora.energy",        "650-609-7684",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Becky",       "Romero",               "she/her",  "Slack, email, text, call",     "becky.romero@antora.energy",            "650-889-0366",  "Onsite (Zanker)",   "",                     ""),
    ("Ben",         "Samways",              "he/him",   "Slack, email, text, call",     "ben.samways@antora.energy",             "267-401-4958",  "Remote",            "Philadelphia, PA",     ""),
    ("Ben",         "Johnson",              "he/him",   "",                             "ben@antora.energy",                     "404-997-9250",  "Onsite (Reamwood)", "",                     ""),
    ("Ben",         "Wilson",               "he/him",   "Urgent: Text/Call; casual: Slack", "benjamin.wilson@antora.energy",    "650-919-4401",  "Onsite (Zanker)",   "",                     ""),
    ("Bharadwaja",  "Ryali",                "he/him",   "If urgent: text/call/Whatsapp; Otherwise: Slack/email", "bharadwaja@antora.energy", "408-334-1917", "Onsite (Zanker)", "San Francisco, CA", ""),
    ("Bijan",       "Shiravi",              "he/him",   "Slack, email; urgent: text, call", "bijan.shiravi@antora.energy",       "949-525-7707",  "Onsite (Zanker)",   "",                     ""),
    ("Brandon",     "Johnson",              "he/him",   "Text",                         "brandon.johnson@antora.energy",         "408-775-2793",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Brendan",     "Kayes",                "he/him",   "text/call/WhatsApp/Signal",    "brendan@antora.com",                    "626-755-1413",  "Onsite (Reamwood)", "Los Gatos, CA",        ""),
    ("Burhan",      "Qazi",                 "he/him",   "Slack or face to face, email; urgent: text, call", "burhan.qazi@antora.energy", "615-957-3455", "Onsite (Zanker)", "San Jose, CA",  ""),
    ("Cece",        "Luciano",              "she/her",  "Slack; urgent: text, call",    "cece@antora.energy",                    "908-328-4599",  "Onsite (Reamwood)", "",                     ""),
    ("Chris",       "Briere",               "he/him",   "Best: Slack, Email",           "chris.briere@antora.energy",            "860-377-3969",  "Remote",            "",                     ""),
    ("Clark",       "Liu",                  "he/him",   "Slack, text, email",           "clark.liu@antora.energy",               "612-940-9608",  "Onsite (Zanker)",   "Half Moon Bay, CA",    ""),
    ("Conrad",      "Brandt",               "he/him",   "Best: Slack, Email, Text/Call","conrad.brandt@antora.energy",           "415-302-7510",  "Hybrid (Zanker)",   "",                     ""),
    ("Dan",         "Freeman",              "he/him",   "Text, Find me on the shop floor", "dan.freeman@antora.energy",          "805-914-3498",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Dan",         "Tran",                 "he/him",   "Best: Call/Text, email",       "dan.tran@antora.energy",                "650-793-7461",  "Onsite (Zanker)",   "",                     ""),
    ("David",       "Bishop",               "he/him",   "Urgent: call; Otherwise: Slack, email, call", "david.bishop@antora.energy", "717-517-6717", "Onsite (Zanker)", "Mountain View, CA",  ""),
    ("Dave",        "Haines",               "he/him",   "Best: Slack, Email, Text/Call","david.haines@antora.energy",            "510-780-6055",  "Onsite (Zanker)",   "San Ramon, CA",        ""),
    ("David",       "Bierman",              "he/him",   "",                             "david@antora.energy",                   "818-624-4127",  "Onsite (Reamwood)", "",                     "Co-founder"),
    ("David",       "Crudo",                "he/him",   "",                             "david.crudo@antora.energy",             "408-594-0756",  "Onsite (Zanker)",   "",                     ""),
    ("Davis",       "Hoffman",              "he/him",   "Slack, call",                  "davis.hoffman@antora.energy",           "706-691-9218",  "Onsite (Zanker)",   "",                     ""),
    ("Deandre",     "Sheard",               "he/him",   "Text",                         "deandre.sheard@antora.energy",          "510-766-9191",  "Onsite (Zanker)",   "Newark, CA",           ""),
    ("Devon",       "Story",                "he/him",   "Urgent: Call or Text; Otherwise: Slack or email", "devon.story@antora.energy", "650-468-3942", "Onsite (Zanker)", "Santa Clara, CA",  ""),
    ("Donald",      "Haines",               "he/him",   "Best: Slack, Email, Text/Call","donald.haines@antora.energy",           "559-960-5620",  "Onsite (Fresno)",   "Tracy, CA",            ""),
    ("Doug",        "Soga",                 "he/him",   "Text",                         "douglas.soga@antora.energy",            "650-892-2459",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Dustin",      "Nizamian",             "he/him",   "Urgent: Call or Text; Otherwise: Slack or email", "dustin@antora.energy", "650-666-7522", "Onsite (Zanker)", "",                     ""),
    ("Edward",      "Montejano",            "he/him",   "Slack or Cell",                "edward.montejano@antora.energy",        "669-206-9443",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Elijah",      "Cruz",                 "he/him",   "Text, Call",                   "elijah.cruz@antora.energy",             "907-390-3995",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Emily",       "Wang",                 "she/her",  "Urgent: Call or Text; Otherwise: Slack or email", "emily.wang@antora.energy", "510-789-5519", "Hybrid (Zanker)", "San Francisco, CA", "Note: also emily.k.wang@antora.energy"),
    ("Emmett",      "Perl",                 "he/him",   "",                             "emmett@antora.energy",                  "303-875-5328",  "Onsite (Reamwood)", "",                     ""),
    ("Ethan",       "Ananny",               "he/him",   "Urgent: Call/text; Non-urgent: Slack", "ethan.ananny@antora.energy",   "617-418-9243",  "Onsite (Zanker)",   "",                     "Left Antora March 2026"),
    ("Gabby",       "Landess",              "she/her",  "Slack, email; urgent: Call, text", "gabrielle.landess@antora.energy",   "408-832-0872",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Galilea",     "von Ruden",            "she/her",  "Slack, email; urgent: Call, slack", "galilea.vonruden@antora.energy",   "650-924-6041",  "Onsite (Zanker)",   "Berkeley / Palo Alto, CA", ""),
    ("Garun",       "Arustamov",            "he/him",   "Call, text",                   "garun.arustamov@antora.energy",         "408-821-0891",  "Onsite (Zanker)",   "Los Gatos, CA",        ""),
    ("Gene",        "Gonzales",             "he/him",   "Slack, email, call",           "gene.gonzales@antora.energy",           "559-351-1645",  "Hybrid (Zanker)",   "",                     ""),
    ("Geordie",     "Zapalac",              "he/him",   "Slack, email, text, call",     "geordie.zapalac@antora.energy",         "831-706-7575",  "Onsite (Reamwood)", "",                     ""),
    ("George",      "Campau",               "he/him",   "Slack, Email",                 "george.campau@antora.energy",           "517-812-0095",  "Remote",            "S. San Francisco, CA", ""),
    ("Gui",         "Divanach",             "he/him",   "Slack, Email, text, call",     "gui.divanach@antora.energy",            "916-837-6023",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Haley",       "Gilbert",              "she/her",  "Gchat or Slack DM",            "haley@antora.energy",                   "919-414-0521",  "Remote",            "Sunnyvale, CA",        ""),
    ("Hamsini",     "Gopalakrishna",        "she/her",  "In person > Slack > Call > Email", "hamsini.gopalakrishna@antora.energy", "408-677-0962", "Onsite (Reamwood)", "San Jose, CA",       ""),
    ("Hayden",      "Hall",                 "he/him",   "slack, in person, text, call", "hayden.hall@antora.energy",             "714-812-3001",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Helen",       "Hsu",                  "she/her",  "Slack, email; text, call if urgent", "helen.hsu@antora.energy",          "424-354-6731",  "Onsite (Zanker)",   "Milpitas, CA",         ""),
    ("Huck",        "Dorn",                 "he/him",   "Slack, text, call, email",     "huck.dorn@antora.energy",               "617-270-6414",  "Onsite (Zanker)",   "",                     ""),
    ("Ian",         "Spearing",             "he/him",   "Slack, Email; urgent: Text",   "ian.spearing@antora.com",               "614-381-8884",  "Onsite (Reamwood)", "",                     ""),
    ("Indigo",      "Ramey-Wright",         "she/her",  "Slack, text if urgent",        "indigo.ramey-wright@antora.energy",     "831-325-8452",  "Onsite (Zanker)",   "Santa Cruz, CA",       ""),
    ("Jack",        "Boes",                 "he/him",   "Slack, email, text, call",     "jack.boes@antora.com",                  "406-231-9002",  "Onsite (Zanker)",   "Sunnyvale, CA",        ""),
    ("Jacob",       "Ng",                   "he/him",   "Slack, Email, Text/call",      "jacob.ng@antora.energy",                "414-477-1257",  "Onsite (Reamwood)", "Sunnyvale, CA",        ""),
    ("Jamal",       "Lorta",                "he/him",   "Slack, Email; urgent: Text",   "jamal.lorta@antora.energy",             "559-593-8025",  "Onsite (Fresno)",   "Lemoore, CA",          ""),
    ("Jasmine",     "Chugh",                "she/her",  "Typical: Slack/Email; Urgent: Text/Call", "jasmine.chugh@antora.energy", "415-310-6830", "Onsite (Zanker)", "San Jose, CA",          ""),
    ("Jason",       "Evans",                "he/him",   "slack, email",                 "jason.evans@antora.energy",             "206-303-0198",  "Remote",            "Seattle, WA",          ""),
    ("Jason",       "Tolentino",            "he/him",   "Best: Slack; Next: Email, Text","jason.tolentino@antora.energy",         "808-391-4095",  "Onsite (Reamwood)", "",                     ""),
    ("Jefre",       "Barrera",              "",         "slack, text, email, call",     "jefre.barrera@antora.energy",           "831-406-0276",  "Onsite (Zanker)",   "Brisbane, CA",         ""),
    ("Jerome",      "Pereira",              "he/him",   "slack, text, email, call",     "jerome.pereira@antora.energy",          "408-398-0136",  "Onsite (Zanker)",   "Cupertino, CA",        ""),
    ("Jessica",     "Hills",                "she/her",  "slack, email",                 "jessica.hills@antora.energy",           "415-378-2006",  "Onsite (Zanker)",   "",                     ""),
    ("John",        "Ash",                  "he/him",   "Cell",                         "john.ash@antora.energy",                "831-207-8251",  "Onsite (Zanker)",   "Castro Valley, CA",    ""),
    ("John",        "Kelly",                "he/him",   "Text/Call/Slack",              "john.kelly@antora.energy",              "510-816-1357",  "Onsite (Zanker)",   "Alameda, CA",          ""),
    ("John",        "Perna",                "he/him",   "Call",                         "john.perna@antora.energy",              "408-206-8678",  "Onsite (Reamwood)", "",                     ""),
    ("John",        "LaPorga",              "he/him",   "Text",                         "john.laporga@antora.energy",            "805-345-9132",  "Onsite (Zanker)",   "",                     ""),
    ("Jonatan",     "Ram",                  "he/him",   "Text/Call/Slack",              "jonatan.ram@antora.energy",             "619-634-6396",  "Remote",            "",                     ""),
    ("Jordan",      "Leventhal",            "he/him",   "Slack",                        "jordan.leventhal@antora.energy",        "215-589-9338",  "Hybrid (Zanker)",   "San Francisco, CA",    ""),
    ("Jordan",      "Kearns",               "he/him",   "Slack, Email",                 "jordan.kearns@antora.energy",           "859-948-2670",  "Remote",            "",                     ""),
    ("Jorge",       "Pascual",              "he/him",   "Call/Text/Email/Slack",        "jorge.pascual@antora.energy",           "209-470-0990",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Justin",      "Briggs",               "he/him",   "text/call",                    "justin@antora.energy",                  "720-937-6310",  "Onsite (Reamwood)", "Oakland, CA",          "Co-founder & COO"),
    ("Kai",         "Caindec",              "he/him",   "Slack, text, email, call",     "kai.caindec@antora.energy",             "415-686-3928",  "Hybrid (Zanker)",   "San Francisco, CA",    ""),
    ("Kara",        "Herson",               "she/her",  "Slack / text / call",          "kara.herson@antora.energy",             "650-644-7723",  "Onsite (Zanker)",   "",                     ""),
    ("Kat",         "Haynes",               "she/her",  "slack, email, call",           "kathleen.haynes@antora.energy",         "408-209-9417",  "Hybrid (Reamwood)", "",                     ""),
    ("Kate",        "Work",                 "she/her",  "Slack, text, call, email",     "katelyn.work@antora.energy",            "419-304-6497",  "Onsite (Zanker)",   "Portland, ME",         ""),
    ("Kevin",       "Chan",                 "he/him",   "Urgent: text/call; Otherwise: Slack/email", "kevin.chan@antora.energy", "650-815-6095", "Hybrid (Zanker)", "Oakland, CA",             ""),
    ("Keyur",       "Shah",                 "he/him",   "Slack / text / call",          "keyur.shah@antora.energy",              "269-276-6652",  "Onsite (Reamwood)", "Sunnyvale, CA",        ""),
    ("Larry",       "Madrid",               "he/him",   "text, call",                   "larry.madrid@antora.energy",            "408-334-4114",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Laura",       "Renfroe",              "she/her",  "Slack, email; call/text if urgent", "laura.renfroe@antora.energy",       "425-829-8488",  "Hybrid (Zanker)",   "San Diego, CA",        ""),
    ("Leah",        "Kirkland",             "she/her",  "Best: email; Next: Slack/text","leah.kirkland@antora.energy",           "478-461-2002",  "Remote",            "Mountain View, CA",    ""),
    ("Leah",        "Kuritzky",             "she/her",  "slack, email, text, call",     "leah@antora.energy",                    "484-264-5435",  "Hybrid (Reamwood)", "Albany, CA",           ""),
    ("LeAutry",     "Bruner",               "he/him",   "Cell, text",                   "leautry.bruner@antora.energy",          "415-825-2913",  "Onsite (Zanker)",   "Pittsburg, CA",        ""),
    ("Luigi",       "Celano",               "he/him",   "Slack, email; call/text if urgent", "luigi.celano@antora.energy",        "650-224-3998",  "Onsite (Reamwood)", "",                     ""),
    ("Luke",        "Humphrey",             "he/him",   "Slack, email, call",           "luke.humphrey@antora.energy",           "406-781-3993",  "Remote",            "",                     ""),
    ("Manny",       "Guth",                 "he/him",   "Slack, text, email, call",     "manfred.guth@antora.energy",            "408-438-2986",  "Onsite (Reamwood)", "San Jose, CA",         ""),
    ("Mark",        "Brueggemann",          "he/him",   "Slack, text, email, call",     "mark.brueggemann@antora.energy",        "859-512-6672",  "",                  "Los Angeles, CA",      ""),
    ("Matt",        "Reyes",                "he/him",   "Slack, text, call, email",     "matthew.reyes@antora.energy",           "510-424-9210",  "Onsite (Zanker)",   "San Mateo, CA",        ""),
    ("Maya",        "Lusk",                 "she/her",  "Slack, email, text",           "maya.lusk@antora.energy",               "213-709-4628",  "Hybrid (Zanker)",   "San Francisco, CA",    ""),
    ("Mohammad",    "Al-Attiyeh",           "he/him",   "Txt, Slack, Email",            "mohammad.al-attiyeh@antora.energy",     "530-739-9390",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Monty",       "Perry",                "he/him",   "Slack, text, call, email",     "montgomery.perry@antora.energy",        "408-603-0803",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Moritz",      "Limpinsel",            "he/him",   "urgent: text/call; if not: email, slack", "moritz@antora.energy",       "949-606-5966",  "Onsite (Reamwood)", "Santa Clara, CA",      ""),
    ("Mugdha",      "Thakur",               "she/her",  "Urgent: Text/Call; Otherwise: in person, Slack, Text, email", "mugdha.thakur@antora.energy", "315-396-7782", "Onsite (Zanker)", "Fremont, CA", ""),
    ("Nehali",      "Jain",                 "she/her",  "Urgent: Call; Slack, email, text", "nehali.jain@antora.energy",          "215-607-1388",  "Onsite (Reamwood)", "",                     ""),
    ("Nick",        "Azpiroz",              "he/him",   "Slack or call",                "nick.azpiroz@antora.energy",            "972-762-9381",  "Onsite (Zanker)",   "San Francisco, CA",    ""),
    ("Nico",        "Robert",               "he/him",   "Slack, cal",                   "nicolas.robert@antora.energy",          "203-273-6452",  "Onsite (Reamwood)", "Los Gatos, CA",        ""),
    ("Nigel",       "Myers",                "he/him",   "Slack, call, email",           "nigel.myers@antora.energy",             "650-898-9760",  "Onsite (Zanker)",   "Mountain View, CA",    ""),
    ("Noah",        "Long",                 "he/him",   "Slack, email, text or call if urgent", "noah.long@antora.energy",       "860-515-6885",  "Remote",            "Santa Fe, NM",         ""),
    ("Oliver",      "Paje",                 "he/him",   "slack, email",                 "oliver.paje@antora.energy",             "408-816-0864",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Paula",       "Loures",               "she/her",  "Slack, email, text, call",     "paula.loures@antora.energy",            "775-357-5778",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Piyush",      "Kapate",               "he/him",   "Slack, text, email, call",     "piyush.kapate@antora.energy",           "906-231-4366",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Raghavendra", "Pai",                  "he/him",   "Slack, email; text/call if urgent", "raghavendra.pai@antora.energy",     "405-837-3382",  "Hybrid (Zanker)",   "",                     ""),
    ("Ranjeet",     "Mankikar",             "he/him",   "Slack, text, email, call",     "ranjeet.mankikar@antora.energy",        "408-667-2463",  "Onsite (Zanker)",   "San Diego, CA",        ""),
    ("RJ",          "Fenton",               "he/him",   "Slack, text, email, call",     "rj.fenton@antora.energy",               "231-714-7261",  "Onsite (Zanker)",   "San Diego, CA",        ""),
    ("Romil",       "Chitalia",             "he/him",   "Slack, Call if urgent",        "romil.chitalia@antora.energy",          "925-336-5732",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Ronnie",      "Cuadro",               "he/him",   "Slack, email, text/call if urgent", "ron.cuadro@antora.energy",          "773-266-3900",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Ruben",       "Rodriguez",            "he/him",   "Slack or email",               "ruben.rodriguez@antora.energy",         "530-458-1717",  "Onsite (Reamwood)", "San Jose, CA",         ""),
    ("Ry",          "Storey-Fisher",        "he/him",   "Slack, email; call/text if urgent", "ry@antora.energy",                  "415-730-6511",  "Hybrid (Zanker)",   "",                     ""),
    ("Sam",         "Kortz",                "he/him",   "",                             "sam@antora.energy",                     "408-425-6031",  "Onsite (Zanker)",   "",                     ""),
    ("Samuel",      "Chen",                 "he/him",   "Slack, text/call if urgent",   "samuel.chen@antora.energy",             "702-881-6559",  "Onsite (Reamwood)", "Menlo Park, CA",       "Also: sache@stanford.edu"),
    ("Sarah",       "Ahmari",               "she/her",  "Slack, text, email, call",     "sarah.ahmari@antora.energy",            "408-568-6163",  "Hybrid (Zanker)",   "",                     ""),
    ("Scott",       "Kato",                 "he/him",   "Slack, text, email, call",     "scott.kato@antora.energy",              "310-344-6559",  "Remote",            "San Jose, CA",         ""),
    ("Scott",       "Merrick",              "he/him",   "Slack, text, email, call",     "scott.merrick@antora.energy",           "530-613-5511",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Sean",        "Gray",                 "he/him",   "Slack/Email/Text/Call",        "sean.gray@antora.energy",               "619-322-1560",  "Remote",            "Houston, TX",          ""),
    ("Seb",         "Lounis",               "he/him",   "Slack unless urgent, then text/call", "seb@antora.energy",               "510-507-1498",  "Hybrid (Reamwood)", "Hayward, CA",          "Also: sebastien.lounis@antora.energy"),
    ("Serena",      "Pallib",               "",         "Slack, email",                 "serena.pallib@antora.energy",           "",              "Onsite (Zanker)",   "",                     ""),
    ("Sherri",      "Bhola",                "she/her",  "Slack/Email/Text/Call",        "sherri.bhola@antora.energy",            "669-268-9440",  "Onsite (Reamwood)", "San Jose, CA",         ""),
    ("Tanner",      "DeVoe",                "he/him",   "Slack unless urgent, then text/call", "tanner.devoe@antora.energy",       "503-729-1553",  "Onsite (Zanker)",   "Cupertino, CA",        ""),
    ("Tarun",       "Narayan",              "he/him",   "Slack unless urgent; Text/call if needed; vacation: WhatsApp", "tarun@antora.energy", "408-608-4983", "Onsite (Zanker)", "San Jose, CA", ""),
    ("Tom",         "Bence",                "he/him",   "Working hours: Slack/Email; Urgent/Off hours: Call/Text", "tom.bence@antora.energy", "248-497-2883", "Hybrid (Zanker)", "Auburn, CA", ""),
    ("Tom",         "Butler",               "he/him",   "Slack, text, email, call",     "tom.butler@antora.energy",              "724-309-5437",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Turner",      "Cotterman",            "he/him",   "Slack, email; call/text if urgent", "turner.cotterman@antora.energy",     "864-351-9010",  "Remote",            "Denver, CO",           ""),
    ("Victoria",    "Mapar",                "she/her",  "Slack, email; call/text if urgent", "victoria.mapar@antora.energy",       "408-464-0211",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Vijay",       "Subramanian",          "he/him",   "Urgent: Text/Call; Otherwise: in person, Slack, email", "vijay.subramanian@antora.energy", "919-607-6977", "Onsite (Zanker)", "",    ""),
    ("Vince",       "Calianno",             "he/him",   "In person, Slack, Text, email, call", "vincent.calianno@antora.energy",   "480-824-8144",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Vishal",      "Patel",                "he/him",   "Slack, text, call, email",     "vishal.patel@antora.energy",            "408-859-7111",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Vlad",        "Voronchikhin",         "he/him",   "Slack, text, email, call",     "vlad.voronchikhin@antora.energy",       "346-932-5537",  "Remote",            "Houston, TX",          ""),
    ("Will",        "Clark",                "he/him",   "Slack, text, call, physical tap", "william.clark@antora.com",            "408-707-0258",  "Onsite (Zanker)",   "San Jose, CA",         ""),
    ("Marc",        "Ramirez",              "he/him",   "Normal: Slack; Urgent: Text",  "marc.ramirez@antora.energy",            "510-407-6223",  "Onsite (Zanker)",   "Redwood City, CA",     ""),
    ("Tyler",       "Bonini",               "he/him",   "Slack; Urgent: Text/Call",     "tyler.bonini@antora.energy",            "860-256-9516",  "Onsite (Zanker)",   "San Francisco, CA",    ""),
]


def normalize_email(e):
    return e.strip().lower()


def main():
    creds = Credentials.from_service_account_file(KEY_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(SHEET_ID).sheet1

    rows = ws.get_all_values()
    headers = rows[0]

    # Add new columns if needed
    new_cols = ["Pronouns", "Contact Method", "Work Location"]
    for col in new_cols:
        if col not in headers:
            ws.update_cell(1, len(headers) + 1, col)
            headers.append(col)

    rows = ws.get_all_values()
    headers = rows[0]

    email_col    = headers.index("Professional Email")
    first_col    = headers.index("First Name")
    last_col     = headers.index("Last Name")
    phone_col    = headers.index("Phone")
    location_col = headers.index("Location / City")
    notes_col    = headers.index("Notes")
    company_col  = headers.index("Current Company")
    pronouns_col = headers.index("Pronouns")
    contact_col  = headers.index("Contact Method")
    workloc_col  = headers.index("Work Location")

    # Build index of existing emails -> row number
    existing = {}
    for i, row in enumerate(rows[1:], start=2):
        e = normalize_email(row[email_col]) if len(row) > email_col else ""
        if e:
            existing[e] = i

    updates = []
    new_rows = []

    def col(idx):
        return chr(ord("A") + idx)

    for entry in DIRECTORY:
        first, last, pronouns, contact, email, phone, workloc, home_city, note_extra = entry
        email_norm = normalize_email(email)

        if email_norm in existing:
            # Update existing row
            r = existing[email_norm]
            row = rows[r - 1]

            def cur(idx):
                return row[idx].strip() if len(row) > idx else ""

            # Phone: update if better (more digits or currently empty)
            if phone and (not cur(phone_col) or len(phone.replace("-","").replace("(","").replace(")","").replace(" ","")) > len(cur(phone_col).replace("-","").replace("(","").replace(")","").replace(" ",""))):
                updates.append({"range": f"{col(phone_col)}{r}", "values": [[phone]]})
            # Location: update if currently empty
            if home_city and not cur(location_col):
                updates.append({"range": f"{col(location_col)}{r}", "values": [[home_city]]})
            elif home_city and home_city not in cur(location_col):
                updates.append({"range": f"{col(location_col)}{r}", "values": [[home_city]]})
            # Pronouns
            if pronouns and not cur(pronouns_col):
                updates.append({"range": f"{col(pronouns_col)}{r}", "values": [[pronouns]]})
            # Contact method
            if contact and not cur(contact_col):
                updates.append({"range": f"{col(contact_col)}{r}", "values": [[contact]]})
            # Work location
            if workloc and not cur(workloc_col):
                updates.append({"range": f"{col(workloc_col)}{r}", "values": [[workloc]]})
            # Notes extra
            if note_extra and note_extra not in cur(notes_col):
                merged_note = (cur(notes_col) + " | " + note_extra).strip(" | ")
                updates.append({"range": f"{col(notes_col)}{r}", "values": [[merged_note]]})
        else:
            # New contact — build full row
            new_row = [""] * len(headers)
            new_row[first_col]    = first
            new_row[last_col]     = last
            new_row[email_col]    = email
            new_row[phone_col]    = phone
            new_row[location_col] = home_city
            new_row[company_col]  = "Antora Energy"
            new_row[pronouns_col] = pronouns
            new_row[contact_col]  = contact
            new_row[workloc_col]  = workloc
            if note_extra:
                new_row[notes_col] = note_extra
            new_rows.append(new_row)

    # Write updates
    if updates:
        for i in range(0, len(updates), 100):
            ws.batch_update(updates[i:i+100])

    # Append new rows
    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")

    total = len(rows) - 1 + len(new_rows)
    print(f"Updated {len(updates)} fields on existing contacts.")
    print(f"Added {len(new_rows)} new contacts.")
    print(f"Sheet total: {total} contacts.")


if __name__ == "__main__":
    main()
