"""
agent.py - VaaniOS Business Transaction Voice Agent
===================================================
Provides deterministic Hinglish / Hindi-English intent and amount parsing,
number-to-words natural Hinglish conversion for Timbre TTS, and integration
logic linking gnani_client.py with database.py.
"""

import base64
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import database
import gnani_client

# Devanagari numerals to ASCII digits
DEV_DIGITS = {
    '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
    '५': '5', '६': '6', '७': '7', '८': '8', '९': '9'
}

# Number words (Devanagari, Latin Hinglish transliterations, English) - Comprehensive 1-99
WORD_TO_NUMBER: Dict[str, int] = {
    # 0
    "zero": 0, "shunya": 0, "sifar": 0, "शून्य": 0,

    # 1 - 9
    "one": 1, "ek": 1, "aik": 1, "एक": 1,
    "two": 2, "do": 2, "doo": 2, "दो": 2,
    "three": 3, "teen": 3, "tin": 3, "तीन": 3,
    "four": 4, "chaar": 4, "char": 4, "चार": 4,
    "five": 5, "paanch": 5, "panch": 5, "पांच": 5, "पाँच": 5,
    "six": 6, "chhe": 6, "che": 6, "chhah": 6, "छह": 6, "छः": 6, "छ": 6,
    "seven": 7, "saat": 7, "sat": 7, "सात": 7,
    "eight": 8, "aath": 8, "ath": 8, "आठ": 8,
    "nine": 9, "nau": 9, "no": 9, "नौ": 9,

    # 10 - 19
    "ten": 10, "das": 10, "dus": 10, "दस": 10,
    "eleven": 11, "gyaarah": 11, "gyarah": 11, "ग्यारह": 11,
    "twelve": 12, "baarah": 12, "barah": 12, "बारह": 12,
    "thirteen": 13, "terah": 13, "tera": 13, "तेरह": 13,
    "fourteen": 14, "chaudah": 14, "choudah": 14, "chauda": 14, "chouda": 14, "चौदह": 14,
    "fifteen": 15, "pandrah": 15, "pandra": 15, "पंद्रह": 15, "पन्द्रह": 15,
    "sixteen": 16, "solah": 16, "sola": 16, "सोलह": 16,
    "seventeen": 17, "satrah": 17, "satra": 17, "सत्रह": 17,
    "eighteen": 18, "athaarah": 18, "atharah": 18, "athara": 18, "अठारह": 18,
    "nineteen": 19, "unnees": 19, "unnis": 19, "उन्नीस": 19,

    # 20 - 29
    "twenty": 20, "bees": 20, "bis": 20, "बीस": 20,
    "twentyone": 21, "twenty-one": 21, "ikkees": 21, "ikkis": 21, "इक्कीस": 21,
    "twentytwo": 22, "twenty-two": 22, "baaees": 22, "bais": 22, "baees": 22, "बाइस": 22, "बाईस": 22,
    "twentythree": 23, "twenty-three": 23, "teyees": 23, "teis": 23, "teees": 23, "तेईस": 23, "तेइस": 23,
    "twentyfour": 24, "twenty-four": 24, "chaubees": 24, "chaubis": 24, "चौबीस": 24,
    "twentyfive": 25, "twenty-five": 25, "pachchees": 25, "pachchis": 25, "pachees": 25, "pachis": 25, "पच्चीस": 25, "पचीस": 25,
    "twentysix": 26, "twenty-six": 26, "chhabbees": 26, "chabbis": 26, "छब्बीस": 26,
    "twentyseven": 27, "twenty-seven": 27, "sattaees": 27, "satais": 27, "सत्ताईस": 27, "सत्ताइस": 27,
    "twentyeight": 28, "twenty-eight": 28, "atthaees": 28, "athais": 28, "अट्ठाईस": 28, "अट्ठाइस": 28,
    "twentynine": 29, "twenty-nine": 29, "untees": 29, "untis": 29, "उनतीस": 29, "उन्तीस": 29,

    # 30 - 39
    "thirty": 30, "tees": 30, "tis": 30, "तीस": 30,
    "thirtyone": 31, "thirty-one": 31, "iktees": 31, "iktis": 31, "ikattis": 31, "इकतीस": 31, "इकत्तीस": 31,
    "thirtytwo": 32, "thirty-two": 32, "battees": 32, "battis": 32, "बत्तीस": 32,
    "thirtythree": 33, "thirty-three": 33, "taintees": 33, "tentis": 33, "taintis": 33, "तैंतीस": 33,
    "thirtyfour": 34, "thirty-four": 34, "chauntees": 34, "chautis": 34, "chauntis": 34, "चौंतीस": 34,
    "thirtyfive": 35, "thirty-five": 35, "paintees": 35, "paintis": 35, "पैंतीस": 35,
    "thirtysix": 36, "thirty-six": 36, "chhattees": 36, "chhattis": 36, "छत्तीस": 36,
    "thirtyseven": 37, "thirty-seven": 37, "saintees": 37, "saintis": 37, "सैंतीस": 37,
    "thirtyeight": 38, "thirty-eight": 38, "adhtees": 38, "adtis": 38, "arhtis": 38, "अड़तीस": 38, "अड़तीस": 38,
    "thirtynine": 39, "thirty-nine": 39, "untalees": 39, "untalis": 39, "unchalis": 39, "उनतालीस": 39, "उनचालीस": 39,

    # 40 - 49
    "forty": 40, "chaalees": 40, "chalis": 40, "चालीस": 40,
    "fortyone": 41, "forty-one": 41, "iktaalees": 41, "iktalis": 41, "इकतालीस": 41,
    "fortytwo": 42, "forty-two": 42, "bayaalees": 42, "bayalis": 42, "बयालीस": 42,
    "fortythree": 43, "forty-three": 43, "tentaalees": 43, "taintalis": 43, "तिंतालीस": 43, "तैंतालीस": 43,
    "fortyfour": 44, "forty-four": 44, "chawaalees": 44, "chavalis": 44, "chauwalis": 44, "चवालीस": 44, "चौवालीस": 44,
    "fortyfive": 45, "forty-five": 45, "paintaalees": 45, "paintalis": 45, "पैंतालीस": 45,
    "fortysix": 46, "forty-six": 46, "chhiyaalees": 46, "chhiyalis": 46, "chhayalis": 46, "छियालीस": 46,
    "fortyseven": 47, "forty-seven": 47, "saintaalees": 47, "saintalis": 47, "सैंतालीस": 47,
    "fortyeight": 48, "forty-eight": 48, "adhtaalees": 48, "adtalis": 48, "arhtalis": 48, "अड़तालीस": 48, "अड़तालीस": 48,
    "fortynine": 49, "forty-nine": 49, "unchaas": 49, "unchas": 49, "उनचास": 49,

    # 50 - 59
    "fifty": 50, "pachaas": 50, "pachas": 50, "पचास": 50,
    "fiftyone": 51, "fifty-one": 51, "ikyaawan": 51, "ikyawan": 51, "इक्यावन": 51,
    "fiftytwo": 52, "fifty-two": 52, "baawan": 52, "bawan": 52, "बावन": 52,
    "fiftythree": 53, "fifty-three": 53, "tirpan": 53, "trepan": 53, "तिरपन": 53,
    "fiftyfour": 54, "fifty-four": 54, "chauwan": 54, "chauvan": 54, "चौवन": 54,
    "fiftyfive": 55, "fifty-five": 55, "pachpan": 55, "पचपन": 55,
    "fiftysix": 56, "fifty-six": 56, "chhappan": 56, "छप्पन": 56,
    "fiftyseven": 57, "fifty-seven": 57, "sattaawan": 57, "sattavan": 57, "सत्तावन": 57,
    "fiftyeight": 58, "fifty-eight": 58, "atthaawan": 58, "atthavan": 58, "अट्ठावन": 58,
    "fiftynine": 59, "fifty-nine": 59, "unsath": 59, "unsat": 59, "unsaath": 59, "उनसठ": 59,

    # 60 - 69
    "sixty": 60, "saath": 60, "sath": 60, "साठ": 60,
    "sixtyone": 61, "sixty-one": 61, "iksath": 61, "iksat": 61, "iksaath": 61, "इकसठ": 61,
    "sixtytwo": 62, "sixty-two": 62, "baasath": 62, "basat": 62, "basaath": 62, "बासठ": 62,
    "sixtythree": 63, "sixty-three": 63, "tirsath": 63, "tirsat": 63, "tirsaath": 63, "तिरसठ": 63,
    "sixtyfour": 64, "sixty-four": 64, "chaunsath": 64, "chaunsat": 64, "chaunsaath": 64, "चौंसठ": 64,
    "sixtyfive": 65, "sixty-five": 65, "painsath": 65, "painsat": 65, "painsaath": 65, "पैंसठ": 65,
    "sixtysix": 66, "sixty-six": 66, "chhiyaasath": 66, "chhiyasat": 66, "chhiyaasaath": 66, "छियासठ": 66,
    "sixtyseven": 67, "sixty-seven": 67, "sadsath": 67, "sarsath": 67, "sarsat": 67, "सड़सठ": 67, "सड़सठ": 67, "सरसठ": 67,
    "sixtyeight": 68, "sixty-eight": 68, "adhsath": 68, "arhsath": 68, "arsat": 68, "अड़सठ": 68, "अड़सठ": 68,
    "sixtynine": 69, "sixty-nine": 69, "unhattar": 69, "unhatar": 69, "उनहत्तर": 69,

    # 70 - 79
    "seventy": 70, "sattar": 70, "satar": 70, "सत्तर": 70,
    "seventyone": 71, "seventy-one": 71, "ikhattar": 71, "ikhatar": 71, "ikahattar": 71, "इकहत्तर": 71,
    "seventytwo": 72, "seventy-two": 72, "bahattar": 72, "bahatar": 72, "बहत्तर": 72,
    "seventythree": 73, "seventy-three": 73, "tihattar": 73, "tihatar": 73, "tehattar": 73, "तिहत्तर": 73,
    "seventyfour": 74, "seventy-four": 74, "chauhattar": 74, "chauhatar": 74, "चौहत्तर": 74,
    "seventyfive": 75, "seventy-five": 75, "pachhattar": 75, "pachhatar": 75, "पचहत्तर": 75,
    "seventysix": 76, "seventy-six": 76, "chhiyattar": 76, "chhiyatar": 76, "chhihattar": 76, "chhihatar": 76, "छिहत्तर": 76, "छियत्तर": 76,
    "seventyseven": 77, "seventy-seven": 77, "sathattar": 77, "satattar": 77, "satatar": 77, "सतहत्तर": 77, "सतत्तर": 77,
    "seventyeight": 78, "seventy-eight": 78, "athhattar": 78, "athattar": 78, "athatar": 78, "अठहत्तर": 78, "अठत्तर": 78,
    "seventynine": 79, "seventy-nine": 79, "unasi": 79, "unyaasi": 79, "unaasi": 79, "unyasi": 79, "उन्यासी": 79, "उनासी": 79,

    # 80 - 89
    "eighty": 80, "assee": 80, "assi": 80, "अस्सी": 80,
    "eightyone": 81, "eighty-one": 81, "ikyaasee": 81, "ikyasi": 81, "ikyaasi": 81, "इक्यासी": 81,
    "eightytwo": 82, "eighty-two": 82, "bayaasee": 82, "bayasi": 82, "bayaasi": 82, "बयासी": 82,
    "eightythree": 83, "eighty-three": 83, "tiraasee": 83, "tirasi": 83, "tiraasi": 83, "तिरासी": 83,
    "eightyfour": 84, "eighty-four": 84, "chauraasee": 84, "chaurasi": 84, "chauraasi": 84, "चौरासी": 84,
    "eightyfive": 85, "eighty-five": 85, "pachaasee": 85, "pachasi": 85, "pachaasi": 85, "पचासी": 85,
    "eightysix": 86, "eighty-six": 86, "chhiyaasee": 86, "chhiyasi": 86, "chhiyaasi": 86, "छियासी": 86,
    "eightyseven": 87, "eighty-seven": 87, "sattaasee": 87, "sattasi": 87, "sattaasi": 87, "सत्तासी": 87,
    "eightyeight": 88, "eighty-eight": 88, "atthaasee": 88, "atthasi": 88, "atthaasi": 88, "अट्ठासी": 88,
    "eightynine": 89, "eighty-nine": 89, "nawasi": 89, "nawaasee": 89, "navasi": 89, "navaasi": 89, "नवासी": 89,

    # 90 - 99
    "ninety": 90, "nabbe": 90, "navve": 90, "nabbey": 90, "नब्बे": 90, "नव्वे": 90,
    "ninetyone": 91, "ninety-one": 91, "ikyaanwe": 91, "ikyanve": 91, "ikyanbe": 91, "ikyaanve": 91, "इक्यानवे": 91, "इक्यानबे": 91,
    "ninetytwo": 92, "ninety-two": 92, "baanwe": 92, "baanve": 92, "banve": 92, "banwe": 92, "बानवे": 92, "बानबे": 92,
    "ninetythree": 93, "ninety-three": 93, "tiraanwe": 93, "tiranve": 93, "tiranbe": 93, "tiraanve": 93, "तिरनवे": 93, "तिरनबे": 93, "तिरहानवे": 93, "तिरानवे": 93, "तिरानबे": 93,
    "ninetyfour": 94, "ninety-four": 94, "chauraanwe": 94, "chauranve": 94, "chauranbe": 94, "chauraanve": 94, "चौरानवे": 94, "चौरानबे": 94,
    "ninetyfive": 95, "ninety-five": 95, "panchaanwe": 95, "panchanve": 95, "panchanbe": 95, "pachanve": 95, "pachanbe": 95, "पचानवे": 95, "पचानबे": 95,
    "ninetysix": 96, "ninety-six": 96, "chhiyaanwe": 96, "chhiyanve": 96, "chhiyanbe": 96, "chhiyaanve": 96, "छियानवे": 96, "छियानबे": 96,
    "ninetyseven": 97, "ninety-seven": 97, "sattaanwe": 97, "sattanve": 97, "sattanbe": 97, "sattaanve": 97, "सत्तानवे": 97, "सत्तानबे": 97,
    "ninetyeight": 98, "ninety-eight": 98, "atthaanwe": 98, "atthanve": 98, "atthanbe": 98, "atthaanve": 98, "अट्ठानवे": 98, "अट्ठानबे": 98,
    "ninetynine": 99, "ninety-nine": 99, "ninaanwe": 99, "ninanve": 99, "ninanbe": 99, "ninaanve": 99, "निन्यानवे": 99, "निन्यानबे": 99,
}

# Quantifier Multipliers
MULTIPLIERS: Dict[str, int] = {
    "sau": 100, "so": 100, "hundred": 100, "hundreds": 100, "सौ": 100,
    "hazaar": 1000, "hazar": 1000, "hajar": 1000, "thousand": 1000, "thousands": 1000,
    "हज़ार": 1000, "हजार": 1000, "k": 1000,
    "lakh": 100000, "laakh": 100000, "lac": 100000, "lacs": 100000, "lakhs": 100000, "लाख": 100000,
    "crore": 10000000, "crores": 10000000, "karor": 10000000, "करोड़": 10000000,
}

# Indian Fractional Scale Multipliers
FRACTIONS: Dict[str, float] = {
    "dedh": 1.5, "derh": 1.5, "डेढ़": 1.5,
    "dhai": 2.5, "dhaai": 2.5, "ढाई": 2.5,
    "sawa": 1.25, "sava": 1.25, "सवा": 1.25,
    "paune": 0.75, "पौने": 0.75,
}

# Map 1-99 for TTS conversion
HINDI_WORDS_1_TO_99: Dict[int, str] = {
    1: "ek", 2: "do", 3: "teen", 4: "chaar", 5: "paanch", 6: "chhe", 7: "saat", 8: "aath", 9: "nau", 10: "das",
    11: "gyaarah", 12: "baarah", 13: "terah", 14: "chaudah", 15: "pandrah", 16: "solah", 17: "satrah", 18: "athaarah", 19: "unnees", 20: "bees",
    21: "ikkis", 22: "baaees", 23: "teyees", 24: "chaubees", 25: "pachees", 26: "chhabbees", 27: "sattaees", 28: "atthaees", 29: "untees", 30: "tees",
    31: "iktees", 32: "battees", 33: "taintees", 34: "chauntees", 35: "paintees", 36: "chhattees", 37: "saintees", 38: "adhtees", 39: "untalees", 40: "chaalees",
    41: "iktaalees", 42: "bayaalees", 43: "tentaalees", 44: "chawaalees", 45: "paintaalees", 46: "chhiyaalees", 47: "saintaalees", 48: "adhtaalees", 49: "unchaas", 50: "pachaas",
    51: "ikyaawan", 52: "baawan", 53: "tirpan", 54: "chauwan", 55: "pachpan", 56: "chhappan", 57: "sattaawan", 58: "atthaawan", 59: "unsath", 60: "saath",
    61: "iksath", 62: "baasath", 63: "tirsath", 64: "chaunsath", 65: "painsath", 66: "chhiyaasath", 67: "sadsath", 68: "adhsath", 69: "unhattar", 70: "sattar",
    71: "ikhattar", 72: "bahattar", 73: "tihattar", 74: "chauhattar", 75: "pachhattar", 76: "chhiyattar", 77: "sathattar", 78: "athhattar", 79: "unasi", 80: "assee",
    81: "ikyaasee", 82: "bayaasee", 83: "tiraasee", 84: "chauraasee", 85: "pachaasee", 86: "chhiyaasee", 87: "sattaasee", 88: "atthaasee", 89: "nawasi", 90: "nabbe",
    91: "ikyaanwe", 92: "baanwe", 93: "tiraanwe", 94: "chauraanwe", 95: "panchaanwe", 96: "chhiyaanwe", 97: "sattaanwe", 98: "atthaanwe", 99: "ninaanwe"
}

# Intent Lexicon
SALE_KEYWORDS = [
    # Required keywords
    "sale", "sell", "bikri", "becha", "bechi", "aaye", "aaya", "jama",
    "kamaya", "received", "mile", "credit", "aamdani", "aamdhani", "profit", "bech diya",
    # Additional English and Hinglish variations
    "biki", "sold", "maal becha", "kamai", "aayi", "mila", "mili", "prapt", "income", "collection",
    # Hindi Devanagari
    "सेल", "बिक्री", "बेचा", "बेची", "जमा", "क्रेडिट", "कमाई", "आया", "आए", "मिले", "आमदनी", "मुनाफा"
]

EXPENSE_KEYWORDS = [
    # Required keywords
    "expense", "kharcha", "kharch", "maal", "kharida", "kharidi", "diye", "diya",
    "bill", "paid", "bought", "chukaya", "bhara", "debit", "gaya", "nuksan", "de diya",
    # Additional English and Hinglish variations
    "kharach", "kharid", "maal kharida", "de diye", "spent", "bill bhara", "bhare",
    "chukaaya", "chuka diya", "chuka diye", "bhugtan", "payment kiya", "payment ki", "gaye", "gayi", "nuksaan",
    # Hindi Devanagari
    "खर्चा", "खर्च", "खरीदा", "खरीदी", "खरीद", "दिया", "दिए", "भुगतान", "डेबिट", "बिल", "गया", "गए", "नुकसान"
]

SUMMARY_KEYWORDS = [
    "summary", "hisab", "hisaab", "total", "report", "kitna bacha",
    "kitni sale", "kitna bikri", "din ka hisab", "balance", "status",
    "हिसाब", "कुल", "रिपोर्ट", "समरी", "बैलेंस"
]


def normalize_text(text: str) -> str:
    """Normalize input text by translating Devanagari numerals, currency symbols, and commas."""
    res = [DEV_DIGITS.get(ch, ch) for ch in text]
    text = "".join(res)
    # Remove digit commas e.g. 2,500 -> 2500
    text = re.sub(r'(\d+),(\d+)', r'\1\2', text)
    # Strip currency signs
    text = re.sub(r'[₹]', ' ', text)
    text = re.sub(r'\b(rs|inr|re)\b\.?', ' ', text, flags=re.IGNORECASE)
    return text.strip()


def parse_number_tokens(tokens: List[str]) -> Optional[int]:
    """Parse a contiguous sequence of number and quantifier tokens into an integer amount."""
    if not tokens:
        return None

    total = 0
    current = 0
    matched_any = False

    i = 0
    while i < len(tokens):
        tok = tokens[i].lower()

        # Fractional scale (e.g., dedh hazaar = 1500, dhai sau = 250)
        if tok in FRACTIONS:
            frac = FRACTIONS[tok]
            matched_any = True
            if i + 1 < len(tokens) and tokens[i + 1].lower() in MULTIPLIERS:
                mult = MULTIPLIERS[tokens[i + 1].lower()]
                total += int(frac * mult)
                i += 2
                continue
            else:
                current = frac
                i += 1
                continue

        # Digits (e.g., "2500", "25", "2")
        if re.match(r'^\d+(\.\d+)?$', tok):
            val = float(tok)
            matched_any = True
            if i + 1 < len(tokens) and tokens[i + 1].lower() in MULTIPLIERS:
                mult = MULTIPLIERS[tokens[i + 1].lower()]
                total += int(val * mult)
                i += 2
                continue
            elif current == 0:
                current = val
            else:
                total += int(current)
                current = val
            i += 1
            continue

        # Words in dictionary (e.g., "pachchis", "paanch", "do")
        if tok in WORD_TO_NUMBER:
            val = WORD_TO_NUMBER[tok]
            matched_any = True
            if i + 1 < len(tokens) and tokens[i + 1].lower() in MULTIPLIERS:
                mult = MULTIPLIERS[tokens[i + 1].lower()]
                total += int(val * mult)
                current = 0
                i += 2
                continue
            elif current == 0:
                current = val
            else:
                current += val
            i += 1
            continue

        # Multiplier token (e.g. "sau", "hazaar")
        if tok in MULTIPLIERS:
            mult = MULTIPLIERS[tok]
            matched_any = True
            if current == 0:
                current = 1
            total += int(current * mult)
            current = 0
            i += 1
            continue

        i += 1

    total += int(current)
    return int(total) if matched_any else None


def extract_amount_from_clause(clause: str) -> Tuple[Optional[int], bool, Optional[str]]:
    """
    Extracts numerical amount from a clause while checking for business ambiguities.
    Returns: (amount, is_ambiguous, clarification_prompt)
    """
    clean = normalize_text(clause)

    # Ambiguity check: e.g. "aaj paanch ka maal gaya" (small amount without unit/sau/hazaar)
    ambiguous_maal = re.search(
        r'\b(ek|do|teen|chaar|char|paanch|panch|chhe|che|saat|sat|aath|ath|nau|das|[1-9]|10)\s+ka\s+maal\b',
        clean,
        re.IGNORECASE
    )
    if ambiguous_maal:
        raw_word = ambiguous_maal.group(1).lower()
        val = WORD_TO_NUMBER.get(raw_word, int(raw_word) if raw_word.isdigit() else 5)
        return (
            val,
            True,
            f"Aapne '{raw_word} ka maal' kaha hai. Kya aap {raw_word} sau ya {raw_word} hazaar kehna chahte hain? Kripya amount clarify karein."
        )

    tokens = re.findall(r'[\w\u0900-\u097F]+', clean)
    num_token_indices = []
    for idx, tok in enumerate(tokens):
        tok_lower = tok.lower()
        if (tok_lower in WORD_TO_NUMBER or
                tok_lower in MULTIPLIERS or
                tok_lower in FRACTIONS or
                re.match(r'^\d+(\.\d+)?$', tok_lower)):
            num_token_indices.append(idx)

    if not num_token_indices:
        return (None, False, "Amount missing")

    # Group contiguous sequence of number tokens
    groups: List[List[int]] = []
    curr_group = [num_token_indices[0]]
    for idx in num_token_indices[1:]:
        if idx == curr_group[-1] + 1:
            curr_group.append(idx)
        else:
            groups.append(curr_group)
            curr_group = [idx]
    groups.append(curr_group)

    amounts = []
    for g in groups:
        sub_tokens = [tokens[i] for i in g]
        amt = parse_number_tokens(sub_tokens)
        if amt is not None:
            amounts.append(amt)

    if not amounts:
        return (None, False, "Amount missing")

    amount = amounts[0] if len(amounts) == 1 else sum(amounts)

    if amount <= 0:
        return (amount, True, "Amount shunya ya negative nahi ho sakta. Kripya sahi amount batayein.")

    return (amount, False, None)


def number_to_hinglish_words(amount: int) -> str:
    """
    Converts an integer amount into natural Hinglish words tuned for Timbre TTS pronunciation.
    Examples:
      - 2500 -> "pachees sau"
      - 1500 -> "pandrah sau"
      - 800  -> "aath sau"
      - 10000 -> "das hazaar"
    """
    if amount == 0:
        return "shunya"
    if amount < 0:
        return "minus " + number_to_hinglish_words(abs(amount))

    parts: List[str] = []

    # Crores (10,000,000)
    if amount >= 10000000:
        cr = amount // 10000000
        amount %= 10000000
        parts.append(f"{number_to_hinglish_words(cr)} crore")

    # Lakhs (100,000)
    if amount >= 100000:
        lakh = amount // 100000
        amount %= 100000
        parts.append(f"{number_to_hinglish_words(lakh)} lakh")

    # Natural hundred-based phrasing for 1100 to 9900 (e.g. 2500 -> "pachees sau")
    if 1100 <= amount <= 9900 and (amount % 100 == 0) and (amount % 1000 != 0):
        hundreds_count = amount // 100
        parts.append(f"{HINDI_WORDS_1_TO_99.get(hundreds_count, str(hundreds_count))} sau")
        return " ".join(parts)

    # Thousands (1,000)
    if amount >= 1000:
        th = amount // 1000
        amount %= 1000
        parts.append(f"{HINDI_WORDS_1_TO_99.get(th, str(th))} hazaar")

    # Hundreds (100)
    if amount >= 100:
        hd = amount // 100
        amount %= 100
        parts.append(f"{HINDI_WORDS_1_TO_99.get(hd, str(hd))} sau")

    # Remainder 1 - 99
    if amount > 0:
        parts.append(HINDI_WORDS_1_TO_99.get(amount, str(amount)))

    return " ".join(parts)


def detect_clause_intent(clause: str) -> Optional[str]:
    """Detects if a clause indicates a 'sale' or an 'expense'."""
    c_lower = clause.lower()

    # Explicit compound phrase priorities
    if any(k in c_lower for k in ["bech diya", "maal becha", "maal biki"]):
        return "sale"
    if any(k in c_lower for k in ["maal kharida", "de diya", "de diye", "chuka diya", "chuka diye", "bill bhara"]):
        return "expense"

    has_expense = any(k in c_lower for k in EXPENSE_KEYWORDS)
    has_sale = any(k in c_lower for k in SALE_KEYWORDS)

    if has_sale and not has_expense:
        return "sale"
    if has_expense and not has_sale:
        return "expense"
    if has_sale and has_expense:
        if any(k in c_lower for k in [
            "maal kharida", "kharcha", "kharch", "kharach", "kharida", "kharidi",
            "kharid", "bought", "chukaya", "chukaaya", "bill", "paid", "de diya",
            "nuksan", "nuksaan"
        ]):
            return "expense"
        return "sale"
    return None


def parse_voice_command(transcript: str) -> Dict[str, Any]:
    """
    Deterministic Hinglish/Hindi-English intent and amount parser.
    Supports:
      - `add_sale`
      - `add_expense`
      - `get_daily_summary`
      - `multi_action` (both sale and expense in one sentence)
      - `clarification_needed` (when amount is ambiguous, missing, or <= 0)
    """
    if not transcript or not transcript.strip():
        return {
            "intent": "clarification_needed",
            "requires_confirmation": True,
            "clarification_prompt": "Koi aawaaz sunai nahi di. Kripya apna command dobara bolein.",
            "response_text": "Koi aawaaz sunai nahi di. Kripya apna command dobara bolein.",
            "transcript": ""
        }

    clean_tr = transcript.strip()
    t_lower = clean_tr.lower()

    # 1. Daily Summary Intent
    if any(k in t_lower for k in SUMMARY_KEYWORDS):
        return {
            "intent": "get_daily_summary",
            "requires_confirmation": False,
            "clarification_prompt": None,
            "response_text": None,
            "transcript": clean_tr
        }

    # 2. Multi-Action Intent (Both sale and expense in one sentence)
    clauses = [
        c.strip() for c in re.split(r'\s+(?:aur|and|tatha|evam|plus|,|और|तथा|एवं)\s+', clean_tr, flags=re.IGNORECASE)
        if c.strip()
    ]

    if len(clauses) >= 2:
        actions = []
        has_ambiguity = False
        clarification_msg = None

        for c in clauses:
            c_intent = detect_clause_intent(c)
            if c_intent in ("sale", "expense"):
                amt, is_amb, reason = extract_amount_from_clause(c)
                if is_amb or amt is None or amt <= 0:
                    has_ambiguity = True
                    clarification_msg = reason or (f"Kitne rupaye ki {c_intent} hui hai? Kripya amount batayein.")
                    break

                desc = "sale" if c_intent == "sale" else "expense"
                if "maal kharida" in c.lower():
                    desc = "maal kharida"
                elif "maal becha" in c.lower():
                    desc = "maal becha"

                actions.append({
                    "type": c_intent,
                    "amount": amt,
                    "description": desc
                })

        if has_ambiguity:
            return {
                "intent": "clarification_needed",
                "requires_confirmation": True,
                "clarification_prompt": clarification_msg,
                "response_text": clarification_msg,
                "transcript": clean_tr
            }

        types_found = {a["type"] for a in actions}
        if len(actions) >= 2 and len(types_found) >= 2:
            resp_parts = []
            for a in actions:
                words = number_to_hinglish_words(a["amount"])
                suffix = "ki sale" if a["type"] == "sale" else "ka kharcha"
                resp_parts.append(f"{a['amount']} rupaye ({words}) {suffix}")
            response_text = " aur ".join(resp_parts) + " record ho gaya hai."

            return {
                "intent": "multi_action",
                "actions": actions,
                "requires_confirmation": False,
                "clarification_prompt": None,
                "response_text": response_text,
                "transcript": clean_tr
            }

    # 3. Single Action Intent
    c_intent = detect_clause_intent(clean_tr)
    if not c_intent:
        return {
            "intent": "clarification_needed",
            "requires_confirmation": True,
            "clarification_prompt": "Kripya batayein ki ye sale hai ya kharcha, aur kitna amount hai.",
            "response_text": "Kripya batayein ki ye sale hai ya kharcha, aur kitna amount hai.",
            "transcript": clean_tr
        }

    amt, is_amb, reason = extract_amount_from_clause(clean_tr)
    if is_amb or amt is None or amt <= 0:
        prompt = reason or (f"Kitne rupaye ki {c_intent} hui hai? Kripya amount batayein.")
        return {
            "intent": "clarification_needed",
            "requires_confirmation": True,
            "clarification_prompt": prompt,
            "response_text": prompt,
            "type": c_intent,
            "amount": amt,
            "transcript": clean_tr
        }

    desc = "sale" if c_intent == "sale" else "expense"
    if "maal kharida" in clean_tr.lower():
        desc = "maal kharida"
    elif "maal becha" in clean_tr.lower():
        desc = "maal becha"

    words = number_to_hinglish_words(amt)
    action_intent = "add_sale" if c_intent == "sale" else "add_expense"
    suffix = "ki sale" if c_intent == "sale" else "ka kharcha"
    response_text = f"Aapki {amt} rupaye ({words}) {suffix} record ho gayi hai."

    return {
        "intent": action_intent,
        "type": c_intent,
        "amount": amt,
        "description": desc,
        "requires_confirmation": False,
        "clarification_prompt": None,
        "response_text": response_text,
        "transcript": clean_tr
    }


def process_voice_action(
    transcript: str,
    auto_commit: bool = True,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    End-to-end coordinator:
      1. Parses voice transcript with agent.parse_voice_command.
      2. If auto_commit is True and unambiguous, commits to SQLite via database.py.
      3. Recomputes today's summary.
      4. Synthesizes spoken response via gnani_client.synthesize_speech and encodes to base64.
    """
    parsed = parse_voice_command(transcript)
    intent = parsed.get("intent")

    # Case 1: Clarification needed
    if intent == "clarification_needed":
        clarification_text = parsed.get("clarification_prompt") or parsed.get("response_text")
        tts_res = gnani_client.synthesize_speech(text=clarification_text)
        audio_b64 = base64.b64encode(tts_res["audio_bytes"]).decode("utf-8") if tts_res.get("success") and tts_res.get("audio_bytes") else None

        return {
            "success": True,
            "executed": False,
            "transaction_saved": False,
            "requires_confirmation": True,
            "transcript": transcript,
            "parsed": parsed,
            "response_text": clarification_text,
            "audio_base64": audio_b64,
            "updated_summary": database.get_summary_today(db_path=db_path)
        }

    # Case 2: Get Daily Summary
    if intent == "get_daily_summary":
        summary = database.get_summary_today(db_path=db_path)
        sales_w = number_to_hinglish_words(summary["sales"])
        exp_w = number_to_hinglish_words(summary["expenses"])
        response_text = f"Aaj ki kul bikri {summary['sales']} rupaye ({sales_w}) aur kharcha {summary['expenses']} rupaye ({exp_w}) hai."

        tts_res = gnani_client.synthesize_speech(text=response_text)
        audio_b64 = base64.b64encode(tts_res["audio_bytes"]).decode("utf-8") if tts_res.get("success") and tts_res.get("audio_bytes") else None

        return {
            "success": True,
            "executed": True,
            "transaction_saved": False,
            "requires_confirmation": False,
            "transcript": transcript,
            "parsed": parsed,
            "response_text": response_text,
            "audio_base64": audio_b64,
            "updated_summary": summary
        }

    # Case 3: Single Transaction (add_sale / add_expense)
    if intent in ("add_sale", "add_expense"):
        record = None
        if auto_commit:
            record = database.insert_transaction(
                trans_type=parsed["type"],
                amount=parsed["amount"],
                description=parsed.get("description"),
                db_path=db_path
            )

        summary = database.get_summary_today(db_path=db_path)
        response_text = parsed["response_text"]
        tts_res = gnani_client.synthesize_speech(text=response_text)
        audio_b64 = base64.b64encode(tts_res["audio_bytes"]).decode("utf-8") if tts_res.get("success") and tts_res.get("audio_bytes") else None

        return {
            "success": True,
            "executed": bool(auto_commit),
            "transaction_saved": bool(auto_commit and record),
            "requires_confirmation": False,
            "transcript": transcript,
            "parsed": parsed,
            "record": record,
            "response_text": response_text,
            "audio_base64": audio_b64,
            "updated_summary": summary
        }

    # Case 4: Multi-Action
    if intent == "multi_action":
        records = []
        if auto_commit:
            for act in parsed.get("actions", []):
                rec = database.insert_transaction(
                    trans_type=act["type"],
                    amount=act["amount"],
                    description=act.get("description"),
                    db_path=db_path
                )
                records.append(rec)

        summary = database.get_summary_today(db_path=db_path)
        response_text = parsed["response_text"]
        tts_res = gnani_client.synthesize_speech(text=response_text)
        audio_b64 = base64.b64encode(tts_res["audio_bytes"]).decode("utf-8") if tts_res.get("success") and tts_res.get("audio_bytes") else None

        return {
            "success": True,
            "executed": bool(auto_commit),
            "transaction_saved": bool(auto_commit and records),
            "requires_confirmation": False,
            "transcript": transcript,
            "parsed": parsed,
            "records": records,
            "response_text": response_text,
            "audio_base64": audio_b64,
            "updated_summary": summary
        }

    # Fallback
    return {
        "success": False,
        "executed": False,
        "requires_confirmation": True,
        "transcript": transcript,
        "parsed": parsed,
        "response_text": "Command samajh nahi aaya. Kripya dobara bolein.",
        "audio_base64": None,
        "updated_summary": database.get_summary_today(db_path=db_path)
    }
