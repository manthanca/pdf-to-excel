"""
PDF parser module for extracting table data from contract notes.
Handles password-protected PDFs and extracts table data using AI with JSON safety.
"""

import pdfplumber
import os
import re
import json
from openai import OpenAI
from typing import Optional, Tuple, Dict, List


def extract_text(pdf_path: str, password: Optional[str] = None) -> Tuple[str, bool]:
    """
    Extract text from pages with data/tables only using pdfplumber.
    
    Args:
        pdf_path (str): Path to the PDF file
        password (Optional[str]): Password for encrypted PDF
        
    Returns:
        Tuple[str, bool]: Extracted text and success status
    """
    try:
        # Check if file exists
        if not os.path.exists(pdf_path):
            return f"Error: File not found - {pdf_path}", False
        
        extracted_text = ""
        
        # Try to open PDF with or without password
        try:
            with pdfplumber.open(pdf_path, password=password) as pdf:
                # Extract text from first 2 pages only
                max_pages = min(2, len(pdf.pages))
                for page_num in range(max_pages):
                    page = pdf.pages[page_num]
                    
                    # First try to extract tables
                    tables = page.extract_tables()
                    
                    if tables:
                        extracted_text += f"--- Page {page_num + 1} Tables ---\n"
                        for table_idx, table in enumerate(tables):
                            extracted_text += f"Table {table_idx + 1}:\n"
                            for row in table:
                                if row:  # Skip empty rows
                                    extracted_text += "|".join(str(cell) if cell else "" for cell in row) + "\n"
                            extracted_text += "\n"
                    
                    # Also extract regular text for context
                    page_text = page.extract_text()
                    if page_text:
                        extracted_text += f"--- Page {page_num + 1} Text ---\n"
                        extracted_text += page_text + "\n\n"
                
                # Apply text length limits
                # First limit to 3000 characters
                if len(extracted_text) > 3000:
                    extracted_text = extracted_text[:3000]
                    
                    # If still too long, limit to 1500 words
                    words = extracted_text.split()
                    if len(words) > 1500:
                        extracted_text = " ".join(words[:1500])
                
                if not extracted_text.strip():
                    return "Error: No text could be extracted from the PDF", False
                    
                return extracted_text, True
                
        except pdfplumber.pdf.PasswordError:
            return "Error: Incorrect password or PDF is password protected", False
        except Exception as e:
            return f"Error opening PDF: {str(e)}", False
            
    except Exception as e:
        return f"Error processing PDF: {str(e)}", False


def normalize(text):
    """
    Normalize text by converting to lowercase and removing all non-alphanumeric characters.
    
    Args:
        text (str): Text to normalize
        
    Returns:
        str: Normalized text
    """
    if text is None:
        return ""
    # Convert to lowercase and remove ALL non-alphanumeric characters
    return re.sub(r'[^a-z0-9]', '', str(text).lower())


def clean_numeric(value):
    """
    Clean numeric values by removing commas, currency symbols, CR/DR, and converting to float.
    Follows strict data integrity rules - preserves original values if conversion fails.
    """
    if value is None or value == '' or value == 'N/A':
        return 0.0
    
    try:
        if isinstance(value, str):
            # Remove commas, currency symbols, whitespace, CR/DR, and other text
            # Use .replace(',', '') before conversion to handle "3,011.99"
            cleaned = str(value).replace(',', '').replace('₹', '').replace('$', '').replace(' ', '')
            # Remove CR/DR and other text suffixes
            cleaned = re.sub(r'[A-Z]+$', '', cleaned)  # Remove trailing letters like CR, DR
            return float(cleaned) if cleaned else 0.0
        
        return float(value)
        
    except (ValueError, TypeError):
        # DATA INTEGRITY: Preserve original value instead of forcing 0
        print(f"WARNING: Could not convert '{value}' to float, preserving as is")
        return value  # Return original value, not 0.0


def extract_data_with_ai(text: str, broker: str, headers: List[str]) -> Optional[Dict]:
    """
    Connect to local Gemma 3 model via openai library to extract structured data.
    Uses fuzzy normalization to handle key variations.
    
    Args:
        text (str): Extracted text from PDF
        broker (str): Broker name
        headers (List[str]): Expected headers for the broker
        
    Returns:
        Optional[Dict]: Structured data or None if failed
    """
    try:
        # Configure OpenAI client for local model
        client = OpenAI(base_url='http://localhost:1234/v1', api_key='lm-studio')
        
        prompt = f"""
Extract structured trade data from this {broker} contract note.

TEXT:
{text}

🚨 CRITICAL EXTRACTION RULES 🚨

1. EXTRACT TWO SEPARATE TABLES:

   TABLE 1 - TRADES (use these short keys):
   - isin (ISIN code)
   - security_name (company name)
   - buy_qty (buy quantity)
   - buy_wap (buy WAP)
   - buy_brokerage (buy brokerage per share)
   - buy_wap_after (buy WAP after brokerage)
   - total_buy (total buy value)
   - sell_qty (sell quantity)
   - sell_wap (sell WAP)
   - sell_brokerage (sell brokerage per share)
   - sell_wap_after (sell WAP after brokerage)
   - total_sell (total sell value)
   - net_qty (net quantity)
   - net_obligation (net obligation)

   TABLE 2 - HEADER INFO:
   - contract_note_no (Contract Note Number - 10-digit numeric from PDF PAGE 1)
   - trade_date (Trade Date in DD-MM-YYYY format from PDF header)

   TABLE 3 - OBLIGATION DETAILS (use these short keys):
   - exchange (exchange name)
   - pay_in_pay_out (Pay In/Pay Out)
   - obligation (obligation amount)
   - securities_transaction_tax (Securities Transaction Tax)
   - taxable_value_of_supply (Taxable value of supply)
   - cgst (CGST amount)
   - sgst (SGST amount)
   - exchange_transaction_charges (Exchange Transaction Charges)
   - sebi_turnover_fees (SEBI turnover fees)
   - stamp_duty (Stamp Duty)
   - ipf_charges (IPF Charges)
   - auction_other_charges (Auction/Other Charges)
   - net_amount_receivable (Net Amount Receivable by Client/(Payable by Client))

2. STRICT NUMERIC EXTRACTION:
   - EVERY numeric field MUST have a valid number
   - NEVER leave any field empty, null, or blank
   - If value is 0 in PDF → write "0" (not empty string)
   - Extract EXACT numbers as shown in PDF

3. FORMATTING:
   - Numbers: plain digits only (no commas, no ₹, no $)
   - ISIN: exact string from PDF
   - Security Name: exact text from PDF
   - Exchange: "NSE-CAPITAL" or similar

🔍 EXTRACTION STRATEGY:

Constraint 1 (No Hallucination): You are a data extraction robot. If "Contract Note No" or "Trade Date" is not explicitly visible in the text, you MUST return null. Do NOT generate placeholders like 1234567890 or 26-10-2023. Accuracy is more important than completeness.

Constraint 2 (Anchor Search): Look for the keyword "Contract Note No." The value is usually a 10-15 character alphanumeric string near the broker name. Look for "Trade Date" or "Date of Contract" specifically. Ignore "Settlement Date" or "Pay-in Date".

Constraint 3 (JSON Schema): Your response must be valid JSON. If fields are missing, the value is null, not a string "null" and not a placeholder.

Constraint 4 (Sell Quantity Critical): PAY SPECIAL ATTENTION to sell quantities! If total_sell value > 0, then sell_qty MUST be > 0. Do NOT set sell_qty to 0 when there are sell transactions. The sell quantity is in the SELL Quantity column of the trade table.

- Scan Page 1 header area AFTER the address section for header info
- Scan the Equity Segment table row by row for TRADES
- For each trade, extract BOTH buy and sell quantities accurately
- If you see a sell value (total_sell > 0), there MUST be a corresponding sell_qty > 0
- Scan the Obligation Details table for OBLIGATION data
- Extract ALL visible data points
- Use ONLY the short keys listed above

Return JSON with all three tables:
{{
  "header_info": {{
    "contract_note_no": "",
    "trade_date": ""
  }},
  "trades": [trade objects],
  "obligation_details": obligation_object
}}
"""
        
        response = client.chat.completions.create(
            model="gemma-3-4b",
            messages=[
                {"role": "system", "content": "You are a financial data extraction expert. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=8000  # Increased from 4000 to handle larger responses
        )
        
        raw_response = response.choices[0].message.content.strip()
        
        # Check if response appears to be truncated
        if raw_response.endswith('```') or raw_response.count('{') > raw_response.count('}'):
            print("WARNING: AI response appears to be truncated!")
            print("Attempting to repair incomplete JSON...")
        
        # JSON Safety: Extract JSON object (not just array)
        start_idx = raw_response.find('{')
        end_idx = raw_response.rfind('}')
        
        if start_idx == -1 or end_idx == -1:
            print("No valid JSON array found in AI response")
            print(f"Raw response: {raw_response}")
            return None
        
        json_str = raw_response[start_idx:end_idx+1]
        
        try:
            parsed_data = json.loads(json_str)
            
            # Handle new JSON structure with header_info
            if isinstance(parsed_data, dict):
                header_info = parsed_data.get('header_info', {})
                trades_data = parsed_data.get('trades', [])
                obligation_data = parsed_data.get('obligation_details', {})
                
                # LOGICAL GUARDRAIL: Blacklist specific hallucinated values
                if header_info.get('contract_note_no') == '':
                    header_info['contract_note_no'] = None
                    print("GUARDRAIL: Blacklisted hallucinated Contract Note No ''")
                
                # VALUE VALIDATION: Check Trade Date for future dates
                trade_date = header_info.get('trade_date', '')
                contract_note = header_info.get('contract_note_no', '')
                
                # Validate Contract Note No format (must be 10 digits)
                if contract_note and (not contract_note.isdigit() or len(contract_note) != 10):
                    print(f"WARNING: Contract Note No '{contract_note}' is not a valid 10-digit number!")
                    header_info['contract_note_no'] = ''
                
                # Validate that header info was actually extracted (not placeholder)
                if not contract_note or not trade_date:
                    print(f"WARNING: Header info not properly extracted from PDF!")
                    print(f"  Contract Note No: '{contract_note}'")
                    print(f"  Trade Date: '{trade_date}'")
                    print("  AI may be generating placeholder values instead of extracting from PDF")
                    # Force empty strings to prevent wrong data in Excel
                    header_info['contract_note_no'] = ''
                    header_info['trade_date'] = ''
                elif contract_note == 'xxxxxxxxxx' or trade_date == 'dd-mm-yyyy':
                    print(f"WARNING: AI is using example placeholder values!")
                    print(f"  Contract Note No: '{contract_note}'")
                    print(f"  Trade Date: '{trade_date}'")
                    print("  Forcing empty strings to prevent wrong data")
                    # Force empty strings for obvious placeholders
                    header_info['contract_note_no'] = ''
                    header_info['trade_date'] = ''
                
                if trade_date:
                    try:
                        from datetime import datetime
                        parsed_date = datetime.strptime(trade_date, '%d-%m-%Y')
                        current_date = datetime.now()
                        
                        if parsed_date.year > current_date.year + 1:  # More than 1 year in future
                            print(f"WARNING: Trade Date {trade_date} appears to be in the future!")
                            print(f"Defaulting to current date: {current_date.strftime('%d-%m-%Y')}")
                            header_info['trade_date'] = current_date.strftime('%d-%m-%Y')
                    except ValueError:
                        print(f"WARNING: Could not parse Trade Date '{trade_date}'")
                        header_info['trade_date'] = datetime.now().strftime('%d-%m-%Y')
                
                # SELL QUANTITY VALIDATION: Fix sell_qty if it's 0 but total_sell > 0
                for trade in trades_data:
                    sell_qty = self._safe_float(trade.get('sell_qty', 0))
                    total_sell = self._safe_float(trade.get('total_sell', 0))
                    sell_wap = self._safe_float(trade.get('sell_wap', 0))
                    
                    if sell_qty == 0 and total_sell > 0 and sell_wap > 0:
                        # Calculate sell_qty from total_sell and sell_wap
                        calculated_sell_qty = total_sell / sell_wap
                        trade['sell_qty'] = str(int(round(calculated_sell_qty)))
                        print(f"FIXED Sell Quantity: {trade.get('security_name', 'Unknown')} - {trade['sell_qty']} (calculated from {total_sell} ÷ {sell_wap})")
                
                # Process trades with header info
                processed_rows = []
                for trade in trades_data:
                    new_row = {}
                    
                    # Add header info at beginning
                    new_row['Contract Note No'] = header_info.get('contract_note_no', '')
                    new_row['Trade Date'] = header_info.get('trade_date', '')
                    
                    # Manual mapping for all 14 columns with proper None handling
                    new_row['ISIN'] = trade.get('isin', '')
                    new_row['Security Name / Symbol'] = trade.get('security_name', '')
                    new_row['Quantity (Buy)'] = clean_numeric(trade.get('buy_qty', 0))
                    new_row['WAP (Across Exchanges) (Buy)'] = clean_numeric(trade.get('buy_wap', 0))
                    new_row['Brokerage Per Share (Rs) (Buy)'] = clean_numeric(trade.get('buy_brokerage', 0))
                    new_row['WAP (Across Exchanges) After Brokerage (Rs) (Buy)'] = clean_numeric(trade.get('buy_wap_after', 0))
                    new_row['Total BUY Value After Brokerage'] = clean_numeric(trade.get('total_buy', 0))
                    new_row['Quantity (Sell)'] = clean_numeric(trade.get('sell_qty', 0))
                    new_row['WAP (Across Exchanges) (Sell)'] = clean_numeric(trade.get('sell_wap', 0))
                    new_row['Brokerage Per Share (Rs) (Sell)'] = clean_numeric(trade.get('sell_brokerage', 0))
                    new_row['WAP (Across Exchanges) After Brokerage (Rs) (Sell)'] = clean_numeric(trade.get('sell_wap_after', 0))
                    new_row['Total SELL Value After Brokerage'] = clean_numeric(trade.get('total_sell', 0))
                    new_row['Net Quantity'] = clean_numeric(trade.get('net_qty', 0))
                    new_row['Net Obligation For ISIN'] = clean_numeric(trade.get('net_obligation', 0))
                    
                    processed_rows.append(new_row)
                
                return {
                    'trades': processed_rows,
                    'obligation_details': obligation_data,
                    'header_info': header_info
                }
            
            # MANDATORY DEBUGGING: Print raw AI keys and expected headers
            if isinstance(parsed_data, list) and len(parsed_data) > 0:
                print(f"CRITICAL DEBUG: AI Data Sample: {parsed_data[0]}")
                print(f"DEBUG: Raw AI Keys: {list(parsed_data[0].keys()) if parsed_data[0] else 'Empty'}")
                print(f"DEBUG: Expected Headers: {headers}")
                print(f"DEBUG: Parsed Data Type: {type(parsed_data)}")
                print(f"DEBUG: Parsed Data Length: {len(parsed_data)}")
                
                # ADDITIONAL DEBUG: Print first 3 trades to see what's happening
                for i, trade in enumerate(parsed_data[:3]):
                    print(f"DEBUG: Trade {i}: {trade}")
                    print(f"DEBUG: Trade {i} Keys: {list(trade.keys())}")
                    print(f"DEBUG: Trade {i} ISIN: {trade.get('isin')}")
            
            # MANUAL MAPPING: Direct assignment without reindexing trap
            if isinstance(parsed_data, list):
                processed_rows = []
                
                for trade in parsed_data:
                    print("AI TRADE DATA:", trade)
                    
                    # Manual mapping for all 14 columns with proper None handling
                    new_row = {}
                    
                    # ISIN mapping
                    isin_val = trade.get('isin')
                    if isin_val is not None:
                        new_row['ISIN'] = isin_val
                    else:
                        new_row['ISIN'] = trade.get('ISIN', 0)
                    
                    # Security Name mapping
                    security_val = trade.get('security_name')
                    if security_val is not None:
                        new_row['Security Name / Symbol'] = security_val
                    else:
                        new_row['Security Name / Symbol'] = trade.get('Security Name / Symbol', '')
                    
                    # Quantity (Buy) mapping
                    buy_qty_val = trade.get('buy_qty')
                    if buy_qty_val is not None:
                        new_row['Quantity (Buy)'] = clean_numeric(buy_qty_val)
                    else:
                        new_row['Quantity (Buy)'] = clean_numeric(trade.get('Quantity (Buy)', 0))
                    
                    # WAP (Buy) mapping
                    buy_wap_val = trade.get('buy_wap')
                    if buy_wap_val is not None:
                        new_row['WAP (Across Exchanges) (Buy)'] = clean_numeric(buy_wap_val)
                    else:
                        new_row['WAP (Across Exchanges) (Buy)'] = clean_numeric(trade.get('WAP (Across Exchanges) (Buy)', 0))
                    
                    # Brokerage (Buy) mapping
                    buy_brokerage_val = trade.get('buy_brokerage')
                    if buy_brokerage_val is not None:
                        new_row['Brokerage Per Share (Rs) (Buy)'] = clean_numeric(buy_brokerage_val)
                    else:
                        new_row['Brokerage Per Share (Rs) (Buy)'] = clean_numeric(trade.get('Brokerage Per Share (Rs) (Buy)', 0))
                    
                    # WAP After (Buy) mapping
                    buy_wap_after_val = trade.get('buy_wap_after')
                    if buy_wap_after_val is not None:
                        new_row['WAP (Across Exchanges) After Brokerage (Rs) (Buy)'] = clean_numeric(buy_wap_after_val)
                    else:
                        new_row['WAP (Across Exchanges) After Brokerage (Rs) (Buy)'] = clean_numeric(trade.get('WAP (Across Exchanges) After Brokerage (Rs) (Buy)', 0))
                    
                    # Total BUY mapping
                    total_buy_val = trade.get('total_buy')
                    if total_buy_val is not None:
                        new_row['Total BUY Value After Brokerage'] = clean_numeric(total_buy_val)
                    else:
                        new_row['Total BUY Value After Brokerage'] = clean_numeric(trade.get('Total BUY Value After Brokerage', 0))
                    
                    # Quantity (Sell) mapping
                    sell_qty_val = trade.get('sell_qty')
                    if sell_qty_val is not None:
                        new_row['Quantity (Sell)'] = clean_numeric(sell_qty_val)
                    else:
                        new_row['Quantity (Sell)'] = clean_numeric(trade.get('Quantity (Sell)', 0))
                    
                    # WAP (Sell) mapping
                    sell_wap_val = trade.get('sell_wap')
                    if sell_wap_val is not None:
                        new_row['WAP (Across Exchanges) (Sell)'] = clean_numeric(sell_wap_val)
                    else:
                        new_row['WAP (Across Exchanges) (Sell)'] = clean_numeric(trade.get('WAP (Across Exchanges) (Sell)', 0))
                    
                    # Brokerage (Sell) mapping
                    sell_brokerage_val = trade.get('sell_brokerage')
                    if sell_brokerage_val is not None:
                        new_row['Brokerage Per Share (Rs) (Sell)'] = clean_numeric(sell_brokerage_val)
                    else:
                        new_row['Brokerage Per Share (Rs) (Sell)'] = clean_numeric(trade.get('Brokerage Per Share (Rs) (Sell)', 0))
                    
                    # WAP After (Sell) mapping
                    sell_wap_after_val = trade.get('sell_wap_after')
                    if sell_wap_after_val is not None:
                        new_row['WAP (Across Exchanges) After Brokerage (Rs) (Sell)'] = clean_numeric(sell_wap_after_val)
                    else:
                        new_row['WAP (Across Exchanges) After Brokerage (Rs) (Sell)'] = clean_numeric(trade.get('WAP (Across Exchanges) After Brokerage (Rs) (Sell)', 0))
                    
                    # Total SELL mapping
                    total_sell_val = trade.get('total_sell')
                    if total_sell_val is not None:
                        new_row['Total SELL Value After Brokerage'] = clean_numeric(total_sell_val)
                    else:
                        new_row['Total SELL Value After Brokerage'] = clean_numeric(trade.get('Total SELL Value After Brokerage', 0))
                    
                    # Net Quantity mapping
                    net_qty_val = trade.get('net_qty')
                    if net_qty_val is not None:
                        new_row['Net Quantity'] = clean_numeric(net_qty_val)
                    else:
                        new_row['Net Quantity'] = clean_numeric(trade.get('Net Quantity', 0))
                    
                    # Net Obligation mapping
                    net_obligation_val = trade.get('net_obligation')
                    if net_obligation_val is not None:
                        new_row['Net Obligation For ISIN'] = clean_numeric(net_obligation_val)
                    else:
                        new_row['Net Obligation For ISIN'] = clean_numeric(trade.get('Net Obligation For ISIN', 0))
                    
                    print("MANUAL MAPPED ROW:", new_row)
                    processed_rows.append(new_row)
                
                # ROBUST FILTERING: Garbage Collector
                import pandas as pd
                trades_df = pd.DataFrame(processed_rows)
                trades_df = trades_df[trades_df['Security Name / Symbol'].notna() & (trades_df['Net Obligation For ISIN'] != 0)]
                
                # NEGATIVE QUANTITY LOGIC: Apply abs() to Quantity (Sell)
                trades_df['Quantity (Sell)'] = trades_df['Quantity (Sell)'].abs()
                
                # DATA INTEGRITY: Force numeric columns to float
                numeric_cols = ['Quantity (Buy)', 'Quantity (Sell)', 'Net Obligation For ISIN']
                for col in numeric_cols:
                    if col in trades_df.columns:
                        trades_df[col] = pd.to_numeric(trades_df[col], errors='coerce').fillna(0)
                
                # MANUAL TOTAL CALCULATION
                sum_buy = trades_df['Quantity (Buy)'].sum()
                sum_sell = trades_df['Quantity (Sell)'].sum()
                sum_net = trades_df['Net Obligation For ISIN'].sum()
                
                # AUDIT COLUMN: Add Audit Check
                trades_df['Audit Check'] = trades_df.apply(
                    lambda row: 'PASS' if (
                        row['Quantity (Buy)'] - row['Quantity (Sell)'] == row['Net Quantity']
                    ) else 'FAIL',
                    axis=1
                )
                
                # FINAL ROW ATTACHMENT
                total_row = {col: 0 for col in headers}
                total_row['Contract Note No'] = header_info.get('contract_note_no', '')
                total_row['Trade Date'] = header_info.get('trade_date', '')
                total_row['ISIN'] = 'TOTAL'
                total_row['Quantity (Buy)'] = sum_buy
                total_row['Quantity (Sell)'] = sum_sell
                total_row['Net Obligation For ISIN'] = sum_net
                total_row['Audit Check'] = 'TOTAL'
                
                total_df = pd.DataFrame([total_row])
                final_df = pd.concat([trades_df, total_df], ignore_index=True)
                
                print("STRICT CLEANUP DONE:", len(trades_df), "trades + TOTAL")
                return final_df.to_dict('records')
            else:
                return parsed_data
                
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Processed JSON string: {json_str}")
            print(f"Raw response: {raw_response}")
            
            # If JSON is truncated, try to repair it
            if "Expecting ',' delimiter" in str(e):
                print("Attempting to repair truncated JSON...")
                # Try to close the JSON properly
                if json_str.count('{') > json_str.count('}'):
                    # Add missing closing braces
                    missing_braces = json_str.count('{') - json_str.count('}')
                    json_str += '}' * missing_braces
                    try:
                        parsed_data = json.loads(json_str)
                        print("Successfully repaired truncated JSON!")
                        return parsed_data
                    except:
                        print("Failed to repair JSON")
                        return None
                else:
                    return None
            else:
                return None
            
    except Exception as e:
        print(f"Error communicating with local AI: {e}")
        print("Make sure LM Studio is running and the model is loaded.")
        return None


def try_passwords(pdf_path: str, passwords: list) -> Tuple[str, bool, Optional[str]]:
    """
    Try multiple passwords to open a PDF file.
    
    Args:
        pdf_path (str): Path to the PDF file
        passwords (list): List of passwords to try
        
    Returns:
        Tuple[str, bool, Optional[str]]: Extracted text, success status, and working password
    """
    for password in passwords:
        if password is None:
            # Try without password first
            text, success = extract_text(pdf_path)
            if success:
                return text, True, None
        else:
            text, success = extract_text(pdf_path, password)
            if success:
                return text, True, password
    
    return "Error: Could not open PDF with any of the provided passwords", False, None


def _retry_extraction_with_strict_rules(text: str, broker: str, headers: List[str]) -> Optional[Dict]:
    """
    Retry extraction with stricter rules when too many fields are empty.
    
    Args:
        text (str): Extracted text from PDF
        broker (str): Broker name
        headers (List[str]): Expected headers for the broker
        
    Returns:
        Optional[Dict]: Structured data or None if failed
    """
    try:
        # Configure OpenAI client for local model
        client = openai.OpenAI(
            base_url="http://localhost:1234/v1",
            api_key="not-needed"
        )
        
        strict_prompt = f"""
🚨 URGENT RETRY - STRICT EXTRACTION MODE 🚨

Previous extraction had too many empty fields. You MUST extract ALL visible data.

TEXT:
{text}

🔥 ABSOLUTE REQUIREMENTS:
1. EVERY numeric field MUST have a number (no exceptions)
2. If you can see data in PDF → EXTRACT IT exactly
3. NO empty strings allowed for numeric fields
4. NO null values allowed
5. Use "0" ONLY when PDF shows 0 or cell is truly empty

MANDATORY 14 FIELDS:
1. ISIN (extract exactly as shown)
2. Security Name / Symbol (extract full company name)
3. Quantity (Buy) (MUST have number)
4. WAP (Across Exchanges) (Buy) (MUST have number)
5. Brokerage Per Share (Rs) (Buy) (number)
6. WAP (Across Exchanges) After Brokerage (Rs) (Buy) (number)
7. Total BUY Value After Brokerage (MUST have number)
8. Quantity (Sell) (MUST have number)
9. WAP (Across Exchanges) (Sell) (number)
10. Brokerage Per Share (Rs) (Sell) (number)
11. WAP (Across Exchanges) After Brokerage (Rs) (Sell) (number)
12. Total SELL Value After Brokerage (number)
13. Net Quantity (MUST have number)
14. Net Obligation For ISIN (MUST have value)

⚡ EXTRACTION DISCIPLINE:
- Scan PDF table cell by cell
- Extract EVERY visible number
- Do NOT skip any data
- Preserve exact values (remove commas only)
- Verify each row has all 14 fields

Return ONLY valid JSON array with complete data.
"""
        
        response = client.chat.completions.create(
            model="gemma-3-4b",
            messages=[
                {"role": "system", "content": "You are a financial data extraction expert. Extract ALL visible data without leaving fields empty."},
                {"role": "user", "content": strict_prompt}
            ],
            temperature=0.05,  # Lower temperature for stricter extraction
            max_tokens=4000
        )
        
        raw_response = response.choices[0].message.content.strip()
        print("DEBUG: Retry AI Response:")
        print(raw_response)
        print("=" * 50)
        
        # Parse the retry response
        json_objects = re.findall(r'\{.*?\}', raw_response, re.DOTALL)
        
        if not json_objects:
            print("Retry failed: No JSON objects found")
            return None
        
        if len(json_objects) == 1:
            json_str = json_objects[0]
        else:
            json_str = '[' + ','.join(json_objects) + ']'
        
        if not (json_str.strip().startswith('[') and json_str.strip().endswith(']')):
            json_str = f'[{json_str}]'
        
        try:
            parsed_data = json.loads(json_str)
            print("✅ Retry extraction completed successfully")
            return parsed_data
        except json.JSONDecodeError as e:
            print(f"Retry JSON decode error: {e}")
            return None
            
    except Exception as e:
        print(f"Retry extraction error: {e}")
        return None


def validate_pdf(pdf_path: str) -> bool:
    """
    Validate if the file is a valid PDF.
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        bool: True if valid PDF, False otherwise
    """
    try:
        return pdf_path.lower().endswith('.pdf') and os.path.exists(pdf_path)
    except:
        return False
