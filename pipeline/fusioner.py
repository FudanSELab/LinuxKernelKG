# coding: utf-8
import json
import sys
import logging
import os
from datetime import datetime
from prompts.fusion import fusionPrompt
from utils.deepseek import deepseek
from utils.utils import *
from utils.utils import strip_json

def setup_logger():
    # 创建logger
    logger = logging.getLogger('fusioner')
    logger.setLevel(logging.DEBUG)
    
    # 创建logs目录（如果不存在）
    logs_dir = "data/log"
    os.makedirs(logs_dir, exist_ok=True)
    
    # 创建文件处理器，将日志写入文件
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(logs_dir, f'fusion_{timestamp}.log')
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    
    # 创建控制台处理器
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    # 创建格式器
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    # 添加处理器到logger
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger

def load_features(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_unique_entities(features):
    unique_entities = set()
    for feature in features:
        if 'entities' in feature:
            unique_entities.update(feature['entities'])
    return list(unique_entities)

def create_entity_mapping(fusion_groups):
    # 创建从别名到规范形式的映射
    entity_mapping = {}
    for group in fusion_groups:
        canonical = group['canonical']
        for alias in group['aliases']:
            entity_mapping[alias] = canonical
        # 确保规范形式也映射到自己
        entity_mapping[canonical] = canonical
    return entity_mapping

def update_feature(feature, entity_mapping):
    # 更新实体列表
    if 'entities' in feature:
        updated_entities = []
        for entity in feature['entities']:
            # 如果实体在映射中，使用其规范形式
            if entity in entity_mapping:
                canonical = entity_mapping[entity]
                if canonical not in updated_entities:
                    updated_entities.append(canonical)
            # 如果实体不在映射中，保持原样
            else:
                updated_entities.append(entity)
        feature['entities'] = updated_entities

    # 更新三元组
    if 'triples' in feature:
        updated_triples = []
        for triple in feature['triples']:
            if len(triple) >= 3:
                # 更新主语和宾语（如果它们在映射中）
                subject = entity_mapping.get(triple[0], triple[0])
                relation = triple[1]
                object_ = entity_mapping.get(triple[2], triple[2])
                updated_triple = [subject, relation, object_]
                # 只添加不重复的三元组
                if updated_triple not in updated_triples:
                    updated_triples.append(updated_triple)
        feature['triples'] = updated_triples

    return feature

def process_entity_batch(entities_batch, llm, logger):
    # 处理一批实体
    logger.info(f"Processing batch of {len(entities_batch)} entities")
    logger.debug(f"Batch entities: {entities_batch}")
    
    prompt = fusionPrompt(entities=entities_batch).format()
    response = llm.get_response(prompt)
    
    try:
        response = strip_json(response)
        logger.debug(f"Cleaned response: {response}")
        fusion_groups = json.loads(response)
        logger.info(f"Successfully processed batch, found {len(fusion_groups)} fusion groups")
        logger.debug(f"Fusion groups: {json.dumps(fusion_groups, ensure_ascii=False, indent=2)}")
        return fusion_groups
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse response: {str(e)}")
        logger.error(f"Raw response: {response}")
        return []

def merge_fusion_groups(all_groups, logger):
    logger.info(f"Merging {len(all_groups)} batches of fusion groups")
    
    # 合并所有批次的融合组
    merged_mapping = {}
    
    # 第一遍：收集所有的规范形式和别名
    for groups in all_groups:
        for group in groups:
            canonical = group['canonical']
            aliases = set(group['aliases'])
            aliases.add(canonical)
            
            # 检查是否与现有组有重叠
            found_overlap = False
            for existing_canonical, existing_aliases in merged_mapping.items():
                if aliases & existing_aliases:  # 如果有交集
                    # 合并到现有组
                    merged_mapping[existing_canonical].update(aliases)
                    logger.debug(f"Merged group '{canonical}' into existing group '{existing_canonical}'")
                    found_overlap = True
                    break
            
            if not found_overlap:
                # 创建新组
                merged_mapping[canonical] = aliases
                logger.debug(f"Created new group with canonical form '{canonical}'")
    
    # 第二遍：整理结果格式
    final_groups = []
    processed_entities = set()
    
    for canonical, aliases in merged_mapping.items():
        if canonical not in processed_entities:
            aliases = list(aliases - {canonical})  # 从别名中移除规范形式
            final_groups.append({
                "canonical": canonical,
                "aliases": sorted(aliases)  # 排序以保持稳定输出
            })
            processed_entities.update(aliases)
            processed_entities.add(canonical)
    
    logger.info(f"Finished merging, got {len(final_groups)} final fusion groups")
    return final_groups

def main():
    # 设置日志
    logger = setup_logger()
    logger.info("Starting entity fusion process")
    
    # 初始化 LLM
    llm = deepseek()
    logger.info("Initialized LLM")

    # 加载特性数据
    features_file = 'data/features/features_output.json'
    features = load_features(features_file)
    logger.info(f"Loaded features from file, got {len(features)} features")
    
    # 获取唯一实体
    unique_entities = get_unique_entities(features)
    logger.info(f"Found {len(unique_entities)} unique entities")
    
    # 分批处理实体，每批50个
    batch_size = 50
    all_fusion_groups = []
    total_batches = (len(unique_entities) + batch_size - 1) // batch_size
    
    for i in range(0, len(unique_entities), batch_size):
        batch = unique_entities[i:i + batch_size]
        logger.info(f"Processing batch {i//batch_size + 1}/{total_batches}")
        fusion_groups = process_entity_batch(batch, llm, logger)
        all_fusion_groups.append(fusion_groups)
    
    # 合并所有批次的结果
    merged_groups = merge_fusion_groups(all_fusion_groups, logger)
    
    # 创建实体映射
    entity_mapping = create_entity_mapping(merged_groups)
    logger.info(f"Created entity mapping with {len(entity_mapping)} entries")
    
    # 更新所有特性
    updated_features = [update_feature(feature, entity_mapping) for feature in features]
    logger.info("Updated all features with new entity mappings")
    
    # 保存更新后的数据
    output_file = 'data/features/features_output_fused.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(updated_features, f, ensure_ascii=False, indent=4)
    logger.info("Saved updated features to features_output_fused.json")
    
    # 保存融合组信息，用于分析
    groups_file = 'data/features/fusion_groups.json'
    with open(groups_file, 'w', encoding='utf-8') as f:
        json.dump(merged_groups, f, ensure_ascii=False, indent=4)
    logger.info("Saved fusion groups to fusion_groups.json")
    
    logger.info("Entity fusion process completed successfully")

if __name__ == '__main__':
    main()
