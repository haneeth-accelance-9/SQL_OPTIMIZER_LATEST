"""
Pre-processing validations for the uploaded Boones workbook.

Checks (in order):
  1. File size       — max 20 MB
  2. File type       — .xlsx only
  3. Column count    — exactly 110 (102 named + 8 intentional empty separators)
  4. Column headers  — each name must match the expected format after normalisation
                       (strip + collapse multiple spaces to one)
"""
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES: int = 20 * 1024 * 1024  # 20 MB
EXPECTED_COLUMN_COUNT: int = 110

# ---------------------------------------------------------------------------
# Expected header sequence (post-normalisation).
# '' marks an intentional empty separator column.
# ---------------------------------------------------------------------------
_E = ''  # empty sentinel

EXPECTED_HEADERS: list[str] = [
    # ── Fixed metadata (10) ────────────────────────────────────────────────
    'Number',
    'Server Name',
    'Is Virtual?',
    'Cluster Name',
    'Criticality',
    'Environment type',
    'Hosting Zone',
    'Installed Status',
    'Location',
    'Platform / Class',

    # ── Logical CPU — Apr-25 → Mar-26 (12) ────────────────────────────────
    'Logical CPU Apr-25',
    'Logical CPU May-25',
    'Logical CPU June-25',
    'Logical CPU July-25',
    'Logical CPU Aug-25',
    'Logical CPU Sept-25',
    'Logical CPU Oct-25',
    'Logical CPU Nov-25',
    'Logical CPU Dec-25',
    'Logical CPU Jan -26',
    'Logical CPU Feb -26',
    'Logical CPU Mar -26',
    _E,

    # ── Average CPU Utilisation (%) — Apr-25 → Mar-26 (12) ────────────────
    'Average CPU Utilisation (%) - Apr-25',
    'Average CPU Utilisation (%) - May-25',
    'Average CPU Utilisation (%) - June-25',
    'Average CPU Utilisation (%) - July-25',
    'Average CPU Utilisation (%) - Aug-25',
    'Average CPU Utilisation (%) - Sept-25',
    'Average CPU Utilisation (%) - Oct-25',
    'Average CPU Utilisation (%) - Nov-25',
    'Average CPU Utilisation (%) - Dec-25',
    'Average CPU Utilisation (%) - Jan-26',
    'Average CPU Utilisation (%) - Feb-26',
    'Average CPU Utilisation (%) - Mar-26',
    _E,

    # ── Maximum CPU Utilisation (%) — Apr-25 → Mar-26 (12) ────────────────
    'Maximum CPU Utilisation (%) - Apr-25',
    'Maximum CPU Utilisation (%) - May-25',
    'Maximum CPU Utilisation (%) - June-25',
    'Maximum CPU Utilisation (%) - July-25',
    'Maximum CPU Utilisation (%) - Aug-25',
    'Maximum CPU Utilisation (%) - Sept-25',
    'Maximum CPU Utilisation (%) - Oct-25',
    'Maximum CPU Utilisation (%) - Nov-25',
    'Maximum CPU Utilisation (%) - Dec-25',
    'Maximum CPU Utilisation (%) -Jan-26',
    'Maximum CPU Utilisation (%) -Feb-26',
    'Maximum CPU Utilisation (%) -Mar-26',
    _E,

    # ── Physical RAM (GiB) — Apr-25 → Mar-26 (12) ─────────────────────────
    'Physical RAM (GiB) - Apr-25',
    'Physical RAM (GiB) - May-25',
    'Physical RAM (GiB) - June-25',
    'Physical RAM (GiB) - July-25',
    'Physical RAM (GiB) -Aug-25',
    'Physical RAM (GiB) -Sept-25',
    'Physical RAM (GiB) -Oct-25',
    'Physical RAM (GiB) -Nov-25',
    'Physical RAM (GiB) -Dec-25',
    'Physical RAM (GiB) -Jan-26',
    'Physical RAM (GiB) -Feb-26',
    'Physical RAM (GiB) -Mar-26',
    _E,

    # ── Average free Memory (%) — Apr-25 → Mar-26 (12) ────────────────────
    'Average free Memory (%) - Apr-25',
    'Average free Memory (%) - May-25',
    'Average free Memory (%) - June-25',
    'Average free Memory (%) - July-25',
    'Average free Memory (%) -Aug-25',
    'Average free Memory (%) -Sept-25',
    'Average free Memory (%) -Oct-25',
    'Average free Memory (%) -Nov-25',
    'Average free Memory (%) -Dec-25',
    'Average free Memory (%) -Jan-26',
    'Average free Memory (%) -Feb-26',
    'Average free Memory (%) -Mar-26',
    _E,

    # ── Maximum free Memory (%) — Apr-25 → Mar-26 (12) ────────────────────
    'Maximum free Memory (%) - Apr-25',
    'Maximum free Memory (%) - May-25',
    'Maximum free Memory (%) - June-25',
    'Maximum free Memory (%) - July-25',
    'Maximum free Memory (%) - Aug-25',
    'Maximum free Memory (%) - Sept-25',
    'Maximum free Memory (%) - Oct-25',
    'Maximum free Memory (%) - Nov-25',
    'Maximum free Memory (%) - Dec-25',
    'Maximum free Memory (%) - Jan-26',
    'Maximum free Memory (%) - Feb-26',
    'Maximum free Memory (%) - Mar-26',
    _E,

    # ── Minimum free Memory (%) — Apr-25 → Mar-26 (12) ────────────────────
    'Minimum free Memory (%) - Apr-25',
    'Minimum free Memory (%) - May-25',
    'Minimum free Memory (%) - June-25',
    'Minimum free Memory (%) - July-25',
    'Minimum free Memory (%) - Aug-25',
    'Minimum free Memory (%) - Sept-25',
    'Minimum free Memory (%) - Oct-25',
    'Minimum free Memory (%) - Nov-25',
    'Minimum free Memory (%) - Dec-25',
    'Minimum free Memory (%) -Jan-26',
    'Minimum free Memory (%) -Feb-26',
    'Minimum free Memory (%) -Mar-26',
    _E,

    # ── Allocated Storage (GB) — Feb-26, Mar-26 (2) ───────────────────────
    'Allocated Storage (GB) -Feb - 26',
    'Allocated Storage (GB) -Mar- 26',
    _E,

    # ── Used Storage (GB) — Feb-26, Mar-26 (2) ────────────────────────────
    'Used Storage (GB) -Feb - 26',
    'Used Storage (GB) -Mar - 26',

    # ── Trailing fixed (4) ─────────────────────────────────────────────────
    'Comments for Allocation (GB)',
    'Comments for Usage (GB)',
    'Utilisation %',
    'Decmmission Check',
]

assert len(EXPECTED_HEADERS) == EXPECTED_COLUMN_COUNT, (
    f"EXPECTED_HEADERS has {len(EXPECTED_HEADERS)} entries, expected {EXPECTED_COLUMN_COUNT}"
)

_VALID_CONTENT_TYPES = frozenset({
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/octet-stream',  # some browsers send this for xlsx
    'application/zip',           # xlsx is a zip; occasionally reported as this
})


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    valid: bool
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(header) -> str:
    """Strip surrounding whitespace and collapse runs of spaces to one."""
    if header is None:
        return ''
    return re.sub(r' {2,}', ' ', str(header).strip())


def _read_first_row(file) -> list:
    """
    Return the raw cell values from row 1 of the first worksheet.
    Resets the file pointer before and after reading.
    """
    import openpyxl
    file.seek(0)
    wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        return [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    finally:
        wb.close()
        file.seek(0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_upload(file) -> ValidationResult:
    """
    Run all pre-processing validations on *file* (a Django UploadedFile).

    Returns ValidationResult(valid=True) on success, or
    ValidationResult(valid=False, error="...") on the first failing check.
    """

    # 1. File size ────────────────────────────────────────────────────────────
    size = getattr(file, 'size', None)
    if size is None:
        try:
            file.seek(0, 2)
            size = file.tell()
            file.seek(0)
        except Exception:
            size = 0

    if size > MAX_FILE_SIZE_BYTES:
        mb = size / (1024 * 1024)
        return ValidationResult(
            False,
            f"File is too large ({mb:.1f} MB). Maximum allowed size is 20 MB.",
        )

    # 2. File type ─────────────────────────────────────────────────────────────
    name = getattr(file, 'name', '') or ''
    if not name.lower().endswith('.xlsx'):
        return ValidationResult(
            False,
            "Only .xlsx files are accepted. Please upload an Excel 2007+ workbook (.xlsx).",
        )

    content_type = (getattr(file, 'content_type', '') or '').split(';')[0].strip()
    if content_type and content_type not in _VALID_CONTENT_TYPES:
        return ValidationResult(
            False,
            f"The uploaded file does not appear to be an Excel workbook. "
            f"Detected content type: {content_type}.",
        )

    # 3 & 4. Column count + header names ──────────────────────────────────────
    try:
        raw_headers = _read_first_row(file)
    except Exception as exc:
        logger.warning("upload_validator: could not read workbook headers — %s", exc)
        return ValidationResult(
            False,
            "Could not read the uploaded file. "
            "Please ensure it is a valid, non-password-protected .xlsx workbook.",
        )

    # 3. Column count
    actual_count = len(raw_headers)
    if actual_count != EXPECTED_COLUMN_COUNT:
        return ValidationResult(
            False,
            f"Unexpected column count: found {actual_count}, expected {EXPECTED_COLUMN_COUNT}. "
            "Please upload the standard Boones workbook.",
        )

    # 4. Header names
    mismatches: list[str] = []
    for idx, (raw, expected) in enumerate(zip(raw_headers, EXPECTED_HEADERS), start=1):
        actual_norm = _normalize(raw)
        if actual_norm != expected:
            mismatches.append(
                f"column {idx}: expected \"{expected}\", got \"{actual_norm}\""
            )
            if len(mismatches) == 5:
                break

    if mismatches:
        return ValidationResult(
            False,
            "Column headers do not match the expected format — "
            + "; ".join(mismatches)
            + ("…" if len(mismatches) == 5 else "")
            + ". Please upload the standard Boones workbook.",
        )

    return ValidationResult(valid=True)
