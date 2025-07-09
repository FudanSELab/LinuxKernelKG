import sys
from pathlib import Path
import unittest
import pandas as pd
from typing import Dict, List, Set
from prompts.extractEntityWithContext import extractEntityWithContextPrompt
import json
# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))
from utils.deepseek import deepseek
from scripts.entity_extraction_processor import collect_features_with_mentions
from pipeline.extractor import EntityRelationExtractor
from pipeline.feature_enhancer import FeatureEnhancer
from config.pipeline_config import PipelineConfig
from utils.logger import setup_logger

def strip_json(text):
    """
    从文本中提取JSON字符串并清理
    Args:
        text: 包含JSON的文本
    Returns:
        清理后的JSON字符串
    """
    # 找到第一个 { 和最后一个 } 的位置
    start = text.find('{')
    end = text.rfind('}')
    
    if start == -1 or end == -1:
        raise ValueError("No valid JSON found in the text")
        
    # 提取JSON部分
    json_str = text[start:end + 1]
    
    try:
        # 验证是否为有效的JSON
        json.loads(json_str)
        return json_str
    except json.JSONDecodeError:
        # 如果解析失败，尝试进一步清理
        # 移除可能的多行注释、空行等
        lines = json_str.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('//') and not line.startswith('/*'):
                cleaned_lines.append(line)
        cleaned_json = ' '.join(cleaned_lines)
        return cleaned_json
    
class TestEntityExtraction(unittest.TestCase):
    """测试实体抽取功能的准确性"""
    
    def setUp(self):
        """初始化测试环境"""
        self.logger = setup_logger()
        self.pipeline_config = PipelineConfig()
        self.benchmark_file = "data/mention_extraction_benchmark_0310.xlsx"
        self.enhancer = FeatureEnhancer(self.pipeline_config)
        self.llm = deepseek()
        # 加载benchmark数据
        self.benchmark_features = collect_features_with_mentions(self.benchmark_file)
        self.logger.info(f"Loaded {len(self.benchmark_features)} features with mentions from benchmark")
    
    def test_entity_extraction_accuracy(self):
        """测试实体抽取的准确性"""
        # 初始化计数器
        total_tp = 0  # 真阳性 (True Positive)
        total_fp = 0  # 假阳性 (False Positive)
        total_fn = 0  # 假阴性 (False Negative)
        feature_results = []
        
        # 获取当前时间戳
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        
        # 创建详细结果文件
        detailed_results_file = f'output/entity_extraction_detailed_results_{timestamp}.txt'
        with open(detailed_results_file, 'w', encoding='utf-8') as f:
            f.write("实体抽取详细结果\n")
            f.write("=" * 80 + "\n\n")
        
        # 处理每个feature
        for feature_id, feature_data in self.benchmark_features.items():
            # 准备feature数据
            feature = {
                'feature_id': feature_id,
                'h1': feature_data['h1'],
                'h2': feature_data['h2'],
                'feature_description': feature_data['feature_description'],
                'version': feature_data['version']
            }
            
            # 获取benchmark中的mentions
            benchmark_mentions = set(mention.lower() for mention in feature_data['mentions'])
            
            # 增强feature
            enhanced_feature = self.enhancer.enhance_features([feature])
            
            # 抽取实体和关系
            extraction_result = self.extract_entities_from_benchmark(enhanced_feature)
            
            # 收集抽取的实体
            extracted_entities = set()
            for result in extraction_result:
                # 从三元组中收集实体
                for triple in result.get('triples', []):
                    extracted_entities.add(triple[0].lower())
                    extracted_entities.add(triple[2].lower())
                
                # 从实体列表中收集实体
                for entity in result.get('entities', []):
                    extracted_entities.add(entity.lower())
            
            # 计算TP, FP, FN
            tp = len(benchmark_mentions.intersection(extracted_entities))  # 真阳性：正确抽取的实体
            fp = len(extracted_entities - benchmark_mentions)  # 假阳性：错误抽取的实体
            fn = len(benchmark_mentions - extracted_entities)  # 假阴性：漏掉的实体
            
            # 累加计数
            total_tp += tp
            total_fp += fp
            total_fn += fn
            
            # 记录每个feature的结果
            feature_result = {
                'feature_id': feature_id,
                'tp': tp,
                'fp': fp,
                'fn': fn,
                'benchmark_mentions': len(benchmark_mentions),
                'extracted_entities': len(extracted_entities)
            }
            
            feature_results.append(feature_result)
            
            # 计算正确和错误的抽取（用于日志和详细结果）
            correct = benchmark_mentions.intersection(extracted_entities)
            missed = benchmark_mentions - extracted_entities
            extra = extracted_entities - benchmark_mentions
            
            # 记录详细信息到日志
            self.logger.info(f"\nFeature ID: {feature_id}")
            self.logger.info(f"Feature Description: {feature_data['feature_description']}")
            self.logger.info(f"Benchmark Mentions ({len(benchmark_mentions)}): {', '.join(benchmark_mentions)}")
            self.logger.info(f"Extracted Entities ({len(extracted_entities)}): {', '.join(extracted_entities)}")
            self.logger.info(f"Correctly Extracted (TP={tp}): {', '.join(correct)}")
            self.logger.info(f"Missed Entities (FN={fn}): {', '.join(missed)}")
            self.logger.info(f"Extra Entities (FP={fp}): {', '.join(extra)}")
            
            # 将详细结果写入文件
            with open(detailed_results_file, 'a', encoding='utf-8') as f:
                f.write(f"Feature ID: {feature_id}\n")
                f.write(f"Feature Description: {feature_data['feature_description']}\n")
                f.write(f"Benchmark Mentions ({len(benchmark_mentions)}): {', '.join(benchmark_mentions)}\n")
                f.write(f"Extracted Entities ({len(extracted_entities)}): {', '.join(extracted_entities)}\n")
                f.write(f"Correctly Extracted (TP={tp}): {', '.join(correct)}\n")
                f.write(f"Missed Entities (FN={fn}): {', '.join(missed)}\n")
                f.write(f"Extra Entities (FP={fp}): {', '.join(extra)}\n")
                
                # 添加提取原因
                for result in extraction_result:
                    if 'reason' in result:
                        f.write(f"Extraction Reason: {result['reason']}\n")
                
                f.write("-" * 80 + "\n\n")
        
        # 计算总体指标
        overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
        overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
        
        if overall_precision + overall_recall > 0:
            overall_f1 = 2 * (overall_precision * overall_recall) / (overall_precision + overall_recall)
        else:
            overall_f1 = 0
        
        # 更新每个feature的结果，添加整体指标
        for feature_result in feature_results:
            feature_result['overall_precision'] = overall_precision
            feature_result['overall_recall'] = overall_recall
            feature_result['overall_f1'] = overall_f1
        
        # 汇总结果
        results = {
            'total_tp': total_tp,
            'total_fp': total_fp,
            'total_fn': total_fn,
            'overall_precision': overall_precision,
            'overall_recall': overall_recall,
            'overall_f1': overall_f1,
            'feature_results': feature_results
        }
        
        self.logger.info(f"Overall Results:")
        self.logger.info(f"Total True Positives (TP): {total_tp}")
        self.logger.info(f"Total False Positives (FP): {total_fp}")
        self.logger.info(f"Total False Negatives (FN): {total_fn}")
        self.logger.info(f"Overall Precision: {overall_precision:.4f}")
        self.logger.info(f"Overall Recall: {overall_recall:.4f}")
        self.logger.info(f"Overall F1 Score: {overall_f1:.4f}")
        
        # 将总体结果添加到详细结果文件
        with open(detailed_results_file, 'a', encoding='utf-8') as f:
            f.write("总体结果\n")
            f.write("=" * 80 + "\n")
            f.write(f"Total True Positives (TP): {total_tp}\n")
            f.write(f"Total False Positives (FP): {total_fp}\n")
            f.write(f"Total False Negatives (FN): {total_fn}\n")
            f.write(f"Overall Precision: {overall_precision:.4f}\n")
            f.write(f"Overall Recall: {overall_recall:.4f}\n")
            f.write(f"Overall F1 Score: {overall_f1:.4f}\n")
        
        # 保存结果到CSV
        self._save_results_to_csv(results)
        
        # 验证结果
        self.assertGreater(overall_precision, 0, "Precision should be greater than 0")
        self.assertGreater(overall_recall, 0, "Recall should be greater than 0")
    
    def _save_results_to_csv(self, results: Dict):
        """将测试结果保存到CSV文件"""
        # 获取当前时间，格式为YYYYMMDD_HHMM
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        
        # 保存每个feature的结果
        feature_df = pd.DataFrame(results['feature_results'])
        feature_df.to_csv(f'output/entity_extraction_feature_results_{timestamp}.csv', index=False)
        
        # 保存总体结果
        overall_df = pd.DataFrame([{
            'total_tp': results['total_tp'],
            'total_fp': results['total_fp'],
            'total_fn': results['total_fn'],
            'overall_precision': results['overall_precision'],
            'overall_recall': results['overall_recall'],
            'overall_f1': results['overall_f1']
        }])
        
        overall_df.to_csv(f'output/entity_extraction_overall_results_{timestamp}.csv', index=False)
        self.logger.info(f"Results saved to CSV files in output directory with timestamp {timestamp}")

    def test_entity_extraction_examples(self):
        """测试并展示一些实体抽取的示例"""
        # 选择几个示例feature进行详细分析
        sample_size = min(  1, len(self.benchmark_features))
        sample_feature_ids = list(self.benchmark_features.keys())[:sample_size]
        
        for feature_id in sample_feature_ids:
            feature_data = self.benchmark_features[feature_id]
            
            # 准备feature数据
            feature = {
                'feature_id': feature_id,
                'h1': feature_data['h1'],
                'h2': feature_data['h2'],
                'feature_description': feature_data['feature_description'],
                'version': feature_data['version']
            }
            
            # 获取benchmark中的mentions
            benchmark_mentions = set(mention.lower() for mention in feature_data['mentions'])
            
            # 增强feature
            enhanced_feature = self.enhancer.enhance_features([feature])
            
            # 抽取实体和关系
            extraction_result = self.extract_entities_from_benchmark(enhanced_feature)
            
            # 收集抽取的实体
            extracted_entities = set()
            for result in extraction_result:
                
                for entity in result.get('entities', []):
                    extracted_entities.add(entity.lower())
            
            # 计算正确和错误的抽取
            correct = benchmark_mentions.intersection(extracted_entities)
            missed = benchmark_mentions - extracted_entities
            extra = extracted_entities - benchmark_mentions
            
            self.logger.info(f"\nExample Feature ID: {feature_id}")
            self.logger.info(f"Feature Description: {feature_data['feature_description']}")
            self.logger.info(f"Benchmark Mentions ({len(benchmark_mentions)}): {', '.join(benchmark_mentions)}")
            self.logger.info(f"Extracted Entities ({len(extracted_entities)}): {', '.join(extracted_entities)}")
            self.logger.info(f"Correctly Extracted ({len(correct)}): {', '.join(correct)}")
            self.logger.info(f"Missed Entities ({len(missed)}): {', '.join(missed)}")
            self.logger.info(f"Extra Entities ({len(extra)}): {', '.join(extra)}")



    def extract_entities_from_benchmark(self, features):
        """
        从基准测试数据中抽取实体和关系，不依赖数据库操作。
        专为测试和基准评估设计。
        
        Args:
            features: list of dict, 每个 dict 包含 feature_id, feature_description 和 version
            
        Returns:
            features_output: list of dict, 每个 dict 包含 feature_id, feature_description, version, entities 和 triples
        """
        try:
            features_output = []
            for index, feature in enumerate(features):
                feature_id = feature['feature_id']
                feature_description = feature['feature_description']
                version = feature.get('version', '')
                h1 = feature.get('h1', '')
                h2 = feature.get('h2', '')
                
                # 合并所有文本信息以提供更丰富的上下文
                full_description = f"{h1}\n{h2}\n{feature_description}".strip()
                
                self.logger.info(f"Processing benchmark item {index+1}/{len(features)}, feature_id {feature_id}")
                
                # 实体抽取 - 使用新的extractEntityWithContextPrompt并传入正确的参数
                prompt_entity = extractEntityWithContextPrompt(
                    h1=h1,
                    h2=h2,
                    feature_description=feature_description
                ).format()
                response_entity = self.llm.get_response(prompt_entity)
                object_entity = json.loads(strip_json(response_entity))
                
                feature_extracted = {
                    "feature_id": feature_id,
                    "feature_description": feature_description,
                    "version": version,
                    "entities": object_entity['entities'],
                    "reason": object_entity.get('reason', '')  # 添加提取原因
                }
                
                features_output.append(feature_extracted)
            return features_output
        
        except Exception as e:
            self.logger.error(f"Failed to extract entities from benchmark: {e}")
            raise e


if __name__ == '__main__':
    unittest.main()
