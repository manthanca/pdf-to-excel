"""
Unified Obligation Table Extraction
Extracts Table 2 (Obligation Details) with proper column headers
and builds the Master_Obligations sheet.
"""

import re
import pdfplumber
from typing import Dict, List, Tuple, Any

# Global registries
pdf_settlement_registry: Dict[str, float] = {}
pdf_master_obligations: List[Dict[str, Any]] = []


def extract_unified_obligation_table(
    pdf_path: str, password: str = None
) -> Tuple[float, str, List[Dict[str, Any]]]:
    """
    Find and extract the Obligation Details table from a PDF.

    Returns:
        (net_settlement, contract_note, obligation_rows)
    """
    settlement_value = 0.0
    filename = pdf_path.split('/')[-1].split('\\')[-1]
    obligation_rows = []

    try:
        with pdfplumber.open(pdf_path, password=password) as pdf:
            first_page_text = pdf.pages[0].extract_text() if pdf.pages else ""
            contract_note = extract_contract_note_from_text(first_page_text) or filename
            trade_date = extract_trade_date_from_text(first_page_text)

            for page in pdf.pages:
                tables = page.extract_tables(
                    horizontal_strategy="text",
                    snap_y_tolerance=3,
                    join_tolerance=3,
                )

                for table in tables:
                    if not table or len(table) < 2:
                        continue

                    table_text_parts = [
                        ' | '.join(str(c).strip() if c else '' for c in row)
                        for row in table if row
                    ]
                    full_text_upper = '\n'.join(table_text_parts).upper()

                    has_obligation = 'OBLIGATION' in full_text_upper
                    has_net = 'NET' in full_text_upper
                    has_receivable = 'RECEIVABLE' in full_text_upper or 'PAYABLE' in full_text_upper
                    is_trade_summary = 'SECURITY DESCRIPTION' in full_text_upper or 'ISIN' in full_text_upper

                    if not (has_obligation and (has_net or has_receivable) and not is_trade_summary):
                        continue

                    headers = _extract_table_headers(table)

                    for row_idx, row in enumerate(table):
                        if not row or row_idx < 2:
                            continue

                        clean_row = [str(c).strip() if c else '' for c in row]
                        if not any(clean_row):
                            continue

                        row_dict = {
                            'Contract Note No': contract_note,
                            'Trade Date': trade_date,
                            'PDF Filename': filename,
                        }
                        for col_idx, header in enumerate(headers):
                            row_dict[header] = clean_row[col_idx] if col_idx < len(clean_row) else ''

                        row_text_upper = ' '.join(clean_row).upper()

                        # Try Net Amount Receivable row first
                        if 'NET AMOUNT' in row_text_upper and 'RECEIVABLE' in row_text_upper:
                            val = _extract_settlement_from_row(clean_row, row_text_upper)
                            if val is not None:
                                settlement_value = val

                        # Fallback: TOTAL(NET) row
                        if settlement_value == 0.0 and 'TOTAL' in row_text_upper and 'NET' in row_text_upper:
                            val = _extract_settlement_from_row(clean_row, row_text_upper)
                            if val is not None:
                                settlement_value = val

                        obligation_rows.append(row_dict)

                    pdf_settlement_registry[contract_note] = settlement_value
                    pdf_master_obligations.extend(obligation_rows)
                    return settlement_value, contract_note, obligation_rows

            # Regex fallback when no table found
            all_text = "\n".join(
                p.extract_text() or "" for p in pdf.pages
            )
            numbers = re.findall(r'\d{1,3}(?:,\d{3})*\.\d{2}', all_text)
            if numbers:
                largest = max(float(n.replace(',', '')) for n in numbers)
                if largest >= 1000:
                    settlement_value = largest
                    if 'PAYABLE' in all_text.upper() and 'RECEIVABLE' not in all_text.upper():
                        settlement_value = -settlement_value
                    pdf_settlement_registry[contract_note] = settlement_value
                    return settlement_value, contract_note, []

            pdf_settlement_registry[contract_note] = 0.0
            return 0.0, contract_note, []

    except Exception as e:
        print(f"[OBLIGATION-ERROR] {filename}: {e}")
        pdf_settlement_registry[filename] = 0.0
        return 0.0, filename, []


def _extract_settlement_from_row(clean_row: list, row_text_upper: str) -> float | None:
    """Extract a settlement value >= 1000 from a table row."""
    for cell in reversed(clean_row):
        if cell:
            m = re.search(r'(\d{1,3}(?:,\d{3})*\.\d{2})', cell.replace(',', ''))
            if m:
                val = float(m.group(1).replace(',', ''))
                if val >= 1000:
                    if 'PAYABLE' in row_text_upper and 'RECEIVABLE' not in row_text_upper:
                        val = -val
                    elif '(DR)' in ' '.join(clean_row):
                        val = -val
                    return val
    return None


def _extract_table_headers(table: list) -> list:
    """Merge first two rows into column headers."""
    if not table:
        return []
    first = [str(c).strip() if c else '' for c in table[0]]
    if len(table) > 1:
        second = [str(c).strip() if c else '' for c in table[1]]
        merged = []
        for i in range(max(len(first), len(second))):
            h1 = first[i] if i < len(first) else ''
            h2 = second[i] if i < len(second) else ''
            if h1 and h2:
                merged.append(f"{h1} {h2}")
            else:
                merged.append(h1 or h2)
        return [h for h in merged if h]
    return [h for h in first if h]


def extract_trade_date_from_text(text: str) -> str:
    if not text:
        return ""
    for pattern in [r'\d{2}/\d{2}/\d{4}', r'\d{2}-\d{2}-\d{4}', r'\d{2}\.\d{2}\.\d{4}']:
        m = re.search(pattern, text)
        if m:
            return m.group(0)
    return ""


def extract_contract_note_from_text(text: str) -> str:
    if not text:
        return ""
    m = re.search(r'(CN_[A-Z0-9]+_\d+)', text)
    if m:
        return m.group(1)
    m = re.search(r'Contract\s+Note[\s:]+([A-Z0-9_]+)', text, re.IGNORECASE)
    if m:
        return m.group(1)
    return ""


def build_settlement_registry(pdf_files: list, password: str = None) -> Dict[str, float]:
    """Build settlement registry from a list of PDF paths."""
    global pdf_settlement_registry, pdf_master_obligations
    pdf_settlement_registry.clear()
    pdf_master_obligations.clear()
    for pdf_path in pdf_files:
        extract_unified_obligation_table(pdf_path, password)
    return pdf_settlement_registry


def get_settlement(key: str) -> float:
    return pdf_settlement_registry.get(key, 0.0)


def get_master_obligations() -> List[Dict[str, Any]]:
    return pdf_master_obligations


# Backward-compatibility aliases
extract_net_settlement = extract_unified_obligation_table
get_all_obligation_rows = get_master_obligations
