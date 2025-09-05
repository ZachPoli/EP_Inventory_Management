# -*- coding: utf-8 -*-
from datetime import datetime
import pandas as pd

from db.queries import fetch_all
from db.connection import get_cursor
from services.inventory_service import parse_dimensions  # reuse
# inches_to_feet_inches imported in main; we do raw numbers here

GAUGE_TO_INCHES = {
    "6": 0.1935,"7": 0.1875,"8": 0.1644,"9": 0.1500,"10": 0.1350,"11": 0.1200,"12": 0.1050,
    "13": 0.0897,"14": 0.0750,"15": 0.0673,"16": 0.0600,"17": 0.0538,"18": 0.0480,"19": 0.0418,
    "20": 0.0360,"22": 0.0300,"24": 0.0240,"26": 0.0180,"28": 0.0150,"30": 0.0120
}

PRONEST_HEADERS = [
    "Description", "Plate Type", "Units", "Length", "Width", "MaterialID",
    "Material", "Thickness", "Stock Qty", "Unit Price", "Date Created",
    "Rotation", "Heat Num", "Stock Num", "Misc1", "Misc2", "Misc3",
    "Location", "Reorder limit", "Reorder quantity", "Supplier",
    "Created by", "Plate Path", "Grade"
]

def fetch_inventory_rows_for_csv():
    return fetch_all("""
        SELECT barcode, shelf, thickness, metal_type,
               dimensions, location, quantity, usable_scrap, date
        FROM inventory
    """)

def build_csv_dataframe(rows):
    columns = ("barcode","shelf","thickness","metal_type","dimensions",
               "location","quantity","usable_scrap","date")
    return pd.DataFrame([list(r) for r in rows], columns=columns)

def fetch_pronest_source_rows(visible_items=None):
    """
    visible_items: list of (shelf, thickness, metal_type, dimensions) or None
    """
    if visible_items:
        out = []
        with get_cursor() as cur:
            for shelf, thickness, metal_type, dimensions in visible_items:
                cur.execute("""
                    SELECT metal_type, thickness, dimensions, quantity, length, width,
                           location, date, shelf, usable_scrap
                    FROM inventory
                    WHERE shelf=%s AND thickness=%s AND metal_type=%s AND dimensions=%s
                """, (shelf, thickness, metal_type, dimensions))
                r = cur.fetchone()
                if r:
                    out.append(r)
        return out
    return fetch_all("""
        SELECT metal_type, thickness, dimensions, quantity, length, width,
               location, date, shelf, usable_scrap
        FROM inventory
    """)

def thickness_to_decimal(thickness_str: str):
    if not thickness_str:
        return 0.0
    s = thickness_str.strip()
    if any(g in s.upper() for g in ["G","GA","GAUGE"]):
        digits = ''.join(c for c in s if c.isdigit())
        if digits and digits in GAUGE_TO_INCHES:
            return GAUGE_TO_INCHES[digits]
        return 0.0
    if s in GAUGE_TO_INCHES:
        return GAUGE_TO_INCHES[s]
    if "/" in s:
        mapping = {"1/8":0.1250,"1/4":0.2500,"3/8":0.3750,"1/2":0.5000,"5/8":0.6250,"3/4":0.7500,"1":1.0,"7/8":0.8750}
        if s in mapping:
            return mapping[s]
        try:
            a,b = s.split('/')
            return float(a)/float(b)
        except Exception:
            return 0.0
    try:
        return float(s)
    except:
        return 0.0

def classify_material_code(metal_type, thickness_original):
    metal_type_l = (metal_type or "").lower()
    code = thickness_original or ""
    if "black" in metal_type_l:
        code += "B"
    elif "plate" in metal_type_l:
        code += "PL"
    elif "galv" in metal_type_l:
        code += "G"
    elif "aluminum" in metal_type_l or metal_type_l == "al":
        code += "AL"
    else:
        code += ''.join(w[0].upper() for w in (metal_type or "").split() if w)
    return code

def pronest_material_abbrev(metal_type):
    mt = (metal_type or "").lower()
    if "aluminum" in mt or mt == "al":
        return "AL"
    if "stainless" in mt or "ss" in mt:
        return "SS"
    return "MS"

def description_prefix(metal_type):
    mt = (metal_type or "").lower()
    if "plate" in mt: return "~"
    if "black" in mt: return "+"
    if "galv" in mt: return "-"
    if "aluminum" in mt or mt == "al": return "="
    if "stainless" in mt or "ss" in mt: return "<"
    return ""

def build_pronest_dataframe(source_rows):
    data = []
    for idx, row in enumerate(source_rows):
        (metal_type, thickness, dimensions, quantity, length, width,
         location, date_val, shelf, usable_scrap) = row

        if (not length or not width) and dimensions and 'x' in str(dimensions).lower():
            parsed = parse_dimensions(dimensions)
            if parsed:
                length, width = parsed
        length = length or 48.0
        width = width or 48.0
        length_feet = int(float(length)/12)
        width_feet = int(float(width)/12)

        thickness_str = thickness.strip() if thickness else ""
        decimal_thickness = thickness_to_decimal(thickness_str)
        material_code = classify_material_code(metal_type, thickness_str)
        prefix = description_prefix(metal_type)
        description = f"{prefix}{material_code} ({width_feet}' x {length_feet}')"
        stock_number = f"{material_code}{width_feet}{length_feet}"
        material_id = f"MAT{idx+1:03d}"
        date_created = date_val if date_val else datetime.now().strftime("%Y-%m-%d")
        qty_int = int(quantity) if quantity else 0
        reorder_limit = max(1, qty_int // 2) if qty_int else 1
        reorder_quantity = max(1, qty_int // 4) if qty_int else 1
        row_out = [
            description, "Rectangular", "Inches",
            float(length), float(width), material_id,
            pronest_material_abbrev(metal_type), decimal_thickness,
            qty_int, 0.0, date_created,
            0, "", stock_number, usable_scrap, shelf, "",
            location, reorder_limit, reorder_quantity,
            "Environmental Pneumatics", "Inventory Manager", "", ""
        ]
        data.append(row_out)
    return pd.DataFrame(data, columns=PRONEST_HEADERS)

def export_inventory_pronest_dataframe(visible_items=None):
    """
    visible_items: list of dicts or tuples (shelf, thickness, metal_type, dimensions)
    Returns pandas DataFrame (no file IO).
    """
    if visible_items:
        normalized = [(i['shelf'], i['thickness'], i['metal_type'], i['dimensions']) for i in visible_items]
        src_rows = fetch_pronest_source_rows(normalized)
    else:
        src_rows = fetch_pronest_source_rows()
    if not src_rows:
        return None
    return build_pronest_dataframe(src_rows)