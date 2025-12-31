# EP Inventory Management System

## Project Overview

The EP Inventory Management System is a Python-based application designed to manage, track, and export inventory data using a structured SQL database. The project simulates a real-world inventory workflow commonly found in retail, logistics, and operational environments, where accurate data handling, validation, and reporting are critical.

This project demonstrates my ability to work with structured datasets, interact with SQL databases, apply data validation and cleaning logic, and prepare data for downstream analysis or reporting. While operational in nature, the architecture and data workflows directly align with analytics and business intelligence use cases.

---

## Key Features

* Create, read, update, and delete (CRUD) inventory records
* SQL-based data storage and retrieval
* Modular service-oriented architecture
* Inventory import and export functionality
* Data backup and recovery support
* Barcode lookup and validation

---

## Technologies Used

* **Python** – Core application logic and services
* **SQL** – Structured data storage and querying
* **SQLite-style database architecture** (via Python DB connection)
* **Modular service design** – Separation of database, business logic, and utilities

---

## Project Structure

```
EP_Inventory_Management/
├── db/
│   ├── config.py           # Database configuration
│   ├── connection.py      # Database connection handling
│   └── queries.py         # Centralized SQL queries
├── services/
│   ├── inventory_service.py  # Core inventory logic
│   ├── export_service.py     # Data export functionality
│   ├── backup_service.py     # Backup and recovery
│   └── barcode_service.py    # Barcode handling and validation
├── utils/
│   └── formatting.py      # Output formatting utilities
├── inventory_import.py    # Inventory import workflow
├── Inventory_Management_Fixed.py  # Main application entry point
├── requirements.txt
└── README.md
```

---

## Data & Analytics Relevance

Although this project focuses on inventory operations, it directly supports data analytics workflows:

* **SQL querying:** Structured queries for extracting, filtering, and validating data
* **Data quality checks:** Handling duplicates, missing values, and invalid entries
* **Data preparation:** Exporting clean datasets suitable for reporting or analysis
* **Scalable design:** Modular architecture that can support analytical extensions such as summary metrics, trend analysis, or BI dashboards

These same patterns are commonly used in analytics pipelines and reporting systems.

---

## Example Use Cases

* Identifying low-stock items using SQL filters
* Exporting inventory datasets for reporting or dashboarding
* Validating incoming inventory data before storage
* Maintaining historical inventory backups

---

## Future Enhancements

* Add aggregate SQL queries (e.g., stock trends, reorder frequency)
* Integrate basic analytics summaries
* Connect exported data to BI tools or dashboards
* Add logging and monitoring for data operations

---

## Author

**Zachary Maness**

This project was developed to demonstrate practical experience with Python, SQL, and data workflows relevant to junior data analyst and data scientist roles.


# Inventory Management (Tkinter + PostgreSQL)

Desktop inventory manager with barcode generation/printing, CSV/ProNest export, and backup/restore.

This single document contains all steps to set up and run the app on a new Windows PC (home). macOS/Linux are similar for Python; PostgreSQL SQL is the same.

---

## Prerequisites

- Python 3.11+ (with pip)
- PostgreSQL 13+ (local service running)
- Optional: Visual Studio 2022 for Git integration (use __Git > Clone Repository...__)

---

## 1) Clone the repository

- Visual Studio 2022: __Git > Clone Repository...__ and paste your repo URL
- Or command line: git clone https://github.com/<you>/<repo>.git cd <repo>


---

## 2) Create and activate a Python virtual environment, then install dependencies

-Windows (PowerShell): python -m venv .venv ..venv\Scripts\Activate.ps1

-If activation is blocked, run this in the same terminal, then activate again: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass ..venv\Scripts\Activate.ps1

-Install dependencies from requirements.txt: python -m pip install --upgrade pip python -m pip install -r requirements.txt


---

## 3) Configure the database connection

Edit db/config.py so it points to your local PostgreSQL: DB_CONFIG = { "dbname": "inventory_db", "user": "postgres", "password": "<your local postgres password>", "host": "localhost", "port": "5432", }


Optional (admin wipe password for the “WIPE DATABASE” button; default is "Zach"):
- Set an environment variable before launching if you want to override:
  - INVENTORY_WIPE_PASSWORD=<your password>

---

## 4) Create the database and schema

Create the database (once, in psql): CREATE DATABASE inventory_db;


Create the schema:
- Save the SQL below as db/schema.sql.
- Apply it:
  - Windows:
    ```
    psql -U postgres -d inventory_db -f db\schema.sql
    ```
  - macOS/Linux:
    ```
    psql -U postgres -d inventory_db -f db/schema.sql
    ```

Schema file (db/schema.sql): CREATE TABLE IF NOT EXISTS inventory ( id SERIAL PRIMARY KEY, barcode TEXT, shelf TEXT, thickness TEXT, metal_type TEXT, dimensions TEXT, location TEXT, quantity INTEGER NOT NULL DEFAULT 0, usable_scrap TEXT, date DATE, length NUMERIC(10,2), width NUMERIC(10,2) );
CREATE INDEX IF NOT EXISTS idx_inventory_barcode ON inventory(barcode); CREATE INDEX IF NOT EXISTS idx_inventory_shelf ON inventory(shelf); CREATE INDEX IF NOT EXISTS idx_inventory_metal_type ON inventory(metal_type);


Tip (Windows): If `psql` is not recognized, use the full path to psql.exe, e.g.: "C:\Program Files\PostgreSQL<version>\bin\psql.exe" -U postgres -d inventory_db -f db\schema.sql


---

## 5) Run the app

From the project root with the venv activated: python Inventory_Management_Fixed.py


---

## 6) Load or import data (optional)

- From another machine:
  - Use the “Backup DB” button to export CSV/XLSX, copy the file home, then use “Restore DB” to import.
- From a CSV:
  - Use “Import CSV” on the View tab and follow prompts.

---

## Features overview

- Add/Edit inventory items (barcode, shelf, thickness, metal_type, dimensions, location, quantity, sheet size, date)
- View tab: sort columns, filter by fields, numeric length/width ranges, toggle dimensions display format
- Export CSV and ProNest CSV
- Barcode generation:
  - Single printable label (PNG)
  - PDF sheets for multiple barcodes
- Backup/Restore to/from CSV/XLSX

Barcode notes:
- PNGs save next to the app and are ignored by Git (.gitignore includes `barcode_*.png`).
- PDF export requires ReportLab (included in requirements).

---

## Troubleshooting

- Cannot connect to DB:
  - Verify db/config.py host="localhost", correct user/password
  - Ensure PostgreSQL service is running (Services.msc)
  - Test:
    ```
    psql -U postgres -d inventory_db -c "SELECT 1;"
    ```
- “relation does not exist” / missing table:
  - Apply schema:
    ```
    psql -U postgres -d inventory_db -f db\schema.sql
    ```
- Date validation errors:
  - Use MM-DD-YYYY or YYYY-MM-DD in the UI
- Missing Python packages:
  - Re-run:
    ```
    python -m pip install -r requirements.txt
    ```
- PDF export complaining about reportlab:
  - Reinstall:
    ```
    python -m pip install --force-reinstall reportlab
    ```
- Barcode image not showing:
  - The app writes `barcode_<code>.png` in the working folder. Verify write permissions and that Pillow is installed.

---

## Quick reference (Windows)

Activate venv
..venv\Scripts\Activate.ps1
Install deps
python -m pip install -r requirements.txt
Create DB
psql -U postgres -d postgres -c "CREATE DATABASE inventory_db;"
Apply schema
psql -U postgres -d inventory_db -f db\schema.sql
Run app
python Inventory_Management_Fixed.py


