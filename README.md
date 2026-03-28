# Private Contract Note Converter

A Python application that converts broker contract notes from PDF to Excel format using local AI processing.

## Features

- **Multi-Broker Support**: Axis Securities, Angel One, and Kotak Securities
- **Password Protection**: Handles password-protected PDFs
- **Local AI Processing**: Uses your local Gemma 3 model via LM Studio
- **Intelligent Detection**: Automatically detects broker from document content
- **Structured Output**: Converts to Excel with proper formatting

## Project Structure

```
├── inputs/          # Place your PDF contract notes here
├── outputs/         # Converted Excel files appear here
├── core/            # Core parsing logic
│   └── parser.py    # PDF text extraction
├── config/          # Configuration files
│   └── broker_rules.py  # Broker detection rules
├── main.py          # Main application
├── requirements.txt # Python dependencies
└── README.md       # This file
```

## Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up Local AI
1. Install and run LM Studio
2. Download and load the Gemma 3 4B GGUF model
3. Start the local server at `http://localhost:1234/v1`

### 3. Run the Application
```bash
python main.py
```

## Usage

1. Place your contract note PDFs in the `inputs/` folder
2. Run `python main.py`
3. The application will:
   - Detect the broker automatically
   - Prompt for PDF passwords if needed
   - Extract data using your local AI model
   - Save converted Excel files in the `outputs/` folder

## Supported Brokers

- **AXIS**: Keywords include 'Axis Securities', 'Trade Confirmation'
- **ANGEL**: Keywords include 'Angel One', 'Transactional Report'  
- **KOTAK**: Keywords include 'Kotak Securities', 'Trade Summary'

## Output Format

The Excel files contain:
- **Trades Sheet**: Extracted transaction data
- **Metadata Sheet**: Processing information and source details

## Requirements

- Python 3.7+
- LM Studio with Gemma 3 model
- PDF contract notes from supported brokers
