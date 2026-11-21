# Paediatric Oncology Multidisciplinary Team (Pead MDT) System

A modern, high-density, compact clinical web application migrated from Microsoft Access to **Python & Django**.

Built specifically for Paediatric Oncology MDT case discussions, clinical staging, multimodality diagnostics (Hematology, Imaging, Pathology, Molecular), consensus documentation, and hospital reporting (Kidwai Memorial Institute of Oncology format).

---

## 1. Quick Start

### Start Server
Double-click `run_server.bat` or run in terminal:
```bash
python manage.py runserver 127.0.0.1:8000
```
Open **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)** in any browser.

### Default User Credentials
All users from the MS Access database (`tblUsers`) have been imported:
- **Admin Users**: `admin` or `n3v` (Password: `admin123`)
- **Clinical User**: `pgtest` (Password: `admin123`)

---

## 2. Key Features & Improvements Added

1. **Simple, Compact Clinical UI**:
   - Designed for high information density without unnecessary padding.
   - Quick navigation, fast switching, hospital ward / meeting room friendly.
2. **Paediatric Age Engine**:
   - Accurately formats paediatric ages across developmental thresholds:
     - `< 30 days`: days
     - `< 1 year`: months
     - `1 to 4 years`: years and months
     - `5+ years`: years
3. **Live Anthropometry & BSA / BMI Calculations**:
   - Auto-calculates Body Surface Area (BSA in $m^2$) using the Mosteller formula:
     $$\text{BSA} = \sqrt{\frac{\text{Height (cm)} \times \text{Weight (kg)}}{3600}}$$
   - Auto-calculates BMI ($kg/m^2$) live as values are typed.
4. **MDT Sequential ID Generator**:
   - Concurrency-safe atomic generation (`PED20260000008`...) with zero race conditions.
5. **Two-Phase Clinical & MDT Approval Workflow**:
   - Draft $\rightarrow$ Approved with automatic consensus stub generation and locking.
6. **Live "Big Screen" MDT Meeting Presentation Mode**:
   - Optimized high-contrast projector/screen layout for weekly multidisciplinary meetings.
   - Features real-time consensus scribe input.
7. **Document / Scan Attachments**:
   - Optional file upload (PDFs, DICOM/radiology cuts, pathology reports) on all 4 investigation categories.
8. **Formal Printable Reports**:
   - Clinical Summary Sheet (`report_clinical_summary`)
   - Formal Full MDT Report with panel signatures (`report_mdt_full`)
9. **Automated Migration Command**:
   - Re-run at any time if base Access database changes:
     ```bash
     python manage.py import_access_data
     ```
10. **Automated Test Suite**:
    - Run all unit and integration tests:
      ```bash
      python manage.py test
      ```

---

## 3. Directory Layout

```
AG project - Pead MDT/
├── config/                  # Django project settings & URL routing
├── mdt/                     # Core clinical app
│   ├── models.py            # Patient, ClinicalDetails, MDTConsensus, 4 Investigations
│   ├── forms.py             # Crisp, compact forms & widgets
│   ├── views.py             # Dashboard, Search, Clinical, MDT, Live Screen, Reports
│   ├── services.py          # BSA/BMI, Age formatting, MDTID sequence, Audit logging
│   ├── tests.py             # Automated unit & integration tests
│   └── management/commands/ # import_access_data command
├── templates/               # Compact HTML templates
│   ├── base.html
│   ├── registration/login.html
│   └── mdt/                 # Dashboard, Patient Search, Forms, Live Screen, Reports
├── static/                  # CSS & JS
│   ├── css/compact_clinical.css
│   └── js/compact_clinical.js
├── media/                   # Uploaded investigation reports & images
├── manage.py
├── run_server.bat
└── db.sqlite3               # Pre-populated with 100% of migrated Access data
```
