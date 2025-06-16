#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Entity Linking Script

This script processes extracted entities from a source JSONL file and performs 
entity linking using the EntityLinker. The linked entities are saved to a JSON file
as an array of entity objects. After each batch is processed, new entities are appended
to the existing JSON array, maintaining a single valid JSON structure while ensuring
data is incrementally saved throughout the process.
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
from pipeline.entity_linker import EntityLinker
from models.entity import Entity
from config.pipeline_config import PipelineConfig
from utils.logger import setup_logger

logger = setup_logger('entity_linking', file_output=True)

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
        # if feature.get('h1') != 'Memory management':
        #     continue
    
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
    if max_feature_id is not None:
        logger.info(f"Skipped {skipped_count} records with feature_id > {max_feature_id}")
    return entities

async def get_processed_count(input_file: str, output_file: str) -> int:
    """
    Get the starting position for processing by finding the last processed feature_id
    in the output file and matching it with the input file position.
    """
    if not os.path.exists(output_file):
        return 0
        
    try:
        # 读取JSON格式的输出文件
        with open(output_file, 'r', encoding='utf-8') as f:
            try:
                # 加载整个JSON数组
                entities = json.load(f)
                
                if not entities:  # 如果是空数组
                    logger.warning("No entities found in output file")
                    return 0
                    
                # 获取最后一个实体的feature_id
                last_feature_id = None
                for entity in entities:
                    if 'feature_id' in entity:
                        last_feature_id = max(last_feature_id or 0, entity['feature_id'])
                
                if last_feature_id is None:
                    logger.warning("No valid feature_id found in output file")
                    return 0
                    
                # 获取输入文件的第一个feature_id
                with open(input_file, 'r', encoding='utf-8') as input_f:
                    first_line = input_f.readline()
                    first_record = json.loads(first_line)
                    first_feature_id = first_record['feature_id']
                    
                # 直接计算位置（因为feature_id是连续的）
                position = last_feature_id - first_feature_id + 1
                
                logger.info(f"Last processed feature_id: {last_feature_id}, first feature_id: {first_feature_id}")
                logger.info(f"Resuming from position {position}")
                return position
                
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON file: {e}")
                return 0
            
    except Exception as e:
        logger.error(f"Unexpected error determining processing position: {e}", exc_info=True)
        return 0

async def process_entities_batch(
    entity_linker: EntityLinker, 
    entities: List[Entity], 
    batch_size: int = 10,
    input_file: str = None,
    output_file: str = None
) -> List[Entity]:
    """
    Process entities in batches for linking and save each batch immediately.
    
    Args:
        entity_linker: EntityLinker instance
        entities: List of Entity objects to process
        batch_size: Number of entities to process in each batch
        input_file: Path to the input JSONL file
        output_file: Path to save the linked entities
        
    Returns:
        List of processed Entity objects with links
    """
    linked_entities = []
    # Create output directory if it doesn't exist
    if output_file:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Get the starting position based on the last processed feature_id

    total_batches = (len(entities) + batch_size - 1) // batch_size
    
    for i in tqdm(range(0, len(entities), batch_size), 
                  total=total_batches, 
                  desc="Linking entities"):
        batch = entities[i:i+batch_size]
        try:
            batch_tasks = [entity_linker.link_entity(entity) for entity in batch]
            batch_results = await asyncio.gather(*batch_tasks)
            
            # Flatten results (link_entity returns a list)
            batch_linked_entities = []
            for result_list in batch_results:
                if result_list:
                    batch_linked_entities.extend(result_list)
            
            # 将本批次的实体添加到结果列表
            linked_entities.extend(batch_linked_entities)
            
            # 每批次处理完成后都写入文件，保存所有已处理的实体
            if output_file and batch_linked_entities:
                # 读取现有文件中的实体（如果文件存在）
                existing_entities = []
                if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                    try:
                        with open(output_file, 'r', encoding='utf-8') as f:
                            existing_entities = json.load(f)
                    except json.JSONDecodeError:
                        logger.error(f"Error reading existing JSON file: {output_file}, will create new file")
                
                # 将当前批次的实体转换为字典
                batch_entity_dicts = [entity.to_dict() for entity in batch_linked_entities]
                
                # 合并现有实体和新处理的实体
                all_entities = existing_entities + batch_entity_dicts
                
                # 写入合并后的完整实体列表
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(all_entities, f, ensure_ascii=False, indent=2)
                
                logger.info(f"Processed batch {(i)//batch_size + 1}/{total_batches} with {len(batch_linked_entities)} entities. Total {len(all_entities)} entities saved to {output_file}")
            else:
                logger.info(f"Processed batch {(i)//batch_size + 1}/{total_batches} with {len(batch_linked_entities)} entities")
                    
        except Exception as e:
            logger.error(f"Error processing batch {(i)//batch_size + 1}/{total_batches}: {e}")
    
    logger.info(f"Linked {len(linked_entities)} entities in total")
    return linked_entities

async def main():
    """Main function to run the entity linking process."""
    parser = argparse.ArgumentParser(description='Entity Linking Script')
    parser.add_argument('--input', '-i', 
                        # default='output/entity_extraction/extraction_results_20250321_1058.jsonl',
                        # default='output/entity_extraction/extraction_results_20250318_1626.jsonl',
                        # default='output/entity_extraction/extraction_results_test.jsonl',
                        default='output/entity_extraction/extraction_results_20250509_0958.jsonl',
                        help='Input file with extracted entities')
    parser.add_argument('--output', '-o', 
                        # default='output/entity_linking/linked_entities_20250409_1533.jsonl',
                        default='output/entity_linking/linked_entities_gpt_0521.json',
                        help='Output file for linked entities')
    parser.add_argument('--batch-size', '-b', type=int, default=10,
                        help='Batch size for processing entities')
    
    args = parser.parse_args()
    
    output_file = args.output
    
    entity_linker = EntityLinker(PipelineConfig)
    
    records = await load_entities_from_file(args.input)
    
    entities = create_entity_objects(records, 33388)
    
    # Process entities in batches and write to file
    linked_entities = await process_entities_batch(
        entity_linker, 
        entities, 
        batch_size=args.batch_size,
        input_file=args.input,
        output_file=output_file
    )
    
    # 每批次都已经写入文件，这里无需再次写入
    logger.info(f"Entity linking completed. Total {len(linked_entities)} entities processed.")

if __name__ == "__main__":
    asyncio.run(main())