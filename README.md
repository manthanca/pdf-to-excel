# MRACA Smart Contract Note Converter

## Overview

The MRACA Smart Contract Note Converter is an enterprise-grade data pipeline that automates the extraction, processing, and analysis of contract note PDFs from Indian brokers. The system features:

### Key Features

- **Automated PDF Parsing**: Decrypts and extracts 17 columns of data from password-protected contract note PDFs using geometric mapping and visual layout extraction
- **FIFO Capital Gains Calculation**: Calculates capital gains using First-In-First-Out (FIFO) method with automatic data normalization for security names and brokers
- **Client Vault UI**: Custom Streamlit interface with client-specific data organization, report vault, and historical tracking
- **Cross-Validation**: Integrates holding statement data with PDF trade data for accurate capital gains computation
- **Multi-Broker Support**: Works with contract notes from multiple Indian brokers including Angel One, Axis Securities, and others

## Installation Guide

### Prerequisites

- Python 3.10 or higher
- Windows operating system

### Step-by-Step Installation

1. **Install Python**
   - Download Python from [python.org](https://www.python.org/downloads/)
   - Run the installer and check "Add Python to PATH"
   - Verify installation by opening Command Prompt and typing: `python --version`

2. **Open Terminal**
   - Press `Win + R`, type `cmd`, and press Enter
   - Navigate to the project directory:
   ```
   cd "c:\Users\Hitakshi-Uday\OneDrive\Desktop\mraca-office\pdf to excel project"
   ```

3. **Install Dependencies**
   ```
   pip install -r requirements.txt
   ```

## How to Run

Start the application by running:

```
streamlit run streamlit_app.py
```

The application will open in your default web browser at `http://localhost:8501`

## Usage

1. **Upload Contract Notes**: Select password-protected PDF contract notes from your broker
2. **Enter PDF Password**: Provide the password to decrypt the PDFs (typically your broker account password)
3. **Upload Holding Statement** (Optional): Upload your holding statement Excel file for capital gains calculation
4. **Select Client**: Choose the client from the dropdown to organize reports
5. **Generate Reports**: Click "Process Contract Notes" to extract data and generate Excel reports
6. **Download Reports**: Access generated reports in the "Report Vault" section

## Output Files

The system generates the following Excel files:

- **Master Trades Sheet**: All extracted trade data with 17 columns
- **Master Obligations Sheet**: Net settlement details from obligation tables
- **Capital Gains Summary Sheet**: FIFO-based capital gains calculations (if holding statement provided)

## Project Structure

```
├── streamlit_app.py              # Main Streamlit application
├── universal_angel_one_processor.py  # Core PDF extraction logic
├── obligation_parser.py          # Obligation data extraction
├── core/
│   └── tax_engine.py            # FIFO capital gains calculation
├── config/                       # Configuration files
├── inputs/                       # Input PDF files
├── outputs/                      # Generated Excel reports
├── Clients/                      # Client-specific data and reports
├── test_files/                   # Archived test and debug scripts
└── requirements.txt              # Python dependencies
```

## Technical Details

### Data Extraction
- Uses pdfplumber for PDF parsing with layout=True to preserve visual structure
- Implements pure visual extraction for Net Settlement values from TOTAL(NET) lines
- Extracts 17 columns including Contract Note No, Trade Date, ISIN, Security Name, Quantities, WAP, Brokerage, Net Obligation, and Net Settlement

### Tax Engine
- FIFO (First-In-First-Out) method for capital gains calculation
- Automatic data normalization (uppercase, remove corporate suffixes, broker name cleaning)
- Supports opening holdings, corporate actions (bonus, split), and trade data
- Classifies gains as STCG (Short-Term) or LTCG (Long-Term) based on holding period

### Data Normalization
- Security names: Uppercase, removes suffixes (LIMITED, LTD, INC, EQ, EQUITY)
- Broker names: Uppercase, removes spaces for exact matching
- Date sorting: Chronological order for accurate FIFO processing

## Support

For issues or questions, please contact the development team.

---

**Version**: 1.0 (MVP - Minimum Viable Product)
**Status**: Production Ready

A Python application that converts Angel One broker contract notes from PDF to Excel format with dual-table extraction logic.

## Features

- **Dual-Table Extraction**: Extracts both Trade Summary (Table 1) and Obligation Details (Table 2) from Angel One PDFs
- **Robust Fallback Strategy**: Uses crop box, text-based reconstruction, and largest number search as fallbacks
- **Master_Obligations Sheet**: Creates a dedicated sheet with all obligation data from all PDFs
- **Column 17 Integration**: Automatically fills Net Settlement (Receivable/Payable) for all trade rows per PDF
- **Negative Value Handling**: Correctly identifies Payable/(Dr) indicators and applies negative signs
- **Password Protection**: Handles password-protected PDFs
- **Streamlit UI**: User-friendly web interface for PDF processing

## Technology Stack

- **pdfplumber**: PDF parsing and table extraction with multiple strategies
- **pandas**: Data manipulation and Excel output
- **openpyxl**: Excel file creation and formatting
- **Streamlit**: Web application framework
- **Regex**: Pattern matching for text-based extraction fallbacks

## Project Structure

```
├── universal_angel_one_processor.py  # Core dual-table extraction logic
├── obligation_parser.py              # Obligation table extraction (legacy)
├── streamlit_app.py                  # Streamlit web interface
├── core/
│   ├── tax_engine.py                # Capital gains calculation
│   └── parser.py                    # Core parsing utilities
├── inputs/                          # Place your PDF contract notes here
├── outputs/                         # Converted Excel files appear here
└── requirements.txt                 # Python dependencies
```

## Dual-Table Extraction Logic

### Table 1: Trade Summary (16 Columns)

The Trade Summary table contains the primary transaction data:

**Columns:**
1. Contract Note No
2. Trade Date
3. ISIN
4. Security Name / Symbol
5. Quantity (Buy)
6. WAP (Across Exchanges) (Buy)
7. Brokerage Per Share (Rs) (Buy)
8. WAP (Across Exchanges) After Brokerage (Rs) (Buy)
9. Total BUY Value After Brokerage
10. Quantity (Sell)
11. WAP (Across Exchanges) (Sell)
12. Brokerage Per Share (Rs) (Sell)
13. WAP (Across Exchanges) After Brokerage (Rs) (Sell)
14. Total SELL Value After Brokerage
15. Net Quantity
16. Net Obligation For ISIN

**Extraction Strategy:**
- Uses three pdfplumber strategies: lines/lines, text/lines, text/text
- Identifies table by keywords: ISIN, Security Name, Quantity, WAP, Brokerage, Total BUY/SELL, Net Obligation
- Requires at least 4 indicators for confident identification
- Stops at TOTAL row
- Applies clean_numeric() to all numeric values

### Table 2: Obligation Details (12 Columns)

The Obligation Details table contains settlement information:

**Columns:**
1. Exchange
2. Pay In/Pay Out Obligation
3. Securities Transaction Tax
4. Taxable value of supply
5. CGST
6. SGST
7. Exchange Transaction Charges
8. SEBI turnover Fees
9. Stamp Duty
10. IPF Charges
11. Auction/Other Charges
12. Net Amount Receivable by Client /(Payable by Client)

**Extraction Strategy:**
- Uses the same pdfplumber strategies as Table 1 for consistency
- Identifies table by keywords: Exchange, Pay In/Pay Out, Securities Transaction Tax, Obligation, Net Amount
- Requires at least 3 indicators for confident identification
- Extracts ALL rows (not just TOTAL(NET)) for Master_Obligations sheet
- Extracts value from last column (Net Amount Receivable/Payable)
- Handles negative values for Payable/(Dr) indicators

### Column 17: Net Settlement (Receivable/Payable)

**Integration Logic:**
- Extracts the value from the last column of Table 2 (TOTAL(NET) row)
- Force-fills this value into Column 17 for EVERY SINGLE TRADE ROW from that PDF
- No more "first row only" logic - uniform filling for all rows
- Applies negative sign if text contains "Payable" or "(DR)"

## Fallback Strategies

When table detection fails, the system uses three levels of fallback:

### Level 1: Text-Based Reconstruction
- Crops the bottom half of the page where Table 1 was found
- Extracts text with `layout=True` for better alignment
- Uses regex patterns:
  - `r'TOTAL\(NET\).+?([\d,]+\.\d{2})\s*$'` for TOTAL(NET) row
  - `r'Net Amount Receivable by Client.*?([\d,]+\.\d{2})'` for Net Amount text
- Handles negative indicators (Payable, (Dr))

### Level 2: Largest Number Search
- Searches entire page for all currency values: `r'[\d,]+\.\d{2}'`
- Uses the largest number (>= 1000) as settlement
- Prints diagnostic: `[DIAGNOSTIC] Largest found: {val}. Is this the settlement?`
- Handles negative indicators

### Level 3: Error Reporting
- If all fallbacks fail, raises ValueError with clear message
- Prints critical error: `CRITICAL: Table 2 missing in {filename} - check coordinates`

## Process Steps

1. **PDF Loading**: Opens PDF with pdfplumber, handles password protection
2. **Table Detection**: Scans first 3 pages using multiple strategies
3. **Dual-Table Search**: Looks for both Table 1 (Trade Summary) and Table 2 (Obligation Details) on the same page
4. **Table 1 Extraction**: Extracts 16 columns of trade data
5. **Table 2 Extraction**: Extracts all rows from Obligation Details table
6. **Net Settlement Extraction**: Gets value from last column of TOTAL(NET) row
7. **Column 17 Filling**: Applies net settlement to ALL trade rows for that PDF
8. **Fallback Activation**: If Table 2 not found, uses text-based reconstruction
9. **Master_Obligations Creation**: Creates sheet with all obligation data from all PDFs
10. **Excel Output**: Generates Excel with Master_Trades and Master_Obligations sheets

## Excel Output Structure

### Master_Trades Sheet
- All trade data with 17 columns
- Column 17 (Net Settlement) filled uniformly per PDF
- Currency formatting (2 decimal places) for Column 17
- Grand TOTAL row at the bottom

### Master_Obligations Sheet
- All obligation data from all PDFs
- Contract Note No and Trade Date as first two columns
- All 12 columns from Obligation Details table
- clean_numeric() applied to all values
- One row per PDF (TOTAL(NET) row)

### Additional Sheets
- **Master Tax Summary**: Tax calculation summary
- **Capital Gains Summary**: Capital gains analysis (if enabled)

## Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Application
```bash
streamlit run streamlit_app.py
```

### 3. Use the Web Interface
1. Open browser to `http://localhost:8501`
2. Upload Angel One contract note PDFs
3. Enter PDF password if required
4. Select date period (optional)
5. Click "Process Contract Notes"
6. Download the generated Excel file

## Requirements

- Python 3.7+
- Angel One contract note PDFs
- Streamlit for web interface

## Key Design Decisions

**Why Dual-Table Extraction?**
- Angel One PDFs contain two critical tables on the same page
- Table 1 provides trade data, Table 2 provides settlement information
- Extracting both ensures complete financial picture
- Master_Obligations sheet provides audit trail

**Why Fallback Strategies?**
- PDF table detection can be unreliable
- Obligation Details table often lacks vertical lines
- Text-based reconstruction provides robustness
- Largest number search as final safety net

**Why Uniform Column 17 Filling?**
- Every trade in a PDF shares the same settlement
- Previous "first row only" logic was incorrect
- Uniform filling ensures accurate financial reporting
- Master_Obligations sheet provides source verification

**Why clean_numeric() on All Values?**
- PDF text can contain formatting characters
- Commas, currency symbols, and parentheses need removal
- Ensures Excel math operations work correctly
- Handles both positive and negative values

## Error Handling

- **Table 1 Missing**: Raises error - no trade data to process
- **Table 2 Missing**: Uses fallback strategies before raising error
- **Password Required**: Prompts user for password
- **Invalid PDF**: Catches and reports extraction errors
- **Zero Settlement**: Raises ValueError if net_settlement is 0 after all fallbacks

## Performance

- Processes multiple PDFs in batch
- Streamlit cache cleared before each processing run
- Progress bar shows processing status
- Individual file processing errors don't stop batch

## Future Enhancements

- Support for additional brokers (Axis, Kotak)
- Advanced date filtering on Master_Obligations sheet
- Automated reconciliation between trade and settlement data
- PDF quality checks before processing
