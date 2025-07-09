#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Entity Linking Script with MySQL Database Storage

This script processes extracted entities from a source JSONL file and performs 
entity linking using the EntityLinker. The linked entities are saved to a MySQL database
using the entities_extraction and entity_aliases tables. The script supports resuming
from where it left off by checking the last processed feature_id in the database.
"""

import os
import json
import asyncio
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from tqdm import tqdm

# Import project modules
from pipeline.entity_linker_ban import EntityLinker
from models.entity import Entity
from config.pipeline_config import PipelineConfig
from utils.logger import setup_logger
from database.mysql_manager import MySQLManager

logger = setup_logger('entity_linking_db', file_output=True)

async def load_entities_from_file(file_path: str) -> List[Dict[str, Any]]:
    """
    Load entities from a JSONL file.
    
    Args:
        file_path: Path to the JSONL file with extracted entities
        
    Returns:
        List of dictionaries containing feature and entity information
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
        logger.error(f"Error loading entities from {file_path}: {e}")
        return []

def create_entity_objects(records: List[Dict[str, Any]], start_feature_id: int = None, max_feature_id: int = None) -> List[Entity]:
    """
    Create Entity objects from the loaded records.
    
    Args:
        records: List of dictionaries containing feature and entity information
        start_feature_id: Optional minimum feature_id to process (for resuming)
        max_feature_id: Optional maximum feature_id to process. Records with feature_id > max_feature_id will be skipped
        
    Returns:
        List of Entity objects
    """
    entities = []
    skipped_count = 0
    
    for record in records:
        feature_id = record.get('feature_id')
        feature = record.get('feature', {})
        
        # Skip records with feature_id less than start_feature_id if specified (for resuming)
        if start_feature_id is not None and feature_id <= start_feature_id:
            skipped_count += 1
            continue
            
        # Skip records with feature_id greater than max_feature_id if specified
        if max_feature_id is not None and feature_id > max_feature_id:
            skipped_count += 1
            continue
            
        feature = record.get('feature', {})
        extraction_result = record.get('extraction_result', {})
        
        if not feature_id or not extraction_result:
            continue
            
        filtered_entities = extraction_result.get('filtered_entities', [])
        feature_description = feature.get('feature_description', '')
        
        # Create Entity objects for each filtered entity
        for entity_name in filtered_entities:
            entity = Entity(
                name=entity_name,
                feature_id=feature_id,
                description=""  # Initially empty, will be filled by entity linker
            )
            # Set feature-related properties
            entity.commit_ids = extraction_result.get('commit_ids', [])
            # Add context as a separate attribute for the entity linker
            entity.set_context_by_feature_description(feature_description)
            
            entities.append(entity)
    
    logger.info(f"Created {len(entities)} Entity objects")
    if start_feature_id is not None:
        logger.info(f"Skipped {skipped_count} records with feature_id <= {start_feature_id} (for resuming)")
    if max_feature_id is not None:
        logger.info(f"Skipped records with feature_id > {max_feature_id}")
    return entities

async def get_resume_feature_id(db_manager: MySQLManager) -> int:
    """
    Get the feature_id to resume from by checking the database.
    
    Args:
        db_manager: MySQLManager instance
        
    Returns:
        int: The last processed feature_id, or 0 if no records exist
    """
    try:
        last_feature_id = db_manager.get_last_processed_feature_id()
        if last_feature_id is not None:
            logger.info(f"Found last processed feature_id in database: {last_feature_id}")
            return last_feature_id
        else:
            logger.info("No existing records found in database, starting from beginning")
            return 0
    except Exception as e:
        logger.error(f"Error getting resume feature_id: {e}")
        return 0

async def process_entities_batch(
    entity_linker: EntityLinker, 
    entities: List[Entity], 
    db_manager: MySQLManager,
    batch_size: int = 10
) -> int:
    """
    Process entities in batches for linking and save each batch to database.
    
    Args:
        entity_linker: EntityLinker instance
        entities: List of Entity objects to process
        db_manager: MySQLManager instance for database operations
        batch_size: Number of entities to process in each batch
        
    Returns:
        int: Number of successfully processed entities
    """
    total_processed = 0
    total_batches = (len(entities) + batch_size - 1) // batch_size
    
    for i in tqdm(range(0, len(entities), batch_size), 
                  total=total_batches, 
                  desc="Linking entities"):
        batch = entities[i:i+batch_size]
        try:
            # Process entity linking for this batch
            batch_tasks = [entity_linker.link_entity(entity) for entity in batch]
            batch_results = await asyncio.gather(*batch_tasks)
            
            # Flatten results (link_entity returns a list)
            batch_linked_entities = []
            for result_list in batch_results:
                if result_list:
                    batch_linked_entities.extend(result_list)
            
            # Save batch to database
            if batch_linked_entities:
                db_results = db_manager.insert_entities_batch(batch_linked_entities)
                
                # Count successful insertions
                successful_inserts = sum(1 for _, eid in db_results if eid is not None)
                total_processed += successful_inserts
                
                # Log batch completion
                current_batch = (i // batch_size) + 1
                logger.info(f"Completed batch {current_batch}/{total_batches}: "
                           f"Linked {len(batch_linked_entities)} entities, "
                           f"Successfully saved {successful_inserts} to database. "
                           f"Total processed: {total_processed}")
            else:
                logger.info(f"Processed batch {(i)//batch_size + 1}/{total_batches} with no linked entities")
                    
        except Exception as e:
            logger.error(f"Error processing batch {(i)//batch_size + 1}/{total_batches}: {e}")
    
    logger.info(f"Entity linking completed. Total {total_processed} entities processed and saved to database.")
    return total_processed

async def main():
    """Main function to run the entity linking process with database storage."""
    parser = argparse.ArgumentParser(description='Entity Linking Script with MySQL Database Storage')
    parser.add_argument('--input', '-i', 
                        default='output/entity_extraction/extraction_results_20250509_0958.jsonl',
                        help='Input file with extracted entities')
    parser.add_argument('--batch-size', '-b', type=int, default=10,
                        help='Batch size for processing entities')
    parser.add_argument('--max-feature-id', type=int, default=32568, # 33388
                        help='Maximum feature_id to process (for testing/limiting scope)')
    parser.add_argument('--resume', action='store_true', default=True,
                        help='Resume from last processed feature_id in database')
    parser.add_argument('--test-db', action='store_true',
                        help='Test database connection and exit')
    
    args = parser.parse_args()
    
    # Initialize database manager
    db_manager = MySQLManager(PipelineConfig)
    
    # Test database connection if requested
    if args.test_db:
        if db_manager.test_connection():
            logger.info("Database connection test passed!")
            print("✅ Database connection successful")
        else:
            logger.error("Database connection test failed!")
            print("❌ Database connection failed")
        return
    
    # Test database connection before starting
    if not db_manager.test_connection():
        logger.error("Failed to connect to database. Exiting.")
        return
    
    # Initialize entity linker
    entity_linker = EntityLinker(PipelineConfig)
    
    # Load records from input file
    records = await load_entities_from_file(args.input)
    if not records:
        logger.error("No records loaded from input file. Exiting.")
        return
    
    # Determine starting point for resuming
    start_feature_id = 0
    if args.resume:
        start_feature_id = await get_resume_feature_id(db_manager)
        # start_feature_id = 33370
        logger.info(f"Resuming from feature_id > {start_feature_id}")
    
    # Create entity objects
    entities = create_entity_objects(
        records, 
        start_feature_id=start_feature_id if args.resume else None,
        max_feature_id=args.max_feature_id
    )
    
    if not entities:
        logger.info("No entities to process (all may have been processed already).")
        return
    
    # Process entities in batches and save to database
    total_processed = await process_entities_batch(
        entity_linker, 
        entities, 
        db_manager,
        batch_size=args.batch_size
    )
    
    logger.info(f"Entity linking completed successfully. Total entities processed: {total_processed}")

if __name__ == "__main__":
    asyncio.run(main())