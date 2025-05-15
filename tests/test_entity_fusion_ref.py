import sys
from pathlib import Path
import asyncio
import json
import pandas as pd
from datetime import datetime
import argparse

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
        2. 对空的feature_id进行向下填充处理
        3. 筛选出mention字段不为空且wikipedia_link字段为空的记录
        4. 清理可能的空白字符
        """
        try:
            data = pd.read_excel(self.data_file)
            self.logger.info(f"成功读取数据文件: {self.data_file}")
            self.logger.info(f"原始数据行数: {len(data)}")
            
            # 检查必要字段是否存在
            required_fields = ['mention', 'wikipedia_link']
            missing_fields = [field for field in required_fields if field not in data.columns]
            if missing_fields:
                error_msg = f"数据文件缺少必要字段: {', '.join(missing_fields)}"
                self.logger.error(error_msg)
                raise ValueError(error_msg)
            
            # 对空的feature_id进行向下填充处理
            if 'feature_id' in data.columns:
                null_feature_ids_before = data['feature_id'].isna().sum()
                data['feature_id'] = data['feature_id'].fillna(method='ffill')
                null_feature_ids_after = data['feature_id'].isna().sum()
                self.logger.info(f"feature_id填充处理: {null_feature_ids_before} 个空值 → {null_feature_ids_after} 个空值")
            else:
                self.logger.warning("数据文件中没有feature_id字段，将使用默认值None")
                data['feature_id'] = None
            
            # 筛选出mention字段不为空且wikipedia_link字段为空的记录
            filtered_data = data[data['mention'].notna() & data['wikipedia_link'].isna()]
            self.logger.info(f"筛选后数据行数: {len(filtered_data)}")
            
            if len(filtered_data) == 0:
                self.logger.warning("筛选后没有符合条件的记录，请检查数据是否正确")
            
            # 清理空白字符
            filtered_data['mention'] = filtered_data['mention'].str.strip()
            
            return filtered_data
            
        except Exception as e:
            self.logger.error(f"读取或处理数据文件时出错: {str(e)}")
            raise
    
    def _log_data_statistics(self):
        """输出数据统计信息"""
        total_rows = len(self.data)
        
        self.logger.info(f"数据集统计信息:")
        self.logger.info(f"总行数: {total_rows}")
        self.logger.info(f"需要处理的实体数: {total_rows}")
        
        # 输出mention列的前几个值做示例
        sample_mentions = self.data['mention'].head(5).tolist()
        self.logger.info("\nmention列的样例值:")
        for sample in sample_mentions:
            self.logger.info(f"  {sample}")

    def calculate_metric(self, results):
        """
        计算实体融合的指标：
        1. 融合准确率：正确融合的实体对数量 / 所有被融合的实体对数量
        2. 融合召回率：正确融合的实体对数量 / 所有应该被融合的实体对数量
        
        匹配规则：
        - reference_type为'documentation'时，使用reference(doc)进行匹配
        - reference_type为'code'时，使用reference(code)进行匹配
        """
        # 1. 从数据集获取所有实体的引用信息
        ground_truth_refs = {}
        for _, row in self.data.iterrows():
            mention = row['mention'].strip()
            code_ref = row.get('reference(code)', '').strip() if pd.notna(row.get('reference(code)')) else None
            doc_ref = row.get('reference(doc)', '').strip() if pd.notna(row.get('reference(doc)')) else None
            
            if mention not in ground_truth_refs:
                ground_truth_refs[mention] = {'code': code_ref, 'doc': doc_ref}
        
        # 2. 从结果中获取所有实际融合的实体对及其引用类型
        predicted_pairs = []
        for group in results:
            # 确保group是字典类型且包含必要的字段
            if not isinstance(group, dict):
                continue
                
            # 获取原始实体（canonical form）和引用类型
            original = group.get('original')
            reference_type = group.get('reference_type')
            if not original or not reference_type:
                continue
                
            # 获取变体列表
            variations = group.get('variations', [])
            if not variations:
                continue
                
            # 添加所有变体到原始实体的映射，包含引用类型信息
            for variation in variations:
                predicted_pairs.append({
                    'variation': variation.strip(),
                    'original': original.strip(),
                    'reference_type': reference_type
                })
        
        # 3. 计算正确的融合对数量
        correct_pairs = 0
        total_predicted = len(predicted_pairs)
        total_ground_truth = sum(1 for refs in ground_truth_refs.values() if refs['code'] or refs['doc'])
        
        for pair in predicted_pairs:
            variation = pair['variation']
            original = pair['original']
            ref_type = pair['reference_type']
            
            # 获取变体实体的真实引用
            variation_refs = ground_truth_refs.get(variation, {'code': None, 'doc': None})
            original_refs = ground_truth_refs.get(original, {'code': None, 'doc': None})
            
            # 根据引用类型判断是否匹配
            if ref_type == 'documentation':
                # 检查doc引用是否存在且匹配
                if variation_refs['doc'] and original_refs['doc'] and variation_refs['doc'] == original_refs['doc']:
                    correct_pairs += 1
            elif ref_type == 'code':
                # 检查code引用是否存在且匹配
                if variation_refs['code'] and original_refs['code'] and variation_refs['code'] == original_refs['code']:
                    correct_pairs += 1
        
        # 4. 计算指标
        precision = correct_pairs / total_predicted if total_predicted > 0 else 0
        recall = correct_pairs / total_ground_truth if total_ground_truth > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        # 5. 记录详细结果
        self.logger.info("\nFusion Evaluation Results:")
        self.logger.info(f"Total Ground Truth Entities with References: {total_ground_truth}")
        self.logger.info(f"Total Predicted Pairs: {total_predicted}")
        self.logger.info(f"Correct Pairs: {correct_pairs}")
        self.logger.info(f"Precision: {precision:.4f}")
        self.logger.info(f"Recall: {recall:.4f}")
        self.logger.info(f"F1 Score: {f1:.4f}")
        
        # 6. 记录错误分析
        incorrect_pairs = []
        for pair in predicted_pairs:
            variation = pair['variation']
            original = pair['original']
            ref_type = pair['reference_type']
            
            variation_refs = ground_truth_refs.get(variation, {'code': None, 'doc': None})
            original_refs = ground_truth_refs.get(original, {'code': None, 'doc': None})
            
            is_correct = False
            if ref_type == 'documentation':
                is_correct = variation_refs['doc'] and original_refs['doc'] and variation_refs['doc'] == original_refs['doc']
            elif ref_type == 'code':
                is_correct = variation_refs['code'] and original_refs['code'] and variation_refs['code'] == original_refs['code']
            
            if not is_correct:
                incorrect_pairs.append({
                    'variation': variation,
                    'original': original,
                    'reference_type': ref_type,
                    'variation_refs': variation_refs,
                    'original_refs': original_refs
                })
        
        if incorrect_pairs:
            self.logger.info("\nIncorrect Fusion Examples (up to 5):")
            for pair in incorrect_pairs[:5]:
                self.logger.info(f"  {pair['variation']} -> {pair['original']} (Type: {pair['reference_type']})")
                self.logger.info(f"    Variation refs: {pair['variation_refs']}")
                self.logger.info(f"    Original refs: {pair['original_refs']}")

        return {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'statistics': {
                'ground_truth_entities': total_ground_truth,
                'predicted_pairs': total_predicted,
                'correct_pairs': correct_pairs,
                'incorrect_pairs': len(incorrect_pairs)
            }
        }

async def test_entity_fusion(input_file, eval_only=False, result_file=None):
    logger = setup_logger('test_entity_fusion', file_output=True)
    logger.info(f"启动实体融合测试，输入文件: {input_file}")
    
    try:
        config = PipelineConfig()
        
        # 从数据文件中加载测试数据
        loader = EntityFusionBenchmarkLoader(input_file, logger)
        
        if eval_only and result_file:
            logger.info(f"仅评估模式，读取结果文件: {result_file}")
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    fusion_results = data['results']
                logger.info("计算已有结果的指标...")
                loader.calculate_metric(fusion_results)
                return
            except FileNotFoundError:
                logger.error(f"结果文件不存在: {result_file}")
                return
            except json.JSONDecodeError:
                logger.error(f"结果文件不是有效的JSON格式: {result_file}")
                return
            except Exception as e:
                logger.error(f"读取结果文件时出错: {str(e)}")
                return
        
        # 添加时间戳到文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        output_file = f'output/test/entity_fusion_test_results_{timestamp}.json'
        Path('output/test').mkdir(parents=True, exist_ok=True)

        logger.info("开始实体融合测试")

        # 初始化处理器
        try:
            processor = EntityProcessor(config)
            logger.info("成功初始化EntityProcessor")
        except Exception as e:
            logger.error(f"初始化EntityProcessor失败: {str(e)}")
            raise
        
        # 获取所有实体及其对应的feature_id
        entity_feature_map = {}
        for _, row in loader.data.iterrows():
            mention = row['mention'].strip()
            feature_id = row['feature_id'] if pd.notna(row['feature_id']) else None
            
            # 如果实体已存在并且feature_id不为空，优先使用已存在的feature_id
            if mention in entity_feature_map:
                if entity_feature_map[mention] is None and feature_id is not None:
                    entity_feature_map[mention] = feature_id
            else:
                entity_feature_map[mention] = feature_id
        
        # 获取所有唯一实体
        unique_entities = list(entity_feature_map.keys())
        logger.info(f"共发现 {len(unique_entities)} 个唯一实体")
        
        if not unique_entities:
            logger.warning("没有找到任何实体，测试结束")
            return
        
        # 获取每个实体对应的feature_id
        feature_ids = [entity_feature_map[entity] for entity in unique_entities]
        
        # 检查feature_id的缺失情况
        null_feature_ids = sum(1 for fid in feature_ids if fid is None)
        if null_feature_ids > 0:
            logger.warning(f"有 {null_feature_ids} 个实体没有对应的feature_id，将使用None")
        
        # 打印实体和feature_id的对应关系作为日志
        logger.info(f"实体与feature_id对应关系样例（前5个）:")
        for i, (entity, feature_id) in enumerate(zip(unique_entities[:5], feature_ids[:5])):
            logger.info(f"  {entity}: {feature_id}")
        
        # 因为数据集中没有commit_ids，所以为每个实体提供一个空列表
        commit_ids_list = [[] for _ in unique_entities]
        
        test_size = min(100, len(unique_entities))
        # 只取前test_size个元素进行测试
        unique_entities = unique_entities[:test_size]
        feature_ids = feature_ids[:test_size]
        commit_ids_list = commit_ids_list[:test_size]
        
        logger.info(f"处理测试实体（共 {test_size} 个）")
        
        try:
            # 一次性处理所有实体融合
            logger.info("开始实体融合处理...")
            all_results = await processor.process_fusion(unique_entities, [],feature_ids, commit_ids_list)
            logger.info(f"处理完成，获得 {len(all_results)} 个结果")
            
            # 保存结果
            logger.info(f"保存结果到文件: {output_file}")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'input_entities': unique_entities,
                    'results': all_results,
                    'feature_ids': feature_ids,
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }, f, ensure_ascii=False, indent=4)
            logger.info(f"结果已保存")
                    
        except Exception as e:
            logger.error(f"处理失败: {str(e)}")
            raise

        # 计算和输出指标
        logger.info("开始计算评估指标...")
        metrics = loader.calculate_metric(all_results)
        logger.info(f"评估完成，F1分数: {metrics.get('f1', 0):.4f}")
        return metrics
    
    except Exception as e:
        logger.error(f"测试过程中发生错误: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise

if __name__ == "__main__":
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='实体融合测试工具')
    parser.add_argument('--input', '-i', dest='input_file', 
                        default='data/mention_extraction_benchmark_0317.xlsx',
                        help='输入数据文件路径')
    parser.add_argument('--eval-only', '-e', dest='eval_only', 
                        action='store_true', 
                        help='仅评估已有结果而不执行融合')
    parser.add_argument('--result', '-r', dest='result_file',
                        help='已有结果文件路径（与eval-only一起使用）')
    parser.add_argument('--test-size', '-n', dest='test_size',
                        type=int, default=100,
                        help='测试实体数量，默认为100')
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 直接设置参数
    eval_only = args.eval_only
    result_file = args.result_file
    input_file = args.input_file
    
    # 打印参数信息
    print(f"实体融合测试启动")
    print(f"输入文件: {input_file}")
    print(f"仅评估模式: {eval_only}")
    if eval_only and result_file:
        print(f"结果文件: {result_file}")
    
    # 运行测试
    try:
        asyncio.run(test_entity_fusion(
            input_file=input_file, 
            eval_only=eval_only, 
            result_file=result_file
        ))
        print("测试完成")
    except KeyboardInterrupt:
        print("测试被用户中断")
    except Exception as e:
        print(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc() 