# -*- coding: utf-8 -*-
import re
from datetime import datetime
from db.queries import fetch_all, fetch_one, execute
from db.connection import get_cursor

DATE_INPUT_FORMATS = [
    "%m-%d-%Y", "%m/%d/%Y",
    "%m-%d-%y", "%m/%d/%y",
    "%Y-%m-%d"
]

def normalize_date_input(raw: str):
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    for fmt in DATE_INPUT_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError("Date must be MM-DD-YYYY (e.g. 08-26-2025).")

def parse_dimensions(dim_text: str):
    if not dim_text or not isinstance(dim_text, str):
        return None
    txt = dim_text.replace("×", "x").lower().strip()  # defensive replace
    parts = [p.strip() for p in re.split(r'\bx\b', txt)]
    if len(parts) < 2:
        nums = re.findall(r'(\d+(?:\.\d+)?)\s*(?:ft|feet|\'|in|")?', txt)
        if len(nums) >= 2:
            parts = [nums[0], nums[1]]
        else:
            return None
    left, right = parts[0], parts[1]

    def to_inches(fragment: str):
        feet_marker = bool(re.search(r"(?:\bft\b|\bfeet\b|'|ft\.)", fragment))
        m = re.search(r"(\d+(?:\.\d+)?)", fragment)
        if not m:
            return 0.0
        val = float(m.group(1))
        return val * 12.0 if feet_marker else val

    length_in = to_inches(left)
    width_in = to_inches(right)
    if length_in <= 0 or width_in <= 0:
        return None
    return length_in, width_in

def extract_dimensions():
    execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='inventory' AND column_name='length') THEN
                ALTER TABLE inventory ADD COLUMN length NUMERIC;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='inventory' AND column_name='width') THEN
                ALTER TABLE inventory ADD COLUMN width NUMERIC;
            END IF;
        END
        $$;
    """)
    rows = fetch_all("SELECT dimensions FROM inventory")
    updated = 0
    with get_cursor() as cur:
        for (dim_text,) in rows:
            if not dim_text:
                continue
            parsed = parse_dimensions(dim_text)
            if not parsed:
                continue
            L, W = parsed
            if L > 0 and W > 0:
                cur.execute("""
                    UPDATE inventory
                    SET length=%s, width=%s
                    WHERE dimensions=%s
                """, (L, W, dim_text))
                if cur.rowcount > 0:
                    updated += 1
    return updated

def add_inventory_item(fields):
    quantity = int(fields["quantity"])
    date_iso = normalize_date_input(fields["date"]) if fields.get("date") else None
    sql = """
        INSERT INTO inventory
            (barcode, shelf, thickness, metal_type, dimensions, location,
             quantity, usable_scrap, date)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    params = (
        fields["barcode"], fields["shelf"], fields["thickness"], fields["metal_type"],
        fields["dimensions"], fields["location"], quantity,
        fields["usable_scrap"], date_iso
    )
    execute(sql, params)

def update_inventory_item(fields):
    quantity = int(fields["quantity"])
    date_iso = normalize_date_input(fields["date"]) if fields.get("date") else None
    sql = """
        UPDATE inventory
        SET barcode=%s, shelf=%s, thickness=%s, location=%s,
            quantity=%s, usable_scrap=%s, date=%s
        WHERE dimensions=%s AND thickness=%s AND metal_type=%s
    """
    params = (
        fields["barcode"], fields["shelf"], fields["thickness"], fields["location"],
        quantity, fields["usable_scrap"], date_iso,
        fields["dimensions"], fields["thickness"], fields["metal_type"]
    )
    return execute(sql, params)

def delete_inventory_item(row_values):
    sql = """
        DELETE FROM inventory
        WHERE shelf=%s AND thickness=%s AND metal_type=%s AND dimensions=%s
          AND location=%s AND quantity=%s AND usable_scrap=%s AND date=%s
    """
    params = (
        row_values[0], row_values[1], row_values[2], row_values[3],
        row_values[4], int(row_values[5]), row_values[6], row_values[7] if row_values[7] else None
    )
    return execute(sql, params)

def adjust_quantity(row_values, delta):
    sql = """
        UPDATE inventory
        SET quantity = GREATEST(0, quantity + %s)
        WHERE shelf=%s AND thickness=%s AND metal_type=%s
          AND dimensions=%s AND location=%s
    """
    params = (delta, row_values[0], row_values[1], row_values[2], row_values[3], row_values[4])
    return execute(sql, params)

def set_quantity_for_barcode(barcode_value, new_qty):
    return execute("UPDATE inventory SET quantity=%s WHERE barcode=%s",
                   (new_qty, barcode_value))

def get_quantity_for_barcode(barcode_value):
    row = fetch_one("SELECT quantity FROM inventory WHERE barcode=%s", (barcode_value,))
    return row[0] if row else None

# Add near other CRUD helpers (e.g. right after update_inventory_item_by_id)

def delete_inventory_item_by_id(item_id: int) -> int:
    """
    Delete inventory row by primary key id.
    Returns number of rows deleted (0 or 1).
    """
    return execute("DELETE FROM inventory WHERE id=%s", (item_id,))

def fetch_item_by_barcode(barcode: str):
    """
    Return a single inventory row by barcode or None.
    Columns: id, barcode, shelf, thickness, metal_type, dimensions, location, quantity, usable_scrap, date
    """
    if not barcode:
        return None
    row = fetch_one("""
        SELECT id, barcode, shelf, thickness, metal_type, dimensions, location,
               quantity, usable_scrap, date
        FROM inventory
        WHERE barcode=%s
        LIMIT 1
    """, (barcode,))
    return row

def update_inventory_item_by_id(item_id: int, fields: dict):
    """
    Update an inventory row (by id) with provided fields.
    Allowed keys: barcode, shelf, thickness, metal_type, dimensions,
                  location, quantity, usable_scrap, date
    Quantity coerced to int. Date normalized if present.
    """
    allowed = {"barcode", "shelf", "thickness", "metal_type", "dimensions",
               "location", "quantity", "usable_scrap", "date"}
    updates = {}
    for k, v in fields.items():
        if k in allowed:
            updates[k] = v

    if "quantity" in updates:
        updates["quantity"] = int(updates["quantity"]) if str(updates["quantity"]).strip() != "" else 0

    if "date" in updates and updates["date"]:
        updates["date"] = normalize_date_input(updates["date"])

    if not updates:
        return 0

    set_clause = ", ".join(f"{k}=%s" for k in updates.keys())
    params = list(updates.values()) + [item_id]
    return execute(f"UPDATE inventory SET {set_clause} WHERE id=%s", params)

__all__ = [
    "normalize_date_input",
    "parse_dimensions",
    "extract_dimensions",
    "add_inventory_item",
    "update_inventory_item",
    "delete_inventory_item",
    "adjust_quantity",
    "set_quantity_for_barcode",
    "get_quantity_for_barcode",
    "fetch_item_by_barcode",
    "update_inventory_item_by_id",
    "delete_inventory_item_by_id",
]