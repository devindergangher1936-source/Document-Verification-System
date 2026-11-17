# Document Verification

A local web dashboard for checking uploaded documents (PDFs and images) for signs of forgery or tampering. It extracts and validates Indian identifiers, gives each document a risk score, and keeps a review queue where documents are approved or rejected.

## Run it

Double-click **`run.bat`**. It opens http://127.0.0.1:8000 in your browser. Keep the console window open while you use the dashboard; closing it stops the server.

Or from a terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Portable use

Copy the folder to any Windows PC that has **Python 3.10+** and double-click `run.bat`. On the first run on a new PC it rebuilds `.venv` and installs `requirements.txt`, which needs internet once. You can skip `.venv` when copying, since it only works on the PC where it was created. Copy `data/` as well if you want to keep the existing documents and decisions.

> Opening `static/index.html` directly in a browser will not work. The page needs the Python API behind it.

To try it out, upload the files in `samples/`:

| File | Expected result |
|---|---|
| `clean_invoice.pdf` | Passed, valid GSTIN |
| `edited_invoice.pdf` | Flagged: edited with iLovePDF, incremental update, font-subset conflict, bad GSTIN and Aadhaar checksums |
| `tampered_cert.jpg` | Auto-check **passes** it. The pasted salary box only shows up as an outline in the ELA image, which is why a person should look at the ELA image for photos and scans |

## What it checks

| Area | Check |
|---|---|
| PDF metadata | Producer/Creator is a consumer editor (iLovePDF, Canva, Photoshop, Sejda…); modified after creation; dates in the future or out of order; metadata stripped |
| PDF structure | Incremental updates (multiple `%%EOF`); same font embedded as several subsets on one page (a typical sign of edited text); JavaScript, Launch actions or embedded files; encryption; digital signature present |
| Images | EXIF `Software` tag shows an editor; capture vs. modify time; **Error Level Analysis** (also run on JPEGs embedded in scanned PDFs) |
| Fields | GSTIN (checksum), PAN (structure), Aadhaar (Verhoeff checksum, stored masked), IFSC, emails, dates, amounts, invoice numbers; PAN vs. GSTIN cross-check |
| Duplicates | Exact file match (SHA-256) and identical text content in a different file |

Score: info = 0, low = 10, medium = 25, high = 40, capped at 100. **0–19 passed · 20–49 review · 50+ flagged.** The score is a heuristic to rank documents for review, not proof. A person should make the final call using Approve or Reject.

## OCR (optional)

Text-based PDFs work without extra software. To read **scanned PDFs and photos**, install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki (default path `C:\Program Files\Tesseract-OCR\`). The app finds it automatically, or you can set `TESSERACT_CMD`. The header badge shows whether OCR is available.

## Layout

```
app/main.py                  FastAPI routes + upload handling
app/db.py                    SQLite (data/documents.db)
app/analyzers/pdf_checks.py  PDF forensics
app/analyzers/image_checks.py EXIF + ELA
app/analyzers/fields.py      Identifier extraction/validation
app/analyzers/ocr.py         Optional Tesseract wrapper
static/                      Dashboard (HTML/CSS/JS)
data/                        Database and uploaded files (git-ignored)
```

## Security notes

- There is no login. The server listens only on `127.0.0.1`. Add authentication before you expose it to the network.
- Uploaded documents are stored unencrypted in `data/uploads/`. Delete documents from the dashboard when they are no longer needed.

## References

- [python-stdnum](https://github.com/arthurdejong/python-stdnum): Aadhaar, PAN and GSTIN validation (used as a library)
- [pypdf](https://github.com/py-pdf/pypdf): PDF parsing
- Didier Stevens, [pdf-parser / pdfid](https://blog.didierstevens.com/2015/02/18/) and ELA on PDF-embedded images: the approach behind the structure checks
- Error Level Analysis: Neal Krawetz's technique, implemented here with Pillow
