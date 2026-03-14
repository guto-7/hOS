# Bloodwork — Stage 1: Importing

## Purpose

Stage 1 is responsible for getting blood work data into the system. It covers what file formats the user can upload, where the raw file is stored, how it's read and parsed into structured data, and the user confirmation step before anything is saved.

Patient context (age, sex, fasting, pregnancy, cycle phase) is handled at the **app level during onboarding** as a global attribute shared across all modules. Stage 1 for bloodwork focuses solely on marker extraction.

---

## 1.1 Accepted File Formats

**Decision: PDF only (digital, text-layer PDFs)**

| Format | Verdict | Reasoning |
|---|---|---|
| PDF (digital) | **Accepted** | 95%+ of pathology reports from major labs (Laverty, QML, Sullivan Nicolaides, Quest, LabCorp) are delivered as digital PDFs with an embedded text layer. Text extraction is deterministic and fast (<1 second). |
| PDF (scanned/image) | **Rejected (v1)** | Requires OCR, which introduces extraction errors on medical values where a misread decimal (13.2 → 132) is clinically dangerous. OCR accuracy on dense tabular lab reports is ~92-96%, unacceptable for health data. Future version could add with mandatory user confirmation per value. |
| Photo/camera capture | **Rejected (v1)** | Same OCR issues as scanned PDFs, compounded by lighting, angle, and resolution variability. |
| CSV/spreadsheet | **Rejected** | No standardised CSV export format exists across pathology providers. Every lab would need a custom parser, and users rarely have access to CSV exports of their results. |
| Manual entry | **Rejected (v1)** | High friction, error-prone for 20-40 markers per report. Defeats the purpose of automated extraction. May be added later as a correction mechanism only. |
| HL7 FHIR / CDA | **Rejected (v1)** | Clinically ideal (structured, coded data), but patients almost never have direct access to their HL7 records. This is a hospital-to-hospital format, not a consumer format. |

**Why PDF-only is the right v1 decision:** It covers the vast majority of real-world user uploads with deterministic, testable extraction. Every other format either requires error-prone ML (OCR) or doesn't exist in consumer hands. Restricting input to high-confidence formats means the data entering Stage 2 is trustworthy from the start — garbage in, garbage out applies especially to health data.

---

## 1.2 Raw File Storage

**Decision: Save the original PDF to `~/Documents/hOS/uploads/` with a SHA-256 hash filename**

| Aspect | Decision | Reasoning |
|---|---|---|
| Storage location | `~/Documents/hOS/uploads/` | Local-first principle — the user's health data never leaves their machine. Using a well-known user directory (not hidden app data) ensures transparency: the user can find, move, or delete their files at any time. |
| Filename | `{SHA-256 hash}.pdf` | Deduplication for free — uploading the same PDF twice produces the same hash, preventing duplicate records without additional logic. Also strips any PII from the original filename (e.g., `Sarah_Chen_Pathology_March2026.pdf`). |
| Original filename | Stored in the `records` SQLite table as metadata | Preserved for display purposes ("You uploaded Sarah_Chen_Pathology.pdf") but not used as the storage key. |
| Retention | Permanent until user deletes | The raw PDF is the audit trail. If extraction logic improves, we can re-process from the original without asking the user to re-upload. |

**Why keep the raw PDF?**
1. **Auditability** — the user can always cross-reference extracted values against the original report
2. **Re-processing** — if extraction logic improves (new lab template, better parser), we can re-run the pipeline without user action
3. **Trust** — users need to know their original document is preserved, unmodified

---

## 1.3 Reading and Parsing the Raw File

**Decision: Deterministic template-based parsing using pdftotext, with lab-specific regex patterns**

### Pipeline

```
PDF file
  │
  ├─→ pdftotext — extract full text layer from PDF
  │
  ├─→ Lab identification — match header/footer against known lab templates
  │     (e.g., "Laverty Pathology", "QML Pathology", "Australian Clinical Labs")
  │
  ├─→ Template parser — regex patterns specific to that lab's layout
  │     • Row pattern: marker name | value | unit | reference range | flag
  │     • Section headers map to categories (CBC, Lipids, Thyroid, etc.)
  │
  ├─→ Alias resolution — match extracted marker name to markers.json via aliases[]
  │     ("Hb", "HGB", "Haemoglobin" all resolve to canonical "Haemoglobin (Hb)")
  │
  ├─→ Unit check — verify extracted unit matches markers.json expected unit
  │
  ├─→ Confidence scoring per marker:
  │     • HIGH — exact alias match + expected unit
  │     • MEDIUM — fuzzy match or unexpected unit (still parseable)
  │     • LOW — unrecognised marker or parse anomaly
  │
  └─→ Output: raw parsed data (marker, value, unit, lab reference range, confidence)
```

### Why template parsing over LLM extraction?

| Criterion | Template Parsing | LLM Extraction |
|---|---|---|
| Speed | <1 second | 5–30 seconds |
| Determinism | Same PDF → same output, every time | Non-deterministic; may vary between runs |
| Testability | Unit-testable per template, regression tests catch breakage | Hard to write deterministic tests |
| Accuracy (known labs) | ~99% | ~95% |
| Accuracy (unknown labs) | 0% (fails gracefully) | ~90% (best fallback) |
| Privacy | Fully local, no model needed | Local only if using on-device model |
| Auditability | Every extraction step is traceable and debuggable | Black box — hard to explain why a value was misread |

**Why this matters:** Determinism is critical for health data. If a user uploads the same PDF twice, they must get identical results. LLM extraction cannot guarantee this. Template parsing also makes the system fully testable — we can build a test suite of sample PDFs and assert exact outputs, which is impossible with probabilistic extraction.

**Fallback strategy (future):** For unrecognised lab layouts, an LLM fallback can attempt extraction, but every LLM-extracted value would be marked LOW confidence and require explicit user confirmation before saving.

---

## 1.4 User Confirmation

**Decision: Mandatory confirmation screen before any data enters the final database**

The confirmation screen shows:
- **Summary:** "Found 38 of 62 markers" with confidence breakdown (32 HIGH, 4 MEDIUM, 2 LOW)
- **Full marker table** with extracted values, units, and confidence indicators
- **LOW confidence markers** highlighted — user can correct value, remap marker name, or skip

### Why mandatory confirmation?

- **Trust** — the user must see and approve what the system extracted before it becomes their health record. Silent auto-save erodes trust.
- **Error correction** — even at 99% accuracy, a 40-marker panel has a ~33% chance of containing at least one error. The confirmation screen catches these.
- **Medicolegal** — the user explicitly confirms "this is my data and it is correct." The system never claims authority over the user's health data.

### What happens on confirm

- Raw extraction saved to `results` table (preserving original values, units, lab ranges, raw text, confidence)
- Record metadata saved to `records` table (PDF hash, collection date, lab provider, timestamps)
- Stage 2 processing begins

---

## 1.5 Stage 1 Summary

```
User selects PDF
  │
  ├─→ Validate file type (PDF only)
  ├─→ Save raw PDF to ~/Documents/hOS/uploads/{SHA-256}.pdf
  ├─→ Extract text via pdftotext
  ├─→ Identify lab provider from header/footer
  ├─→ Parse markers using lab-specific regex templates
  ├─→ Resolve aliases against markers.json
  ├─→ Score confidence per marker (HIGH / MEDIUM / LOW)
  ├─→ Present confirmation screen to user
  ├─→ User reviews, corrects if needed, confirms
  └─→ Save to SQLite (records + results tables) → hand off to Stage 2
```

| Input | Output |
|---|---|
| Raw PDF file from user | Validated, parsed marker data in SQLite with original PDF preserved |
