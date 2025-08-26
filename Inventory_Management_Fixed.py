import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import psycopg2
import tkinter.simpledialog
import pandas as pd
import csv
from datetime import datetime
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageTk
import os

print("Script started")  # At the very top

# Global variables
current_filters = {}
filter_comboboxes = {}
show_dimensions_in_feet = False
sort_column = None
sort_reverse = False

def treeview_sort_column(tv, col, reverse):
    """Sort treeview contents when a column header is clicked."""
    global sort_column, sort_reverse
    
    # Update sort indicators
    sort_column = col
    sort_reverse = reverse
    
    # Get all items in the treeview
    data_list = [(tv.set(k, col), k) for k in tv.get_children('')]
    
    try:
        # Try to sort numerically for quantity column
        if col == "quantity":
            data_list.sort(key=lambda x: int(x[0]), reverse=reverse)
        # Try to sort numerically for thickness if possible
        elif col == "thickness":
            data_list.sort(key=lambda x: float(x[0]) if x[0].replace('.', '', 1).isdigit() else x[0].lower(), 
                           reverse=reverse)
        # Otherwise sort alphabetically
        else:
            data_list.sort(key=lambda x: x[0].lower(), reverse=reverse)
    except (ValueError, TypeError):
        # Fallback to string sort if numeric conversion fails
        data_list.sort(reverse=reverse)
        
    # Rearrange items in sorted positions
    for index, (val, k) in enumerate(data_list):
        tv.move(k, '', index)

    # Reverse sort next time if same column is clicked
    tv.heading(col, command=lambda: treeview_sort_column(tv, col, not reverse))
    
    # Add visual indicator of sort direction in column heading
    for c in tv['columns']:
        if c == col:
            if c == "usable_scrap":
                tv.heading(c, text=f"Sheet size {'▼' if reverse else '▲'}")
            else:
                tv.heading(c, text=f"{c.capitalize()} {'▼' if reverse else '▲'}")
        else:
            if c == "usable_scrap":
                tv.heading(c, text="Sheet size")
            else:
                tv.heading(c, text=c.capitalize())

def inches_to_feet_inches(inches):
    """Convert a decimal inch value to feet and inches format."""
    try:
        inches_float = float(inches)
        feet = int(inches_float // 12)
        remaining_inches = round(inches_float % 12, 1)
        if feet > 0:
            return f"{feet}' {remaining_inches}\""
        else:
            return f"{remaining_inches}\""
    except (ValueError, TypeError):
        return inches  # Return original value if conversion fails

def sanitize_filename(barcode_value):
    # Remove or replace illegal filename characters for Windows
    illegal_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
    for ch in illegal_chars:
        barcode_value = barcode_value.replace(ch, '_')
    return barcode_value

def get_distinct_values(column):
    try:
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        cur.execute(f"SELECT DISTINCT {column} FROM inventory ORDER BY {column}")
        values = [row[0] for row in cur.fetchall() if row[0] is not None]
        cur.close()
        conn.close()
        return values
    except Exception:
        return []

def refresh_comboboxes():
    for col, cb in entry_comboboxes.items():
        if isinstance(cb, ttk.Combobox):
            cb['values'] = get_distinct_values(col)
    for col, cb in filter_comboboxes.items():
        if isinstance(cb, ttk.Combobox):
            cb['values'] = [''] + get_distinct_values(col)  # '' for no filter

def get_field_values():
    return {
        "barcode": entry_comboboxes["barcode"].get(),  # Add this line
        "shelf": shelf_entry.get(),
        "thickness": thickness_entry.get(),
        "metal_type": metal_type_entry.get(),
        "dimensions": dimensions_entry.get(),
        "location": location_entry.get(),
        "quantity": quantity_entry.get(),
        "usable_scrap": usable_scrap_entry.get(),
        "date": date_entry.get()
    }

def update_entry():
    fields = get_field_values()
    try:
        quantity = int(fields["quantity"])
    except ValueError:
        messagebox.showerror("Error", "Quantity must be an integer.")
        return
    try:
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE inventory
            SET barcode = %s, shelf = %s, thickness = %s, location = %s, quantity = %s, usable_scrap = %s, date = %s
            WHERE dimensions = %s AND thickness = %s AND metal_type = %s
            """,
            (
                fields["barcode"], fields["shelf"], fields["thickness"], fields["location"], quantity,
                fields["usable_scrap"], fields["date"] if fields["date"] else None,
                fields["dimensions"], fields["thickness"], fields["metal_type"]
            )
        )
        if cur.rowcount == 0:
            messagebox.showwarning("Not Found", "No matching entry found to update.")
        else:
            conn.commit()
            messagebox.showinfo("Success", "Entry updated!")
        cur.close()
        conn.close()
        refresh_table(current_filters)  # Pass current filters
        refresh_comboboxes()
    except Exception as e:
        messagebox.showerror("Error", str(e))

def add_entry():
    fields = get_field_values()
    try:
        quantity = int(fields["quantity"])
    except ValueError:
        messagebox.showerror("Error", "Quantity must be an integer.")
        return
    try:
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO inventory (barcode, shelf, thickness, metal_type, dimensions, location, quantity, usable_scrap, date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                fields["barcode"], fields["shelf"], fields["thickness"], fields["metal_type"], fields["dimensions"],
                fields["location"], quantity, fields["usable_scrap"], fields["date"] if fields["date"] else None
            )
        )
        conn.commit()
        cur.close()
        conn.close()
        messagebox.showinfo("Success", "New entry added!")
        refresh_table(current_filters)  # Pass current filters
        refresh_comboboxes()
    except Exception as e:
        messagebox.showerror("Error", str(e))

def extract_dimensions_from_database():
    try:
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        
        # First, check if the length and width columns exist, if not create them
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='inventory' AND column_name='length') THEN
                    ALTER TABLE inventory ADD COLUMN length NUMERIC;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='inventory' AND column_name='width') THEN
                    ALTER TABLE inventory ADD COLUMN width NUMERIC;
                END IF;
            END
            $$;
        """)
        
        # Get all records with dimensions
        cur.execute("SELECT dimensions FROM inventory")
        records = cur.fetchall()
        
        # Process each record
        for record in records:
            dimensions = record[0]
            if dimensions and isinstance(dimensions, str) and 'x' in dimensions.lower():
                try:
                    # Extract the length and width
                    parts = dimensions.lower().replace('"', '').split('x')
                    length = float(''.join(c for c in parts[0] if c.isdigit() or c == '.'))
                    width = float(''.join(c for c in parts[1] if c.isdigit() or c == '.'))
                    
                    # Update the record
                    cur.execute(
                        "UPDATE inventory SET length = %s, width = %s WHERE dimensions = %s",
                        (length, width, dimensions)
                    )
                except (ValueError, IndexError):
                    # Skip if parsing fails
                    continue
        
        conn.commit()
        cur.close()
        conn.close()
        messagebox.showinfo("Success", "Dimension data extracted and updated")
    except Exception as e:
        messagebox.showerror("Error", f"Could not extract dimensions: {str(e)}")

def setup_filter_section():
    global filter_comboboxes, length_min_entry, length_max_entry, width_min_entry, width_max_entry, current_filters
    
    # Reset current filters
    current_filters = {}
    
    # Clear existing filter widgets
    for widget in filter_frame.winfo_children():
        widget.destroy()
        
    # Standard filters - update Usable Scrap to Sheet size
    filter_labels = [
        ("Shelf:", "shelf"), ("Thickness:", "thickness"), ("Metal Type:", "metal_type"), 
        ("Dimensions:", "dimensions"), ("Location:", "location"), 
        ("Sheet size:", "usable_scrap"), ("Date:", "date")
    ]

    filter_comboboxes = {}
    for idx, (label, col) in enumerate(filter_labels):
        if idx % 3 == 0:
            frame_row = tk.Frame(filter_frame)
            frame_row.pack(fill="x", pady=2)
        
        filter_label = tk.Label(frame_row, text=f"Filter {label}")
        filter_label.pack(side="left", padx=5)
        cb = ttk.Combobox(frame_row, state="readonly", width=15)
        cb.pack(side="left", padx=5)
        filter_comboboxes[col] = cb

    # Add numeric dimension filters
    dimension_frame = tk.Frame(filter_frame)
    dimension_frame.pack(fill="x", pady=5)

    # Length filters
    length_frame = tk.Frame(dimension_frame)
    length_frame.pack(side="left", padx=20)
    tk.Label(length_frame, text="Length Range (inches):").pack(anchor="w")

    length_range_frame = tk.Frame(length_frame)
    length_range_frame.pack(fill="x")

    tk.Label(length_range_frame, text="Min:").pack(side="left")
    length_min_entry = tk.Entry(length_range_frame, width=8)
    length_min_entry.pack(side="left", padx=2)

    tk.Label(length_range_frame, text="Max:").pack(side="left", padx=(10,0))
    length_max_entry = tk.Entry(length_range_frame, width=8)
    length_max_entry.pack(side="left", padx=2)

    # Width filters
    width_frame = tk.Frame(dimension_frame)
    width_frame.pack(side="left", padx=20)
    tk.Label(width_frame, text="Width Range (inches):").pack(anchor="w")

    width_range_frame = tk.Frame(width_frame)
    width_range_frame.pack(fill="x")

    tk.Label(width_range_frame, text="Min:").pack(side="left")
    width_min_entry = tk.Entry(width_range_frame, width=8)
    width_min_entry.pack(side="left", padx=2)

    tk.Label(width_range_frame, text="Max:").pack(side="left", padx=(10,0))
    width_max_entry = tk.Entry(width_range_frame, width=8)
    width_max_entry.pack(side="left", padx=2)

    # Filter button
    tk.Button(filter_frame, text="Apply Filter", command=apply_filter).pack(pady=5)

    # Add button to extract dimensions
    tk.Button(filter_frame, text="Extract Dimensions from Database", 
              command=extract_dimensions_from_database).pack(pady=5)

def apply_filter():
    global current_filters
    current_filters = {col: cb.get() for col, cb in filter_comboboxes.items() if cb.get()}
    
    # Add dimension range filters
    dimension_filters = {}
    
    # Get length range
    try:
        if length_min_entry.get():
            dimension_filters["length_min"] = float(length_min_entry.get())
        if length_max_entry.get():
            dimension_filters["length_max"] = float(length_max_entry.get())
    except ValueError:
        messagebox.showerror("Error", "Length values must be numeric")
        return
    
    # Get width range
    try:
        if width_min_entry.get():
            dimension_filters["width_min"] = float(width_min_entry.get())
        if width_max_entry.get():
            dimension_filters["width_max"] = float(width_max_entry.get())
    except ValueError:
        messagebox.showerror("Error", "Width values must be numeric")
        return
    
    refresh_table(current_filters, dimension_filters)

def refresh_table(filters=None, dimension_filters=None):
    global show_dimensions_in_feet, sort_column, sort_reverse
    
    for row in tree.get_children():
        tree.delete(row)
    try:
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        # Add barcode to the SELECT statement
        query = "SELECT barcode, shelf, thickness, metal_type, dimensions, location, quantity, usable_scrap, date, length, width FROM inventory"
        params = []
        clauses = []
        
        # Regular filters
        if filters:
            for key, value in filters.items():
                if value:
                    clauses.append(f"{key} = %s")
                    params.append(value)
        
        # Dimension range filters
        if dimension_filters:
            if "length_min" in dimension_filters:
                clauses.append("length >= %s")
                params.append(dimension_filters["length_min"])
            if "length_max" in dimension_filters:
                clauses.append("length <= %s")
                params.append(dimension_filters["length_max"])
            if "width_min" in dimension_filters:
                clauses.append("width >= %s")
                params.append(dimension_filters["width_min"])
            if "width_max" in dimension_filters:
                clauses.append("width <= %s")
                params.append(dimension_filters["width_max"])
        
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        
        cur.execute(query, params)
        for row in cur.fetchall():
            # Convert the row to a list so we can modify it
            row_list = list(row)
            
            # Check if we need to convert length and width to feet/inches format
            if show_dimensions_in_feet and row[8] is not None:
                # Add a converted format hint to dimensions field
                original_dimensions = row_list[3]
                length_str = inches_to_feet_inches(row[8])
                width_str = inches_to_feet_inches(row[9])
                if length_str and width_str:
                    row_list[3] = f"{original_dimensions} ({length_str} x {width_str})"
            
            # Insert just the visible columns (excluding length and width which are hidden)
            tree.insert("", "end", values=row_list[:9])
        
        # After populating the tree, apply current sort if one exists
        if sort_column:
            treeview_sort_column(tree, sort_column, sort_reverse)
            
        cur.close()
        conn.close()
    except Exception as e:
        messagebox.showerror("Error", str(e))

def delete_entry():
    selected = tree.selection()
    if not selected:
        messagebox.showwarning("No selection", "Please select an entry to delete.")
        return
    values = tree.item(selected[0], "values")
    confirm = messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this entry?")
    if not confirm:
        return
    try:
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        cur.execute(
            """
            DELETE FROM inventory
            WHERE shelf = %s AND thickness = %s AND metal_type = %s AND dimensions = %s
              AND location = %s AND quantity = %s AND usable_scrap = %s AND date = %s
            """,
            (
                values[0], values[1], values[2], values[3],
                values[4], int(values[5]), values[6], values[7] if values[7] else None
            )
        )
        conn.commit()
        cur.close()
        conn.close()
        messagebox.showinfo("Success", "Entry deleted!")
        refresh_table(current_filters)  # Pass current filters
        refresh_comboboxes()
    except Exception as e:
        messagebox.showerror("Error", str(e))

def increment_quantity():
    selected = tree.selection()
    if not selected:
        messagebox.showwarning("No selection", "Please select an entry to update quantity.")
        return
    values = tree.item(selected[0], "values")
    
    # Ask for amount to add
    amount = tk.simpledialog.askinteger("Add Quantity", "Enter quantity to add:", minvalue=1)
    if amount is None:
        return
        
    try:
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        # Update only the quantity field
        cur.execute(
            """
            UPDATE inventory 
            SET quantity = quantity + %s
            WHERE shelf = %s AND thickness = %s AND metal_type = %s AND dimensions = %s
              AND location = %s
            """,
            (
                amount, values[0], values[1], values[2], values[3], values[4]
            )
        )
        conn.commit()
        cur.close()
        conn.close()
        messagebox.showinfo("Success", f"Added {amount} to quantity!")
        refresh_table(current_filters)  # Pass current filters
    except Exception as e:
        messagebox.showerror("Error", str(e))

def decrement_quantity():
    selected = tree.selection()
    if not selected:
        messagebox.showwarning("No selection", "Please select an entry to update quantity.")
        return
    values = tree.item(selected[0], "values")
    
    # Ask for amount to remove
    amount = tk.simpledialog.askinteger("Remove Quantity", "Enter quantity to remove:", minvalue=1)
    if amount is None:
        return
        
    try:
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        # Update only the quantity field, but check it doesn't go below 0
        cur.execute(
            """
            UPDATE inventory 
            SET quantity = GREATEST(0, quantity - %s)
            WHERE shelf = %s AND thickness = %s AND metal_type = %s AND dimensions = %s
              AND location = %s
            """,
            (
                amount, values[0], values[1], values[2], values[3], values[4]
            )
        )
        conn.commit();
        cur.close()
        conn.close()
        messagebox.showinfo("Success", f"Removed {amount} from quantity!")
        refresh_table(current_filters)  # Pass current filters
    except Exception as e:
        messagebox.showerror("Error", str(e))

def fix_field():
    selected = tree.selection()
    if not selected:
        messagebox.showwarning("No selection", "Please select an entry to fix.")
        return
    values = tree.item(selected[0], "values")
    
    # Create a small dialog to select field and new value
    fix_dialog = tk.Toplevel(root)
    fix_dialog.title("Fix Field")
    
    tk.Label(fix_dialog, text="Field to fix:").grid(row=0, column=0)
    field_cb = ttk.Combobox(fix_dialog, values=columns)
    field_cb.grid(row=0, column=1)
    
    tk.Label(fix_dialog, text="New value:").grid(row=1, column=0)
    new_value = tk.Entry(fix_dialog)
    new_value.grid(row=1, column=1)
    
    def apply_fix():
        field = field_cb.get()
        if not field or not new_value.get():
            messagebox.showwarning("Missing input", "Please select a field and enter a new value.")
            return
            
        try:
            conn = psycopg2.connect(
                dbname="inventory_db",
                user="postgres",
                password="MANman1@6",
                host="192.168.0.90",
                port="5432"
            )
            cur = conn.cursor()
            
            # Create dynamic SQL to update only the selected field
            cur.execute(
                f"""
                UPDATE inventory 
                SET {field} = %s
                WHERE shelf = %s AND thickness = %s AND metal_type = %s AND dimensions = %s
                  AND location = %s AND quantity = %s AND usable_scrap = %s AND date = %s
                """,
                (
                    new_value.get(), values[0], values[1], values[2], values[3],
                    values[4], int(values[5]), values[6], values[7] if values[7] else None
                )
            )
            conn.commit()
            cur.close()
            conn.close()
            messagebox.showinfo("Success", f"Updated {field} to {new_value.get()}!")
            fix_dialog.destroy()
            refresh_table(current_filters)  # Pass current filters
            refresh_comboboxes()
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    tk.Button(fix_dialog, text="Apply Fix", command=apply_fix).grid(row=2, column=0, columnspan=2)

def export_to_csv():
    """Export inventory data to Microsoft Excel CSV format."""
    try:
        # Get the current data from the treeview
        data = []
        
        # If no items visible, get all data from database
        if not tree.get_children():
            conn = psycopg2.connect(
                dbname="inventory_db",
                user="postgres",
                password="MANman1@6",
                host="192.168.0.90",
                port="5432"
            )
            cur = conn.cursor()
            cur.execute("SELECT shelf, thickness, metal_type, dimensions, location, quantity, usable_scrap, date FROM inventory")
            for row in cur.fetchall():
                data.append(list(row))
            cur.close()
            conn.close()
        else:
            # Use data from current view (with filters applied)
            for item_id in tree.get_children():
                values = tree.item(item_id)['values']
                data.append(values)
        
        # Create pandas DataFrame
        df = pd.DataFrame(data, columns=columns)
        
        # Get the filename from user
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx"), ("All files", "*.*")],
            title="Save Inventory Data as CSV"
        )
        
        if not filename:  # User cancelled
            return
            
        # Export to CSV using Excel-compatible format
        if filename.endswith('.csv'):
            # Use Excel's preferred encoding and delimiter
            df.to_csv(filename, index=False, encoding='utf-8-sig', sep=',')
        else:
            # If user selected Excel format, still use Excel
            df.to_excel(filename, index=False)
            
        messagebox.showinfo("Success", f"Data exported to {filename}")
    
    except Exception as e:
        messagebox.showerror("Export Error", str(e))

def export_to_pronest():
    """Export inventory data in ProNest format with formatted descriptions and stock numbers."""
    try:
        # First, try to extract dimensions for any entries that need it
        extract_dimensions_from_database()
        
        # Get currently visible items from tree if any are filtered/displayed
        visible_items = []
        if tree.get_children():
            for item_id in tree.get_children():
                values = tree.item(item_id, 'values')
                visible_items.append({
                    'shelf': values[0], 
                    'thickness': values[1], 
                    'metal_type': values[2], 
                    'dimensions': values[3], 
                    'location': values[4], 
                    'quantity': values[5], 
                    'usable_scrap': values[6], 
                    'date': values[7]
                })
        
        # Connect to database to get all required fields
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        
        rows = []
        # If we have visible items, use those to query complete data
        if visible_items:
            for item in visible_items:
                # Get complete data for this item including length and width
                cur.execute("""
                    SELECT 
                        metal_type, thickness, dimensions, quantity, length, width, 
                        location, date, shelf, usable_scrap
                    FROM inventory 
                    WHERE shelf = %s AND thickness = %s AND metal_type = %s AND dimensions = %s
                """, (item['shelf'], item['thickness'], item['metal_type'], item['dimensions']))
                
                result = cur.fetchone()
                if result:
                    rows.append(result)
        else:
            # Fall back to getting all data if no items visible
            cur.execute("""
                SELECT 
                    metal_type, thickness, dimensions, quantity, length, width, 
                    location, date, shelf, usable_scrap
                FROM inventory
            """)
            rows = cur.fetchall()
        
        cur.close()
        conn.close()
        
        if not rows:
            messagebox.showwarning("No Data", "No inventory data available for export.")
            return
            
        # Get file name for saving
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx"), ("All files", "*.*")],
            title="Export to ProNest Format"
        )
        
        if not filename:
            return  # User canceled
            
        # ProNest headers exactly as provided
        pronest_headers = [
            "Description", "Plate Type", "Units", "Length", "Width", "MaterialID", 
            "Material", "Thickness", "Stock Qty", "Unit Price", "Date Created", 
            "Rotation", "Heat Num", "Stock Num", "Misc1", "Misc2", "Misc3", 
            "Location", "Reorder limit", "Reorder quantity", "Supplier", 
            "Created by", "Plate Path", "Grade"
        ]
        
        # Sheet metal gauge to decimal inches conversion table
        gauge_to_inches = {
            "6": 0.1935,
            "7": 0.1875,
            "8": 0.1644,
            "9": 0.1500,
            "10": 0.1350,
            "11": 0.1200,
            "12": 0.1050,
            "13": 0.0897,
            "14": 0.0750,
            "15": 0.0673,
            "16": 0.0600,
            "17": 0.0538,
            "18": 0.0480,
            "19": 0.0418,
            "20": 0.0360,
            "22": 0.0300,
            "24": 0.0240,
            "26": 0.0180,
            "28": 0.0150,
            "30": 0.0120
        }
        
        # Create data for ProNest format
        pronest_data = []
        
        # Process each row from the database
        for idx, row in enumerate(rows):
            metal_type, thickness, dimensions, quantity, length, width, location, date, shelf, usable_scrap = row
            
            # Try to extract dimensions from the dimensions string if they're not available
            if (not length or not width) and dimensions and 'x' in dimensions.lower():
                try:
                    parts = dimensions.lower().replace('"', '').split('x')
                    length = float(''.join(c for c in parts[0] if c.isdigit() or c == '.'))
                    width = float(''.join(c for c in parts[1] if c.isdigit() or c == '.'))
                except (ValueError, IndexError):
                    # If we can't extract, set defaults so it still exports
                    length = 48.0  # Default to 4'
                    width = 48.0   # Default to 4'
            
            # Set defaults if we still don't have dimensions
            length = length or 48.0
            width = width or 48.0
                
            # Convert dimensions to feet for description and stock number
            length_feet = int(float(length) / 12) if length else 0
            width_feet = int(float(width) / 12) if width else 0
            
            # Extract thickness value and convert to proper decimal format
            thickness_str = thickness.strip() if thickness else ""
            original_thickness = thickness_str
            decimal_thickness = 0.0  # Default numeric value

            # Check if it has a gauge suffix (like "12G")
            if thickness_str and any(g in thickness_str.upper() for g in ["G", "GA", "GAUGE"]):
                # Extract the numeric part
                numeric_part = ''.join(c for c in thickness_str if c.isdigit())
                if numeric_part and numeric_part.isdigit():
                    gauge_number = numeric_part
                    # Look up in gauge table
                    if gauge_number in gauge_to_inches:
                        decimal_thickness = gauge_to_inches[gauge_number]
                    else:
                        # Default conversion if not in table
                        try:
                            gauge = int(gauge_number)
                            # Rough estimation for missing gauges
                            decimal_thickness = 0.2 - (gauge * 0.005)
                        except:
                            decimal_thickness = 0.0
            # Regular digit check (unchanged from before)
            elif thickness_str.isdigit():
                # It's a gauge number, look up the decimal equivalent
                if thickness_str in gauge_to_inches:
                    decimal_thickness = gauge_to_inches[thickness_str]
                else:
                    # Default conversion if not in table
                    try:
                        gauge = int(thickness_str)
                        # Rough estimation for missing gauges
                        decimal_thickness = 0.2 - (gauge * 0.005)
                    except:
                        decimal_thickness = 0.0
            elif "/" in thickness_str:
                # It's a fractional thickness, convert to decimal
                try:
                    if thickness_str.startswith("1/8"):
                        decimal_thickness = 0.1250
                    elif thickness_str.startswith("1/4"):
                        decimal_thickness = 0.2500
                    elif thickness_str.startswith("3/8"):
                        decimal_thickness = 0.3750
                    elif thickness_str.startswith("1/2"):
                        decimal_thickness = 0.5000
                    elif thickness_str.startswith("5/8"):
                        decimal_thickness = 0.6250
                    elif thickness_str.startswith("3/4"):
                        decimal_thickness = 0.7500
                    elif thickness_str == "1":
                        decimal_thickness = 1.0000
                    elif thickness_str.startswith("7/8"):
                        decimal_thickness = 0.8750
                    else:
                        # Try to evaluate the fraction
                        parts = thickness_str.split('/')
                        if len(parts) == 2:
                            decimal_thickness = float(parts[0]) / float(parts[1])
                        else:
                            decimal_thickness = 0.0
                except:
                    decimal_thickness = 0.0
            else:
                # Try to interpret as a decimal
                try:
                    decimal_thickness = float(thickness_str)
                except:
                    decimal_thickness = 0.0
            
            # Generate material code based on thickness and metal_type
            material_code = ""
            
            # Use original thickness for the material code
            material_code += original_thickness
            
            # Add material type abbreviation
            if "black" in metal_type.lower():
                material_code += "B"  # Changed from GB to B
            elif "plate" in metal_type.lower():
                material_code += "PL"
            elif "galv" in metal_type.lower():
                material_code += "G"  # Changed from GG to G
            elif "aluminum" in metal_type.lower() or metal_type.lower() == "al":
                material_code += "AL"  # Changed from GAL to AL
            else:
                # Default abbreviation using first letter of each word
                material_code += ''.join(word[0].upper() for word in metal_type.split() if word)
            
            # Map metal_type to standard ProNest material values
            pronest_material = "MS"  # Default to mild steel

            if "galv" in metal_type.lower() or "black" in metal_type.lower() or "plate" in metal_type.lower():
                pronest_material = "MS"  # Both galvanized and black/plate as MS
            elif "aluminum" in metal_type.lower() or metal_type.lower() == "al":
                pronest_material = "AL"  # Aluminum
            elif "stainless" in metal_type.lower() or "ss" in metal_type.lower():
                pronest_material = "SS"  # Stainless Steel
            
            # Determine prefix character for description based on metal type
            metal_type_lower = metal_type.lower() if metal_type else ""
            if "plate" in metal_type_lower:
                desc_prefix = "~"
            elif "black" in metal_type_lower:
                desc_prefix = "+"
            elif "galv" in metal_type_lower:
                desc_prefix = "-"
            elif "aluminum" in metal_type_lower or metal_type_lower == "al":
                desc_prefix = "="
            elif "stainless" in metal_type_lower or "ss" in metal_type_lower:
                desc_prefix = "<"
            else:
                desc_prefix = ""

            # Create formatted description with prefix and dimensions in feet
            formatted_description = f"{desc_prefix}{material_code} ({width_feet}' x {length_feet}')"
            
            # Create stock number in format like "10B510"
            stock_number = f"{material_code}{width_feet}{length_feet}"
            
            # Generate material ID using row index to ensure uniqueness
            material_id = f"MAT{idx+1:03d}"
            
            # Format date correctly if available
            date_created = date if date else datetime.now().strftime("%Y-%m-%d")
            
            # Calculate reorder values based on quantity
            reorder_limit = max(1, int(quantity) // 2) if quantity else 1
            reorder_quantity = max(1, int(quantity) // 4) if quantity else 1
            
            # Create a row with all the ProNest fields
            pronest_row = [
                formatted_description,              # Description
                "Rectangular",                      # Plate Type
                "Inches",                           # Units
                float(length) if length else 0,     # Length
                float(width) if width else 0,       # Width
                material_id,                        # MaterialID
                pronest_material,                   # Material - Using standardized ProNest material types
                decimal_thickness,                  # Thickness - now a float value, not a string
                int(quantity) if quantity else 0,   # Stock Qty
                0.0,                                # Unit Price
                date_created,                       # Date Created
                0,                                  # Rotation
                "",                                 # Heat Num
                stock_number,                       # Stock Num
                usable_scrap,                       # Misc1
                shelf,                              # Misc2
                "",                                 # Misc3
                location,                           # Location
                reorder_limit,                      # Reorder limit
                reorder_quantity,                   # Reorder quantity
                "Environmental Pneumatics",         # Supplier
                "Inventory Manager",                # Created by
                "",                                 # Plate Path
                ""                                  # Grade
            ]
            
            pronest_data.append(pronest_row)
        
        # Create DataFrame with ProNest structure
        df = pd.DataFrame(pronest_data, columns=pronest_headers)
        
        # Export based on file extension - default to CSV for Excel
        if filename.endswith('.xlsx'):
            df.to_excel(filename, index=False)
        else:
            # Use Excel's preferred CSV format
            df.to_csv(filename, index=False, encoding='utf-8-sig', sep=',')
            
        messagebox.showinfo("Success", f"Data exported in ProNest format to {filename}")
        
    except Exception as e:
        messagebox.showerror("Export Error", f"Error: {str(e)}")

def backup_database():
    """Create a backup of the entire inventory database."""
    try:
        # Get all data from database
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        
        # Get column names for the inventory table
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='inventory' 
            ORDER BY ordinal_position
        """)
        columns = [col[0] for col in cur.fetchall()]
        
        # Get all data
        cur.execute(f"SELECT {', '.join(columns)} FROM inventory")
        rows = cur.fetchall()
        
        cur.close()
        conn.close()
        
        if not rows:
            messagebox.showinfo("No Data", "There is no inventory data to backup.")
            return
            
        # Create DataFrame
        df = pd.DataFrame(rows, columns=columns)
        
        # Get the filename from user
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"inventory_backup_{timestamp}.csv"
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx"), ("All files", "*.*")],
            title="Save Backup File",
            initialfile=default_filename
        )
        
        if not filename:
            return  # User canceled
            
        # Export based on file extension
        if filename.endswith('.xlsx'):
            df.to_excel(filename, index=False)
        else:
            # Use Excel's preferred CSV format
            df.to_csv(filename, index=False, encoding='utf-8-sig', sep=',')
            
        messagebox.showinfo("Success", f"Backup saved to {filename}")
        
    except Exception as e:
        messagebox.showerror("Backup Error", str(e))

def restore_from_backup():
    """Restore inventory data from a backup file."""
    try:
        # Ask user to select backup file
        filename = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("Excel files", "*.xlsx"), ("All files", "*.*")],
            title="Select Backup File to Restore"
        )
        
        if not filename:  # User cancelled
            return
            
        # Load the data from the backup file
        if filename.endswith('.csv'):
            df = pd.read_csv(filename)
        else:  # Default to Excel
            df = pd.read_excel(filename)
            
        if df.empty:
            messagebox.showwarning("Empty Backup", "The selected backup file contains no data.")
            return
            
        # Ask if user wants to append or replace existing data
        mode = messagebox.askquestion(
            "Restore Mode",
            "Do you want to REPLACE all existing data?\n\n"
            "• Click 'Yes' to wipe existing data and restore from backup\n"
            "• Click 'No' to add backup data to existing inventory"
        )
        
        # If replacing, confirm again since this will delete current data
        if mode == 'yes':
            confirm = messagebox.askyesno(
                "Confirm Replace",
                "This will DELETE ALL current inventory data and replace it with the backup.\n\n"
                "Are you sure you want to continue?",
                icon="warning"
            )
            if not confirm:
                return
                
            # Wipe the database first
            try:
                conn = psycopg2.connect(
                    dbname="inventory_db",
                    user="postgres",
                    password="MANman1@6",
                    host="192.168.0.90",
                    port="5432"
                )
                cur = conn.cursor()
                cur.execute("DELETE FROM inventory")
                conn.commit()
                cur.close()
                conn.close()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear database: {str(e)}")
                return
        
        # Connect to the database
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        
        # Get current table columns to ensure we only insert valid columns
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='inventory'
        """)
        valid_columns = [col[0] for col in cur.fetchall()]
        
        # Filter the DataFrame to only include columns that exist in the database
        backup_columns = df.columns.tolist()
        columns_to_use = [col for col in backup_columns if col in valid_columns]
        
        if not columns_to_use:
            messagebox.showerror("Error", "No valid columns found in backup file.")
            return
            
        # Insert each row from the backup
        rows_added = 0
        for _, row in df[columns_to_use].iterrows():
            # Handle NaN/None values
            values = [None if pd.isna(val) else val for val in row]
            
            # Create dynamic SQL query with correct number of placeholders
            placeholders = ', '.join(['%s'] * len(columns_to_use))
            columns_str = ', '.join(columns_to_use);
            
            query = f"INSERT INTO inventory ({columns_str}) VALUES ({placeholders})"
            
            try:
                cur.execute(query, values)
                rows_added += 1
            except Exception as e:
                print(f"Error inserting row: {e}")
                continue
                
        conn.commit()
        cur.close()
        conn.close();
        
        messagebox.showinfo("Restore Complete", 
                           f"Successfully restored {rows_added} records from backup.")
        refresh_table()
        refresh_comboboxes()
        
    except Exception as e:
        messagebox.showerror("Restore Error", str(e))

def wipe_database():
    """Delete all entries from the inventory database."""
    # First confirmation    
    messagebox.showwarning(
        "WARNING", 
        "You are about to delete ALL inventory data. This cannot be undone!\n\n"
        "Type 'DELETE' in the next dialog to confirm.",
        icon="warning"
    )
    
    # Ask user to type DELETE to confirm
    confirmation = tk.simpledialog.askstring(
        "Confirm Delete ALL", 
        "Type 'DELETE' to confirm wiping the entire database:"
    )
    
    if confirmation != "DELETE":
        messagebox.showinfo("Cancelled", "Database wipe cancelled.")
        return
    
    # Final confirmation
    final_confirm = messagebox.askyesno(
        "FINAL WARNING", 
        "This will permanently delete ALL inventory records. Proceed?",
        icon="warning"
    )
    
    if not final_confirm:
        messagebox.showinfo("Cancelled", "Database wipe cancelled.")
        return
    
    try:
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        
        # Delete all records
        cur.execute("DELETE FROM inventory")
        
        # Get the count of deleted rows
        deleted_count = cur.rowcount
        
        conn.commit()
        cur.close()
        conn.close()
        
        messagebox.showinfo("Success", f"Database wiped. {deleted_count} records deleted.")
        refresh_table()
        refresh_comboboxes()
    except Exception as e:
        messagebox.showerror("Error", f"Failed to wipe database: {str(e)}")

def toggle_dimension_format():
    global show_dimensions_in_feet
    show_dimensions_in_feet = not show_dimensions_in_feet
    dimension_format_btn.config(text=f"Show Dimensions in {'Inches' if show_dimensions_in_feet else 'Feet/Inches'}")
    refresh_table(current_filters)  # Refresh to apply the new format

# Initialize the main window
root = tk.Tk()
root.title("Inventory Manager")

# Create a notebook (tabbed interface)
notebook = ttk.Notebook(root)
notebook.pack(fill='both', expand=True, padx=10, pady=10)

# Create tabs
add_edit_tab = ttk.Frame(notebook)
view_tab = ttk.Frame(notebook)
notebook.add(add_edit_tab, text="Add/Edit")
notebook.add(view_tab, text="View Inventory")

# Title at the top of the Add/Edit tab
tk.Label(add_edit_tab, text="Environmental Pneumatics Inventory", 
         font=("Arial", 14, "bold")).grid(row=0, column=0, columnspan=2, pady=10)

# Entry section with comboboxes in the Add/Edit tab
entry_labels = [
    ("Barcode:", "barcode"),  # Add this line
    ("Shelf:", "shelf"), ("Thickness:", "thickness"), ("Metal Type:", "metal_type"),
    ("Dimensions:", "dimensions"), ("Location:", "location"), ("Quantity:", "quantity"),
    ("Sheet size:", "usable_scrap"), ("Date (YYYY-MM-DD):", "date")
]
entry_comboboxes = {}
for idx, (label, col) in enumerate(entry_labels):
    tk.Label(add_edit_tab, text=label).grid(row=idx+1, column=0, sticky='e', padx=5, pady=2)
    if col == "barcode":
        entry = tk.Entry(add_edit_tab, width=25)
        entry.grid(row=idx+1, column=1, padx=5, pady=2)
        entry_comboboxes[col] = entry
        entry.bind("<Return>", lambda event: [scan_and_update_quantity(), show_barcode_image()])
        entry.bind("<FocusOut>", lambda event: show_barcode_image())
    else:
        entry = ttk.Combobox(add_edit_tab, state="normal", width=25)
        entry.grid(row=idx+1, column=1, padx=5, pady=2)
        entry_comboboxes[col] = entry

shelf_entry = entry_comboboxes["shelf"]
thickness_entry = entry_comboboxes["thickness"]
metal_type_entry = entry_comboboxes["metal_type"]
dimensions_entry = entry_comboboxes["dimensions"]
location_entry = entry_comboboxes["location"]
quantity_entry = entry_comboboxes["quantity"]
usable_scrap_entry = entry_comboboxes["usable_scrap"]
date_entry = entry_comboboxes["date"]

# Buttons for entry operations
button_frame = tk.Frame(add_edit_tab)
button_frame.grid(row=10, column=0, columnspan=2, pady=10)
tk.Button(button_frame, text="Update Entry", command=update_entry).grid(row=0, column=0, padx=5)
tk.Button(button_frame, text="Add New Entry", command=add_entry).grid(row=0, column=1, padx=5)

# Add backup/restore buttons
backup_restore_frame = tk.Frame(add_edit_tab)
backup_restore_frame.grid(row=11, column=0, columnspan=2, pady=5)

tk.Button(backup_restore_frame, text="Backup Database", 
          command=backup_database, 
          bg="green", fg="white").grid(row=0, column=0, padx=5)

tk.Button(backup_restore_frame, text="Restore from Backup", 
          command=restore_from_backup,
          bg="blue", fg="white").grid(row=0, column=1, padx=5)

# Add wipe database button with warning styling
wipe_btn = tk.Button(
    add_edit_tab, 
    text="WIPE DATABASE", 
    command=wipe_database,
    bg="red", 
    fg="white", 
    font=("Arial", 10, "bold")
)
wipe_btn.grid(row=12, column=0, columnspan=2, pady=10)

# Set the window size
root.geometry("800x650")  # Width x Height

columns = ("barcode", "shelf", "thickness", "metal_type", "dimensions", "location", "quantity", "usable_scrap", "date")
# Treeview for visualization with scrollbars
tree_frame = ttk.Frame(view_tab)
tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

tree_scroll_y = ttk.Scrollbar(tree_frame)
tree_scroll_y.pack(side="right", fill="y")

tree_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal")
tree_scroll_x.pack(side="bottom", fill="x")

tree = ttk.Treeview(tree_frame, columns=columns, show="headings", 
                   yscrollcommand=tree_scroll_y.set, 
                   xscrollcommand=tree_scroll_x.set)

# Configure column widths to be smaller
for col in columns:
    # Special case for usable_scrap column to display as Sheet size
    if col == "usable_scrap":
        tree.heading(col, text="Sheet size", 
                     command=lambda c=col: treeview_sort_column(tree, c, False))
    else:
        tree.heading(col, text=col.capitalize(), 
                     command=lambda c=col: treeview_sort_column(tree, c, False))
    tree.column(col, width=100)  # Smaller width

tree.pack(fill="both", expand=True)

# Connect scrollbars to the treeview
tree_scroll_y.config(command=tree.yview)
tree_scroll_x.config(command=tree.xview)

# Action buttons for operations on selected rows
action_frame = tk.Frame(view_tab)
action_frame.pack(fill="x", padx=5, pady=5)

tk.Button(action_frame, text="Delete Entry", command=delete_entry).pack(side="left", padx=5)
tk.Button(action_frame, text="Increase Quantity", command=increment_quantity).pack(side="left", padx=5)
tk.Button(action_frame, text="Decrease Quantity", command=decrement_quantity).pack(side="left", padx=5)
tk.Button(action_frame, text="Fix Field", command=fix_field).pack(side="left", padx=5)

# Create dimension format button but define toggle function afterward
dimension_format_btn = tk.Button(action_frame, text="Show Dimensions in Feet/Inches")
dimension_format_btn.pack(side="left", padx=5)

# Update the button command after function is defined
dimension_format_btn.config(command=toggle_dimension_format)

# Add export buttons
export_frame = tk.Frame(view_tab)
export_frame.pack(fill="x", padx=5, pady=5)

tk.Button(export_frame, text="Export to CSV", command=export_to_csv).pack(side="left", padx=5)
tk.Button(export_frame, text="Export for ProNest", command=export_to_pronest, 
         bg="#007ACC", fg="white").pack(side="left", padx=5)

filter_frame = ttk.LabelFrame(view_tab, text="Filters")
filter_frame.pack(fill="x", padx=5, pady=5)

setup_filter_section()  # Call this first to create filter_comboboxes
refresh_table()
refresh_comboboxes()  # Then call this after filter_comboboxes exists

def scan_and_update_quantity():
    barcode = entry_comboboxes["barcode"].get().strip()
    if not barcode:
        messagebox.showwarning("No Barcode", "Please scan or enter a barcode.")
        return

    # Search for the item by barcode
    try:
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        cur.execute("SELECT quantity, shelf, thickness, metal_type, dimensions, location FROM inventory WHERE barcode = %s", (barcode,))
        result = cur.fetchone()
        if not result:
            messagebox.showwarning("Not Found", "No item found with that barcode.")
            cur.close()
            conn.close()
            return

        current_quantity = result[0]
        # Ask user if they want to add or remove quantity
        action = messagebox.askquestion("Update Quantity", "Add to quantity? (No = Remove)")
        if action == "yes":
            amount = tk.simpledialog.askinteger("Add Quantity", "Enter quantity to add:", minvalue=1)
            if amount is None:
                cur.close()
                conn.close()
                return
            new_quantity = current_quantity + amount
        else:
            amount = tk.simpledialog.askinteger("Remove Quantity", "Enter quantity to remove:", minvalue=1)
            if amount is None:
                cur.close()
                conn.close()
                return
            new_quantity = max(0, current_quantity - amount)

        # Update the quantity in the database
        cur.execute(
            "UPDATE inventory SET quantity = %s WHERE barcode = %s",
            (new_quantity, barcode)
        )
        conn.commit()
        cur.close()
        conn.close()
        messagebox.showinfo("Success", f"Quantity updated to {new_quantity}.")
        refresh_table(current_filters)
    except Exception as e:
        messagebox.showerror("Error", str(e))

def generate_barcode_image(barcode_value, filename_no_exit):
    # Adjust writer options for optimal scanning
    writer_options = {
        "module_width": 0.6,       # Much thicker bars for reliable scanning
        "module_height": 20.0,     # Taller bars for better scanning
        "quiet_zone": 10,          # More quiet zone (white space) on sides
        "font_size": 8,            # Smaller font to avoid overlapping
        "text_distance": 6.0,      # Even more space between barcode and text
        "write_text": True,        # Include text below the barcode
        "dpi": 300                 # High resolution
    }
    
    # Try Code39 which can be easier to scan with some readers
    try:
        code = barcode.get('code39', barcode_value, writer=ImageWriter())
        code.save(filename_no_exit, options=writer_options)
    except:
        # Fall back to Code128 if Code39 fails (e.g., unsupported characters)
        code = barcode.get('code128', barcode_value, writer=ImageWriter())
        code.save(filename_no_exit, options=writer_options)
        

# Replace the generate_all_barcodes function with this version that doesn't rely on ID
def generate_all_barcodes():
    try:
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        
        # Get all items from inventory
        cur.execute("""
            SELECT shelf, thickness, metal_type, dimensions, barcode, location 
            FROM inventory 
            ORDER BY metal_type, thickness
        """)
        items = cur.fetchall()
        
        generated_count = 0
        for shelf, thickness, metal_type, dimensions, current_barcode, location in items:
            # If item already has a barcode, use it, otherwise generate a new one
            if not current_barcode or not str(current_barcode).strip():
                timestamp = datetime.now().strftime("%y%m%d%H%M%S")[2:]
                material_code = ''.join(word[0].upper() for word in str(metal_type).split()[:2]) if metal_type else "XX"
                unique_id = f"{shelf}-{thickness}-{material_code}-{timestamp}"
                barcode_value = f"EP-{thickness}-{material_code}-{unique_id}"
                
                # Update the database with this barcode
                cur.execute("""
                    UPDATE inventory 
                    SET barcode = %s 
                    WHERE shelf = %s AND thickness = %s AND metal_type = %s AND dimensions = %s AND location = %s
                """, (barcode_value, shelf, thickness, metal_type, dimensions, location))
                if cur.rowcount == 0:
                    print(f"WARNING: No row updated for {shelf}, {thickness}, {metal_type}, {dimensions}, {location}")
                else:
                    conn.commit()
                    generated_count += 1
            else:
                barcode_value = current_barcode
                
            # Generate image for the barcode
            filename_no_ext = f"barcode_{sanitize_filename(barcode_value)}"
            try:
                generate_barcode_image(barcode_value, filename_no_ext)
            except Exception as img_err:
                print(f"Error generating image for {barcode_value}: {img_err}")
            
        cur.close()
        conn.close()
        
        # Refresh the data in both views
        refresh_table(current_filters)
        load_barcode_items()
        
        if generated_count > 0:
            messagebox.showinfo("Success", f"Generated {generated_count} new barcodes and updated inventory.")
        else:
            messagebox.showinfo("Success", "All items already had barcodes. Image files were created.")
            
    except Exception as e:
        messagebox.showerror("Error", f"Barcode generation failed: {str(e)}")
        print(f"Error details: {str(e)}")  # Print to console for debugging

# Barcode display area (add after the Generate Barcodes button)
barcode_display_frame = tk.Frame(add_edit_tab)
barcode_display_frame.grid(row=14, column=0, columnspan=2, pady=5)
barcode_image_label = tk.Label(barcode_display_frame)
barcode_image_label.pack()

# Add this after the barcode display frame setup
generate_barcode_frame = tk.Frame(add_edit_tab)
generate_barcode_frame.grid(row=13, column=0, columnspan=2, pady=5)

# Generate barcode for current item
tk.Button(
    generate_barcode_frame, 
    text="Generate Barcode", 
    command=lambda: generate_and_show_barcode()
).pack(side="left", padx=5)

# Generate barcodes for all items
tk.Button(
    generate_barcode_frame, 
    text="Generate All Barcodes", 
    command=generate_all_barcodes
).pack(side="left", padx=5)

def generate_and_show_barcode():
    barcode_value = entry_comboboxes["barcode"].get().strip()
    if not barcode_value:
        messagebox.showwarning("No Barcode", "Please enter a barcode value first.")
        return

    filename_no_ext = f"barcode_{sanitize_filename(barcode_value)}"
    generate_barcode_image(barcode_value, filename_no_ext)
    filename = filename_no_ext + ".png"
    try:
        show_barcode_image()
        messagebox.showinfo("Success", f"Barcode generated as {filename}")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to generate barcode: {str(e)}")

def show_barcode_image():
    barcode_value = entry_comboboxes["barcode"].get().strip()
    if not barcode_value:
        barcode_image_label.config(image='', text='No barcode')
        return
    filename_no_ext = f"barcode_{sanitize_filename(barcode_value)}"
    filename = filename_no_ext + ".png"  # Use this for loading/displaying
    try:
        img = Image.open(filename)
        # Use newer PIL resize with resampling parameter
        img = img.resize((250, 80), Image.LANCZOS if hasattr(Image, 'LANCZOS') else Image.ANTIALIAS)
        img_tk = ImageTk.PhotoImage(img)
        barcode_image_label.img_tk = img_tk  # Keep reference!
        barcode_image_label.config(image=img_tk, text='')
    except Exception as e:
        barcode_image_label.config(image='', text='Barcode image not found')

# Add a new tab for barcode printing/viewing (after the tab creation code)
barcode_tab = ttk.Frame(notebook)
notebook.add(barcode_tab, text="Barcodes")

# Barcode printing section
barcode_print_frame = ttk.LabelFrame(barcode_tab, text="Print Barcodes")
barcode_print_frame.pack(fill="x", padx=10, pady=10, expand=False)

tk.Label(barcode_print_frame, text="Select items to print barcodes for:").pack(anchor="w", padx=10, pady=5)

# Create a treeview for barcode selection
barcode_tree_frame = ttk.Frame(barcode_print_frame)
barcode_tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

barcode_tree = ttk.Treeview(barcode_tree_frame, columns=("barcode", "shelf", "thickness", "metal_type", "dimensions", "quantity"), show="headings")
for col in ("barcode", "shelf", "thickness", "metal_type", "dimensions", "quantity"):
    barcode_tree.heading(col, text=col.capitalize())
    barcode_tree.column(col, width=100)

barcode_tree.pack(fill="both", expand=True, side="left")
barcode_scroll = ttk.Scrollbar(barcode_tree_frame, orient="vertical", command=barcode_tree.yview)
barcode_scroll.pack(side="right", fill="y")
barcode_tree.configure(yscrollcommand=barcode_scroll.set)

# Function to load items into barcode tree
def load_barcode_items():
    for row in barcode_tree.get_children():
        barcode_tree.delete(row)
    try:
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        # Show all items, even those without barcodes
        cur.execute("SELECT barcode, shelf, thickness, metal_type, dimensions, quantity FROM inventory ORDER BY metal_type, thickness")
        for row in cur.fetchall():
            barcode_tree.insert("", "end", values=row)
        cur.close()
        conn.close()
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load barcode items: {str(e)}")

# Button frame for barcode operations
barcode_btn_frame = ttk.Frame(barcode_print_frame)
barcode_btn_frame.pack(fill="x", padx=5, pady=10)

# Load barcode items button
tk.Button(barcode_btn_frame, text="Load Items", command=load_barcode_items).pack(side="left", padx=5)

# View selected barcode
def view_selected_barcode():
    selected = barcode_tree.selection()
    if not selected:
        messagebox.showwarning("No Selection", "Please select an item to view its barcode")
        return
    
    barcode_val = barcode_tree.item(selected[0], "values")[0]
    if not barcode_val:
        messagebox.showwarning("No Barcode", "Selected item has no barcode")
        return
    
    # Create popup to display barcode
    popup = tk.Toplevel()
    popup.title(f"Barcode: {barcode_val}")
    
    # Generate barcode image if needed
    filename = f"barcode_{barcode_val.replace(' ', '_')}.png"
    try:
        if not os.path.exists(filename):
            generate_barcode_image(barcode_val, filename)
        
        # Display the barcode
        img = Image.open(filename)
        img = img.resize((300, 100), Image.LANCZOS if hasattr(Image, 'LANCZOS') else Image.ANTIALIAS)
        img_tk = ImageTk.PhotoImage(img)
        
        label = tk.Label(popup, image=img_tk)
        label.img_tk = img_tk  # Keep reference
        label.pack(padx=20, pady=20)
        
        # Add print button
        tk.Button(popup, text="Print", command=lambda: os.startfile(filename) if os.name == 'nt' else messagebox.showinfo("Print", f"Barcode saved as {filename}")).pack(pady=10)
        
    except Exception as e:
        tk.Label(popup, text=f"Error displaying barcode: {str(e)}").pack(padx=20, pady=20)

# Add view barcode button
tk.Button(barcode_btn_frame, text="View Selected Barcode", command=view_selected_barcode).pack(side="left", padx=5)

# Batch generate multiple barcodes
def generate_selected_barcodes():
    selected = barcode_tree.selection()
    if not selected:
        messagebox.showwarning("No Selection", "Please select items to generate barcodes for")
        return
    
    barcodes_generated = 0
    for item in selected:
        barcode_val = barcode_tree.item(item, "values")[0]
        if barcode_val:
            filename_no_ext = f"barcode_{sanitize_filename(barcode_val)}"
            try:
                generate_barcode_image(barcode_val, filename_no_ext)
                barcodes_generated += 1
            except Exception:
                continue
    
    messagebox.showinfo("Success", f"Generated {barcodes_generated} barcodes successfully.")

# Add generate barcodes button for batch generation
tk.Button(barcode_btn_frame, text="Generate Selected Barcodes", command=generate_selected_barcodes).pack(side="left", padx=5)

# Import os for file operations
import os

# Make sure these lines are at the VERY END of your script

# Load items in the barcode view when the tab is first shown
load_barcode_items()

print("Starting mainloop")
root.mainloop()

def setup_database_if_needed():
    """Ensure database has required columns for barcode operations"""
    try:
        conn = psycopg2.connect(
            dbname="inventory_db",
            user="postgres",
            password="MANman1@6",
            host="192.168.0.90",
            port="5432"
        )
        cur = conn.cursor()
        
        # Check if id column exists, if not, create it
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='inventory' AND column_name='id') THEN
                    -- Add ID column
                    ALTER TABLE inventory ADD COLUMN id SERIAL PRIMARY KEY;
                END IF;
            END
            $$;
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("Database setup completed successfully")
    except Exception as e:
        print(f"Database setup error: {str(e)}")

# Call it here, right after the function definition but before other database operations
setup_database_if_needed()

def view_barcode_large():
    barcode_value = entry_comboboxes["barcode"].get().strip()
    if not barcode_value:
        messagebox.showwarning("No Barcode", "Please enter a barcode value first.")
        return

    filename_no_ext = f"barcode_{sanitize_filename(barcode_value)}"
    filename = filename_no_ext + ".png"
    
    # Generate the barcode if it doesn't exist
    if not os.path.exists(filename):
        generate_barcode_image(barcode_value, filename_no_ext)
    
    # Create a popup window to display a large barcode
    popup = tk.Toplevel(root)
    popup.title(f"Large Barcode: {barcode_value}")
    
    try:
        img = Image.open(filename)
        # Create a much larger version for easier scanning
        img = img.resize((600, 200), Image.LANCZOS if hasattr(Image, 'LANCZOS') else Image.ANTIALIAS)
        img_tk = ImageTk.PhotoImage(img)
        
        label = tk.Label(popup, image=img_tk)
        label.img_tk = img_tk  # Keep reference
        label.pack(padx=20, pady=20)
        
        # Add print button for direct printing
        tk.Button(popup, text="Print Barcode", 
                 command=lambda: os.startfile(filename) if os.name == 'nt' else 
                 messagebox.showinfo("Print", f"Barcode saved as {filename}")).pack(pady=10)
        
    except Exception as e:
        tk.Label(popup, text=f"Error displaying barcode: {str(e)}").pack(padx=20, pady=20)
