#!/usr/bin/env python3
"""
Capital Gains FIFO Engine
Income-tax Act, 2025 Rules Implementation
"""

import pandas as pd
from datetime import datetime, timedelta
from collections import deque
from typing import List, Dict, Tuple, Optional
import re

def parse_date(date_str: str) -> datetime:
    """Parse date string in DD-MM-YYYY format to datetime object."""
    try:
        if isinstance(date_str, str):
            # Handle DD-MM-YYYY format
            if '-' in date_str:
                parts = date_str.split('-')
                if len(parts) == 3:
                    return datetime(int(parts[2]), int(parts[1]), int(parts[0]))
            # Handle DD/MM/YYYY format
            elif '/' in date_str:
                parts = date_str.split('/')
                if len(parts) == 3:
                    return datetime(int(parts[2]), int(parts[1]), int(parts[0]))
        return None
    except (ValueError, TypeError):
        return None

def calculate_holding_period(buy_date: datetime, sell_date: datetime) -> int:
    """Calculate holding period in days between buy and sell dates."""
    if buy_date and sell_date:
        return (sell_date - buy_date).days
    return 0

def classify_capital_gain(holding_days: int) -> str:
    """Classify capital gain as STCG or LTCG based on holding period."""
    if holding_days > 365:
        return "LTCG"
    else:
        return "STCG"

def parse_holdings_csv(holdings_file) -> Dict:
    """Parse holdings CSV file and return dictionary by ISIN."""
    holdings = {}
    if holdings_file:
        try:
            holdings_df = pd.read_csv(holdings_file)
            # Normalize holdings data for tax engine
            holdings_df = normalize_for_tax_engine(holdings_df)
            
            for _, row in holdings_df.iterrows():
                isin = str(row.get('ISIN', '')).strip()
                if isin and isin not in holdings:
                    holdings[isin] = []
                
                if isin:
                    holdings[isin].append({
                        'quantity': float(row.get('Quantity', 0)),
                        'date': parse_date(str(row.get('Purchase Date', ''))),
                        'purchase_price': float(row.get('Purchase Price', 0)),
                        'source': 'opening'
                    })
        except Exception as e:
            print(f"Error parsing holdings file: {str(e)}")
    return holdings

def process_corporate_actions(corporate_actions_df, holdings) -> Dict:
    """Process corporate actions and update holdings."""
    if corporate_actions_df is None or corporate_actions_df.empty:
        return holdings
    
    corporate_actions_df = corporate_actions_df.dropna(subset=['ISIN', 'Action Type'])
    
    for _, action in corporate_actions_df.iterrows():
        isin = str(action['ISIN']).strip()
        action_type = action['Action Type']
        ratio = str(action['Ratio'])
        effective_date = parse_date(str(action['Effective Date']))
        
        if not isin or not action_type or not ratio or not effective_date:
            continue
            
        if isin not in holdings:
            holdings[isin] = []
        
        # Parse ratio (e.g., "1:5" for bonus, "1:2" for split)
        if ':' in ratio:
            parts = ratio.split(':')
            if len(parts) == 2:
                numerator = float(parts[0])
                denominator = float(parts[1])
                
                if action_type == 'Bonus':
                    # Bonus logic: Increase quantity, set COA to 0
                    for holding in holdings[isin]:
                        bonus_qty = holding['quantity'] * (denominator / numerator - 1)
                        holdings[isin].append({
                            'quantity': bonus_qty,
                            'date': effective_date,
                            'purchase_price': 0.0,  # COA = 0 for bonus
                            'source': 'bonus',
                            'original_holding': holding
                        })
                
                elif action_type == 'Split':
                    # Split logic: Multiply quantity by ratio, divide COA by ratio
                    split_ratio = denominator / numerator
                    for holding in holdings[isin]:
                        split_qty = holding['quantity'] * split_ratio
                        split_price = holding['purchase_price'] / split_ratio
                        holdings[isin].append({
                            'quantity': split_qty,
                            'date': effective_date,
                            'purchase_price': split_price,
                            'source': 'split',
                            'original_holding': holding
                        })
    
    return holdings

def normalize_for_tax_engine(df):
    """
    Normalize data for tax engine by cleaning security names and brokers.
    
    Args:
        df: DataFrame with trades or holdings data
        
    Returns:
        Normalized DataFrame
    """
    df = df.copy()
    
    # Name cleaning logic
    if 'Security Name / Symbol' in df.columns:
        # Uppercase everything
        df['Security Name / Symbol'] = df['Security Name / Symbol'].str.upper()
        # Remove common corporate suffixes
        df['Security Name / Symbol'] = df['Security Name / Symbol'].str.replace(r'\s+(LIMITED|LTD|LTD\.|INC|EQ|EQUITY)\s*$', '', regex=True)
        # Strip trailing/leading whitespace
        df['Security Name / Symbol'] = df['Security Name / Symbol'].str.strip()
    
    if 'ISIN' in df.columns:
        # Uppercase everything
        df['ISIN'] = df['ISIN'].str.upper()
        # Remove common corporate suffixes
        df['ISIN'] = df['ISIN'].str.replace(r'\s+(LIMITED|LTD|LTD\.|INC|EQ|EQUITY)\s*$', '', regex=True)
        # Strip trailing/leading whitespace
        df['ISIN'] = df['ISIN'].str.strip()
    
    # Broker cleaning logic
    if 'Broker' in df.columns:
        # Uppercase and remove spaces
        df['Broker'] = df['Broker'].str.upper().str.replace(' ', '')
    
    return df


def calculate_capital_gains(master_df: pd.DataFrame, holdings_file=None, corporate_actions=None) -> pd.DataFrame:
    """
    Calculate capital gains using FIFO method for each ISIN.
    
    Args:
        master_df: DataFrame with consolidated trade data
        
    Returns:
        DataFrame with capital gains calculations
    """
    # Ensure 'Trade Date' column exists
    if 'Trade Date' not in master_df.columns and 'date' in master_df.columns:
        master_df['Trade Date'] = master_df['date']
    
    # Normalize master_df for tax engine (clean names and brokers)
    master_df = normalize_for_tax_engine(master_df)
    
    # Date sorting: ensure master_df is sorted chronologically from oldest to newest
    master_df = master_df.sort_values(by='Trade Date')
    
    # Parse holdings and corporate actions
    holdings = parse_holdings_csv(holdings_file)
    holdings = process_corporate_actions(corporate_actions, holdings)
    
    # Filter out TOTAL rows and create a copy
    trades_df = master_df[master_df['ISIN'] != 'TOTAL'].copy()
    
    # Convert dates
    trades_df['Trade Date'] = trades_df['Trade Date'].apply(parse_date)
    
    # Add trades to holdings - use Security Name for matching instead of ISIN
    for _, trade in trades_df.iterrows():
        security_name = trade['Security Name / Symbol']
        isin = trade['ISIN']
        
        # Use security name as key for matching (since PDF may not have actual ISINs)
        key = security_name if security_name and security_name != '' else isin
        
        if pd.notna(key) and key != '':
            if key not in holdings:
                holdings[key] = []
            
            # Add trade to holdings if it's a buy transaction
            if trade['Quantity (Buy)'] > 0:
                holdings[key].append({
                    'date': trade['Trade Date'],
                    'quantity': trade['Quantity (Buy)'],
                    'price': trade['WAP (Across Exchanges) After Brokerage (Rs) (Buy)'],
                    'isin': isin,
                    'security_name': security_name,
                    'source': 'trade'
                })
    
    # Sort holdings by key and date for proper FIFO processing
    for key in holdings:
        holdings[key].sort(key=lambda x: (x['date'], x['source']))  # Opening holdings first
    
    capital_gains_data = []
    
    # Process each security separately
    for key in holdings.keys():
        if pd.isna(key) or key == '':
            continue
        
        # Match trades by security name (fallback to ISIN if security name is empty)
        if 'Security Name / Symbol' in trades_df.columns:
            matched_trades = trades_df[trades_df['Security Name / Symbol'] == key].copy()
            if matched_trades.empty:
                matched_trades = trades_df[trades_df['ISIN'] == key].copy()
        else:
            matched_trades = trades_df[trades_df['ISIN'] == key].copy()
        
        if matched_trades.empty:
            continue
            
        security_name = matched_trades['Security Name / Symbol'].iloc[0] if not matched_trades.empty else key
        isin = matched_trades['ISIN'].iloc[0] if not matched_trades.empty else key
        
        # Use holdings as FIFO queue (includes opening holdings and corporate actions)
        buy_queue = deque(holdings.get(key, []))
        
        for _, trade in matched_trades.iterrows():
            trade_date = trade['Trade Date']
            quantity_buy = trade['Quantity (Buy)']
            quantity_sell = trade['Quantity (Sell)']
            buy_wap = trade['WAP (Across Exchanges) After Brokerage (Rs) (Buy)']
            sell_wap = trade['WAP (Across Exchanges) After Brokerage (Rs) (Sell)']
            
            # Add buy transactions to queue
            if quantity_buy > 0:
                buy_queue.append({
                    'date': trade_date,
                    'quantity': quantity_buy,
                    'price': buy_wap,
                    'isin': isin,
                    'security_name': security_name,
                    'source': 'trade'
                })
            
            # Process sell transactions using FIFO
            if quantity_sell > 0 and buy_queue:
                remaining_sell_qty = quantity_sell
                
                while remaining_sell_qty > 0 and buy_queue:
                    oldest_buy = buy_queue[0]
                    
                    # Calculate quantity to match
                    match_qty = min(remaining_sell_qty, oldest_buy['quantity'])
                    
                    # Calculate capital gain/loss
                    buy_price = oldest_buy['price']
                    sell_price = sell_wap
                    gain_loss = (sell_price - buy_price) * match_qty
                    
                    # Calculate holding period and classification
                    holding_days = calculate_holding_period(oldest_buy['date'], trade_date)
                    classification = classify_capital_gain(holding_days)
                    
                    # Check for grandfathering rule
                    grandfathering_note = ""
                    if oldest_buy['date'] and oldest_buy['date'] < datetime(2018, 1, 31):
                        grandfathering_note = "Manual FMV Required"
                    
                    # Determine opening qty matched and corporate action adjustment
                    opening_qty_matched = 0
                    corporate_action_adjustment = ""
                    purchase_consideration = (match_qty * buy_price)
                    
                    if oldest_buy.get('source') in ['opening', 'bonus', 'split']:
                        opening_qty_matched += match_qty
                        corporate_action_adjustment = f"{oldest_buy['source'].title()}"
                    
                    # Calculate full value of consideration
                    full_value_consideration = (match_qty * sell_price)
                    
                    # Add to capital gains data
                    capital_gains_data.append({
                        'ISIN': isin,
                        'Security Name': security_name,
                        'Buy Date': oldest_buy['date'].strftime('%d-%m-%Y'),
                        'Sell Date': trade_date.strftime('%d-%m-%Y'),
                        'Quantity': match_qty,
                        'Buy Price': round(buy_price, 2),
                        'Sell Price': round(sell_price, 2),
                        'Gain/Loss': round(gain_loss, 2),
                        'Classification': classification,
                        'Holding Period (Days)': holding_days,
                        'Grandfathering Note': grandfathering_note,
                        'Opening Qty Matched': opening_qty_matched,
                        'Corporate Action Adjustment': corporate_action_adjustment,
                        'Purchase Consideration': round(purchase_consideration, 2),
                        'Full Value of Consideration': round(full_value_consideration, 2)
                    })
                    
                    # Update quantities
                    oldest_buy['quantity'] -= match_qty
                    remaining_sell_qty -= match_qty
                    
                    # Remove buy from queue if fully consumed
                    if oldest_buy['quantity'] <= 0:
                        buy_queue.popleft()
    
    # Create DataFrame from capital gains data
    capital_gains_df = pd.DataFrame(capital_gains_data)
    
    if not capital_gains_df.empty:
        # Add summary calculations
        stcg_total = capital_gains_df[capital_gains_df['Classification'] == 'STCG']['Gain/Loss'].sum()
        ltcg_total = capital_gains_df[capital_gains_df['Classification'] == 'LTCG']['Gain/Loss'].sum()
        
        # Calculate closing stock valuation
        closing_stock_data = []
        for isin in holdings.keys():
            remaining_qty = sum(holding['quantity'] for holding in holdings[isin])
            total_invested_value = sum(holding['quantity'] * holding['price'] for holding in holdings[isin])
            
            if remaining_qty > 0:
                # Calculate average buy price
                avg_buy_price = total_invested_value / remaining_qty if remaining_qty > 0 else 0.0
                
                # Get security name from master_df or use ISIN as fallback
                security_name = ""
                if not master_df.empty:
                    security_row = master_df[master_df['ISIN'] == isin]
                    if not security_row.empty:
                        security_name = security_row['Security Name / Symbol'].iloc[0]
                
                if not security_name:
                    security_name = isin  # Use ISIN as temporary name if not found
                
                closing_stock_data.append({
                    'ISIN': isin,
                    'Security Name': security_name,
                    'Remaining Quantity': remaining_qty,
                    'Average Buy Price': round(avg_buy_price, 2),
                    'Total Invested Value': round(total_invested_value, 2)
                })
        
        # Add summary rows
        summary_row = {
            'ISIN': 'TOTAL',
            'Security Name': 'SUMMARY',
            'Buy Date': '',
            'Sell Date': '',
            'Quantity': '',
            'Buy Price': '',
            'Sell Price': '',
            'Gain/Loss': round(stcg_total + ltcg_total, 2),
            'Classification': 'TOTAL',
            'Holding Period (Days)': '',
            'Grandfathering Note': '',
            'Opening Qty Matched': '',
            'Corporate Action Adjustment': '',
            'Purchase Consideration': '',
            'Full Value of Consideration': ''
        }
        
        # Add STCG and LTCG summary rows
        stcg_row = {
            'ISIN': '',
            'Security Name': 'Total STCG (Taxable @ 20%)',
            'Buy Date': '',
            'Sell Date': '',
            'Quantity': '',
            'Buy Price': '',
            'Sell Price': '',
            'Gain/Loss': round(stcg_total, 2),
            'Classification': 'STCG',
            'Holding Period (Days)': '',
            'Grandfathering Note': '',
            'Opening Qty Matched': '',
            'Corporate Action Adjustment': '',
            'Purchase Consideration': '',
            'Full Value of Consideration': ''
        }
        
        ltcg_row = {
            'ISIN': '',
            'Security Name': 'Total LTCG (Taxable @ 12.5% after 1.25L exemption)',
            'Buy Date': '',
            'Sell Date': '',
            'Quantity': '',
            'Buy Price': '',
            'Sell Price': '',
            'Gain/Loss': round(ltcg_total, 2),
            'Classification': 'LTCG',
            'Holding Period (Days)': '',
            'Grandfathering Note': '',
            'Opening Qty Matched': '',
            'Corporate Action Adjustment': '',
            'Purchase Consideration': '',
            'Full Value of Consideration': ''
        }
        
        # Append summary rows
        summary_df = pd.DataFrame([stcg_row, ltcg_row, summary_row])
        capital_gains_df = pd.concat([capital_gains_df, summary_df], ignore_index=True)
        
        # Add closing stock valuation table
        if closing_stock_data:
            closing_stock_df = pd.DataFrame(closing_stock_data)
            
            # Add separator row with proper header
            separator_row = {
                'ISIN': '',
                'Security Name': '--- CLOSING STOCK VALUATION (PORTFOLIO) ---',
                'Buy Date': '',
                'Sell Date': '',
                'Quantity': '',
                'Buy Price': '',
                'Sell Price': '',
                'Gain/Loss': '',
                'Classification': '',
                'Holding Period (Days)': '',
                'Grandfathering Note': '',
                'Opening Qty Matched': '',
                'Corporate Action Adjustment': '',
                'Purchase Consideration': '',
                'Full Value of Consideration': ''
            }
            
            # Create closing stock valuation table with proper column structure
            closing_stock_table = []
            for stock in closing_stock_data:
                closing_stock_table.append({
                    'ISIN': stock['ISIN'],
                    'Security Name': stock['Security Name'],
                    'Buy Date': '',
                    'Sell Date': '',
                    'Quantity': stock['Remaining Quantity'],
                    'Buy Price': stock['Average Buy Price'],
                    'Sell Price': '',
                    'Gain/Loss': stock['Total Invested Value'],
                    'Classification': '',
                    'Holding Period (Days)': '',
                    'Grandfathering Note': '',
                    'Opening Qty Matched': '',
                    'Corporate Action Adjustment': '',
                    'Purchase Consideration': '',
                    'Full Value of Consideration': ''
                })
            
            closing_stock_with_header = pd.DataFrame([separator_row] + closing_stock_table)
            capital_gains_df = pd.concat([capital_gains_df, closing_stock_with_header], ignore_index=True)
    
    return capital_gains_df

def create_capital_gains_summary_sheet(writer, master_df, holdings_file=None, corporate_actions=None):
    """
    Create Capital Gains Summary sheet in the Master Excel file.
    
    Args:
        writer: Excel writer object
        master_df: Master trades DataFrame
    """
    try:
        # Calculate capital gains
        capital_gains_df = calculate_capital_gains(master_df, holdings_file, corporate_actions)
        
        if not capital_gains_df.empty:
            # Write to Excel
            capital_gains_df.to_excel(writer, sheet_name='Capital_Gains_Summary', index=False)
            
            # Get the worksheet for formatting
            worksheet = writer.sheets['Capital_Gains_Summary']
            
            # Auto-adjust column widths
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
            
            # Format summary rows and closing stock valuation
            for row in worksheet.iter_rows():
                for cell in row:
                    if cell.value in ['TOTAL', 'SUMMARY']:
                        cell.font = cell.font.copy(bold=True)
                        cell.fill = cell.fill.copy(start_color="D9E1F2")
                    elif 'Taxable' in str(cell.value):
                        cell.font = cell.font.copy(bold=True, color="FF0000")
                        cell.fill = cell.fill.copy(start_color="FFE6E6")
                    elif 'CLOSING STOCK VALUATION' in str(cell.value):
                        cell.font = cell.font.copy(bold=True, color="FFFFFF")
                        cell.fill = cell.fill.copy(start_color="4F81BD")
                    elif isinstance(cell.value, (int, float)) and cell.value != 0:
                        # Format numeric columns to 2 decimal places
                        cell.number_format = '#,##0.00'
                        
                    # Highlight closing stock valuation rows
                    if cell.row > 1 and worksheet.cell(cell.row, 2).value and 'CLOSING STOCK VALUATION' in str(worksheet.cell(cell.row, 2).value):
                        if cell.row > 1 and worksheet.cell(cell.row - 1, 2).value and 'CLOSING STOCK VALUATION' in str(worksheet.cell(cell.row - 1, 2).value):
                            # This is a data row in the closing stock valuation
                            if cell.column_letter in ['E', 'G']:  # Quantity, Buy Price, Gain/Loss columns
                                if isinstance(cell.value, (int, float)):
                                    cell.number_format = '#,##0.00'
                                    cell.fill = cell.fill.copy(start_color="F2F2F2")
            
            return True
        else:
            # Create empty sheet with message
            empty_df = pd.DataFrame({'Message': ['No capital gains data found']})
            empty_df.to_excel(writer, sheet_name='Capital_Gains_Summary', index=False)
            return False
            
    except Exception as e:
        print(f"Error creating Capital Gains Summary: {str(e)}")
        return False

def get_tax_summary_stats(capital_gains_df: pd.DataFrame) -> Dict:
    """
    Get summary statistics for tax calculations.
    
    Args:
        capital_gains_df: DataFrame with capital gains data
        
    Returns:
        Dictionary with tax summary statistics
    """
    if capital_gains_df.empty:
        return {
            'total_stcg': 0.0,
            'total_ltcg': 0.0,
            'total_gain_loss': 0.0,
            'stcg_tax': 0.0,
            'ltcg_tax': 0.0
        }
    
    # Filter out summary rows
    gains_data = capital_gains_df[capital_gains_df['ISIN'] != 'TOTAL']
    gains_data = gains_data[gains_data['Security Name'] != 'SUMMARY']
    
    # Calculate totals
    total_stcg = gains_data[gains_data['Classification'] == 'STCG']['Gain/Loss'].sum()
    total_ltcg = gains_data[gains_data['Classification'] == 'LTCG']['Gain/Loss'].sum()
    total_gain_loss = total_stcg + total_ltcg
    
    # Calculate tax (FY 2025-26 rates)
    stcg_tax = total_stcg * 0.20  # 20% on STCG
    ltcg_tax = max(0, (total_ltcg - 125000) * 0.125)  # 12.5% after 1.25L exemption
    
    return {
        'total_stcg': round(total_stcg, 2),
        'total_ltcg': round(total_ltcg, 2),
        'total_gain_loss': round(total_gain_loss, 2),
        'stcg_tax': round(stcg_tax, 2),
        'ltcg_tax': round(ltcg_tax, 2)
    }

def validate_capital_gains_data(master_df: pd.DataFrame) -> Dict:
    """
    Validate master DataFrame for capital gains calculation.
    
    Args:
        master_df: Master trades DataFrame
        
    Returns:
        Dictionary with validation results
    """
    validation_result = {
        'is_valid': True,
        'errors': [],
        'warnings': [],
        'stats': {}
    }
    
    # Check required columns
    required_columns = [
        'ISIN', 'Security Name / Symbol', 'Trade Date',
        'Quantity (Buy)', 'Quantity (Sell)',
        'WAP (Across Exchanges) After Brokerage (Rs) (Buy)',
        'WAP (Across Exchanges) After Brokerage (Rs) (Sell)'
    ]
    
    missing_columns = [col for col in required_columns if col not in master_df.columns]
    if missing_columns:
        validation_result['is_valid'] = False
        validation_result['errors'].append(f"Missing required columns: {', '.join(missing_columns)}")
    
    # Check for buy/sell data
    if not validation_result['is_valid']:
        return validation_result
    
    # Filter out TOTAL rows
    trades_df = master_df[master_df['ISIN'] != 'TOTAL']
    
    # Check for valid ISINs
    valid_isins = trades_df[trades_df['ISIN'].notna() & (trades_df['ISIN'] != '')]['ISIN'].unique()
    if len(valid_isins) == 0:
        validation_result['is_valid'] = False
        validation_result['errors'].append("No valid ISIN data found")
    
    # Check for buy/sell transactions
    total_buy = trades_df['Quantity (Buy)'].sum()
    total_sell = trades_df['Quantity (Sell)'].sum()
    
    validation_result['stats'] = {
        'total_isins': len(valid_isins),
        'total_buy_qty': total_buy,
        'total_sell_qty': total_sell,
        'total_trades': len(trades_df)
    }
    
    # Warnings
    if total_buy == 0:
        validation_result['warnings'].append("No buy transactions found")
    if total_sell == 0:
        validation_result['warnings'].append("No sell transactions found")
    
    return validation_result
