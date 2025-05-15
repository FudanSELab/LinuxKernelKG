#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Entity Fusion Script

This script processes extracted entities from a source JSONL file and a list of 
linked entities from a JSON file, then performs entity fusion using the EntityFusion class. 
The fused entity groups are saved to a JSON file as an array of entity objects.
"""

import os
import json
import asyncio
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
# from tqdm import tqdm # tqdm might not be directly applicable to a single call to process_fusion

# Import project modules
# from pipeline.entity_linker import EntityLinker
from pipeline.entity_fusion import EntityFusion
from models.entity import Entity
from config.pipeline_config import PipelineConfig
from utils.logger import setup_logger

logger = setup_logger('entity_fusion_script', file_output=True)

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

def create_entity_objects(records: List[Dict[str, Any]], max_feature_id: int = None) -> List[Entity]:
    """
    Create Entity objects from the loaded records.
    
    Args:
        records: List of dictionaries containing feature and entity information
        max_feature_id: Optional maximum feature_id to process. Records with feature_id > max_feature_id will be skipped
        
    Returns:
        List of Entity objects
    """
    entities = []
    skipped_count = 0
    
    for record in records:
        feature_id = record.get('feature_id')
        feature = record.get('feature', {})
        if feature.get('h1') != 'Memory management': # Retaining this filter as per discussion
            continue
    
        # Skip records with feature_id greater than max_feature_id if specified
        if max_feature_id is not None and feature_id is not None and feature_id <= max_feature_id:
            skipped_count += 1
            continue
            
        # feature = record.get('feature', {}) # Already got feature above
        extraction_result = record.get('extraction_result', {})
        
        if not feature_id or not extraction_result:
            logger.warning(f"Skipping record due to missing feature_id or extraction_result: {record.get('id', 'Unknown ID')}")
            continue
            
        filtered_entities = extraction_result.get('filtered_entities', [])
        feature_description = feature.get('feature_description', '')
        
        # Create Entity objects for each filtered entity
        for entity_name in filtered_entities:
            entity = Entity(
                name=entity_name,
                feature_id=feature_id,
                description=""  # Initially empty, will be filled by entity linker/fusor
            )
            # Set feature-related properties
            entity.commit_ids = extraction_result.get('commit_ids', [])
            # Add context as a separate attribute
            entity.set_context_by_feature_description(feature_description)
            
            entities.append(entity)
    
    logger.info(f"Created {len(entities)} Entity objects from input records.")
    if max_feature_id is not None:
        logger.info(f"Skipped {skipped_count} records with feature_id > {max_feature_id}")
    return entities

async def load_linked_entities_from_json(file_path: str) -> List[Entity]:
    """
    Load linked Entity objects from a JSON file.
    The JSON file should contain an array of entity dictionaries.
    """
    entities = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            entity_dicts = json.load(f) # Expects a list of dicts
            if not isinstance(entity_dicts, list):
                logger.error(f"Error: Linked entities file {file_path} does not contain a JSON array.")
                return []
            for entity_dict in entity_dicts:
                # Ensure that the necessary fields for Entity.from_dict are present
                # or handle potential KeyError if from_dict is strict
                try:
                    entities.append(Entity.from_dict(entity_dict))
                except KeyError as ke:
                    logger.error(f"Skipping an entity from linked list due to missing key: {ke} in dict {entity_dict.get('id', 'Unknown ID')}")
                except Exception as ex_inner:
                    logger.error(f"Error converting dict to Entity for {entity_dict.get('id', 'Unknown ID')}: {ex_inner}")

        logger.info(f"Loaded {len(entities)} linked entities from {file_path}")
        return entities
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from linked entities file {file_path}: {e}")
        return []
    except FileNotFoundError:
        logger.error(f"Linked entities file not found: {file_path}")
        return []
    except Exception as e:
        logger.error(f"Error loading linked entities from {file_path}: {e}")
        return []

# Removed get_processed_count function
# Removed process_entities_batch function

async def main():
    """Main function to run the entity fusion process."""
    parser = argparse.ArgumentParser(description='Entity Fusion Script')
    parser.add_argument('--input', '-i', 
                        # default='output/entity_extraction/extraction_results_20250321_1058.jsonl',
                        # default='output/entity_extraction/extraction_results_20250318_1626.jsonl',
                        # default='output/entity_extraction/extraction_results_test.jsonl',
                        default='output/entity_extraction/extraction_results_20250509_0958.jsonl', # Example default
                        help='Input JSONL file with extracted entities')
    parser.add_argument('--linked-input', '-l', 
                        default='output/entity_linking/linked_entities_gpt_mm_0508.json', # Example, but made required
                        help='Input JSON file with linked entities (list of entity dicts)')
    parser.add_argument('--output', '-o', 
                        default='output/entity_fusion/fused_entities_result_mm_0513.json', # Example default
                        help='Output JSON file for fused entity groups')
    # parser.add_argument('--batch-size', '-b', type=int, default=10, # Removed
    #                     help='Batch size for processing entities')
    parser.add_argument('--max-feature-id', type=int, default=None, 
                        help='Maximum feature_id to process from the input file (for original entities)')
    
    args = parser.parse_args()
    
    output_file = args.output # Use directly from args
    
    # Instantiate EntityFusion
    entity_fusor = EntityFusion(PipelineConfig)
    
    # Load original entities
    records = await load_entities_from_file(args.input)
    if not records:
        logger.error(f"No records loaded from {args.input}. Aborting.")
        return
    
    max_feature_id = 0
    original_entities = create_entity_objects(records, max_feature_id)
    if not original_entities:
        logger.warning(f"No original entity objects created from {args.input}. Proceeding with empty list if linked entities exist.")

    # Load linked entities
    linked_entities_list = await load_linked_entities_from_json(args.linked_input)
    if not linked_entities_list:
        # Depending on requirements, one might choose to proceed if original_entities exist
        # or abort if linked_entities are crucial.
        logger.warning(f"No linked entities loaded from {args.linked_input}. Proceeding with fusion if original entities exist.")
        # If both are empty, fusion won't do much.
        if not original_entities:
            logger.error("Both original and linked entity lists are empty. Aborting fusion.")
            return
    # Filter linked entities based on max_feature_id if specified
    logger.info(f"Filtering linked entities with feature_id > {max_feature_id}")
    original_count = len(linked_entities_list)
    linked_entities_list = [entity for entity in linked_entities_list if entity.feature_id > max_feature_id]
    logger.info(f"Filtered out {original_count - len(linked_entities_list)} linked entities, {len(linked_entities_list)} remaining")

    # Perform Fusion
    logger.info(f"Starting entity fusion for {len(original_entities)} original entities and {len(linked_entities_list)} linked entities.")
    fused_groups = await entity_fusor.process_fusion(
        entities=original_entities, 
        linked_entities=linked_entities_list
    )
    
    # Save Fused Results
    if fused_groups:
        fused_groups_dicts = [entity.to_dict() for entity in fused_groups]
        
        output_dir = os.path.dirname(output_file) # Use output_file directly
        if output_dir: # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)
            
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(fused_groups_dicts, f, ensure_ascii=False, indent=2)
        logger.info(f"Entity fusion completed. {len(fused_groups_dicts)} fused entity groups saved to {output_file}")
    else:
        logger.info("Entity fusion completed. No fused entity groups were produced or an error occurred.")
        # Ensure output file is at least an empty array if no groups are produced and file needs to be created
        output_dir = os.path.dirname(output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        logger.info(f"Empty list saved to {output_file} as no fused groups were produced.")


if __name__ == "__main__":
    asyncio.run(main())
