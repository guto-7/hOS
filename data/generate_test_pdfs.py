#!/usr/bin/env python3
"""Generate 3 test blood panel PDFs for patient 9711769738 (Male, 32, 177cm).

Doc 1: 15/09/2025 — Healthy baseline, few mild flags
Doc 2: 15/12/2025 — Some deterioration, triggers conditions
Doc 3: 15/03/2026 — Mixed, shows trending + red flags
"""

from fpdf import FPDF


def make_pdf(filename: str, collected_date: str, markers: list[tuple[str, str, str, str]]):
    """
    markers: list of (name, value, unit, ref_range)
    ref_range: e.g. "136 - 145" or "< 5.0"
    """
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Courier", size=10)

    # Header
    pdf.cell(0, 6, "  Laverty Pathology", ln=True)
    pdf.cell(0, 6, f"  Collection Date: {collected_date}", ln=True)
    pdf.cell(0, 6, "  Patient: Vladimir Vranesevic   DOB: 15/03/1994   Sex: Male", ln=True)
    pdf.cell(0, 6, "  ID: 9711769738", ln=True)
    pdf.cell(0, 6, "", ln=True)
    pdf.cell(0, 6, "  " + "-" * 90, ln=True)
    pdf.cell(0, 6, f"  {'Marker':<38} {'Value':>8}  {'Unit':<18} {'Reference':<16}", ln=True)
    pdf.cell(0, 6, "  " + "-" * 90, ln=True)

    for name, value, unit, ref in markers:
        line = f"  {name:<38} {value:>8}  {unit:<18} {ref:<16}"
        pdf.cell(0, 5, line, ln=True)

    pdf.cell(0, 6, "  " + "-" * 90, ln=True)
    pdf.cell(0, 6, "  --- END OF REPORT ---", ln=True)

    pdf.output(filename)
    print(f"  Created {filename}")


# ── All markers for each doc ──

COMMON_MARKERS = [
    # Growth Axis
    ("IGF-1",                          "ng/mL",   "114 - 492"),
    ("Growth Hormone",                 "ug/L",    "0.05 - 5.0"),
    # Electrolytes/Renal
    ("Sodium",                         "mmol/L",  "136 - 145"),
    ("Potassium",                      "mmol/L",  "3.5 - 5.0"),
    ("Chloride",                       "mmol/L",  "98 - 106"),
    ("Bicarbonate",                    "mmol/L",  "23 - 28"),
    ("Urea",                           "mmol/L",  "2.9 - 7.1"),
    ("Creatinine",                     "umol/L",  "62 - 115"),
    ("eGFR",                           "mL/min/1.73m2", "60 - 120"),
    ("Calcium",                        "mmol/L",  "2.15 - 2.55"),
    ("Adjusted Calcium",               "mmol/L",  "2.15 - 2.55"),
    ("Phosphate",                      "mmol/L",  "0.97 - 1.45"),
    ("Magnesium",                      "mmol/L",  "0.66 - 1.07"),
    ("Uric Acid",                      "mmol/L",  "0.24 - 0.51"),
    # Liver Function
    ("Total Protein",                  "g/L",     "55 - 90"),
    ("Albumin",                        "g/L",     "35 - 55"),
    ("Globulin",                       "g/L",     "20 - 35"),
    ("Alkaline Phosphatase",           "U/L",     "30 - 120"),
    ("Total Bilirubin",                "umol/L",  "5 - 17"),
    ("GGT",                            "U/L",     "9 - 50"),
    ("AST",                            "U/L",     "10 - 40"),
    ("ALT",                            "U/L",     "10 - 40"),
    # Lipids
    ("Total Cholesterol",              "mmol/L",  "3.0 - 5.18"),
    ("HDL Cholesterol",                "mmol/L",  "1.04 - 2.07"),
    ("LDL Cholesterol",                "mmol/L",  "1.0 - 4.13"),
    ("Non-HDL Cholesterol",            "mmol/L",  "1.0 - 3.37"),
    ("Triglycerides",                  "mmol/L",  "0.45 - 1.70"),
    ("LDL/HDL Ratio",                  "ratio",   "0.5 - 2.5"),
    ("Chol/HDL Ratio",                 "ratio",   "1.0 - 4.0"),
    # Metabolic
    ("Glucose",                        "mmol/L",  "3.9 - 5.5"),
    ("Insulin",                        "mU/L",    "2.0 - 20"),
    ("HbA1c",                          "%",       "4.0 - 5.6"),
    # Inflammation
    ("hsCRP",                          "mg/L",    "0 - 3.0"),
    # Androgens
    ("Total Testosterone",             "nmol/L",  "10.1 - 38.2"),
    ("SHBG",                           "nmol/L",  "10 - 57"),
    ("Free Testosterone",              "pmol/L",  "243 - 1041"),
    ("DHEA-S",                         "umol/L",  "2.42 - 12.4"),
    # Pituitary/Gonadal
    ("FSH",                            "IU/L",    "1 - 7"),
    ("LH",                             "IU/L",    "2 - 9"),
    ("Oestradiol",                     "pmol/L",  "73 - 184"),
    ("Progesterone",                   "nmol/L",  "0.38 - 0.95"),
    ("Prolactin",                      "mIU/L",   "50 - 420"),
    # Thyroid
    ("TSH",                            "mIU/L",   "0.50 - 4.00"),
    ("Free T4",                        "pmol/L",  "10 - 23"),
    ("Free T3",                        "pmol/L",  "3.5 - 6.5"),
    # Vitamins/Minerals
    ("Vitamin D",                      "nmol/L",  "50 - 250"),
    ("Homocysteine",                   "umol/L",  "5 - 15"),
    ("Vitamin B12",                    "pmol/L",  "148 - 590"),
    ("Folate",                         "nmol/L",  "4.1 - 20.4"),
    # Iron Studies
    ("Ferritin",                       "ug/L",    "24 - 336"),
    ("Iron",                           "umol/L",  "9 - 27"),
    ("Transferrin",                    "g/L",     "2.0 - 4.0"),
    ("Iron Saturation",               "%",       "20 - 50"),
    # CBC
    ("WBC",                            "x10^9/L", "4.0 - 11.0"),
    ("RBC",                            "x10^12/L","4.5 - 5.9"),
    ("Haemoglobin",                    "g/L",     "140 - 180"),
    ("Haematocrit",                    "ratio",   "0.42 - 0.50"),
    ("MCV",                            "fL",      "80 - 98"),
    ("MCH",                            "pg",      "28 - 32"),
    ("RDW",                            "%",       "9.0 - 14.5"),
    ("Platelets",                      "x10^9/L", "150 - 450"),
    # Prostate
    ("PSA",                            "ug/L",    "0 - 4.0"),
]

# ── Doc 1: 15/09/2025 — Healthy baseline, a few mild yellow flags ──
# Mostly normal, slight vitamin D insufficiency, mildly elevated triglycerides
doc1_values = [
    "168",    # IGF-1         normal
    "0.9",    # GH            normal
    "140",    # Sodium        normal
    "4.2",    # Potassium     normal
    "101",    # Chloride      normal
    "25",     # Bicarbonate   normal
    "5.2",    # Urea          normal
    "82",     # Creatinine    normal
    "92",     # eGFR          normal
    "2.35",   # Calcium       normal
    "2.38",   # Adj Calcium   normal
    "1.12",   # Phosphate     normal
    "0.85",   # Magnesium     normal
    "0.38",   # Uric Acid     normal
    "72",     # Total Protein normal
    "44",     # Albumin       normal
    "28",     # Globulin      normal
    "65",     # ALP           normal
    "10",     # Total Bili    normal
    "28",     # GGT           normal
    "22",     # AST           normal
    "19",     # ALT           normal
    "4.8",    # Total Chol    normal
    "1.42",   # HDL           normal
    "2.85",   # LDL           normal
    "3.38",   # Non-HDL       yellow (just over 3.37)
    "1.85",   # Triglycerides yellow (over 1.70)
    "2.01",   # LDL/HDL       normal
    "3.38",   # Chol/HDL      normal
    "5.1",    # Glucose       normal
    "7.5",    # Insulin       normal
    "5.2",    # HbA1c         normal
    "1.2",    # hsCRP         normal
    "22.5",   # Testosterone  normal
    "32",     # SHBG          normal
    "480",    # Free Testo    normal
    "6.8",    # DHEA-S        normal
    "3.5",    # FSH           normal
    "4.2",    # LH            normal
    "105",    # Oestradiol    normal
    "0.62",   # Progesterone  normal
    "180",    # Prolactin     normal
    "2.1",    # TSH           normal
    "16.5",   # Free T4       normal
    "5.2",    # Free T3       normal
    "45",     # Vitamin D     yellow (below 50)
    "9.5",    # Homocysteine  normal
    "320",    # B12           normal
    "12.5",   # Folate        normal
    "120",    # Ferritin      normal
    "18",     # Iron          normal
    "2.8",    # Transferrin   normal
    "32",     # Iron Sat      normal
    "6.5",    # WBC           normal
    "5.1",    # RBC           normal
    "152",    # Hb            normal
    "0.45",   # Hct           normal
    "88",     # MCV           normal
    "30",     # MCH           normal
    "12.5",   # RDW           normal
    "245",    # Platelets     normal
    "0.8",    # PSA           normal
]

# ── Doc 2: 15/12/2025 — Deterioration, triggers conditions ──
# Elevated insulin/glucose (insulin resistance), low vitamin D, elevated hsCRP,
# high LDL, metabolic stress, mild liver enzyme elevation
doc2_values = [
    "145",    # IGF-1         normal
    "1.2",    # GH            normal
    "142",    # Sodium        normal
    "4.5",    # Potassium     normal
    "103",    # Chloride      normal
    "24",     # Bicarbonate   normal
    "6.1",    # Urea          normal
    "88",     # Creatinine    normal
    "85",     # eGFR          normal
    "2.42",   # Calcium       normal
    "2.40",   # Adj Calcium   normal
    "1.05",   # Phosphate     normal
    "0.78",   # Magnesium     normal
    "0.45",   # Uric Acid     normal
    "75",     # Total Protein normal
    "42",     # Albumin       normal
    "33",     # Globulin      normal
    "78",     # ALP           normal
    "14",     # Total Bili    normal
    "45",     # GGT           yellow (near upper)
    "38",     # AST           normal (near upper)
    "42",     # ALT           yellow (over 40)
    "5.8",    # Total Chol    yellow (over 5.18)
    "1.08",   # HDL           normal (low-normal)
    "3.9",    # LDL           normal (near upper)
    "4.72",   # Non-HDL       red (way over 3.37)
    "2.1",    # Triglycerides yellow (over 1.70)
    "3.61",   # LDL/HDL       red (over 2.5)
    "5.37",   # Chol/HDL      red (over 4.0)
    "5.8",    # Glucose       yellow (prediabetes range)
    "18.5",   # Insulin       normal (high-normal)
    "5.7",    # HbA1c         yellow (prediabetes threshold)
    "3.8",    # hsCRP         red (over 3.0)
    "18.2",   # Testosterone  normal
    "38",     # SHBG          normal
    "390",    # Free Testo    normal
    "5.5",    # DHEA-S        normal
    "4.0",    # FSH           normal
    "5.1",    # LH            normal
    "120",    # Oestradiol    normal
    "0.55",   # Progesterone  normal
    "210",    # Prolactin     normal
    "3.8",    # TSH           normal (high-normal)
    "12.0",   # Free T4       normal (low-normal)
    "4.0",    # Free T3       normal
    "32",     # Vitamin D     red (deficiency/insufficiency, triggers condition)
    "13.5",   # Homocysteine  normal (elevated)
    "280",    # B12           normal
    "8.2",    # Folate        normal
    "85",     # Ferritin      normal
    "14",     # Iron          normal
    "2.5",    # Transferrin   normal
    "28",     # Iron Sat      normal
    "7.2",    # WBC           normal
    "5.3",    # RBC           normal
    "158",    # Hb            normal
    "0.47",   # Hct           normal
    "89",     # MCV           normal
    "30",     # MCH           normal
    "13.0",   # RDW           normal
    "230",    # Platelets     normal
    "1.1",    # PSA           normal
]

# ── Doc 3: 15/03/2026 — Current, mixed results, shows trending ──
# Vitamin D improved (supplementing), but metabolic worse (higher HbA1c),
# hsCRP still elevated, iron declining, testosterone slightly low
doc3_values = [
    "135",    # IGF-1         normal
    "0.7",    # GH            normal
    "138",    # Sodium        normal
    "4.0",    # Potassium     normal
    "100",    # Chloride      normal
    "26",     # Bicarbonate   normal
    "5.8",    # Urea          normal
    "95",     # Creatinine    normal
    "82",     # eGFR          normal
    "2.32",   # Calcium       normal
    "2.35",   # Adj Calcium   normal
    "1.22",   # Phosphate     normal
    "0.72",   # Magnesium     normal
    "0.52",   # Uric Acid     yellow (just over 0.51)
    "68",     # Total Protein normal
    "40",     # Albumin       normal
    "28",     # Globulin      normal
    "72",     # ALP           normal
    "12",     # Total Bili    normal
    "52",     # GGT           yellow (over 50)
    "35",     # AST           normal
    "48",     # ALT           yellow (over 40)
    "5.5",    # Total Chol    yellow (over 5.18)
    "1.10",   # HDL           normal
    "3.68",   # LDL           normal
    "4.40",   # Non-HDL       red (over 3.37)
    "1.95",   # Triglycerides yellow (over 1.70)
    "3.35",   # LDL/HDL       red (over 2.5)
    "5.0",    # Chol/HDL      red (over 4.0)
    "6.2",    # Glucose       yellow (prediabetes)
    "22",     # Insulin       yellow (over 20)
    "5.9",    # HbA1c         yellow (prediabetes, worse)
    "3.2",    # hsCRP         yellow (just over 3.0)
    "9.8",    # Testosterone  red (below 10.1, triggers low T)
    "45",     # SHBG          normal
    "220",    # Free Testo    red (below 243)
    "4.2",    # DHEA-S        normal
    "5.5",    # FSH           normal
    "6.8",    # LH            normal
    "95",     # Oestradiol    normal
    "0.48",   # Progesterone  normal
    "250",    # Prolactin     normal
    "4.5",    # TSH           yellow (over 4.0, subclinical hypothyroid)
    "10.5",   # Free T4       normal (low-normal)
    "3.8",    # Free T3       normal
    "68",     # Vitamin D     normal (improved with supplementation)
    "16.5",   # Homocysteine  yellow (over 15)
    "250",    # B12           normal
    "6.8",    # Folate        normal
    "42",     # Ferritin      normal (declining)
    "8",      # Iron          red (below 9)
    "3.5",    # Transferrin   normal
    "18",     # Iron Sat      red (below 20, triggers iron deficiency)
    "5.8",    # WBC           normal
    "4.8",    # RBC           normal
    "142",    # Hb            normal (low-normal)
    "0.43",   # Hct           normal
    "90",     # MCV           normal
    "29.5",   # MCH           normal
    "14.8",   # RDW           yellow (over 14.5)
    "210",    # Platelets     normal
    "0.9",    # PSA           normal
]


def build_markers(values: list[str]) -> list[tuple[str, str, str, str]]:
    return [(name, val, unit, ref) for (name, unit, ref), val in zip(COMMON_MARKERS, values)]


if __name__ == "__main__":
    import os
    out_dir = os.path.join(os.path.dirname(__file__), "..", "docs", "5. Business")
    os.makedirs(out_dir, exist_ok=True)

    print("Generating test blood panel PDFs...")
    make_pdf(
        os.path.join(out_dir, "vranesevic_blood_panel_2025_09.pdf"),
        "15/09/2025",
        build_markers(doc1_values),
    )
    make_pdf(
        os.path.join(out_dir, "vranesevic_blood_panel_2025_12.pdf"),
        "15/12/2025",
        build_markers(doc2_values),
    )
    make_pdf(
        os.path.join(out_dir, "vranesevic_blood_panel_2026_03.pdf"),
        "15/03/2026",
        build_markers(doc3_values),
    )
    print("Done! 3 PDFs generated.")
