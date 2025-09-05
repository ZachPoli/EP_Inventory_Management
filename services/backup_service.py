import pandas as pd
from datetime import datetime
from tkinter import filedialog, messagebox
from db.queries import fetch_all, execute
from db.connection import get_cursor

TABLE_NAME = "inventory"

def backup_inventory():
    """
    Backup the entire inventory table to CSV or XLSX.
    """
    try:
        cols = [c[0] for c in fetch_all(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='{TABLE_NAME}'
            ORDER BY ordinal_position
        """)]
        if not cols:
            messagebox.showinfo("No Data", "No columns found.")
            return

        rows = fetch_all(f"SELECT {', '.join(cols)} FROM {TABLE_NAME}")
        if not rows:
            messagebox.showinfo("No Data", "No rows to backup.")
            return

        df = pd.DataFrame(rows, columns=cols)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=f"{TABLE_NAME}_backup_{ts}.csv",
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx")],
            title="Save Backup"
        )
        if not filename:
            return

        if filename.lower().endswith(".xlsx"):
            df.to_excel(filename, index=False)
        else:
            df.to_csv(filename, index=False, encoding="utf-8-sig")

        messagebox.showinfo("Success", f"Backup saved: {filename}")
    except Exception as e:
        messagebox.showerror("Backup Error", str(e))


def restore_inventory(refresh_table_fn=None, refresh_comboboxes_fn=None):
    """
    Restore rows from a CSV/XLSX backup file into inventory.
    Strategy: always ignore primary key 'id' to avoid duplicate key conflicts
    and let the database assign new IDs.
    If REPLACE is chosen, existing rows are deleted first.
    """
    try:
        filename = filedialog.askopenfilename(
            title="Select Backup File",
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        if not filename:
            return

        if filename.lower().endswith(".csv"):
            df = pd.read_csv(filename)
        else:
            df = pd.read_excel(filename)

        if df.empty:
            messagebox.showwarning("Empty", "Backup file has no data.")
            return

        mode = messagebox.askquestion(
            "Restore Mode",
            "REPLACE existing data? (Yes = wipe first, No = append)"
        )
        replace_mode = (mode == "yes")

        if replace_mode:
            if not messagebox.askyesno("Confirm Replace", "This will DELETE all current data. Continue?"):
                return
            execute(f"DELETE FROM {TABLE_NAME}")

        valid_columns = [c[0] for c in fetch_all(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='{TABLE_NAME}'
        """)]

        # Determine usable columns (intersection) and drop 'id' if present
        use_cols = [c for c in df.columns if c in valid_columns]
        if not use_cols:
            messagebox.showerror("Error", "No valid inventory columns in backup.")
            return

        if 'id' in use_cols:
            use_cols = [c for c in use_cols if c != 'id']

        if not use_cols:
            messagebox.showerror("Error", "No restorable (non-id) columns found.")
            return

        rows_added = 0
        with get_cursor() as cur:
            placeholders = ", ".join(["%s"] * len(use_cols))
            col_list_sql = ", ".join(use_cols)
            for _, r in df[use_cols].iterrows():
                vals = [None if pd.isna(v) else v for v in r]
                cur.execute(
                    f"INSERT INTO {TABLE_NAME} ({col_list_sql}) VALUES ({placeholders})",
                    vals
                )
                rows_added += 1

        messagebox.showinfo(
            "Restore Complete",
            f"Restored {rows_added} rows.\n(Primary keys re-generated)"
        )

        if refresh_table_fn:
            refresh_table_fn()
        if refresh_comboboxes_fn:
            refresh_comboboxes_fn()

    except Exception as e:
        messagebox.showerror("Restore Error", str(e))


__all__ = ["backup_inventory", "restore_inventory"]