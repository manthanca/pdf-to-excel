"""
Broker configuration rules for contract note parsing.
Contains anchor keywords, headers, and column mapping rules for different brokers.
"""

BROKER_CONFIG = {
    'ANGELONE': {
        'anchor_keywords': [
            'Equity Segment - Trade Summary'
        ],
        'headers': [
            'ISIN', 'Security Name / Symbol', 'BUY Quantity', 'BUY WAP (Across Exchanges)', 'Total BUY Value After Brokerage', 'SELL Quantity', 'SELL WAP (Across Exchanges)', 'Total SELL Value After Brokerage', 'Net Quantity', 'Net Obligation For ISIN'
        ],
        'mapping_rule': {
            'buy_columns': [2, 3, 4],  # BUY Quantity, BUY WAP, Total BUY Value
            'sell_columns': [5, 6, 7]  # SELL Quantity, SELL WAP, Total SELL Value
        }
    },
    'AXIS': {
        'anchor_keywords': [
            'SETTLEMENT DATE'
        ],
        'headers': [
            'ISIN', 'Security Name / Symbol', 'BUY Quantity', 'BUY WAP (Across Exchanges)', 'Total BUY Value After Brokerage', 'SELL Quantity', 'SELL WAP (Across Exchanges)', 'Total SELL Value After Brokerage', 'Net Quantity', 'Net Obligation For ISIN'
        ],
        'mapping_rule': {
            'buy_columns': [2, 3, 4],  # BUY Quantity, BUY WAP, Total BUY Value
            'sell_columns': [5, 6, 7]  # SELL Quantity, SELL WAP, Total SELL Value
        }
    },
    'KOTAK': {
        'anchor_keywords': [
            'Equity Segment Summary'
        ],
        'headers': [
            'ISIN', 'Security Name / Symbol', 'BUY Quantity', 'BUY WAP (Across Exchanges)', 'Total BUY Value After Brokerage', 'SELL Quantity', 'SELL WAP (Across Exchanges)', 'Total SELL Value After Brokerage', 'Net Quantity', 'Net Obligation For ISIN'
        ],
        'mapping_rule': {
            'buy_columns': [2, 3, 4],  # BUY Quantity, BUY WAP, Total BUY Value
            'sell_columns': [5, 6, 7]  # SELL Quantity, SELL WAP, Total SELL Value
        }
    }
}

def detect_broker(text):
    """
    Detect broker based on anchor keywords in the text.
    
    Args:
        text (str): Text content from PDF
        
    Returns:
        str: Broker name (AXIS, ANGEL, KOTAK) or 'UNKNOWN'
    """
    text_upper = text.upper()
    
    for broker, config in BROKER_CONFIG.items():
        for keyword in config['anchor_keywords']:
            if keyword.upper() in text_upper:
                return broker
    
    return 'UNKNOWN'

def get_broker_config(broker_name):
    """
    Get broker configuration by name.
    
    Args:
        broker_name (str): Broker name
        
    Returns:
        dict: Broker configuration or None
    """
    return BROKER_CONFIG.get(broker_name.upper())
