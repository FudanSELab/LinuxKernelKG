#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Memory Management Filter Script

This script filters records from a JSONL file to only include those with h1='Memory management'.
The filtered records are saved to a new JSONL file.
"""

import os
import json
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from tqdm import tqdm

# Import project modules
from utils.logger import setup_logger

logger = setup_logger('memory_management_filter', file_output=True)

def load_records_from_file(file_path: str) -> List[Dict[str, Any]]:
    """
    Load records from a JSONL file.
    
    Args:
        file_path: Path to the JSONL file
        
    Returns:
        List of dictionaries containing records
    """
    records = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    records.append(record)
        logger.info(f"Loaded {len(records)} records from {file_path}")
        return records
    except Exception as e:
        logger.error(f"Error loading records from {file_path}: {e}")
        return []

def filter_memory_management_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter records to only include those with h1='Memory management'.
    
    Args:
        records: List of dictionaries containing records
        
    Returns:
        List of filtered records
    """
    filtered_records = []
    for record in records:
        feature = record.get('feature', {})
        if feature.get('h1') == 'Memory management':
            filtered_records.append(record)
    
    logger.info(f"Filtered {len(filtered_records)} memory management records from {len(records)} total records")
    return filtered_records

def save_records_to_file(records: List[Dict[str, Any]], output_file: str):
    """
    Save records to a JSONL file.
    
    Args:
        records: List of dictionaries containing records
        output_file: Path to save the records
    """
    try:
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        
        logger.info(f"Saved {len(records)} records to {output_file}")
    except Exception as e:
        logger.error(f"Error saving records to {output_file}: {e}")

def main():
    """Main function to run the memory management filtering process."""
    parser = argparse.ArgumentParser(description='Memory Management Filter Script')
    parser.add_argument('--input', '-i', 
                        default='output/entity_extraction/extraction_results_20250509_0958.jsonl',
                        help='Input file with records')
    parser.add_argument('--output', '-o', 
                        default='output/entity_extraction/extraction_results__mm_20250509_0958.jsonl',
                        help='Output file for filtered records')
    
    args = parser.parse_args()
    
    # Load records from input file
    records = load_records_from_file(args.input)
    
    # Filter memory management records
    filtered_records = filter_memory_management_records(records)
    
    # Save filtered records to output file
    save_records_to_file(filtered_records, args.output)
    
    logger.info("Memory management filtering completed.")

if __name__ == "__main__":
    main() 