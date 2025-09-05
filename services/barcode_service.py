# -*- coding: utf-8 -*-
"""
Barcode service (custom naming adjustments)

Adjustments:
 - Black metal -> GB.
 - Aluminum thickness decimal token without leading zero (.04, .125, .063).
 - Plate fractions 1/4 -> 14, 3/8 -> 38, 1/2 -> 12 etc.
 - Gauge (other materials) stays 2-digit (e.g., 12).
 - Format: <THICKNESS_TOKEN><MATERIAL_CODE><W><LL>
"""

from __future__ import annotations
from datetime import datetime
import os
import re
from typing import Iterable, Tuple, Dict, Optional, List

import barcode
from barcode.writer import ImageWriter

from utils.formatting import sanitize_filename
from db.queries import fetch_all
from db.connection import get_cursor

# ------------------------------------------------------------------
# Visual tuning
# ------------------------------------------------------------------
BARCODE_TEXT_DISTANCE = 12.0

BARCODE_PROFILES: Dict[str, dict] = {
    "SAMPLE": {"module_width": 1.0, "module_height": 55.0, "quiet_zone": 15,
               "font_size": 20, "text_distance": BARCODE_TEXT_DISTANCE, "write_text": True, "dpi": 300},
    "MEDIUM": {"module_width": 0.85, "module_height": 60.0, "quiet_zone": 18,
               "font_size": 18, "text_distance": BARCODE_TEXT_DISTANCE - 1, "write_text": True, "dpi": 300},
    "LONG": {"module_width": 0.70, "module_height": 65.0, "quiet_zone": 20,
             "font_size": 16, "text_distance": BARCODE_TEXT_DISTANCE - 2, "write_text": True, "dpi": 300},
}

DEFAULT_WRITER_OPTS = {
    "module_width": 0.6,
    "module_height": 20.0,
    "quiet_zone": 10,
    "font_size": 8,
    "text_distance": BARCODE_TEXT_DISTANCE - 4,
    "write_text": True,
    "dpi": 300
}

# ------------------------------------------------------------------
# File helper
# ------------------------------------------------------------------
def build_barcode_filename(barcode_value: str, directory: str = ".") -> str:
    return os.path.join(directory, f"barcode_{sanitize_filename(barcode_value)}.png")

# ------------------------------------------------------------------
# Hash compaction fallback
# ------------------------------------------------------------------
def generate_compact_code(source: str, length: int = 10) -> str:
    import hashlib
    h = hashlib.sha1(source.encode("utf-8")).hexdigest()
    num = int(h, 16)
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    chars = []
    while num and len(chars) < 32:
        num, r = divmod(num, 36)
        chars.append(alphabet[r])
    base36 = ''.join(reversed(chars)) or "0"
    return base36[:length]

def ensure_compact_if_needed(code: str, max_len: int = 16, target_len: int = 10) -> str:
    return code if len(code) <= max_len else generate_compact_code(code, target_len)

# ------------------------------------------------------------------
# Material / thickness formatting rules
# ------------------------------------------------------------------
_BASE_MATERIAL_CODES = {
    "GALVANIZED": "GG", "GALV": "GG", "GAL": "GG",
    "STAINLESS": "SS", "STAINLESS STEEL": "SS", "SS": "SS",
    "CARBON": "CS", "CARBON STEEL": "CS", "MILD STEEL": "CS", "MS": "CS",
    "ALUMINUM": "AL", "ALUMINIUM": "AL", "ALUM": "AL", "AL": "AL",
    "BRASS": "BR", "COPPER": "CU", "STEEL": "ST"
}

MATERIAL_CODE_OVERRIDES = {
    "BLACK": "GB",
    "BLACK STEEL": "GB",
    "BLACK METAL": "GB",
}

_DIMENSION_RE = re.compile(r'(\d+(?:\.\d+)?)\s*[xX*]\s*(\d+(?:\.\d+)?)')
_FRACTION_RE = re.compile(r'^\s*(\d+)\s*/\s*(\d+)\s*$')
_DECIMAL_RE = re.compile(r'^\s*0?\.(\d{1,4})')

def _normalize(s: Optional[str]) -> str:
    return (s or "").strip().upper()

def _material_code(metal_type: Optional[str]) -> str:
    key = _normalize(metal_type)
    if not key:
        return "XX"
    for k, v in MATERIAL_CODE_OVERRIDES.items():
        if key.startswith(k):
            return v
    if key in _BASE_MATERIAL_CODES:
        return _BASE_MATERIAL_CODES[key]
    first = key.split()[0]
    if first in _BASE_MATERIAL_CODES:
        return _BASE_MATERIAL_CODES[first]
    letters = ''.join(ch for ch in first if ch.isalpha())[:2].upper()
    return letters.ljust(2, "X") if letters else "XX"

def _parse_dimensions(dimensions: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    if not dimensions:
        return None, None
    m = _DIMENSION_RE.search(dimensions.replace('"', '').replace("in", ""))
    if not m:
        return None, None
    try:
        a = float(m.group(1)); b = float(m.group(2))
    except ValueError:
        return None, None
    return max(a, b), min(a, b)

def _parse_fraction(thickness: str) -> Optional[Tuple[int, int]]:
    m = _FRACTION_RE.match(thickness)
    if not m:
        return None
    try:
        num = int(m.group(1)); den = int(m.group(2))
        if num > 0 and den > 0:
            return num, den
    except ValueError:
        return None
    return None

def _format_aluminum_thickness(raw: str) -> Optional[str]:
    s = raw.strip().lower().replace('"', '')
    if '/' in s:
        frac = _parse_fraction(s)
        if frac:
            return f"{frac[0]}{frac[1]}"
    if s.startswith('0') and len(s) > 1:
        s = s[1:]
    if not s.startswith('.'):
        if not _DECIMAL_RE.match(s) and '.' not in s:
            return None
    if '.' in s:
        _, tail = s.split('.', 1)
        tail = tail[:3].rstrip('0')
        return f".{tail}" if tail else ".0"
    return s

def _format_plate_thickness(raw: str) -> Optional[str]:
    s = raw.strip().replace('"', '').lower()
    frac = _parse_fraction(s)
    if not frac and '.' in s:
        try:
            val = float(s)
            common = {
                (1, 8): 0.125, (1, 4): 0.25, (3, 8): 0.375, (1, 2): 0.5,
                (5, 8): 0.625, (3, 4): 0.75, (7, 8): 0.875
            }
            for (n, d), fval in common.items():
                if abs(val - fval) < 0.002:
                    frac = (n, d); break
        except ValueError:
            pass
    if frac:
        n, d = frac
        return f"{n}{d}"
    digits = ''.join(ch for ch in s if ch.isdigit())
    return digits[:3] or None

def _extract_gauge_numeric(thickness: str) -> Optional[str]:
    m = re.search(r'(\d+)', thickness)
    if not m:
        return None
    return m.group(1)[:2].zfill(2)

def format_thickness_token(thickness: Optional[str], metal_type: Optional[str]) -> Optional[str]:
    if not thickness:
        return None
    mt = _normalize(metal_type)
    raw = thickness.strip()
    if 'PLATE' in mt or mt.startswith('PL ') or mt == 'PL' or mt.endswith(' PL'):
        return _format_plate_thickness(raw)
    if 'AL' in mt:
        at = _format_aluminum_thickness(raw)
        if at:
            return at
    return _extract_gauge_numeric(raw)

def derive_compact_barcode_value(thickness: Optional[str],
                                 metal_type: Optional[str],
                                 dimensions: Optional[str]) -> Optional[str]:
    thickness_token = format_thickness_token(thickness, metal_type)
    mat_code = _material_code(metal_type)
    length_in, width_in = _parse_dimensions(dimensions)
    if thickness_token is None or length_in is None or width_in is None:
        return None
    width_ft = int(round(width_in / 12.0))
    length_ft = int(round(length_in / 12.0))
    if width_ft <= 0 or length_ft <= 0:
        return None
    if length_ft < width_ft:
        length_ft, width_ft = width_ft, length_ft
    return f"{thickness_token}{mat_code}{width_ft}{length_ft:02d}"

_COMPACT_PATTERN = re.compile(r'^[0-9\.]{1,4}[A-Z]{2}\d{1,2}\d{2}[A-Z]?$')

def _is_legacy_barcode(bc: str) -> bool:
    return (not bc) or bc.startswith("EP-") or len(bc) > 16

def _looks_compact(bc: str) -> bool:
    return bool(_COMPACT_PATTERN.fullmatch(bc))

def _ensure_unique(code: str, cur) -> str:
    base = code
    idx = 0
    def alpha(n: int) -> str:
        chars = []
        while True:
            n, r = divmod(n, 26)
            chars.append(chr(65 + r))
            if n == 0:
                break
            n -= 1
        return ''.join(reversed(chars))
    while True:
        cur.execute("SELECT 1 FROM inventory WHERE barcode=%s LIMIT 1", (code,))
        if not cur.fetchone():
            return code
        code = f"{base}{alpha(idx)}"
        idx += 1

# ------------------------------------------------------------------
# Barcode image generation
# ------------------------------------------------------------------
def _pick_profile_for_length(length: int) -> str:
    if length <= 12: return "SAMPLE"
    if length <= 18: return "MEDIUM"
    return "LONG"

def _save_barcode(sym: str, value: str, writer_opts: dict, directory: str) -> str:
    filename_no_ext = build_barcode_filename(value, directory)[:-4]
    code_obj = barcode.get(sym, value, writer=ImageWriter())
    code_obj.save(filename_no_ext, options=writer_opts)
    return filename_no_ext + ".png"

def generate_barcode_image(barcode_value: str,
                           directory: str = ".",
                           writer_options: dict | None = None) -> str:
    if not barcode_value:
        raise ValueError("Empty barcode value")
    writer_opts = writer_options or BARCODE_PROFILES[_pick_profile_for_length(len(barcode_value))]
    try:
        return _save_barcode('code128', barcode_value, writer_opts, directory)
    except Exception:
        return _save_barcode('code39', barcode_value, writer_opts, directory)

def generate_scannable_barcode(barcode_value: str,
                               directory: str = ".",
                               force_compact: bool = False,
                               overwrite: bool = True,
                               profile: str | None = None,
                               compact_max_len: int = 16,
                               compact_target_len: int = 10,
                               **override_opts) -> str:
    if not barcode_value:
        raise ValueError("Empty barcode value")
    original = barcode_value
    if force_compact:
        barcode_value = ensure_compact_if_needed(barcode_value, compact_max_len, compact_target_len)
    chosen_profile = profile or _pick_profile_for_length(len(barcode_value))
    base_opts = BARCODE_PROFILES.get(chosen_profile, BARCODE_PROFILES["LONG"])
    writer_opts = {**base_opts, **override_opts}
    path = build_barcode_filename(barcode_value, directory)
    if not overwrite and os.path.exists(path):
        return path
    try:
        final_path = _save_barcode('code128', barcode_value, writer_opts, directory)
    except Exception:
        final_path = _save_barcode('code39', barcode_value, writer_opts, directory)
    if force_compact and barcode_value != original:
        try:
            with open(final_path + ".meta", "w", encoding="utf-8") as f:
                f.write(f"original={original}\ncompact={barcode_value}\n")
        except Exception:
            pass
    return final_path

def get_or_create_barcode_image(barcode_value: str,
                                ensure_scannable: bool = True,
                                directory: str = ".") -> str:
    path = build_barcode_filename(barcode_value, directory)
    if ensure_scannable:
        return generate_scannable_barcode(barcode_value, directory=directory,
                                          overwrite=not os.path.exists(path))
    if not os.path.exists(path):
        return generate_barcode_image(barcode_value, directory=directory)
    return path

# ------------------------------------------------------------------
# Inventory bulk helpers
# ------------------------------------------------------------------
def get_barcode_items():
    return fetch_all("""
        SELECT barcode, shelf, thickness, metal_type, dimensions, quantity
        FROM inventory ORDER BY metal_type, thickness
    """)

def generate_all_barcodes_service() -> Tuple[int, int]:
    rows = fetch_all("""
        SELECT shelf, thickness, metal_type, dimensions, barcode, location
        FROM inventory ORDER BY metal_type, thickness
    """)
    generated = 0
    total = len(rows)
    with get_cursor() as cur:
        for shelf, thickness, metal_type, dimensions, current_barcode, location in rows:
            bc = current_barcode
            if not bc or not str(bc).strip():
                ts = datetime.now().strftime("%y%m%d%H%M%S")[2:]
                mat_code = ''.join(word[0].upper() for word in str(metal_type).split()[:2]) if metal_type else "XX"
                bc = f"EP-{thickness}-{mat_code}-{ts}"
                cur.execute("""
                    UPDATE inventory
                    SET barcode=%s
                    WHERE shelf=%s AND thickness=%s AND metal_type=%s AND dimensions=%s AND location=%s
                """, (bc, shelf, thickness, metal_type, dimensions, location))
                if cur.rowcount:
                    generated += 1
            try:
                generate_scannable_barcode(bc, overwrite=True)
            except Exception:
                pass
    return generated, total

def _derive_or_fallback(thickness, metal_type, dimensions, shelf, rec_id) -> str:
    derived = derive_compact_barcode_value(
        str(thickness) if thickness else None,
        str(metal_type) if metal_type else None,
        str(dimensions) if dimensions else None
    )
    if not derived:
        composite = f"{shelf}|{thickness}|{metal_type}|{dimensions}|{rec_id}"
        derived = generate_compact_code(composite, length=8)
    return derived

def generate_compact_barcodes_service(migrate_legacy: bool = True,
                                      regenerate_images: bool = True,
                                      force_rebuild_all: bool = False,
                                      dry_run: bool = False) -> Tuple[int, int, int, int]:
    """
    Returns (assigned_new, migrated_existing, rewritten_total, total_rows)
    """
    rows = fetch_all("""
        SELECT id, shelf, thickness, metal_type, dimensions, barcode
        FROM inventory ORDER BY id
    """)
    total = len(rows)
    assigned = migrated = rewritten = 0

    with get_cursor() as cur:
        for rec_id, shelf, thickness, metal_type, dimensions, bc in rows:
            need_rebuild = force_rebuild_all
            if not force_rebuild_all:
                if not bc or not str(bc).strip():
                    need_rebuild = True
                elif migrate_legacy and _is_legacy_barcode(bc):
                    need_rebuild = True
                elif migrate_legacy and not _looks_compact(bc):
                    need_rebuild = True

            if not need_rebuild:
                if regenerate_images and not dry_run:
                    try:
                        generate_scannable_barcode(bc, overwrite=True)
                    except Exception:
                        pass
                continue

            new_code_raw = _derive_or_fallback(thickness, metal_type, dimensions, shelf, rec_id)
            unique_code = _ensure_unique(new_code_raw, cur) if not dry_run else new_code_raw

            if not bc or not bc.strip():
                assigned += 1
            else:
                migrated += 1
            rewritten += 1

            if not dry_run:
                cur.execute("UPDATE inventory SET barcode=%s WHERE id=%s", (unique_code, rec_id))
                if regenerate_images:
                    try:
                        generate_scannable_barcode(unique_code, overwrite=True)
                    except Exception:
                        pass

    return assigned, migrated, rewritten, total

def generate_selected_barcodes_service(barcode_values: Iterable[str]) -> int:
    count = 0
    for bc in barcode_values:
        if not bc:
            continue
        try:
            generate_scannable_barcode(bc, overwrite=True)
            count += 1
        except Exception:
            continue
    return count

def preview_compact_barcode_changes(force_rebuild_all: bool = False,
                                    migrate_legacy: bool = True,
                                    sample: int = 25) -> List[Tuple[int, str, str]]:
    rows = fetch_all("""
        SELECT id, shelf, thickness, metal_type, dimensions, barcode
        FROM inventory ORDER BY id
    """)
    results: List[Tuple[int, str, str]] = []
    for rec_id, shelf, thickness, metal_type, dimensions, bc in rows:
        need_rebuild = force_rebuild_all
        if not force_rebuild_all:
            if not bc or not str(bc).strip():
                need_rebuild = True
            elif migrate_legacy and _is_legacy_barcode(bc):
                need_rebuild = True
            elif migrate_legacy and not _looks_compact(bc):
                need_rebuild = True
        if not need_rebuild:
            continue
        new_raw = _derive_or_fallback(thickness, metal_type, dimensions, shelf, rec_id)
        results.append((rec_id, bc, new_raw))
        if len(results) >= sample:
            break
    return results

def test_barcode_naming_cases() -> Dict[str, str]:
    cases = [
        ("12 gauge black 120x60", derive_compact_barcode_value("12", "Black Steel", "120x60")),
        ("12 gauge galvanized 120x60", derive_compact_barcode_value("12", "Galvanized", "120x60")),
        ("0.040 aluminum 96x48", derive_compact_barcode_value("0.040", "Aluminum", "96x48")),
        (".063 aluminum 144x48", derive_compact_barcode_value(".063", "AL", "144x48")),
        ("1/4 plate 96x48", derive_compact_barcode_value("1/4", "PLATE", "96x48")),
        ("3/8 plate 120x60", derive_compact_barcode_value("3/8", "PL", "120x60")),
        ("1/2 plate 96x48", derive_compact_barcode_value("1/2", "PL", "96x48")),
        ("Decimal plate .25 96x48", derive_compact_barcode_value(".25", "Plate", "96x48")),
        ("Fallback no dims", derive_compact_barcode_value("12", "Black", None)),
    ]
    return {k: (v or "None") for k, v in cases}

# ------------------------------------------------------------------
# Printable / PDF
# ------------------------------------------------------------------
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    _REPORTLAB_AVAILABLE = True
except Exception:
    _REPORTLAB_AVAILABLE = False

from PIL import Image

def generate_barcode_image_pil(barcode_value: str,
                               profile: str | None = None,
                               force_compact: bool = False,
                               target_width_px: int | None = None,
                               directory: str = ".") -> Image.Image:
    path = generate_scannable_barcode(barcode_value, directory=directory,
                                      force_compact=force_compact, overwrite=True,
                                      profile=profile)
    img = Image.open(path)
    if target_width_px and target_width_px > 0:
        scale = target_width_px / img.width
        if scale != 1:
            img = img.resize((int(round(img.width * scale)),
                              int(round(img.height * scale))), Image.NEAREST)
    return img

def save_single_printable_label(barcode_value: str,
                                out_path: str,
                                width_in: float = 1.8,
                                max_height_in: float = 1.0,
                                dpi: int = 300,
                                profile: str | None = "SAMPLE",
                                force_compact: bool = False):
    px_w = int(width_in * dpi)
    px_h = int(max_height_in * dpi)
    base = generate_barcode_image_pil(barcode_value, profile=profile, force_compact=force_compact)
    if base.width > px_w:
        base = base.resize((px_w, int(base.height * (px_w / base.width))), Image.NEAREST)
    if base.width < px_w * 0.65:
        scale = (px_w * 0.8) / base.width
        base = base.resize((int(base.width * scale), int(base.height * scale)), Image.NEAREST)
    if base.height > px_h * 0.9:
        scale = (px_h * 0.9) / base.height
        base = base.resize((int(base.width * scale), int(base.height * scale)), Image.NEAREST)
    canvas_img = Image.new("RGB", (px_w, px_h), "white")
    canvas_img.paste(base, ((px_w - base.width)//2, (px_h - base.height)//2))
    canvas_img.save(out_path, dpi=(dpi, dpi))
    return out_path

def generate_barcode_sheet_pdf(barcodes: List[str],
                               pdf_path: str,
                               labels_per_row: int = 4,
                               label_width_in: float = 1.8,
                               label_height_in: float = 1.0,
                               margin_in: float = 0.5,
                               h_gap_in: float = 0.25,
                               v_gap_in: float = 0.35,
                               dpi: int = 300):
    if not _REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab not installed. Install with: pip install reportlab")
    page_w_in, page_h_in = 8.5, 11.0
    c = canvas.Canvas(pdf_path, pagesize=(page_w_in * inch, page_h_in * inch))
    x = margin_in; y = page_h_in - margin_in - label_height_in
    col = 0
    for code_val in barcodes:
        tmp_path = build_barcode_filename(f"PRINTSHEET_{code_val}")
        save_single_printable_label(code_val, tmp_path,
                                    width_in=label_width_in, max_height_in=label_height_in,
                                    dpi=dpi, profile="SAMPLE", force_compact=False)
        c.drawImage(tmp_path, x * inch, y * inch,
                    width=label_width_in * inch, height=label_height_in * inch,
                    preserveAspectRatio=True, anchor='sw')
        col += 1
        if col >= labels_per_row:
            col = 0; x = margin_in; y -= (label_height_in + v_gap_in)
            if y < margin_in:
                c.showPage(); y = page_h_in - margin_in - label_height_in
        else:
            x += (label_width_in + h_gap_in)
    c.showPage(); c.save(); return pdf_path

def export_barcodes_to_pdf(barcodes: List[str],
                           pdf_path: str,
                           labels_per_row: int = 4,
                           label_width_in: float = 1.8,
                           label_height_in: float = 1.0,
                           margin_in: float = 0.5,
                           h_gap_in: float = 0.25,
                           v_gap_in: float = 0.35,
                           dpi: int = 300) -> str:
    clean = [c.strip() for c in barcodes if c and str(c).strip()]
    if not clean:
        raise ValueError("No barcodes provided to export.")
    seen = set(); ordered = []
    for c in clean:
        if c not in seen:
            seen.add(c); ordered.append(c)
    return generate_barcode_sheet_pdf(ordered, pdf_path,
                                      labels_per_row, label_width_in, label_height_in,
                                      margin_in, h_gap_in, v_gap_in, dpi)

# ------------------------------------------------------------------
# Public exports
# ------------------------------------------------------------------
__all__ = [
    "build_barcode_filename",
    "generate_barcode_image",
    "generate_scannable_barcode",
    "get_or_create_barcode_image",
    "generate_compact_code",
    "ensure_compact_if_needed",
    "derive_compact_barcode_value",
    "generate_compact_barcodes_service",
    "get_barcode_items",
    "generate_all_barcodes_service",
    "generate_selected_barcodes_service",
    "preview_compact_barcode_changes",
    "test_barcode_naming_cases",
    "generate_barcode_image_pil",
    "save_single_printable_label",
    "generate_barcode_sheet_pdf",
    "export_barcodes_to_pdf"
]