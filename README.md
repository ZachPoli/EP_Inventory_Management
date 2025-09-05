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

Windows (PowerShell): python -m venv .venv ..venv\Scripts\Activate.ps1
