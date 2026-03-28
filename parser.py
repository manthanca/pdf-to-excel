"""
PDF parser module for extracting table data from contract notes.
Handles password-protected PDFs and extracts table data using AI with JSON safety.
"""

import pdfplumber
import os
import re
import json
import openai
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


def extract_data_with_ai(text: str, broker: str, headers: List[str]) -> Optional[Dict]:
    """
    Connect to local Gemma 3 model via openai library to extract structured data.
    
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
            api_key="not-needed"  # Local models don't need API key
        )
        
        prompt = f"""
Extract structured trade data from this {broker} contract note.

TEXT:
{text}

CRITICAL EXTRACTION RULES:
- Extract EVERY single row from the table that has an ISIN number
- Include ALL rows, especially the last 3 rows before the Total row
- Explicitly capture the 'Total' row at the very bottom of the table
- Do NOT skip any rows that contain data

EXACT COLUMN NAMES (use these precisely):
{headers}

DATA HANDLING:
- For 'Net Obligation For ISIN': Extract the exact string/value from PDF without performing any math calculations
- If PDF shows positive values, extract them as positive (do not convert to negative)
- Preserve the exact format and values as shown in the PDF

Also extract obligation details (GST, STT, SEBI Fees, Stamp Duty, Net Obligation) and include them in a nested object under "obligation_details".

Return ONLY valid JSON array without any conversational text or explanations.
"""
        
        response = client.chat.completions.create(
            model="gemma-3-4b",
            messages=[
                {"role": "system", "content": "You are a financial data extraction expert. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=4000
        )
        
        raw_response = response.choices[0].message.content.strip()
        
        # JSON Safety: Extract all individual JSON objects and handle multiple objects
        json_objects = re.findall(r'\{.*?\}', raw_response, re.DOTALL)
        
        if not json_objects:
            print("No JSON objects found in AI response")
            print(f"Raw response: {raw_response}")
            return None
        
        # Join all JSON objects into a valid list
        if len(json_objects) == 1:
            json_str = json_objects[0]
        else:
            json_str = '[' + ','.join(json_objects) + ']'
        
        # Additional check: if string doesn't start with [ and end with ], wrap it
        if not (json_str.strip().startswith('[') and json_str.strip().endswith(']')):
            json_str = f'[{json_str}]'
        
        try:
            parsed_data = json.loads(json_str)
            return parsed_data
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Processed JSON string: {json_str}")
            print(f"Raw response: {raw_response}")
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
