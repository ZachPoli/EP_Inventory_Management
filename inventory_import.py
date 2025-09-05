import pandas as pd
import re  # <- add near top if not already imported
from tkinter import filedialog, messagebox
from db.queries import fetch_all, execute, fetch_one
from services.inventory_service import normalize_date_input
from services.barcode_service import (
    generate_scannable_barcode,
    derive_compact_barcode_value,
    generate_compact_code
)

DEBUG_IMPORT = False  # set to False after fixing

def run_import(refresh_table_fn, refresh_comboboxes_fn, load_barcode_items_fn, current_filters):
    """
    Performs inventory import. UI callbacks (refresh_table, etc.) are passed in
    to avoid circular imports.
    """
    filename = filedialog.askopenfilename(
        title="Select Inventory CSV/XLSX",
        filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx"), ("All files", "*.*")]
    )
    if not filename:
        return

    # Load file
    try:
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(filename)
        else:
            df = pd.read_excel(filename)
    except Exception as e:
        messagebox.showerror("Import Error", f"Failed to read file:\n{e}")
        return

    if df.empty:
        messagebox.showwarning("Import", "File has no rows.")
        return

    # Column normalization
    col_map = {
        "barcode": "barcode",
        "shelf": "shelf",
        "thickness": "thickness",
        "metal_type": "metal_type",
        "metal": "metal_type",
        "material": "metal_type",
        "dimensions": "dimensions",
        "dimension": "dimensions",
        "location": "location",
        "qty": "quantity",
        "quantity": "quantity",
        "usable_scrap": "usable_scrap",
        "sheet size": "usable_scrap",
        "sheet_size": "usable_scrap",
        "date": "date",
        "date_added": "date"
    }
    renamed = {}
    for c in df.columns:
        k = str(c).strip().lower()
        if k in col_map:
            renamed[c] = col_map[k]
    df = df.rename(columns=renamed)
    canonical_cols = set(col_map.values())
    if not any(c in canonical_cols for c in df.columns):
        messagebox.showerror("Import Error", "No recognizable inventory columns found.")
        return

    # Duplicate behavior
    mode = messagebox.askquestion(
        "Duplicate Strategy",
        "If imported row matches existing (shelf+thickness+metal_type+dimensions+location):\n"
        "Yes = Update existing row's quantity to imported value\n"
        "No  = Skip duplicates"
    )
    duplicate_update = (mode == "yes")

    gen_barcodes = messagebox.askyesno(
        "Generate Missing Barcodes",
        "Generate barcode images for rows with blank/missing barcodes?"
    )

    added = updated = skipped = errors = barcode_generated = 0

    existing_rows = fetch_all("""
        SELECT shelf, thickness, metal_type, dimensions, location
        FROM inventory
    """)
    existing_set = set(tuple("" if v is None else str(v) for v in row) for row in existing_rows)

    if DEBUG_IMPORT:
        print(f"[IMPORT] Loaded rows: {len(df)}. Columns: {list(df.columns)}")
        
    # Replace the loop body with added debug prints (only added lines start with # DEBUG):
    for idx, r in df.iterrows():
        if DEBUG_IMPORT and idx < 5:  # sample first few
            print(f"[IMPORT] Row {idx} raw: {r.to_dict()}")
        def gv(col):
            if col not in r: return None
            val = r[col]
            if isinstance(val, float) and pd.isna(val):
                return None
            return str(val).strip()

        shelf = gv("shelf")
        thickness = gv("thickness")
        metal_type = gv("metal_type")
        dimensions = gv("dimensions")
        location = gv("location")
        quantity_raw = gv("quantity")
        usable_scrap = gv("usable_scrap")
        date_raw = gv("date")
        barcode_val = gv("barcode")

        if not any([shelf, thickness, metal_type, dimensions, location]):
            if DEBUG_IMPORT:
                print(f"[IMPORT] Skipping row {idx} (no key fields)")
            continue

        # Robust quantity parsing
        def parse_quantity(raw):
            if raw in (None, "", "NaN"):
                return 0
            if isinstance(raw, (int, float)) and not pd.isna(raw):
                return int(raw)
            s = str(raw).strip()
            if s == "":
                return 0
            # Accept forms like "10.0", "7.", "12.3" (will floor)
            if re.fullmatch(r"\d+\.\d+", s):
                return int(float(s))
            if re.fullmatch(r"\d+\.", s):
                return int(float(s))
            if s.isdigit():
                return int(s)
            # Last chance: try float then int
            try:
                return int(float(s))
            except Exception:
                raise ValueError(f"Unrecognized quantity '{raw}'")

        try:
            quantity_val = parse_quantity(quantity_raw)
        except ValueError:
            errors += 1
            if DEBUG_IMPORT:
                print(f"[IMPORT][ERROR] Bad quantity at row {idx}: {quantity_raw} (type={type(quantity_raw)})")
            continue

        try:
            date_iso = normalize_date_input(date_raw) if date_raw else None
        except ValueError:
            if DEBUG_IMPORT:
                print(f"[IMPORT][WARN] Bad date at row {idx}: {date_raw} (left as None)")
            date_iso = None

        key = (shelf or "", thickness or "", metal_type or "", dimensions or "", location or "")
        is_duplicate = key in existing_set

        if is_duplicate:
            if duplicate_update:
                try:
                    execute("""
                        UPDATE inventory
                        SET barcode=%s, usable_scrap=%s, quantity=%s, date=%s
                        WHERE shelf=%s AND thickness=%s AND metal_type=%s AND dimensions=%s AND location=%s
                    """, (
                        barcode_val, usable_scrap, quantity_val, date_iso,
                        shelf, thickness, metal_type, dimensions, location
                    ))
                    updated += 1
                    if DEBUG_IMPORT:
                        print(f"[IMPORT] Updated duplicate row {idx}: {key}")
                except Exception as ex:
                    errors += 1
                    if DEBUG_IMPORT:
                        print(f"[IMPORT][ERROR] Update failed row {idx}: {ex}")
                # Continue after update/skip
            else:
                skipped += 1
                if DEBUG_IMPORT:
                    print(f"[IMPORT] Skipped duplicate row {idx}: {key}")
            continue
        else:
            try:
                execute("""
                    INSERT INTO inventory
                        (barcode, shelf, thickness, metal_type, dimensions,
                         location, quantity, usable_scrap, date)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    barcode_val, shelf, thickness, metal_type, dimensions,
                    location, quantity_val, usable_scrap, date_iso
                ))
                added += 1
                existing_set.add(key)
                if DEBUG_IMPORT:
                    print(f"[IMPORT] Inserted row {idx}: {key}")
            except Exception as ex:
                errors += 1
                if DEBUG_IMPORT:
                    print(f"[IMPORT][ERROR] Insert failed row {idx}: {ex}")
                continue

        if gen_barcodes and (not barcode_val or not barcode_val.strip()):
            try:
                derived = derive_compact_barcode_value(thickness, metal_type, dimensions)
                if not derived:
                    base = f"{(thickness or '')}-{(metal_type or '')}-{(dimensions or '')}-{idx}"
                    derived = generate_compact_code(base, length=8)
                test_code = derived
                suffix_i = 0
                while fetch_one("SELECT 1 FROM inventory WHERE barcode=%s", (test_code,)):
                    suffix_i += 1
                    test_code = f"{derived}{suffix_i}"
                execute("""
                    UPDATE inventory SET barcode=%s WHERE shelf=%s AND thickness=%s
                      AND metal_type=%s AND dimensions=%s AND location=%s
                """, (test_code, shelf, thickness, metal_type, dimensions, location))
                try:
                    generate_scannable_barcode(test_code, overwrite=True)
                except Exception:
                    pass
                barcode_generated += 1
                if DEBUG_IMPORT:
                    print(f"[IMPORT] Generated barcode {test_code} for row {idx}")
            except Exception as ex:
                if DEBUG_IMPORT:
                    print(f"[IMPORT][WARN] Barcode gen failed row {idx}: {ex}")
                pass

    # Callbacks
    refresh_table_fn(current_filters)
    refresh_comboboxes_fn()
    load_barcode_items_fn()

    messagebox.showinfo(
        "Import Complete",
        f"Added: {added}\nUpdated: {updated}\nSkipped: {skipped}\n"
        f"Errors: {errors}\nBarcodes generated: {barcode_generated}"
    )