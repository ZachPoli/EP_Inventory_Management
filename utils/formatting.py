def inches_to_feet_inches(inches):
    """Convert a decimal inch value to feet and inches format."""
    try:
        inches_float = float(inches)
        feet = int(inches_float // 12)
        remaining_inches = round(inches_float % 12, 1)
        return f"{feet}' {remaining_inches}\"" if feet > 0 else f"{remaining_inches}\""
    except (ValueError, TypeError):
        return inches  # Fallback to original

def sanitize_filename(value: str) -> str:
    """Replace characters illegal in Windows filenames with underscores."""
    if not isinstance(value, str):
        value = str(value)
    for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        value = value.replace(ch, '_')
    return value