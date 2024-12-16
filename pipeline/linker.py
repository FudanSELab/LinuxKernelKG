# coding: utf-8
import json
import logging
import os
from datetime import datetime
from prompts.link import linkPrompt
from utils.deepseek import deepseek
from utils.utils import strip_json

def setup_logger():
    # 创建logger
    logger = logging.getLogger('linker')
    logger.setLevel(logging.DEBUG)
    
    # 创建logs目录（如果不存在）
    logs_dir = "data/log"
    os.makedirs(logs_dir, exist_ok=True)
    
    # 创建文件处理器，将日志写入文件
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(logs_dir, f'link_{timestamp}.log')
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

def process_entity_batch(entities_batch, entities_expert, llm, logger):
    # 处理一批实体
    logger.info(f"Processing batch of {len(entities_batch)} entities")
    logger.debug(f"Batch entities: {entities_batch}")
    
    prompt = linkPrompt(entities=entities_batch, entities_expert=entities_expert).format()
    response = llm.get_response(prompt)
    
    try:
        response = strip_json(response)
        logger.debug(f"Cleaned response: {response}")
        link_pairs = json.loads(response)
        
        # 转换为标准格式
        link_results = []
        for entity, expert_entity in link_pairs:
            link_results.append({
                "entity": entity,
                "linked": expert_entity != "null",
                "expert_entity": expert_entity if expert_entity != "null" else None
            })
            
        logger.info(f"Successfully processed batch, found {len(link_results)} links")
        logger.debug(f"Link results: {json.dumps(link_results, ensure_ascii=False, indent=2)}")
        return link_results
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse response: {str(e)}")
        logger.error(f"Raw response: {response}")
        return []

def main():
    # 专家实体列表
    entities_expert = ["Zone Management", "Memory Control Policies", "Copy-On-Write", "Virtual Memory Allocation", "Memory Protection", "Page Fault", "Memory Initialization", "Shared Memory Management", "Failure Detecting & Handling", "Performance Monitoring", "Debug & Test", "Memory Mapping", "Memory Re-mapping", "Reverse Mapping", "Page Isolation", "Page Migration", "Hotplug", "Kernel Same-page Merging", "Page Ownership Management", "Memory Pool Management", "Huge Pages Management", "Page Writeback", "Page I/O", "Workingset Management", "Page Allocation", "Contiguous Memory Allocation", "Memory Slab Allocation", "DMA", "highmem", "Memory Compaction", "Memory Swapping", "Direct Mapping Management", "Concurrency Control (Locks)"]
    
    # 设置日志
    logger = setup_logger()
    logger.info("Starting entity linking process")
    
    # 初始化 LLM
    llm = deepseek()
    logger.info("Initialized LLM")

    # 加载特性数据
    features_file = 'data/features/features_output_fused.json'
    features = load_features(features_file)
    logger.info(f"Loaded features from file, got {len(features)} features")
    
    # 获取唯一实体
    unique_entities = get_unique_entities(features)
    logger.info(f"Found {len(unique_entities)} unique entities")
    
    # 分批处理实体，每批50个
    batch_size = 50
    all_link_results = []
    total_batches = (len(unique_entities) + batch_size - 1) // batch_size
    
    for i in range(0, len(unique_entities), batch_size):
        batch = unique_entities[i:i + batch_size]
        logger.info(f"Processing batch {i//batch_size + 1}/{total_batches}")
        link_results = process_entity_batch(batch, entities_expert, llm, logger)
        all_link_results.extend(link_results)
    
    # 统计链接信息
    linked_count = sum(1 for result in all_link_results if result['linked'])
    total_entities = len(unique_entities)
    
    logger.info(f"Entity linking completed:")
    logger.info(f"Total unique entities: {total_entities}")
    logger.info(f"Successfully linked entities: {linked_count}")
    logger.info(f"Linking rate: {linked_count/total_entities*100:.2f}%")
    
    # 保存链接结果，用于分析
    link_file = 'data/features/entity_links.json'
    with open(link_file, 'w', encoding='utf-8') as f:
        json.dump(all_link_results, f, ensure_ascii=False, indent=4)
    logger.info("Saved link results to entity_links.json")
    
    logger.info("Entity linking process completed successfully")

if __name__ == '__main__':
    main()