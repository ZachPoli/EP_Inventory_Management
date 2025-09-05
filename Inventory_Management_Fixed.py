import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import tkinter.simpledialog
import pandas as pd
from datetime import datetime
from PIL import Image, ImageTk
import os

from utils.formatting import inches_to_feet_inches
from db.queries import fetch_all, execute
from db.connection import get_cursor
from services.barcode_service import (
    generate_barcode_image,
    generate_all_barcodes_service,          # still imported (legacy function) – remove if no longer used anywhere
    get_barcode_items,
    build_barcode_filename,
    generate_selected_barcodes_service,
    generate_scannable_barcode,
    get_or_create_barcode_image,
    generate_compact_barcodes_service,      # still needed for rebuild / migrate buttons on Barcodes tab
    export_barcodes_to_pdf,
    preview_compact_barcode_changes,
    test_barcode_naming_cases
)
from services.export_service import (
    fetch_inventory_rows_for_csv,
    build_csv_dataframe,
    export_inventory_pronest_dataframe
)

from inventory_import import run_import
# --- UPDATE import from inventory_service to include new helpers ---
from services.inventory_service import (
    add_inventory_item, update_inventory_item, delete_inventory_item,
    adjust_quantity, extract_dimensions, parse_dimensions,
    get_quantity_for_barcode, set_quantity_for_barcode, normalize_date_input,
    fetch_item_by_barcode, update_inventory_item_by_id, delete_inventory_item_by_id
)

# --- imports (add fetch_one) ---
from db.queries import fetch_all, execute, fetch_one
from services.backup_service import backup_inventory, restore_inventory

# ------------------------------------------------------------------
# Global UI state
# ------------------------------------------------------------------
current_filters = {}
filter_comboboxes = {}
show_dimensions_in_feet = False
sort_column = None
sort_reverse = False
# After global UI state variables:
ADMIN_WIPE_PASSWORD = os.environ.get("INVENTORY_WIPE_PASSWORD", "Zach")

# ------------------------------------------------------------------
# Sorting / data helpers
# ------------------------------------------------------------------
def treeview_sort_column(tv, col, reverse):
    global sort_column, sort_reverse
    sort_column = col
    sort_reverse = reverse
    data_list = [(tv.set(k, col), k) for k in tv.get_children("")]
    try:
        if col == "quantity":
            data_list.sort(key=lambda x: int(x[0]), reverse=reverse)
        elif col == "thickness":
            data_list.sort(key=lambda x: float(x[0]) if x[0].replace('.', '', 1).isdigit()
                           else x[0].lower(), reverse=reverse)
        else:
            data_list.sort(key=lambda x: x[0].lower(), reverse=reverse)
    except (ValueError, TypeError):
        data_list.sort(reverse=reverse)
    for idx, (_, k) in enumerate(data_list):
        tv.move(k, "", idx)
    tv.heading(col, command=lambda: treeview_sort_column(tv, col, not reverse))
    for c in tv['columns']:
        label = "Sheet size" if c == "usable_scrap" else c.capitalize()
        if c == col:
            tv.heading(c, text=f"{label} {'▼' if reverse else '▲'}")
        else:
            tv.heading(c, text=label)

# Mapping helpers for service-layer expectations
def ui_row_to_service_tuple(row_vals):
    return (
        row_vals[1],  # shelf
        row_vals[2],  # thickness
        row_vals[3],  # metal_type
        row_vals[4],  # dimensions
        row_vals[5],  # location
        row_vals[6],  # quantity
        row_vals[7],  # usable_scrap
        row_vals[8]   # date
    )

def ui_row_to_adjust_tuple(row_vals):
    return (
        row_vals[1],  # shelf
        row_vals[2],  # thickness
        row_vals[3],  # metal_type
        row_vals[4],  # dimensions
        row_vals[5],  # location
    )

def get_distinct_values(column):
    try:
        rows = fetch_all(f"SELECT DISTINCT {column} FROM inventory ORDER BY {column}")
        return [r[0] for r in rows if r[0] is not None]
    except Exception:
        return []

def refresh_comboboxes():
    for col, cb in entry_comboboxes.items():
        if isinstance(cb, ttk.Combobox):
            cb['values'] = get_distinct_values(col)
    for col, cb in filter_comboboxes.items():
        if isinstance(cb, ttk.Combobox):
            cb['values'] = [''] + get_distinct_values(col)

def get_field_values():
    return {
        "barcode": entry_comboboxes["barcode"].get(),
        "shelf": entry_comboboxes["shelf"].get(),
        "thickness": entry_comboboxes["thickness"].get(),
        "metal_type": entry_comboboxes["metal_type"].get(),
        "dimensions": entry_comboboxes["dimensions"].get(),
        "location": entry_comboboxes["location"].get(),
        "quantity": entry_comboboxes["quantity"].get(),
        "usable_scrap": entry_comboboxes["usable_scrap"].get(),
        "date": entry_comboboxes["date"].get()
    }

# ------------------------------------------------------------------
# Inventory CRUD
# ------------------------------------------------------------------
def extract_dimensions_from_database():
    try:
        updated = extract_dimensions()
        messagebox.showinfo("Success", f"Dimension data updated for {updated} record(s)")
    except Exception as e:
        messagebox.showerror("Error", f"Could not extract dimensions: {str(e)}")

def update_entry():
    fields = get_field_values()
    try:
        int(fields["quantity"])
    except ValueError:
        messagebox.showerror("Error", "Quantity must be an integer.")
        return
    try:
        if fields.get("date"):
            normalize_date_input(fields["date"])
    except ValueError as ve:
        messagebox.showerror("Invalid Date", str(ve))
        return
    try:
        affected = update_inventory_item(fields)
        messagebox.showinfo("Success", "Entry updated!" if affected else "No matching entry found.")
        refresh_table(current_filters)
        refresh_comboboxes()
    except Exception as e:
        messagebox.showerror("Error", str(e))

def add_entry():
    fields = get_field_values()
    try:
        int(fields["quantity"])
    except ValueError:
        messagebox.showerror("Error", "Quantity must be an integer.")
        return
    try:
        if fields.get("date"):
            normalize_date_input(fields["date"])
    except ValueError as ve:
        messagebox.showerror("Invalid Date", str(ve))
        return
    try:
        add_inventory_item(fields)
        messagebox.showinfo("Success", "New entry added!")
        refresh_table(current_filters)
        refresh_comboboxes()
    except Exception as e:
        messagebox.showerror("Error", str(e))

# ------------------------------------------------------------------
# Filters
# ------------------------------------------------------------------
def setup_filter_section():
    global filter_comboboxes, length_min_entry, length_max_entry, width_min_entry, width_max_entry, current_filters
    current_filters = {}
    for w in filter_frame.winfo_children():
        w.destroy()
    labels = [
        ("Shelf:", "shelf"), ("Thickness:", "thickness"), ("Metal Type:", "metal_type"),
        ("Dimensions:", "dimensions"), ("Location:", "location"),
        ("Sheet size:", "usable_scrap"), ("Date:", "date")
    ]
    filter_comboboxes = {}
    row_frame = None
    for idx, (lbl, col) in enumerate(labels):
        if idx % 3 == 0:
            row_frame = tk.Frame(filter_frame)
            row_frame.pack(fill="x", pady=2)
        tk.Label(row_frame, text=f"Filter {lbl}").pack(side="left", padx=5)
        cb = ttk.Combobox(row_frame, state="readonly", width=15)
        cb.pack(side="left", padx=5)
        filter_comboboxes[col] = cb
    dim_frame = tk.Frame(filter_frame); dim_frame.pack(fill="x", pady=5)
    lf = tk.Frame(dim_frame); lf.pack(side="left", padx=20)
    tk.Label(lf, text="Length (in) Range:").pack(anchor="w")
    lf_inner = tk.Frame(lf); lf_inner.pack(fill="x")
    tk.Label(lf_inner, text="Min:").pack(side="left")
    length_min_entry = tk.Entry(lf_inner, width=8); length_min_entry.pack(side="left", padx=2)
    tk.Label(lf_inner, text="Max:").pack(side="left", padx=(10, 0))
    length_max_entry = tk.Entry(lf_inner, width=8); length_max_entry.pack(side="left", padx=2)
    wf = tk.Frame(dim_frame); wf.pack(side="left", padx=40)
    tk.Label(wf, text="Width (in) Range:").pack(anchor="w")
    wf_inner = tk.Frame(wf); wf_inner.pack(fill="x")
    tk.Label(wf_inner, text="Min:").pack(side="left")
    width_min_entry = tk.Entry(wf_inner, width=8); width_min_entry.pack(side="left", padx=2)
    tk.Label(wf_inner, text="Max:").pack(side="left", padx=(10, 0))
    width_max_entry = tk.Entry(wf_inner, width=8); width_max_entry.pack(side="left", padx=2)
    tk.Button(filter_frame, text="Apply Filter", command=apply_filter).pack(pady=5)
    tk.Button(filter_frame, text="Extract Dimensions", command=extract_dimensions_from_database).pack(pady=5)

def apply_filter():
    global current_filters
    current_filters = {c: cb.get() for c, cb in filter_comboboxes.items() if cb.get()}
    dimension_filters = {}
    try:
        if length_min_entry.get(): dimension_filters["length_min"] = float(length_min_entry.get())
        if length_max_entry.get(): dimension_filters["length_max"] = float(length_max_entry.get())
        if width_min_entry.get():  dimension_filters["width_min"] = float(width_min_entry.get())
        if width_max_entry.get():  dimension_filters["width_max"] = float(width_max_entry.get())
    except ValueError:
        messagebox.showerror("Error", "Dimension range values must be numeric.")
        return
    refresh_table(current_filters, dimension_filters)

# ------------------------------------------------------------------
# Table refresh
# ------------------------------------------------------------------
def build_inventory_query(filters=None, dimension_filters=None):
    base = """SELECT barcode, shelf, thickness, metal_type, dimensions,
                     location, quantity, usable_scrap, date, length, width
              FROM inventory"""
    clauses = []
    params = []
    if filters:
        for k, v in filters.items():
            clauses.append(f"{k} = %s")
            params.append(v)
    if dimension_filters:
        mapping = {
            "length_min": "length >= %s",
            "length_max": "length <= %s",
            "width_min": "width >= %s",
            "width_max": "width <= %s"
        }
        for key, clause in mapping.items():
            if key in dimension_filters:
                clauses.append(clause)
                params.append(dimension_filters[key])
    if clauses:
        base += " WHERE " + " AND ".join(clauses)
    return base, params

def refresh_table(filters=None, dimension_filters=None):
    global show_dimensions_in_feet, sort_column, sort_reverse
    for row_id in tree.get_children():
        tree.delete(row_id)
    try:
        query, params = build_inventory_query(filters, dimension_filters)
        rows = fetch_all(query, params)
        for row in rows:
            row_list = list(row)
            if show_dimensions_in_feet:
                length_val = row[9]; width_val = row[10]
                if (length_val is None or width_val is None) and row[4]:
                    parsed = parse_dimensions(row[4])
                    if parsed:
                        length_val, width_val = parsed
                if length_val and width_val:
                    length_str = inches_to_feet_inches(length_val)
                    width_str = inches_to_feet_inches(width_val)
                    original = row_list[4] or ""
                    row_list[4] = f"{original} ({length_str} x {width_str})"
            tree.insert("", "end", values=row_list[:9])
        if sort_column:
            treeview_sort_column(tree, sort_column, sort_reverse)
    except Exception as e:
        messagebox.showerror("Error", str(e))

# ------------------------------------------------------------------
# Row operations
# ------------------------------------------------------------------
def delete_entry():
    sel = tree.selection()
    if not sel:
        messagebox.showwarning("No selection", "Select a row to delete.")
        return
    ui_vals = tree.item(sel[0], "values")
    if not messagebox.askyesno("Confirm Delete", "Delete this entry?"):
        return
    try:
        svc_tuple = ui_row_to_service_tuple(ui_vals)
        affected = delete_inventory_item(svc_tuple)
        if affected == 0:
            messagebox.showwarning("Not Found", "No matching entry removed.")
        else:
            messagebox.showinfo("Success", "Entry deleted.")
        refresh_table(current_filters)
        refresh_comboboxes()
    except ValueError as ve:
        messagebox.showerror("Error", f"Quantity parse error: {ve}")
    except Exception as e:
        messagebox.showerror("Error", str(e))

def increment_quantity():
    sel = tree.selection()
    if not sel:
        messagebox.showwarning("No selection", "Select a row.")
        return
    ui_vals = tree.item(sel[0], "values")
    amt = tk.simpledialog.askinteger("Add Quantity", "Amount to add:", minvalue=1)
    if amt is None:
        return
    try:
        base_tuple = ui_row_to_adjust_tuple(ui_vals)
        adjust_quantity(base_tuple, amt)
        messagebox.showinfo("Success", f"Added {amt}.")
        refresh_table(current_filters)
    except Exception as e:
        messagebox.showerror("Error", str(e))

def decrement_quantity():
    sel = tree.selection()
    if not sel:
        messagebox.showwarning("No selection", "Select a row.")
        return
    ui_vals = tree.item(sel[0], "values")
    amt = tk.simpledialog.askinteger("Remove Quantity", "Amount to remove:", minvalue=1)
    if amt is None:
        return
    try:
        base_tuple = ui_row_to_adjust_tuple(ui_vals)
        adjust_quantity(base_tuple, -amt)
        messagebox.showinfo("Success", f"Removed {amt}.")
        refresh_table(current_filters)
    except Exception as e:
        messagebox.showerror("Error", str(e))

def fix_field():
    sel = tree.selection()
    if not sel:
        messagebox.showwarning("No selection", "Select an entry.")
        return
    ui_vals = tree.item(sel[0], "values")
    dialog = tk.Toplevel(root); dialog.title("Fix Field")
    tk.Label(dialog, text="Field:").grid(row=0, column=0, sticky="e")
    field_cb = ttk.Combobox(dialog, values=columns, state="readonly")
    field_cb.grid(row=0, column=1, padx=4, pady=4)
    tk.Label(dialog, text="New Value:").grid(row=1, column=0, sticky="e")
    new_value_entry = tk.Entry(dialog)
    new_value_entry.grid(row=1, column=1, padx=4, pady=4)

    def apply_fix():
        field = field_cb.get()
        new_val = new_value_entry.get()
        if not field or new_val is None:
            messagebox.showwarning("Missing", "Select field and provide a new value.")
            return
        shelf = ui_vals[1]; thickness = ui_vals[2]; metal_type = ui_vals[3]
        dimensions = ui_vals[4]; location = ui_vals[5]
        quantity = ui_vals[6]; usable_scrap = ui_vals[7]
        date_val = ui_vals[8] if ui_vals[8] else None
        try:
            quantity_int = int(quantity)
        except ValueError:
            messagebox.showerror("Error", f"Stored quantity not numeric: {quantity}")
            return
        sql = f"""
            UPDATE inventory
            SET {field} = %s
            WHERE shelf = %s AND thickness = %s AND metal_type = %s AND dimensions = %s
              AND location = %s AND quantity = %s AND usable_scrap = %s AND date = %s
        """
        params = (new_val, shelf, thickness, metal_type, dimensions,
                  location, quantity_int, usable_scrap, date_val)
        try:
            execute(sql, params)
            messagebox.showinfo("Success", "Field updated.")
            dialog.destroy()
            refresh_table(current_filters)
            refresh_comboboxes()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    tk.Button(dialog, text="Apply", command=apply_fix).grid(row=2, column=0, columnspan=2, pady=6)

# ------------------------------------------------------------------
# Export / backup
# ------------------------------------------------------------------
def export_to_csv():
    try:
        if tree.get_children():
            data = [tree.item(iid)['values'] for iid in tree.get_children()]
            df = pd.DataFrame(data, columns=columns)
        else:
            rows = fetch_inventory_rows_for_csv()
            df = build_csv_dataframe(rows)
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx"), ("All files", "*.*")],
            title="Save Inventory Data"
        )
        if not filename:
            return
        if filename.endswith(".xlsx"):
            df.to_excel(filename, index=False)
        else:
            df.to_csv(filename, index=False, encoding="utf-8-sig")
        messagebox.showinfo("Success", f"Exported: {filename}")
    except Exception as e:
        messagebox.showerror("Export Error", str(e))

def export_to_pronest():
    try:
        extract_dimensions_from_database()
        visible = []
        if tree.get_children():
            for iid in tree.get_children():
                v = tree.item(iid, 'values')
                visible.append({
                    'shelf': v[1],
                    'thickness': v[2],
                    'metal_type': v[3],
                    'dimensions': v[4]
                })
        df = export_inventory_pronest_dataframe(visible if visible else None)
        if df is None or df.empty:
            messagebox.showwarning("No Data", "Nothing to export.")
            return
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx"), ("All files", "*.*")],
            title="Export ProNest CSV"
        )
        if not filename:
            return
        if filename.endswith(".xlsx"):
            df.to_excel(filename, index=False)
        else:
            df.to_csv(filename, index=False, encoding="utf-8-sig")
        messagebox.showinfo("Success", f"ProNest export: {filename}")
    except Exception as e:
        messagebox.showerror("Export Error", str(e))

def backup_database():
    backup_inventory()

def import_csv_inventory():
    try:
        run_import(refresh_table, refresh_comboboxes, load_barcode_items, current_filters)
    except Exception as e:
        import traceback, io
        buf = io.StringIO()
        traceback.print_exc(file=buf)
        messagebox.showerror("Import Crash", f"{e}\n\nTraceback:\n{buf.getvalue()}")

def restore_from_backup():
    restore_inventory(refresh_table, refresh_comboboxes)

def wipe_database():
    if not messagebox.askyesno("WARNING", "Delete ALL inventory data?"):
        return
    confirm = tk.simpledialog.askstring("Confirm", "Type DELETE to continue:")
    if confirm != "DELETE":
        messagebox.showinfo("Cancelled", "Wipe cancelled.")
        return
    pwd = tk.simpledialog.askstring("Authentication", "Enter wipe password:", show="*")
    if pwd != ADMIN_WIPE_PASSWORD:
        messagebox.showerror("Denied", "Incorrect password.")
        return
    if not messagebox.askyesno("FINAL CONFIRM", "Really delete all records?"):
        return
    try:
        deleted = execute("DELETE FROM inventory")
        messagebox.showinfo("Success", f"Database wiped ({deleted} rows).")
        refresh_table()
        refresh_comboboxes()
    except Exception as e:
        messagebox.showerror("Error", str(e))

def toggle_dimension_format():
    global show_dimensions_in_feet
    show_dimensions_in_feet = not show_dimensions_in_feet
    dimension_format_btn.config(
        text=f"Show Dimensions in {'Inches' if show_dimensions_in_feet else 'Feet/Inches'}"
    )
    refresh_table(current_filters)

# ------------------------------------------------------------------
# Barcode (single item)
# ------------------------------------------------------------------
def generate_and_show_barcode():
    bc = entry_comboboxes["barcode"].get().strip()
    if not bc:
        messagebox.showwarning("No Barcode", "Enter a barcode first.")
        return
    try:
        path = generate_scannable_barcode(bc, overwrite=True)
        show_barcode_image()
        messagebox.showinfo("Success", f"Generated: {os.path.basename(path)}")
    except Exception as e:
        messagebox.showerror("Error", str(e))

def show_barcode_image():
    bc = entry_comboboxes["barcode"].get().strip()
    if not bc:
        barcode_image_label.config(image='', text='No barcode')
        return
    try:
        path = get_or_create_barcode_image(bc)
        img = Image.open(path)
        max_w = 400
        if img.width > max_w:
            scale = max_w / img.width
            img = img.resize((max_w, int(img.height * scale)), Image.NEAREST)
        tk_img = ImageTk.PhotoImage(img)
        barcode_image_label.img_tk = tk_img
        barcode_image_label.config(image=tk_img, text='')
    except Exception:
        barcode_image_label.config(image='', text='Barcode image not found')

def show_barcode_for_scan():
    bc = entry_comboboxes["barcode"].get().strip()
    if not bc:
        messagebox.showwarning("No Barcode", "Enter a barcode first.")
        return
    try:
        path = get_or_create_barcode_image(bc, ensure_scannable=True)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to generate barcode: {e}")
        return
    popup = tk.Toplevel(root); popup.title(f"Scan: {bc}")
    try:
        img = Image.open(path)
        tk_img = ImageTk.PhotoImage(img)
        lbl = tk.Label(popup, image=tk_img); lbl.img_tk = tk_img
        lbl.pack(padx=20, pady=20)
        tk.Button(popup, text="Print",
                  command=lambda: os.startfile(path) if os.name == 'nt'
                  else messagebox.showinfo("Print", f"File saved: {path}")
                  ).pack(pady=8)
    except Exception as e:
        tk.Label(popup, text=f"Error displaying barcode: {e}").pack(padx=20, pady=20)

# (Legacy / migration / rebuild functions retained for Barcodes tab – remove if not needed there)
def migrate_compact_barcodes():
    if not messagebox.askyesno("Confirm", "Migrate all barcodes to compact format?"):
        return
    try:
        assigned, migrated, total = generate_compact_barcodes_service(
            migrate_legacy=True, regenerate_images=True
        )
        refresh_table(current_filters)
        load_barcode_items()
        messagebox.showinfo("Migration Complete",
                            f"New codes: {assigned}\nMigrated legacy: {migrated}\nTotal rows: {total}")
    except Exception as e:
        messagebox.showerror("Migration Error", str(e))

def regenerate_barcode_images():
    try:
        generate_compact_barcodes_service(migrate_legacy=False, regenerate_images=True)
        refresh_table(current_filters)
        load_barcode_items()
        messagebox.showinfo("Success", "Barcode images regenerated.")
    except Exception as e:
        messagebox.showerror("Error", str(e))

def generate_all_barcodes():
    try:
        new_count, total = generate_all_barcodes_service()
        refresh_table(current_filters)
        load_barcode_items()
        messagebox.showinfo("Done",
                            f"New legacy barcodes: {new_count}\nTotal items: {total}")
    except Exception as e:
        messagebox.showerror("Error", str(e))

def preview_barcode_renaming():
    try:
        rows = preview_compact_barcode_changes(force_rebuild_all=True, migrate_legacy=True, sample=25)
        if not rows:
            messagebox.showinfo("Preview", "No rows would change.")
            return
        popup = tk.Toplevel(root)
        popup.title("Barcode Renaming Preview (first 25)")
        txt = tk.Text(popup, width=80, height=min(30, len(rows)+2))
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", "ID | Old -> New\n" + "-"*40 + "\n")
        for rec_id, old, new in rows:
            txt.insert("end", f"{rec_id} | {(old or '(None)')} -> {new}\n")
        txt.config(state="disabled")
    except Exception as e:
        messagebox.showerror("Preview Error", str(e))

def force_rebuild_all_barcodes():
    if not messagebox.askyesno(
        "Confirm Force Rebuild",
        "This will overwrite ALL existing barcodes with new naming rules.\nHave you backed up?"
    ):
        return
    if not messagebox.askyesno("Final Confirmation", "Proceed with FULL barcode rebuild?"):
        return
    try:
        assigned, migrated, rewritten, total = generate_compact_barcodes_service(
            migrate_legacy=True, regenerate_images=True, force_rebuild_all=True, dry_run=False
        )
        refresh_table(current_filters)
        load_barcode_items()
        messagebox.showinfo(
            "Rebuild Complete",
            f"New (empty before): {assigned}\nReplaced existing: {migrated}\n"
            f"Total rewritten: {rewritten}\nRows scanned: {total}"
        )
    except Exception as e:
        messagebox.showerror("Rebuild Error", str(e))

# ------------------------------------------------------------------
# Barcode printing / sheets
# ------------------------------------------------------------------
def save_printable_barcode():
    bc = entry_comboboxes["barcode"].get().strip()
    if not bc:
        messagebox.showwarning("No Barcode", "Enter a barcode first.")
        return
    filename = filedialog.asksaveasfilename(
        defaultextension=".png",
        filetypes=[("PNG files", "*.png")],
        title="Save Printable Barcode"
    )
    if not filename:
        return
    try:
        from services.barcode_service import save_single_printable_label
        save_single_printable_label(
            bc, filename, width_in=1.8, max_height_in=1.0, dpi=300,
            profile="SAMPLE", force_compact=False
        )
        messagebox.showinfo("Success", f"Saved: {filename}")
    except Exception as e:
        messagebox.showerror("Error", str(e))

def save_barcode_sheet():
    codes = []
    for iid in tree.get_children():
        val = tree.item(iid, "values")[0]
        if val and val not in codes:
            codes.append(val)
    if not codes:
        messagebox.showwarning("No Data", "No barcodes visible.")
        return
    filename = filedialog.asksaveasfilename(
        defaultextension=".pdf",
        filetypes=[("PDF files", "*.pdf")],
        title="Save All Visible Barcodes (PDF)"
    )
    if not filename:
        return
    try:
        from services.barcode_service import generate_barcode_sheet_pdf
        generate_barcode_sheet_pdf(
            codes, filename, labels_per_row=4,
            label_width_in=1.8, label_height_in=1.0,
            margin_in=0.5, h_gap_in=0.25, v_gap_in=0.35, dpi=300
        )
        messagebox.showinfo("Success", f"Saved sheet: {filename}")
    except RuntimeError as re:
        messagebox.showerror("Dependency Missing", str(re))
    except Exception as e:
        messagebox.showerror("Error", str(e))

# ------------------------------------------------------------------
# Barcode tab (batch functions)
# ------------------------------------------------------------------
def load_barcode_items():
    for r in barcode_tree.get_children():
        barcode_tree.delete(r)
    try:
        for row in get_barcode_items():
            barcode_tree.insert("", "end", values=row)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load barcode items: {e}")

# --- ADD this new popup function (place near other barcode single-item functions) ---
def open_barcode_detail_popup(barcode_value: str):
    """
    Show a popup with all fields for the item identified by barcode.
    Allows in-place editing & saving. If not found, offer to create a new entry.
    """
    barcode_value = (barcode_value or "").strip()
    if not barcode_value:
        messagebox.showwarning("No Barcode", "Scan or enter a barcode first.")
        return

    row = fetch_item_by_barcode(barcode_value)
    if not row:
        if not messagebox.askyesno("Not Found", "No item with that barcode. Create new entry?"):
            return
        # Pre-fill defaults for creation
        new_popup = tk.Toplevel(root)
        new_popup.title(f"New Item for Barcode {barcode_value}")
        fields_order = [
            ("Barcode", "barcode", barcode_value),
            ("Shelf", "shelf", ""),
            ("Thickness", "thickness", ""),
            ("Metal Type", "metal_type", ""),
            ("Dimensions", "dimensions", ""),
            ("Location", "location", ""),
            ("Quantity", "quantity", "0"),
            ("Sheet size", "usable_scrap", ""),
            ("Date (MM-DD-YYYY)", "date", "")
        ]
        entries = {}
        for r, (label, key, default) in enumerate(fields_order):
            tk.Label(new_popup, text=label + ":").grid(row=r, column=0, sticky="e", padx=4, pady=3)
            e = tk.Entry(new_popup, width=28)
            e.grid(row=r, column=1, padx=4, pady=3)
            e.insert(0, default)
            entries[key] = e

        def create_item():
            data = {k: ent.get().strip() for k, ent in entries.items()}
            try:
                if data["date"]:
                    normalize_date_input(data["date"])
                int(data["quantity"] or "0")
            except ValueError as ve:
                messagebox.showerror("Invalid", str(ve))
                return
            try:
                add_inventory_item(data)
                messagebox.showinfo("Created", "New item added.")
                refresh_table(current_filters)
                load_barcode_items()
                new_popup.destroy()
                entry_comboboxes["barcode"].focus_set()  # <--- ADD
            except Exception as e:
                messagebox.showerror("Error", str(e))

        tk.Button(new_popup, text="Create", command=create_item, bg="#2d7").grid(
            row=len(fields_order), column=0, pady=10, padx=5
        )
        tk.Button(
            new_popup, text="Cancel",
            command=lambda: (new_popup.destroy(), entry_comboboxes["barcode"].focus_set())
        ).grid(row=len(fields_order), column=1, pady=10, padx=5, sticky="e")
        return

    # Existing row found
    # row: (id, barcode, shelf, thickness, metal_type, dimensions, location, quantity, usable_scrap, date)
    item_id = row[0]
    existing = {
        "barcode": row[1] or "",
        "shelf": row[2] or "",
        "thickness": row[3] or "",
        "metal_type": row[4] or "",
        "dimensions": row[5] or "",
        "location": row[6] or "",
        "quantity": str(row[7] if row[7] is not None else 0),
        "usable_scrap": row[8] or "",
        "date": row[9].strftime("%Y-%m-%d") if row[9] else ""
    }

    popup = tk.Toplevel(root)
    popup.title(f"Item: {existing['barcode']}")
    popup.geometry("430x520")

    fields_order = [
        ("Barcode", "barcode"),
        ("Shelf", "shelf"),
        ("Thickness", "thickness"),
        ("Metal Type", "metal_type"),
        ("Dimensions", "dimensions"),
        ("Location", "location"),
        ("Quantity", "quantity"),
        ("Sheet size", "usable_scrap"),
        ("Date (YYYY-MM-DD or MM-DD-YYYY)", "date")
    ]

    entries: dict[str, tk.Entry] = {}

    for r, (label, key) in enumerate(fields_order):
        tk.Label(popup, text=label + ":").grid(row=r, column=0, sticky="e", padx=6, pady=4)
        e = tk.Entry(popup, width=28)
        e.grid(row=r, column=1, padx=6, pady=4, sticky="w")
        e.insert(0, existing[key])
        entries[key] = e

    # Quick quantity adjust
    def adjust_qty(delta: int):
        try:
            q = int(entries["quantity"].get() or "0")
            q = max(0, q + delta)
            entries["quantity"].delete(0, tk.END)
            entries["quantity"].insert(0, str(q))
        except ValueError:
            messagebox.showerror("Invalid", "Quantity must be integer.")

    tk.Frame(popup, height=6).grid(row=len(fields_order), column=0)

    btn_frame = tk.Frame(popup)
    btn_frame.grid(row=len(fields_order) + 1, column=0, columnspan=2, pady=8)

    tk.Button(btn_frame, text="+1", width=4, command=lambda: adjust_qty(1)).pack(side="left", padx=2)
    tk.Button(btn_frame, text="+5", width=4, command=lambda: adjust_qty(5)).pack(side="left", padx=2)
    tk.Button(btn_frame, text="-1", width=4, command=lambda: adjust_qty(-1)).pack(side="left", padx=2)
    tk.Button(btn_frame, text="-5", width=4, command=lambda: adjust_qty(-5)).pack(side="left", padx=2)

    def save_changes():
        updated = {k: ent.get().strip() for k, ent in entries.items()}
        # Validate quantity & date
        try:
            int(updated["quantity"] or "0")
        except ValueError:
            messagebox.showerror("Invalid", "Quantity must be integer.")
            return
        try:
            if updated["date"]:
                normalize_date_input(updated["date"])
        except ValueError as ve:
            messagebox.showerror("Invalid Date", str(ve))
            return
        try:
            changed = update_inventory_item_by_id(item_id, updated)
            if changed:
                messagebox.showinfo("Saved", "Item updated.")
            else:
                messagebox.showinfo("No Change", "No fields changed.")
            refresh_table(current_filters)
            load_barcode_items()
            popup.destroy()
            entry_comboboxes["barcode"].focus_set()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def delete_item():
        if not messagebox.askyesno("Confirm Delete", "Delete this item?"):
            return
        if not messagebox.askyesno("Final Confirm", "This cannot be undone. Proceed?"):
            return
        try:
            deleted = delete_inventory_item_by_id(item_id)
            messagebox.showinfo("Deleted" if deleted else "Not Found",
                                "Item removed." if deleted else "Item not found.")
            refresh_table(current_filters)
            load_barcode_items();
            popup.destroy();
            entry_comboboxes["barcode"].focus_set()
        except Exception as ex:
            messagebox.showerror("Delete Error", str(ex))

    btn_row = len(fields_order) + 2
    tk.Button(popup, text="Save", command=save_changes, bg="#2d7").grid(
        row=btn_row, column=0, pady=10, padx=8, sticky="e"
    )
    tk.Button(popup, text="Delete", command=delete_item, bg="#c33", fg="white").grid(
        row=btn_row, column=1, pady=10, padx=4, sticky="w"
    )
    tk.Button(
        popup, text="Cancel",
        command=lambda: (popup.destroy(), entry_comboboxes["barcode"].focus_set())
    ).grid(row=btn_row + 1, column=0, columnspan=2, pady=4)

def view_selected_barcode():
    sel = barcode_tree.selection()
    if not sel:
        messagebox.showwarning("No Selection", "Select an item.")
        return
    bc = barcode_tree.item(sel[0], "values")[0]
    if not bc:
        messagebox.showwarning("No Barcode", "Selected item has no barcode.")
        return
    filename = build_barcode_filename(bc)
    if not os.path.exists(filename):
        try:
            generate_barcode_image(bc)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot generate barcode: {e}")
            return
    popup = tk.Toplevel(root); popup.title(f"Barcode: {bc}")
    try:
        img = Image.open(filename).resize((300, 100),
                                          Image.LANCZOS if hasattr(Image, 'LANCZOS') else Image.NEAREST)
        tk_img = ImageTk.PhotoImage(img)
        lbl = tk.Label(popup, image=tk_img); lbl.img_tk = tk_img
        lbl.pack(padx=15, pady=15)
        tk.Button(popup, text="Print",
                  command=lambda: os.startfile(filename) if os.name == 'nt'
                  else messagebox.showinfo("Print", f"File saved: {filename}")
                  ).pack(pady=6)
    except Exception as e:
        tk.Label(popup, text=f"Error: {e}").pack(padx=20, pady=20)

def generate_selected_barcodes():
    sel = barcode_tree.selection()
    if not sel:
        messagebox.showwarning("No Selection", "Select one or more rows.")
        return
    codes = []
    for item in sel:
        v = barcode_tree.item(item, "values")
        if v and v[0]:
            codes.append(v[0])
    try:
        count = generate_selected_barcodes_service(codes)
        messagebox.showinfo("Success", f"Generated {count} barcode images.")
    except Exception as e:
        messagebox.showerror("Error", str(e))

def print_selected_barcodes_sheet():
    sel = barcode_tree.selection()
    if not sel:
        messagebox.showwarning("No Selection", "Select one or more rows.")
        return
    codes = []
    for item in sel:
        v = barcode_tree.item(item, "values")
        if v and v[0]:
            codes.append(v[0])
    if not codes:
        messagebox.showwarning("No Data", "No valid barcodes in selection.")
        return
    filename = filedialog.asksaveasfilename(
        defaultextension=".pdf",
        filetypes=[("PDF files", "*.pdf")],
        title="Save Selected Barcodes (PDF)"
    )
    if not filename:
        return
    try:
        export_barcodes_to_pdf(
            codes, filename, labels_per_row=4,
            label_width_in=1.8, label_height_in=1.0,
            margin_in=0.5, h_gap_in=0.25, v_gap_in=0.35, dpi=300
        )
        messagebox.showinfo("Success", f"Saved PDF: {filename}")
        if os.name == "nt":
            try:
                os.startfile(filename)
            except Exception:
                pass
    except RuntimeError as re:
        messagebox.showerror("Dependency Missing", str(re))
    except Exception as e:
        messagebox.showerror("Error", str(e))

# ------------------------------------------------------------------
# Scan quantity adjustment
# ------------------------------------------------------------------
def scan_and_update_quantity():
    """
    Enter pressed in barcode field -> open detail popup,
    then clear and refocus the barcode entry for rapid scanning.
    """
    bc = entry_comboboxes["barcode"].get().strip()
    if not bc:
        messagebox.showwarning("No Barcode", "Scan or enter a barcode.")
        return
    # Open popup using current barcode
    open_barcode_detail_popup(bc)
    # Clear field and refocus for next scan
    entry = entry_comboboxes["barcode"]
    entry.delete(0, tk.END)
    entry.focus_set()

# ------------------------------------------------------------------
# Initial UI setup
# ------------------------------------------------------------------
root = tk.Tk()
root.title("Inventory Manager")
notebook = ttk.Notebook(root)
notebook.pack(fill='both', expand=True, padx=10, pady=10)

add_edit_tab = ttk.Frame(notebook)
view_tab = ttk.Frame(notebook)
barcode_tab = ttk.Frame(notebook)
notebook.add(add_edit_tab, text="Add/Edit")
notebook.add(view_tab, text="View Inventory")
notebook.add(barcode_tab, text="Barcodes")

tk.Label(add_edit_tab, text="Environmental Pneumatics Inventory",
         font=("Arial", 14, "bold")).grid(row=0, column=0, columnspan=2, pady=10)

entry_labels = [
    ("Barcode:", "barcode"),
    ("Shelf:", "shelf"),
    ("Thickness:", "thickness"),
    ("Metal Type:", "metal_type"),
    ("Dimensions:", "dimensions"),
    ("Location:", "location"),
    ("Quantity:", "quantity"),
    ("Sheet size:", "usable_scrap"),
    ("Date (MM-DD-YYYY):", "date")
]
entry_comboboxes = {}
for idx, (label, key) in enumerate(entry_labels):
    tk.Label(add_edit_tab, text=label).grid(row=idx + 1, column=0, sticky="e", padx=5, pady=2)
    if key == "barcode":
        ent = tk.Entry(add_edit_tab, width=25)
        ent.grid(row=idx + 1, column=1, padx=5, pady=2)
        ent.bind("<Return>", lambda e: [scan_and_update_quantity(), show_barcode_image()])
        ent.bind("<FocusOut>", lambda e: show_barcode_image())
        entry_comboboxes[key] = ent
    else:
        cb = ttk.Combobox(add_edit_tab, state="normal", width=25)
        cb.grid(row=idx + 1, column=1, padx=5, pady=2)
        entry_comboboxes[key] = cb

# Action buttons
btn_frame = tk.Frame(add_edit_tab)
btn_frame.grid(row=len(entry_labels) + 1, column=0, columnspan=2, pady=10)
tk.Button(btn_frame, text="Update Entry", command=update_entry).pack(side="left", padx=5)
tk.Button(btn_frame, text="Add New Entry", command=add_entry).pack(side="left", padx=5)

# Backup / restore
backup_frame = tk.Frame(add_edit_tab)
backup_frame.grid(row=len(entry_labels) + 2, column=0, columnspan=2, pady=5)
tk.Button(backup_frame, text="Backup DB", command=backup_database,
          bg="green", fg="white").pack(side="left", padx=5)
tk.Button(backup_frame, text="Restore DB", command=restore_from_backup,
          bg="blue", fg="white").pack(side="left", padx=5)

wipe_btn = tk.Button(add_edit_tab, text="WIPE DATABASE", command=wipe_database,
                     bg="red", fg="white", font=("Arial", 10, "bold"))
wipe_btn.grid(row=len(entry_labels) + 3, column=0, columnspan=2, pady=8)

# Barcode actions (Add/Edit) – REMOVED legacy/migrate/regenerate/preview per request
barcode_button_frame = tk.Frame(add_edit_tab)
barcode_button_frame.grid(row=len(entry_labels) + 4, column=0, columnspan=2, pady=6)
tk.Button(barcode_button_frame, text="Generate Barcode", command=generate_and_show_barcode).pack(side="left", padx=5)
tk.Button(barcode_button_frame, text="Show Barcode (Scan)", command=show_barcode_for_scan).pack(side="left", padx=5)
# (Legacy Generate, Migrate Compact, Regenerate Images, Preview Renaming removed)

# Printable actions
print_frame = tk.Frame(add_edit_tab)
print_frame.grid(row=len(entry_labels) + 5, column=0, columnspan=2, pady=4)
tk.Button(print_frame, text="Save Printable Label", command=save_printable_barcode).pack(side="left", padx=5)
tk.Button(print_frame, text="Save Visible Sheet (PDF)", command=save_barcode_sheet).pack(side="left", padx=5)

# Barcode preview
barcode_display_frame = tk.Frame(add_edit_tab)
barcode_display_frame.grid(row=len(entry_labels) + 6, column=0, columnspan=2, pady=5)
barcode_image_label = tk.Label(barcode_display_frame, text="No barcode")
barcode_image_label.pack()

root.geometry("1000x720")

# View tab
columns = ("barcode", "shelf", "thickness", "metal_type", "dimensions",
           "location", "quantity", "usable_scrap", "date")
tree_frame = ttk.Frame(view_tab)
tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
tree_scroll_y = ttk.Scrollbar(tree_frame); tree_scroll_y.pack(side="right", fill="y")
tree_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal"); tree_scroll_x.pack(side="bottom", fill="x")

tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                    yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
for col in columns:
    hdr = "Sheet size" if col == "usable_scrap" else col.capitalize()
    tree.heading(col, text=hdr, command=lambda c=col: treeview_sort_column(tree, c, False))
    tree.column(col, width=110)
tree.pack(fill="both", expand=True)
tree_scroll_y.config(command=tree.yview)
tree_scroll_x.config(command=tree.xview)

action_frame = tk.Frame(view_tab)
action_frame.pack(fill="x", padx=5, pady=5)
tk.Button(action_frame, text="Delete Entry", command=delete_entry).pack(side="left", padx=5)
tk.Button(action_frame, text="Increase Qty", command=increment_quantity).pack(side="left", padx=5)
tk.Button(action_frame, text="Decrease Qty", command=decrement_quantity).pack(side="left", padx=5)
tk.Button(action_frame, text="Fix Field", command=fix_field).pack(side="left", padx=5)
dimension_format_btn = tk.Button(action_frame, text="Show Dimensions in Feet/Inches",
                                 command=toggle_dimension_format)
dimension_format_btn.pack(side="left", padx=5)

export_frame = tk.Frame(view_tab); export_frame.pack(fill="x", padx=5, pady=5)
tk.Button(export_frame, text="Export CSV", command=export_to_csv).pack(side="left", padx=5)
tk.Button(export_frame, text="Export ProNest", command=export_to_pronest,
          bg="#007ACC", fg="white").pack(side="left", padx=5)

filter_frame = ttk.LabelFrame(view_tab, text="Filters")
filter_frame.pack(fill="x", padx=5, pady=5)
setup_filter_section()

# After UI construction (before root.mainloop()):
entry_comboboxes["barcode"].focus_set()

# Barcode tab
barcode_print_frame = ttk.LabelFrame(barcode_tab, text="Barcodes")
barcode_print_frame.pack(fill="both", expand=True, padx=10, pady=10)
tk.Label(barcode_print_frame, text="Select items then use actions below:").pack(anchor="w", padx=8, pady=4)

barcode_tree_frame = ttk.Frame(barcode_print_frame)
barcode_tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

barcode_tree = ttk.Treeview(
    barcode_tree_frame,
    columns=("barcode", "shelf", "thickness", "metal_type", "dimensions", "quantity"),
    show="headings",
    selectmode="extended"
)
for col in ("barcode", "shelf", "thickness", "metal_type", "dimensions", "quantity"):
    barcode_tree.heading(col, text=col.capitalize())
    barcode_tree.column(col, width=110)
barcode_tree.pack(fill="both", expand=True, side="left")
barcode_scroll = ttk.Scrollbar(barcode_tree_frame, orient="vertical", command=barcode_tree.yview)
barcode_scroll.pack(side="right", fill="y")
barcode_tree.configure(yscrollcommand=barcode_scroll.set)

barcode_btn_frame = ttk.Frame(barcode_print_frame)
barcode_btn_frame.pack(fill="x", padx=5, pady=8)
tk.Button(barcode_btn_frame, text="Load Items", command=load_barcode_items).pack(side="left", padx=5)
tk.Button(barcode_btn_frame, text="View Selected", command=view_selected_barcode).pack(side="left", padx=5)
tk.Button(barcode_btn_frame, text="Generate Selected Images", command=generate_selected_barcodes).pack(side="left", padx=5)
tk.Button(barcode_btn_frame, text="Print Selected (PDF)", command=print_selected_barcodes_sheet).pack(side="left", padx=5)
# Keep preview / force rebuild tools on Barcodes tab (remove if not desired there)
tk.Button(barcode_btn_frame, text="Preview Renaming", command=preview_barcode_renaming).pack(side="left", padx=5)
tk.Button(barcode_btn_frame, text="Force Rebuild", command=force_rebuild_all_barcodes).pack(side="left", padx=5)
tk.Button(export_frame, text="Import CSV", command=import_csv_inventory,
          bg="#444", fg="white").pack(side="left", padx=5)

# ------------------------------------------------------------------
# DB setup
# ------------------------------------------------------------------
def setup_database_if_needed():
    try:
        execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='inventory' AND column_name='id'
                ) THEN
                    ALTER TABLE inventory ADD COLUMN id SERIAL PRIMARY KEY;
                END IF;
            END
            $$;
        """)
    except Exception as e:
        print(f"Database setup error: {e}")

setup_database_if_needed()

# Initial loads
load_barcode_items()
refresh_table()
refresh_comboboxes()

if __name__ == "__main__":
    root.mainloop()