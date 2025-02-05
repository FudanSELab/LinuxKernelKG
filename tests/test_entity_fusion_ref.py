import sys
from pathlib import Path
import asyncio
import json
import pandas as pd
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from config.pipeline_config import PipelineConfig
from pipeline.entity_processor import EntityProcessor
from utils.logger import setup_logger
from utils.db import DB

class EntityFusionBenchmarkLoader:
    """
    导入实体融合测试数据
    """
    def __init__(self, data_file, logger):
        self.data_file = data_file
        self.logger = logger
        
        # 读取数据时进行预处理
        self.data = self._load_and_clean_data()
        self.db = DB(PipelineConfig())
        
        # 输出数据统计信息
        self._log_data_statistics()
    
    def _load_and_clean_data(self):
        """
        加载并清理数据：
        1. 读取Excel文件
        2. 将'fused_to'列中的'/'替换为NaN
        3. 清理可能的空白字符
        """
        data = pd.read_excel(self.data_file)
        
        # # 清理 fused_to 列
        # data['fused_to'] = data['fused_to'].replace({
        #     '/': pd.NA,  # 将'/'替换为NA
        #     '': pd.NA,   # 将空字符串替换为NA
        # }).str.strip()   # 清理前后空白字符
        
        return data
    
    def _log_data_statistics(self):
        """输出数据统计信息"""
        total_rows = len(self.data)
        fusion_rows = self.data['fused_to'].notna().sum()
        
        self.logger.info(f"数据集统计信息:")
        self.logger.info(f"总行数: {total_rows}")
        self.logger.info(f"需要融合的实体数: {fusion_rows}")
        self.logger.info(f"不需要融合的实体数: {total_rows - fusion_rows}")
        
        # 输出 fused_to 列的值分布
        value_counts = self.data['fused_to'].value_counts(dropna=False)
        self.logger.info("\nfused_to 列的值分布:")
        self.logger.info(value_counts)

    def calculate_metric(self, results):
        """
        计算实体融合的指标：
        1. 融合准确率：正确融合的实体对数量 / 所有被融合的实体对数量
        2. 融合召回率：正确融合的实体对数量 / 所有应该被融合的实体对数量
        """
        # 1. 从数据集获取所有应该融合的实体对
        ground_truth_pairs = set()
        for _, row in self.data.iterrows():
            if pd.notna(row['fused_to']):
                # 确保实体对的顺序一致性（变体 -> 原始形式）
                ground_truth_pairs.add((row['original_mention'].strip(), row['fused_to'].strip()))
        
        # 2. 从结果中获取所有实际融合的实体对
        predicted_pairs = set()
        for group in results:
            # 确保group是字典类型且包含必要的字段
            if not isinstance(group, dict):
                continue
                
            # 获取原始实体（canonical form）
            original = group.get('original')
            if not original:
                continue
                
            # 获取变体列表
            variations = group.get('variations', [])
            if not variations:
                continue
                
            # 添加所有变体到原始实体的映射
            for variation in variations:
                # 确保实体对的顺序一致性（变体 -> 原始形式）
                predicted_pairs.add((variation.strip(), original.strip()))
        
        # 3. 计算正确的融合对数量
        correct_pairs = ground_truth_pairs & predicted_pairs
        
        # 4. 计算指标
        total_predicted = len(predicted_pairs) if predicted_pairs else 0
        total_ground_truth = len(ground_truth_pairs) if ground_truth_pairs else 0
        total_correct = len(correct_pairs)
        
        precision = total_correct / total_predicted if total_predicted > 0 else 0
        recall = total_correct / total_ground_truth if total_ground_truth > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        # 5. 记录详细结果
        self.logger.info("\nFusion Evaluation Results:")
        self.logger.info(f"Ground Truth Pairs: {total_ground_truth}")
        self.logger.info(f"Predicted Pairs: {total_predicted}")
        self.logger.info(f"Correct Pairs: {total_correct}")
        self.logger.info(f"Precision: {precision:.4f}")
        self.logger.info(f"Recall: {recall:.4f}")
        self.logger.info(f"F1 Score: {f1:.4f}")
        
        # 6. 记录错误分析
        false_positives = predicted_pairs - ground_truth_pairs
        false_negatives = ground_truth_pairs - predicted_pairs
        
        if false_positives:
            self.logger.info("\nFalse Positive Examples (up to 5):")
            for pair in list(false_positives)[:5]:
                self.logger.info(f"  {pair[0]} -> {pair[1]}")
                
        if false_negatives:
            self.logger.info("\nFalse Negative Examples (up to 5):")
            for pair in list(false_negatives)[:5]:
                self.logger.info(f"  {pair[0]} -> {pair[1]}")

        return {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'statistics': {
                'ground_truth_pairs': total_ground_truth,
                'predicted_pairs': total_predicted,
                'correct_pairs': total_correct,
                'false_positives': len(false_positives),
                'false_negatives': len(false_negatives)
            }
        }

async def test_entity_fusion(input_file, eval_only=False, result_file=None):
    logger = setup_logger('test_entity_fusion', file_output=True)
    config = PipelineConfig()
    
    # 从数据文件中加载测试数据
    loader = EntityFusionBenchmarkLoader(input_file, logger)
    
    if eval_only and result_file:
        logger.info(f"Loading existing results from {result_file}")
        # try:
        with open(result_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            fusion_results = data['results']
            # feature_ids = data['featurse_ids']
            # commit_ids_list = data['commit_ids_list']
        logger.info("Calculating metrics for existing results...")
        loader.calculate_metric(fusion_results)
        return
        # except Exception as e:
        #     logger.error(f"Failed to load results file: {str(e)}")
        #     return
    
    BATCH_SIZE = 10
    
    # 添加时间戳到文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    output_file = f'output/test/entity_fusion_test_results_{timestamp}.json'
    Path('output/test').mkdir(parents=True, exist_ok=True)

    logger.info("Starting entity fusion test")

    # 初始化处理器
    processor = EntityProcessor(config)
    
    # 获取所有唯一实体
    unique_entities = loader.data['original_mention'].unique().tolist()
    feature_ids = loader.data['feature_id'].tolist()
    commit_ids_list = loader.data['commit_ids'].tolist()
    commit_ids_list = [
        json.loads(commit_ids_str.replace("'", '"'))
        for commit_ids_str in commit_ids_list
    ]
    test_size = 100
    # [测试] 只取前5个元素看看流程是否有问题
    # test_size = 5
    # unique_entities = unique_entities[:test_size]
    # feature_ids = feature_ids[:test_size]
    # commit_ids_list = commit_ids_list[:test_size]
    
    logger.info(f"Processing test entities (first {test_size}): {unique_entities}")
    
    try:
        # 一次性处理所有实体融合
        all_results = await processor.process_fusion(unique_entities, feature_ids, commit_ids_list)
        
        # 保存结果
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'input_entities': unique_entities,
                'results': all_results,
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }, f, ensure_ascii=False, indent=4)
                
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        raise

    # 计算和输出指标
    metrics = loader.calculate_metric(all_results)

if __name__ == "__main__":
    # 直接设置参数
    eval_only = False
    result_file = 'output/test/entity_fusion_test_results_20250124_0138.json'
    input_file = 'data/entity_link_fusion_benchmark_0124.xlsx'  # 融合测试数据文件

    asyncio.run(test_entity_fusion(input_file=input_file, eval_only=eval_only, result_file=result_file)) 