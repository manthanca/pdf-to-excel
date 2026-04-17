#!/usr/bin/env python3
"""
Universal Angel One PDF Processor
Extracts Trade Summary (Table 1, 16 cols) and Obligation Details (Table 2)
from Angel One contract note PDFs. Fills Column 17 (Net Settlement) for
every trade row from the same PDF.
"""

import pdfplumber
import pandas as pd
import re
import os
import tempfile
from pathlib import Path
from datetime import datetime

from obligation_parser import (
    extract_unified_obligation_table,
    build_settlement_registry,
    pdf_settlement_registry,
    get_settlement,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_numeric(value) -> float:
    """Strip formatting chars and return a float (0.0 on failure)."""
    if value is None or value == '' or value == 'N/A':
        return 0.0
    try:
        if isinstance(value, str):
            cleaned = (
                value.replace(',', '')
                     .replace('Rs.', '')
                     .replace('Rs', '')
                     .replace('$', '')
                     .replace(' ', '')
            )
            cleaned = re.sub(r'[A-Z]+$', '', cleaned)
            if any(ind in cleaned.upper() for ind in ['DR', 'CR', '(', ')']):
                m = re.search(r'-?\d+\.?\d*', cleaned)
                return float(m.group()) if m else 0.0
            return float(cleaned) if cleaned else 0.0
        return float(value)
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Table-detection predicates
# ---------------------------------------------------------------------------

def is_trade_summary_table(table) -> bool:
    """Return True when table contains enough Trade Summary indicators."""
    if not table or len(table) < 3:
        return False
    text = " ".join(str(c) for row in table[:5] for c in row if c)
    indicators = [
        'ISIN' in text,
        'Security Name' in text,
        'Quantity' in text,
        'WAP' in text,
        'Brokerage' in text,
        'Total BUY' in text,
        'Total SELL' in text,
        'Net Obligation' in text,
    ]
    return sum(indicators) >= 4


def is_obligation_details_table(table) -> bool:
    """Return True when table looks like the Obligation Details table."""
    if not table or len(table) < 3:
        return False
    text = " ".join(str(c) for row in table[:5] for c in row if c)

    # Reject if it looks like the Trade Summary table
    trade_hits = [
        'ISIN' in text,
        'Security Name' in text,
        'Quantity' in text and 'WAP' in text,
        'Brokerage' in text,
        'Net Obligation For ISIN' in text,
    ]
    if sum(trade_hits) >= 3:
        return False

    obligation_hits = [
        'Exchange' in text,
        'Pay In/Pay Out' in text,
        'Securities Transaction Tax' in text,
        'STT' in text,
        'Stamp Duty' in text,
        'Net Amount' in text and ('Receivable' in text or 'Payable' in text),
        'Net Amount Receivable' in text,
        'Payable by Client' in text,
        'TOTAL' in text and 'NET' in text,
    ]
    return sum(obligation_hits) >= 1


# ---------------------------------------------------------------------------
# Table extractors
# ---------------------------------------------------------------------------

def extract_trades_from_table(table, pdf_path: str, password: str = None) -> list:
    """Extract trade rows from a confirmed Trade Summary table."""
    trades = []

    # Locate header row (contains 'ISIN')
    header_row_idx = None
    for i, row in enumerate(table[:5]):
        if row and any('ISIN' in str(c) for c in row):
            header_row_idx = i
            break
    if header_row_idx is None:
        for i, row in enumerate(table):
            if row and re.search(r'INE[A-Z0-9]+', str(row[0])):
                header_row_idx = max(0, i - 1)
                break
    if header_row_idx is None:
        header_row_idx = 1

    contract_note_no = extract_contract_note_from_pdf(pdf_path, password)
    trade_date = extract_trade_date_from_pdf(pdf_path, password)
    if not trade_date:
        trade_date = extract_date_from_filename(os.path.basename(pdf_path))

    for row in table[header_row_idx + 1:]:
        if not row or len(row) < 5:
            continue
        first_cell = str(row[0]).strip() if row[0] else ""
        if first_cell.upper() == 'TOTAL':
            break
        isin_match = re.search(r'INE[A-Z0-9]+', first_cell)
        if not isin_match:
            continue

        isin = isin_match.group()
        security_name = str(row[1]).strip().replace('\n', ' ') if len(row) > 1 and row[1] else ""

        numeric_values = []
        for cell in row[2:]:
            if cell:
                for num in re.findall(r'[\d,]+\.?\d*', str(cell)):
                    try:
                        numeric_values.append(float(num.replace(',', '')))
                    except ValueError:
                        continue

        trade = {
            'Contract Note No': contract_note_no,
            'Trade Date': trade_date,
            'ISIN': isin,
            'Security Name / Symbol': security_name,
            'Quantity (Buy)': 0.0,
            'WAP (Across Exchanges) (Buy)': 0.0,
            'Brokerage Per Share (Rs) (Buy)': 0.0,
            'WAP (Across Exchanges) After Brokerage (Rs) (Buy)': 0.0,
            'Total BUY Value After Brokerage': 0.0,
            'Quantity (Sell)': 0.0,
            'WAP (Across Exchanges) (Sell)': 0.0,
            'Brokerage Per Share (Rs) (Sell)': 0.0,
            'WAP (Across Exchanges) After Brokerage (Rs) (Sell)': 0.0,
            'Total SELL Value After Brokerage': 0.0,
            'Net Quantity': 0.0,
            'Net Obligation For ISIN': 0.0,
            'Net Settlement (Receivable/Payable)': 0.0,
        }

        if len(numeric_values) >= 8:
            keys = [
                'Quantity (Buy)', 'WAP (Across Exchanges) (Buy)',
                'Brokerage Per Share (Rs) (Buy)',
                'WAP (Across Exchanges) After Brokerage (Rs) (Buy)',
                'Total BUY Value After Brokerage',
                'Quantity (Sell)', 'WAP (Across Exchanges) (Sell)',
                'Brokerage Per Share (Rs) (Sell)',
                'WAP (Across Exchanges) After Brokerage (Rs) (Sell)',
                'Total SELL Value After Brokerage',
                'Net Quantity', 'Net Obligation For ISIN',
            ]
            for idx, key in enumerate(keys):
                if idx < len(numeric_values):
                    trade[key] = numeric_values[idx]

        trades.append(trade)

    return trades


def extract_obligation_from_table(table, pdf_path: str) -> dict | None:
    """Extract obligation data from a confirmed Obligation Details table."""
    # Locate header row (starts with 'Exchange')
    header_row_idx = None
    for i, row in enumerate(table[:5]):
        if row and any('Exchange' in str(c) for c in row):
            header_row_idx = i
            break
    if header_row_idx is None:
        return None

    headers = [
        str(c).strip() if c else f"Column_{i}"
        for i, c in enumerate(table[header_row_idx])
    ]

    # Find the Net Settlement column
    net_col_idx = None
    for i, h in enumerate(headers):
        hu = h.upper()
        if (('NET' in hu and 'RECEIVABLE' in hu) or
                ('NET' in hu and 'PAYABLE' in hu) or
                ('NET' in hu and 'AMOUNT' in hu) or
                ('NET' in hu and 'CLIENT' in hu)):
            net_col_idx = i
            break
    if net_col_idx is None:
        for i in range(len(headers) - 1, max(0, len(headers) - 4), -1):
            if any(k in headers[i].upper() for k in ['NET', 'TOTAL', 'AMOUNT']):
                net_col_idx = i
                break
    if net_col_idx is None:
        net_col_idx = len(headers) - 1

    all_rows = []
    total_net_row = None
    net_settlement = 0.0

    for row in table[header_row_idx + 1:]:
        if not row:
            continue
        first = str(row[0]).strip() if row[0] else ""
        if 'TOTAL' in first.upper() and 'NET' in first.upper():
            total_net_row = row
            if net_col_idx < len(row) and row[net_col_idx]:
                net_settlement = clean_numeric(row[net_col_idx])
                row_text = ' '.join(str(c) for c in row if c).upper()
                if 'PAYABLE' in row_text and 'RECEIVABLE' not in row_text:
                    net_settlement = -net_settlement
                elif '(DR)' in str(row[net_col_idx]) or 'DR.' in str(row[net_col_idx]):
                    net_settlement = -net_settlement

        row_values = {}
        for i, h in enumerate(headers):
            row_values[h] = clean_numeric(row[i]) if i < len(row) and row[i] else 0.0
        all_rows.append(row_values)

    if not total_net_row:
        return None

    return {
        'Contract Note No': extract_contract_note_from_pdf(pdf_path),
        'Trade Date': extract_trade_date_from_pdf(pdf_path),
        'headers': headers,
        'all_rows': all_rows,
        'net_settlement': net_settlement,
        'total_net_row': total_net_row,
    }


# ---------------------------------------------------------------------------
# Pure-visual fallback for Net Settlement
# ---------------------------------------------------------------------------

def extract_net_settlement_pure_visual(pdf) -> float | None:
    """
    Scan every page for a line starting with TOTAL(NET) and return
    the last monetary value on that line.
    """
    for page in pdf.pages:
        text = page.extract_text(layout=True)
        if not text:
            continue
        for line in text.split('\n'):
            if line.strip().startswith('TOTAL(NET)'):
                numbers = re.findall(r'([\d,]+\.\d{2})', line)
                if numbers:
                    try:
                        return float(numbers[-1].replace(',', ''))
                    except ValueError:
                        continue
    return None


# ---------------------------------------------------------------------------
# Main extraction entry point
# ---------------------------------------------------------------------------

def extract_from_angel_one_pdf(pdf_path: str, password: str = None):
    """
    Extract trades (Table 1) and obligation data (Table 2) from a PDF.
    Returns (trades, obligation_data).
    """
    strategies = [
        {"vertical_strategy": "lines",  "horizontal_strategy": "lines"},
        {"vertical_strategy": "text",   "horizontal_strategy": "lines"},
        {"vertical_strategy": "text",   "horizontal_strategy": "text"},
    ]
    filename = os.path.basename(pdf_path)

    try:
        with pdfplumber.open(pdf_path, password=password) as pdf:
            trades = []
            obligation_data = None
            table1_found = False
            table2_found = False

            for page in pdf.pages[:3]:
                for strategy in strategies:
                    try:
                        for table in (page.extract_tables(strategy) or []):
                            if not table:
                                continue
                            if not table1_found and is_trade_summary_table(table):
                                trades.extend(extract_trades_from_table(table, pdf_path, password))
                                table1_found = True
                            if not table2_found and is_obligation_details_table(table):
                                obligation_data = extract_obligation_from_table(table, pdf_path)
                                if obligation_data:
                                    table2_found = True
                    except Exception:
                        continue

                if table1_found and table2_found:
                    break

            # Fallback: Table 1 found but Table 2 missing — pure visual scan
            if table1_found and not table2_found:
                net_settlement = extract_net_settlement_pure_visual(pdf)
                if net_settlement is not None:
                    obligation_data = {
                        'Contract Note No': extract_contract_note_from_pdf(pdf_path),
                        'Trade Date': extract_trade_date_from_pdf(pdf_path),
                        'headers': [],
                        'all_rows': [],
                        'net_settlement': net_settlement,
                        'total_net_row': None,
                        'extraction_method': 'pure-visual',
                        'raw_text': '',
                    }
                    table2_found = True
                else:
                    obligation_data = None
                    print(f"[ERROR] {filename}: pure-visual fallback failed")

            return trades, obligation_data

    except Exception as e:
        print(f"[ERROR] {filename}: {e}")
        return [], None


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------

def extract_trade_date_from_pdf(pdf_path: str, password: str = None) -> str:
    try:
        with pdfplumber.open(pdf_path, password=password) as pdf:
            text = pdf.pages[0].extract_text() or ""
            for pattern in [
                r'Trade Date[:\s]*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})',
                r'Trade Date[:\s]*([0-9]{1,2}-[0-9]{1,2}-[0-9]{4})',
                r'Date[:\s]*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4})',
                r'Date[:\s]*([0-9]{1,2}-[0-9]{1,2}-[0-9]{4})',
            ]:
                m = re.findall(pattern, text, re.IGNORECASE)
                if m:
                    return m[0].replace('/', '-')
    except Exception:
        pass
    return ""


def extract_contract_note_from_pdf(pdf_path: str, password: str = None) -> str:
    try:
        with pdfplumber.open(pdf_path, password=password) as pdf:
            text = pdf.pages[0].extract_text() or ""
            for pattern in [
                r'Contract Note No[:\s]*([0-9]+)',
                r'Contract Note[:\s]*([0-9]+)',
                r'Note No[:\s]*([0-9]+)',
                r'([0-9]{10})',
            ]:
                m = re.findall(pattern, text, re.IGNORECASE)
                if m:
                    return m[0]
    except Exception:
        pass
    return ""


def extract_date_from_filename(filename: str) -> str:
    for pattern in [
        r'(\d{2}-\d{2}-\d{4})',
        r'(\d{8})',
        r'(\d{4}-\d{2}-\d{2})',
    ]:
        m = re.search(pattern, filename)
        if m:
            s = m.group(1)
            if len(s) == 8 and s.isdigit():
                if int(s[:4]) > 2000:
                    return f"{s[6:8]}-{s[4:6]}-{s[:4]}"
                return f"{s[:2]}-{s[2:4]}-{s[4:]}"
            return s
    return datetime.now().strftime("%d-%m-%Y")


# ---------------------------------------------------------------------------
# Excel output (individual file)
# ---------------------------------------------------------------------------

def create_excel_output(trades: list, pdf_path: str) -> str | None:
    """Create a single Excel file for one PDF's trades."""
    if not trades:
        return None

    df = pd.DataFrame(trades)
    required_columns = [
        'Contract Note No', 'Trade Date', 'ISIN', 'Security Name / Symbol',
        'Quantity (Buy)', 'WAP (Across Exchanges) (Buy)', 'Brokerage Per Share (Rs) (Buy)',
        'WAP (Across Exchanges) After Brokerage (Rs) (Buy)', 'Total BUY Value After Brokerage',
        'Quantity (Sell)', 'WAP (Across Exchanges) (Sell)', 'Brokerage Per Share (Rs) (Sell)',
        'WAP (Across Exchanges) After Brokerage (Rs) (Sell)', 'Total SELL Value After Brokerage',
        'Net Quantity', 'Net Obligation For ISIN',
    ]
    for col in required_columns:
        if col not in df.columns:
            df[col] = 0.0
    df = df[required_columns]

    numeric_cols = required_columns[4:]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    total_row = {
        'Contract Note No': '', 'Trade Date': '', 'ISIN': 'TOTAL',
        'Security Name / Symbol': '',
        'Quantity (Buy)': df['Quantity (Buy)'].sum(),
        'WAP (Across Exchanges) (Buy)': 0.0,
        'Brokerage Per Share (Rs) (Buy)': 0.0,
        'WAP (Across Exchanges) After Brokerage (Rs) (Buy)': 0.0,
        'Total BUY Value After Brokerage': 0.0,
        'Quantity (Sell)': df['Quantity (Sell)'].sum(),
        'WAP (Across Exchanges) (Sell)': 0.0,
        'Brokerage Per Share (Rs) (Sell)': 0.0,
        'WAP (Across Exchanges) After Brokerage (Rs) (Sell)': 0.0,
        'Total SELL Value After Brokerage': 0.0,
        'Net Quantity': 0.0,
        'Net Obligation For ISIN': df['Net Obligation For ISIN'].sum(),
    }
    final_df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)

    filename = os.path.basename(pdf_path).replace('.pdf', '')
    output_path = f"outputs/{filename}_Trades.xlsx"
    Path(output_path).parent.mkdir(exist_ok=True)

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        final_df.to_excel(writer, sheet_name='Trades', index=False)

    return output_path


# ---------------------------------------------------------------------------
# Holding statement parser
# ---------------------------------------------------------------------------

def parse_holding_statement_balances(excel_file) -> dict | None:
    """Parse the Balances sheet from a holding statement Excel file."""
    sheet_names = ['Balances', 'Balance', 'balances', 'BALANCES']
    df = None

    def _read(path):
        nonlocal df
        for sheet in sheet_names:
            try:
                df = pd.read_excel(path, sheet_name=sheet)
                return
            except Exception:
                continue
        try:
            df = pd.read_excel(path)
        except Exception:
            pass

    if isinstance(excel_file, str):
        _read(excel_file)
    else:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp.write(excel_file.read())
            tmp_path = tmp.name
        try:
            _read(tmp_path)
        finally:
            os.unlink(tmp_path)

    if df is None or df.empty:
        return None

    # Find the actual header row
    header_row_idx = 0
    for i in range(min(20, len(df))):
        row_str = ' '.join(str(v) for v in df.iloc[i].values if pd.notna(v)).upper()
        if sum(1 for k in ['SR.', 'NAME', 'BROKER', 'QTY', 'RATE', 'DATE'] if k in row_str) >= 3:
            header_row_idx = i
            break

    if header_row_idx > 0:
        df.columns = df.iloc[header_row_idx].values
        df = df.iloc[header_row_idx + 1:].reset_index(drop=True)

    df.columns = [' '.join(str(c).strip().replace('\n', ' ').split()) for c in df.columns]

    column_mapping = {
        'Sr. N': 'Sr_No', 'Sr. No': 'Sr_No', 'SR. NO': 'Sr_No',
        'Name of security': 'Security_Name', 'Security Name': 'Security_Name',
        'Security': 'Security_Name', 'Broker': 'Broker',
        'Date MM/DD/YYYY': 'Date', 'Date': 'Date',
        'QTY': 'Qty', 'Quantity': 'Qty', 'Total QTY': 'Total_Qty',
        'RATE': 'Rate', 'Amt Rs.': 'Amount', 'Amount': 'Amount',
    }
    df.columns = [column_mapping.get(c, c) for c in df.columns]
    df = df.dropna(how='all').reset_index(drop=True)

    holdings_data = {}
    for _, row in df.iterrows():
        broker = str(row.get('Broker', '')).strip()
        security_name = str(row.get('Security_Name', '')).strip()
        qty = float(row.get('Qty', 0)) if pd.notna(row.get('Qty')) else 0.0
        rate = float(row.get('Rate', 0)) if pd.notna(row.get('Rate')) else 0.0
        date_str = str(row.get('Date', '')).strip()

        if not broker or not security_name or broker == 'nan' or security_name == 'nan':
            continue
        if qty <= 0:
            continue

        trade_date = None
        date_val = row.get('Date')
        if pd.notna(date_val) and isinstance(date_val, datetime):
            trade_date = date_val
        elif date_str and date_str not in ('nan', 'NaT'):
            try:
                if '/' in date_str:
                    p = date_str.split('/')
                    trade_date = datetime(int(p[2]), int(p[0]), int(p[1]))
                elif '-' in date_str:
                    p = date_str.split('-')
                    trade_date = datetime(int(p[2]), int(p[1]), int(p[0]))
            except Exception:
                pass

        key = (broker, security_name)
        holdings_data.setdefault(key, []).append({
            'quantity': qty,
            'rate': rate,
            'date': trade_date,
            'amount': qty * rate if rate > 0 else 0.0,
        })

    return holdings_data if holdings_data else None
