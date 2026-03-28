"""
Main application for Private Contract Note Converter with Audit Guard and Excel Pro.
Processes PDF files from inputs folder, detects brokers, validates calculations, and exports to Excel.
"""

import os
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
import re

# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.parser import extract_text, try_passwords, validate_pdf, extract_data_with_ai
from config.broker_rules import detect_broker, get_broker_config, BROKER_CONFIG


class ContractNoteConverter:
    def __init__(self, local_ai_url: str = "http://localhost:1234/v1"):
        """
        Initialize the converter with local AI endpoint.
        
        Args:
            local_ai_url (str): URL for local Gemma 3 model
        """
        self.local_ai_url = local_ai_url
        self.inputs_dir = Path("inputs")
        self.outputs_dir = Path("outputs")
        
        # Create directories if they don't exist
        self.inputs_dir.mkdir(exist_ok=True)
        self.outputs_dir.mkdir(exist_ok=True)
    
    def verify_math(self, row: Dict[str, Any]) -> bool:
        """
        Audit Guard: Verify trade calculations for every trade.
        Calculate (Buy Qty * Buy WAP) - (Sell Qty * Sell WAP) and compare to Net Obligation.
        
        Args:
            row (Dict[str, Any]): Trade data row
            
        Returns:
            bool: True if audit passes, False if audit fails
        """
        try:
            # Extract numeric values safely
            buy_qty = self._safe_float(row.get('Buy Qty', 0))
            buy_wap = self._safe_float(row.get('Buy WAP', 0))
            sell_qty = self._safe_float(row.get('Sell Qty', 0))
            sell_wap = self._safe_float(row.get('Sell WAP', 0))
            net_obligation = self._safe_float(row.get('Net Value', 0))
            
            # Calculate expected net obligation
            calculated_value = (buy_qty * buy_wap) - (sell_qty * sell_wap)
            
            # Compare with extracted net obligation (allow 0.50 tolerance)
            difference = abs(calculated_value - net_obligation)
            
            return difference <= 0.50
            
        except Exception as e:
            print(f"Error in verify_math: {e}")
            return False
    
    def _safe_float(self, value: Any) -> float:
        """
        Safely convert value to float, handling common string formats.
        
        Args:
            value (Any): Value to convert
            
        Returns:
            float: Converted value or 0.0 if conversion fails
        """
        try:
            if value is None or value == '' or value == 'N/A':
                return 0.0
            
            if isinstance(value, str):
                # Remove common formatting characters
                cleaned = re.sub(r'[^\d.-]', '', str(value))
                return float(cleaned) if cleaned else 0.0
            
            return float(value)
            
        except (ValueError, TypeError):
            return 0.0
    
    def get_pdf_password(self, pdf_path: str) -> Optional[str]:
        """
        Prompt user for PDF password if needed.
        
        Args:
            pdf_path (str): Path to PDF file
            
        Returns:
            Optional[str]: Password or None
        """
        print(f"\n🔐 PDF {os.path.basename(pdf_path)} appears to be password protected.")
        
        # Try common passwords first
        common_passwords = [
            None,  # Try without password
            "",    # Empty password
            "password",
            "123456",
            "qwerty"
        ]
        
        text, success, working_password = try_passwords(pdf_path, common_passwords)
        if success:
            return working_password
        
        # Ask user for password
        while True:
            password = input(f"Enter password for {os.path.basename(pdf_path)} (or 'skip' to skip): ").strip()
            if password.lower() == 'skip':
                return None
            
            text, success = extract_text(pdf_path, password)
            if success:
                return password
            else:
                print("❌ Incorrect password. Please try again.")
    
    def extract_date_from_filename(self, filename: str) -> str:
        """
        Extract date from filename for output naming.
        
        Args:
            filename (str): Original PDF filename
            
        Returns:
            str: Date in DD-MM-YYYY format or current date if not found
        """
        # Try to extract date patterns from filename
        date_patterns = [
            r'(\d{2}-\d{2}-\d{4})',  # DD-MM-YYYY
            r'(\d{2}\d{2}\d{4})',     # DDMMYYYY
            r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
            r'(\d{8})',              # YYYYMMDD
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, filename)
            if match:
                date_str = match.group(1)
                # Normalize to DD-MM-YYYY format
                if len(date_str) == 8 and date_str.isdigit():
                    if date_str[4] == '-':  # YYYY-MM-DD
                        return f"{date_str[8:10]}-{date_str[5:7]}-{date_str[0:4]}"
                    else:  # DDMMYYYY
                        return f"{date_str[:2]}-{date_str[2:4]}-{date_str[4:]}"
                return date_str
        
        # Default to current date
        return datetime.now().strftime("%d-%m-%Y")
    
    def process_single_pdf(self, pdf_path: str) -> bool:
        """
        Process a single PDF file with complete audit and excel export logic.
        
        Args:
            pdf_path (str): Path to PDF file
            
        Returns:
            bool: Success status
        """
        try:
            print(f"\n📄 Processing: {os.path.basename(pdf_path)}")
            
            # Validate PDF
            if not validate_pdf(pdf_path):
                print(f"❌ Invalid PDF file: {pdf_path}")
                return False
            
            # Get password if needed
            password = self.get_pdf_password(pdf_path)
            if password is None:
                # Try without password one more time
                text, success = extract_text(pdf_path)
                if not success:
                    print(f"❌ Could not open PDF: {pdf_path}")
                    return False
            else:
                text, success = extract_text(pdf_path, password)
                if not success:
                    print(f"❌ Could not extract text from PDF: {pdf_path}")
                    return False
            
            # Detect broker
            broker = detect_broker(text)
            if broker == 'UNKNOWN':
                print(f"⚠️  Could not detect broker for {os.path.basename(pdf_path)}")
                print("Available brokers: ANGELONE, AXIS, KOTAK")
                
                # Ask user to specify broker
                while True:
                    user_broker = input("Enter broker name (ANGELONE/AXIS/KOTAK) or 'skip': ").strip().upper()
                    if user_broker in ['ANGELONE', 'AXIS', 'KOTAK']:
                        broker = user_broker
                        break
                    elif user_broker == 'SKIP':
                        return False
                    else:
                        print("Invalid broker. Please enter ANGELONE, AXIS, or KOTAK.")
            
            print(f"🏢 Detected broker: {broker}")
            
            # Get broker configuration
            broker_config = get_broker_config(broker)
            if not broker_config:
                print(f"❌ No configuration found for broker: {broker}")
                return False
            
            # Extract data using AI
            extracted_data = extract_data_with_ai(text, broker, broker_config['headers'])
            if extracted_data is None:
                print(f"❌ Failed to extract data using AI")
                return False
            
            # Process trades data
            trades_data = self._process_trades_data(extracted_data, broker_config)
            if not trades_data:
                print(f"❌ No valid trades data found")
                return False
            
            # Process tax/obligation data
            tax_data = self._process_tax_data(extracted_data)
            
            # Create Excel output
            return self._create_excel_output(trades_data, tax_data, broker, pdf_path)
            
        except Exception as e:
            print(f"❌ Error processing PDF {pdf_path}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _process_trades_data(self, extracted_data: Dict, broker_config: Dict) -> List[Dict]:
        """
        Process trades data with audit guard validation and TOTAL row calculation.
        
        Args:
            extracted_data (Dict): Raw data from AI
            broker_config (Dict): Broker configuration
            
        Returns:
            List[Dict]: Processed trades with audit status and TOTAL row
        """
        trades = []
        
        # Handle different data structures from AI
        if 'trades' in extracted_data:
            trade_list = extracted_data['trades']
        elif isinstance(extracted_data, list):
            trade_list = extracted_data
        else:
            # Assume the main dict contains trade data
            trade_list = [extracted_data]
        
        total_buy_qty = 0
        total_sell_qty = 0
        total_net_obligation = 0
        
        for trade_data in trade_list:
            # Create row with all expected headers
            row = {}
            for header in broker_config['headers']:
                row[header] = trade_data.get(header, 'N/A')
            
            # Apply audit guard (skip for TOTAL rows)
            if str(trade_data.get('Security Name / Symbol', '')).upper() != 'TOTAL':
                audit_status = 'AUDIT_PASS' if self.verify_math(row) else 'AUDIT_FAIL'
                row['Audit_Status'] = audit_status
                
                # Accumulate totals (skip non-numeric and TOTAL rows)
                try:
                    buy_qty = self._safe_float(trade_data.get('BUY Quantity', 0))
                    sell_qty = self._safe_float(trade_data.get('SELL Quantity', 0))
                    net_obligation = self._safe_float(trade_data.get('Net Obligation For ISIN', 0))
                    
                    total_buy_qty += buy_qty
                    total_sell_qty += sell_qty
                    total_net_obligation += net_obligation
                except:
                    pass
            else:
                row['Audit_Status'] = 'TOTAL_ROW'
            
            trades.append(row)
        
        # Add TOTAL row if not already present - extract from AI data instead of calculating
        has_total_row = any(str(trade.get('Security Name / Symbol', '')).upper() == 'TOTAL' for trade in trades)
        if not has_total_row:
            # Look for Total row in extracted data
            total_buy_qty = None
            total_sell_qty = None  
            total_net_obligation = None
            
            for trade_data in trade_list:
                symbol = str(trade_data.get('Security Name / Symbol', '')).upper()
                if symbol == 'TOTAL':
                    total_buy_qty = self._safe_float(trade_data.get('BUY Quantity', 0))
                    total_sell_qty = self._safe_float(trade_data.get('SELL Quantity', 0))
                    total_net_obligation = self._safe_float(trade_data.get('Net Obligation For ISIN', 0))
                    break
            
            # If no Total row found, use calculated totals as fallback
            if total_buy_qty is None:
                total_buy_qty = sum(self._safe_float(trade.get('BUY Quantity', 0)) for trade in trades if trade.get('Audit_Status') != 'TOTAL_ROW')
                total_sell_qty = sum(self._safe_float(trade.get('SELL Quantity', 0)) for trade in trades if trade.get('Audit_Status') != 'TOTAL_ROW')
                total_net_obligation = sum(self._safe_float(trade.get('Net Obligation For ISIN', 0)) for trade in trades if trade.get('Audit_Status') != 'TOTAL_ROW')
            
            total_row = {}
            for header in broker_config['headers']:
                if header == 'Security Name / Symbol':
                    total_row[header] = 'TOTAL'
                elif header == 'BUY Quantity':
                    total_row[header] = total_buy_qty
                elif header == 'SELL Quantity':
                    total_row[header] = total_sell_qty
                elif header == 'Net Obligation For ISIN':
                    total_row[header] = total_net_obligation
                else:
                    total_row[header] = 'N/A'
            
            total_row['Audit_Status'] = 'TOTAL_ROW'
            trades.append(total_row)
        
        return trades
    
    def _process_tax_data(self, extracted_data) -> Dict[str, float]:
        """
        Process tax/obligation details for summary.
        
        Args:
            extracted_data: Raw data from AI (could be dict or list)
            
        Returns:
            Dict[str, float]: Tax details
        """
        tax_data = {
            'GST': 0.0,
            'STT': 0.0,
            'SEBI_Fees': 0.0,
            'Stamp_Duty': 0.0,
            'Net_Obligation': 0.0
        }
        
        # Handle case where extracted_data is a list (direct trades)
        if isinstance(extracted_data, list):
            # No obligation details available when AI returns just trades list
            return tax_data
        
        # Extract obligation details if it's a dict
        obligation_details = extracted_data.get('obligation_details', {})
        
        for key in tax_data.keys():
            value = obligation_details.get(key.replace('_', ' '), 0)
            tax_data[key] = self._safe_float(value)
        
        return tax_data
    
    def _create_excel_output(self, trades_data: List[Dict], tax_data: Dict, 
                           broker: str, pdf_path: str) -> bool:
        """
        Excel Pro: Create two-sheet Excel output with proper formatting.
        
        Args:
            trades_data (List[Dict]): Processed trades data
            tax_data (Dict): Tax/obligation data
            broker (str): Broker name
            pdf_path (str): Original PDF path
            
        Returns:
            bool: Success status
        """
        try:
            # Extract date for filename
            date_str = self.extract_date_from_filename(os.path.basename(pdf_path))
            
            # Create output filename
            excel_filename = f"{broker}_{date_str}_Converted.xlsx"
            excel_path = self.outputs_dir / excel_filename
            
            # Create DataFrames
            trades_df = pd.DataFrame(trades_data)
            
            # Create tax summary DataFrame
            tax_summary_data = [
                ['Particular', 'Amount (₹)'],
                ['GST', tax_data['GST']],
                ['STT', tax_data['STT']],
                ['SEBI Fees', tax_data['SEBI_Fees']],
                ['Stamp Duty', tax_data['Stamp_Duty']],
                ['Net Obligation', tax_data['Net_Obligation']]
            ]
            tax_df = pd.DataFrame(tax_summary_data[1:], columns=tax_summary_data[0])
            
            # Write to Excel with multiple sheets
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                # Trades sheet
                trades_df.to_excel(writer, sheet_name='Trades', index=False)
                
                # Tax_Summary sheet
                tax_df.to_excel(writer, sheet_name='Tax_Summary', index=False)
                
                # Get workbook and worksheet objects for formatting
                workbook = writer.book
                
                # Format Trades sheet
                trades_sheet = writer.sheets['Trades']
                self._format_worksheet(trades_sheet, trades_df, workbook)
                
                # Format Tax_Summary sheet
                tax_sheet = writer.sheets['Tax_Summary']
                self._format_worksheet(tax_sheet, tax_df, workbook)
            
            print(f"✅ Successfully saved to: {excel_path}")
            print(f"📊 Trades processed: {len(trades_data)}")
            print(f"🔍 Audit results: {sum(1 for t in trades_data if t['Audit_Status'] == 'AUDIT_PASS')} passed, {sum(1 for t in trades_data if t['Audit_Status'] == 'AUDIT_FAIL')} failed")
            
            return True
            
        except Exception as e:
            print(f"❌ Error creating Excel output: {e}")
            return False
    
    def _format_worksheet(self, worksheet, dataframe, workbook):
        """
        Apply basic formatting to Excel worksheet.
        
        Args:
            worksheet: Excel worksheet object
            dataframe: Pandas DataFrame
            workbook: Excel workbook object
        """
        try:
            # Auto-adjust column widths
            for column in dataframe.columns:
                max_length = max(
                    dataframe[column].astype(str).map(len).max(),
                    len(str(column))
                )
                # Adjust width (with some padding)
                worksheet.column_dimensions[chr(65 + dataframe.columns.get_loc(column))].width = min(max_length + 2, 50)
        except:
            pass  # Ignore formatting errors
    
    def process_all_pdfs(self):
        """
        Process all PDF files in the inputs directory with try-except for error resilience.
        """
        print("🚀 Starting Contract Note Converter with Audit Guard & Excel Pro")
        print(f"📂 Input directory: {self.inputs_dir.absolute()}")
        print(f"📁 Output directory: {self.outputs_dir.absolute()}")
        print(f"🤖 Using local AI at: {self.local_ai_url}")
        
        # Get all PDF files
        pdf_files = list(self.inputs_dir.glob("*.pdf"))
        
        if not pdf_files:
            print("❌ No PDF files found in the inputs directory.")
            print("Please place your contract note PDFs in the 'inputs' folder.")
            return
        
        print(f"📊 Found {len(pdf_files)} PDF file(s)")
        
        # Process each PDF with try-except for error resilience
        success_count = 0
        failed_files = []
        
        for pdf_path in pdf_files:
            try:
                if self.process_single_pdf(str(pdf_path)):
                    success_count += 1
                else:
                    failed_files.append(pdf_path.name)
            except Exception as e:
                print(f"❌ Unexpected error processing {pdf_path.name}: {e}")
                failed_files.append(pdf_path.name)
                continue  # Continue with next file
        
        print(f"\n✅ Processing complete!")
        print(f"📈 Successfully processed: {success_count}/{len(pdf_files)} files")
        
        if failed_files:
            print(f"❌ Failed files: {', '.join(failed_files)}")
        
        print(f"📁 Check the 'outputs' folder for converted Excel files.")


def main():
    """Main entry point."""
    converter = ContractNoteConverter()
    
    try:
        converter.process_all_pdfs()
    except KeyboardInterrupt:
        print("\n\n⏹️  Processing interrupted by user.")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
