# coding: utf-8
import json
import os
import sys
from pathlib import Path
import datetime
import pandas as pd
from typing import List, Dict, Any, Optional, Union
from config.llm_config import LLMType
# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from prompts.extractEntityWithContext import extractEntityWithContextPrompt
from prompts.enhancedEntityExtractor import EnhancedEntityExtractor
from utils.deepseek import deepseek
from utils.logger import setup_logger
from scripts.entity_extraction_processor import collect_features_with_mentions
from config.pipeline_config import PipelineConfig

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

class EntityExtractionEvaluator:
    """实体抽取策略评估器"""
    
    def __init__(self, benchmark_file=None):
        """初始化评估器"""
        self.logger = setup_logger()
        self.pipeline_config = PipelineConfig()
        self.llm1 = deepseek(LLMType.OPENAI)  # 主模型
        self.llm2 = deepseek(LLMType.DEEPSEEK)  # 辅助模型 (可以是同一个模型实例)
        self.extractor = EnhancedEntityExtractor()
        
        # 加载benchmark数据
        if benchmark_file:
            self.benchmark_file = benchmark_file
            self.benchmark_features = collect_features_with_mentions(self.benchmark_file)
            self.logger.info(f"Loaded {len(self.benchmark_features)} features with mentions from benchmark")
        else:
            # 使用测试数据
            self.benchmark_features = self._get_test_cases()
            self.logger.info(f"Using {len(self.benchmark_features)} test cases")
        
        # 创建输出目录
        os.makedirs('output', exist_ok=True)
        
        # 获取当前时间戳
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        
    def _get_test_cases(self):
        """获取测试用例"""
        test_cases = {
            "test1": {
                'h1': 'Memory Management',
                'h2': 'Page Allocation',
                'feature_description': 'Prohibit the last subpage from reusing the entire large folio',
                'version': 'v5.15',
                'mentions': ['subpage', 'large folio', 'reusing']
            },
            "test2": {
                'h1': 'Networking',
                'h2': 'TCP/IP',
                'feature_description': 'Implement TCP congestion control algorithm for high-latency networks',
                'version': 'v5.15',
                'mentions': ['TCP', 'congestion control', 'algorithm', 'high-latency networks','TCP congestion control']
            },
            "test3": {
                'h1': 'File Systems',
                'h2': 'Ext4',
                'feature_description': 'Add support for larger inode numbers in ext4 filesystem',
                'version': 'v5.15',
                'mentions': ['inode numbers', 'ext4', 'filesystem', 'inode']
            }
        }
        return test_cases
    
    def parse_llm_response(self, response: str) -> List[str]:
        """解析LLM响应，提取实体列表"""
        try:
            # 尝试解析JSON响应
            response_json = json.loads(strip_json(response))
            
            if 'output' in response_json and 'entities' in response_json['output']:
                return response_json['output']['entities']
            elif 'entities' in response_json:
                return response_json['entities']
            elif 'additional_entities' in response_json:
                return response_json['additional_entities']
            else:
                self.logger.warning(f"Unexpected JSON structure: {response_json}")
                return []
        except (json.JSONDecodeError, ValueError) as e:
            self.logger.warning(f"Failed to parse response: {e}")
            return []
    
    def strategy_a_multi_model(self, feature):
        """策略A: 不同大模型分析后的结果进行合并"""
        # 第一个模型抽取
        prompt1 = self.extractor.format_original_prompt(
            feature['h1'], feature['h2'], feature['feature_description']
        )
        response1 = self.llm1.get_response(prompt1)
        entities1 = self.parse_llm_response(response1)
        
        # 第二个模型抽取
        prompt2 = self.extractor.format_original_prompt(
            feature['h1'], feature['h2'], feature['feature_description']
        )
        response2 = self.llm2.get_response(prompt2)
        entities2 = self.parse_llm_response(response2)
        
        # 合并结果
        merged_entities = self.extractor.merge_entities([entities1, entities2])
        
        return {
            'strategy': 'A - Multi-Model Parallel',
            'model1_entities': entities1,
            'model2_entities': entities2,
            'merged_entities': merged_entities
        }
    
    def strategy_b_sequential_models(self, feature):
        """策略B: 前一个大模型分析完成后另一个大模型进行补充"""
        # 第一个模型抽取
        prompt1 = self.extractor.format_original_prompt(
            feature['h1'], feature['h2'], feature['feature_description']
        )
        response1 = self.llm1.get_response(prompt1)
        entities1 = self.parse_llm_response(response1)
        
        # 第二个模型补充抽取
        prompt2 = self.extractor.format_supplementary_prompt(
            feature['h1'], feature['h2'], feature['feature_description'], entities1
        )
        response2 = self.llm2.get_response(prompt2)
        entities2 = self.parse_llm_response(response2)
        
        # 合并结果
        merged_entities = self.extractor.merge_entities([entities1, entities2])
        
        # 添加启发式过滤
        filtered_entities = self.filter_entities(merged_entities)
        
        return {
            'strategy': 'B - Sequential Models',
            'model1_entities': entities1,
            'model2_additional_entities': entities2,
            'merged_entities': filtered_entities
        }
    
    def filter_entities(self, entities):
        """应用启发式规则过滤实体"""
        filtered = []
        forbidden_verbs = {'add', 'support', 'implement', 'enable', 'check', 'export',
                          'create', 'improve', 'optimize', 'fix', 'allow', 'make',
                          'use', 'handle', 'provide'}
        generic_adjectives = {'new', 'better', 'faster', 'improved', 'enhanced',
                             'basic', 'simple'}
        
        for entity in entities:
            # 规则9：过滤单独形容词/副词
            if self.is_standalone_adjective_adverb(entity):
                continue
                
            # 规则10-11：过滤通用动词和形容词
            if self.is_forbidden_word(entity, forbidden_verbs, generic_adjectives):
                continue
            
            filtered.append(entity)
        return filtered

    def is_standalone_adjective_adverb(self, text):
        """检查是否是单独的形容词/副词"""
        from nltk import pos_tag, word_tokenize
        tokens = word_tokenize(text)
        if len(tokens) != 1:
            return False  # 只检查单个词的情况
            
        pos = pos_tag(tokens)[0][1]
        return pos in ['JJ', 'JJR', 'JJS', 'RB', 'RBR', 'RBS']  # 形容词/副词词性标记

    def is_forbidden_word(self, text, verbs, adjectives):
        """检查是否在禁用词列表中"""
        from nltk.stem import WordNetLemmatizer
        lemmatizer = WordNetLemmatizer()
        
        # 处理动词的不同形式
        base_verb = lemmatizer.lemmatize(text.lower(), 'v')
        if base_verb in verbs:
            return True
            
        # 处理形容词
        if text.lower() in adjectives:
            return True
            
        return False
    
    def strategy_c_segmented_extraction(self, feature):
        """策略C: 同一个大模型分多次告诉它需求点，然后汇总结果"""
        all_entities = []
        
        # 分段抽取
        for i, focus_areas in enumerate(self.extractor.focus_area_groups):
            prompt = self.extractor.format_segmented_prompt(
                feature['h1'], feature['h2'], feature['feature_description'], focus_areas
            )
            response = self.llm1.get_response(prompt)
            entities = self.parse_llm_response(response)
            all_entities.append(entities)
        
        # 合并结果
        merged_entities = self.extractor.merge_entities(all_entities)
        
        return {
            'strategy': 'C - Segmented Extraction',
            'segment1_entities': all_entities[0] if len(all_entities) > 0 else [],
            'segment2_entities': all_entities[1] if len(all_entities) > 1 else [],
            'segment3_entities': all_entities[2] if len(all_entities) > 2 else [],
            'merged_entities': merged_entities
        }
    
    def baseline_extraction(self, feature):
        """基准: 单一模型单次抽取"""
        prompt = self.extractor.format_original_prompt(
            feature['h1'], feature['h2'], feature['feature_description']
        )
        response = self.llm1.get_response(prompt)
        entities = self.parse_llm_response(response)
        
        return {
            'strategy': 'Baseline - Single Model',
            'entities': entities
        }
    
    def evaluate_strategies(self, sample_size=None):
        """评估所有策略"""
        # 初始化计数器
        metrics = {
            'baseline': {'tp': 0, 'fp': 0, 'fn': 0},
            'strategy_a': {'tp': 0, 'fp': 0, 'fn': 0},
            'strategy_b': {'tp': 0, 'fp': 0, 'fn': 0},
            'strategy_c': {'tp': 0, 'fp': 0, 'fn': 0}
        }
        
        feature_results = []
        
        # 如果指定了样本大小，则只处理部分特征
        feature_ids = list(self.benchmark_features.keys())
        if sample_size:
            feature_ids = feature_ids[:min(sample_size, len(feature_ids))]
        
        # 创建详细结果文件
        detailed_results_file = f'output/entity_extraction_strategies_results_{self.timestamp}.txt'
        with open(detailed_results_file, 'w', encoding='utf-8') as f:
            f.write("实体抽取策略评估详细结果\n")
            f.write("=" * 80 + "\n\n")
        
        for feature_id in feature_ids:
            feature_data = self.benchmark_features[feature_id]
            
            # 准备feature数据
            feature = {
                'feature_id': feature_id,
                'h1': feature_data['h1'],
                'h2': feature_data['h2'],
                'feature_description': feature_data['feature_description'],
                'version': feature_data.get('version', '')
            }
            
            # 获取benchmark中的mentions
            benchmark_mentions = set(mention.lower() for mention in feature_data['mentions'])
            
            self.logger.info(f"\nProcessing feature ID: {feature_id}")
            self.logger.info(f"Feature Description: {feature_data['feature_description']}")
            
            # 记录到详细结果文件
            with open(detailed_results_file, 'a', encoding='utf-8') as f:
                f.write(f"Feature ID: {feature_id}\n")
                f.write(f"H1: {feature_data['h1']}\n")
                f.write(f"H2: {feature_data['h2']}\n")
                f.write(f"Feature Description: {feature_data['feature_description']}\n")
                f.write(f"Benchmark Mentions ({len(benchmark_mentions)}): {', '.join(benchmark_mentions)}\n\n")
            
            feature_result = {
                'feature_id': feature_id,
                'feature_description': feature_data['feature_description'],
                'benchmark_mentions': list(benchmark_mentions),
                'strategies': []
            }
            
            # 基准抽取
            baseline = self.baseline_extraction(feature)
            baseline_entities = set(e.lower() for e in baseline['entities'])
            
            # 计算基准TP, FP, FN
            baseline_tp = len(benchmark_mentions.intersection(baseline_entities))
            baseline_fp = len(baseline_entities - benchmark_mentions)
            baseline_fn = len(benchmark_mentions - baseline_entities)
            
            # 累加基准指标
            metrics['baseline']['tp'] += baseline_tp
            metrics['baseline']['fp'] += baseline_fp
            metrics['baseline']['fn'] += baseline_fn
            
            # 记录基准结果
            self.logger.info(f"Baseline Entities ({len(baseline_entities)}): {', '.join(baseline_entities)}")
            self.logger.info(f"Baseline - TP: {baseline_tp}, FP: {baseline_fp}, FN: {baseline_fn}")
            
            with open(detailed_results_file, 'a', encoding='utf-8') as f:
                f.write(f"--- Baseline Results ---\n")
                f.write(f"Entities ({len(baseline_entities)}): {', '.join(baseline_entities)}\n")
                f.write(f"TP: {baseline_tp}, FP: {baseline_fp}, FN: {baseline_fn}\n\n")
            
            # 保存基准结果
            feature_result['baseline'] = {
                'strategy': 'Baseline - Single Model',
                'entities': list(baseline_entities),
                'tp': baseline_tp,
                'fp': baseline_fp,
                'fn': baseline_fn
            }
            
            # 策略A: 多模型并行
            result_a = self.strategy_a_multi_model(feature)
            strategy_a_entities = set(e.lower() for e in result_a['merged_entities'])
            
            # 计算策略A的TP, FP, FN
            strategy_a_tp = len(benchmark_mentions.intersection(strategy_a_entities))
            strategy_a_fp = len(strategy_a_entities - benchmark_mentions)
            strategy_a_fn = len(benchmark_mentions - strategy_a_entities)
            
            # 累加策略A指标
            metrics['strategy_a']['tp'] += strategy_a_tp
            metrics['strategy_a']['fp'] += strategy_a_fp
            metrics['strategy_a']['fn'] += strategy_a_fn
            
            # 记录策略A结果
            self.logger.info(f"\nStrategy A Entities ({len(strategy_a_entities)}): {', '.join(strategy_a_entities)}")
            self.logger.info(f"Strategy A - TP: {strategy_a_tp}, FP: {strategy_a_fp}, FN: {strategy_a_fn}")
            
            with open(detailed_results_file, 'a', encoding='utf-8') as f:
                f.write(f"--- Strategy A Results ---\n")
                f.write(f"Model 1 Entities ({len(result_a['model1_entities'])}): {', '.join(result_a['model1_entities'])}\n")
                f.write(f"Model 2 Entities ({len(result_a['model2_entities'])}): {', '.join(result_a['model2_entities'])}\n")
                f.write(f"Merged Entities ({len(strategy_a_entities)}): {', '.join(strategy_a_entities)}\n")
                f.write(f"TP: {strategy_a_tp}, FP: {strategy_a_fp}, FN: {strategy_a_fn}\n\n")
            
            # 保存策略A结果
            feature_result['strategies'].append({
                'strategy': 'A - Multi-Model Parallel',
                'model1_entities': result_a['model1_entities'],
                'model2_entities': result_a['model2_entities'],
                'merged_entities': list(strategy_a_entities),
                'tp': strategy_a_tp,
                'fp': strategy_a_fp,
                'fn': strategy_a_fn
            })
            
            # 策略B: 串行模型
            result_b = self.strategy_b_sequential_models(feature)
            strategy_b_entities = set(e.lower() for e in result_b['merged_entities'])
            
            # 计算策略B的TP, FP, FN
            strategy_b_tp = len(benchmark_mentions.intersection(strategy_b_entities))
            strategy_b_fp = len(strategy_b_entities - benchmark_mentions)
            strategy_b_fn = len(benchmark_mentions - strategy_b_entities)
            
            # 累加策略B指标
            metrics['strategy_b']['tp'] += strategy_b_tp
            metrics['strategy_b']['fp'] += strategy_b_fp
            metrics['strategy_b']['fn'] += strategy_b_fn
            
            # 记录策略B结果
            self.logger.info(f"\nStrategy B Entities ({len(strategy_b_entities)}): {', '.join(strategy_b_entities)}")
            self.logger.info(f"Strategy B - TP: {strategy_b_tp}, FP: {strategy_b_fp}, FN: {strategy_b_fn}")
            
            with open(detailed_results_file, 'a', encoding='utf-8') as f:
                f.write(f"--- Strategy B Results ---\n")
                f.write(f"Model 1 Entities ({len(result_b['model1_entities'])}): {', '.join(result_b['model1_entities'])}\n")
                f.write(f"Model 2 Additional Entities ({len(result_b['model2_additional_entities'])}): {', '.join(result_b['model2_additional_entities'])}\n")
                f.write(f"Merged Entities ({len(strategy_b_entities)}): {', '.join(strategy_b_entities)}\n")
                f.write(f"TP: {strategy_b_tp}, FP: {strategy_b_fp}, FN: {strategy_b_fn}\n\n")
            
            # 保存策略B结果
            feature_result['strategies'].append({
                'strategy': 'B - Sequential Models',
                'model1_entities': result_b['model1_entities'],
                'model2_additional_entities': result_b['model2_additional_entities'],
                'merged_entities': list(strategy_b_entities),
                'tp': strategy_b_tp,
                'fp': strategy_b_fp,
                'fn': strategy_b_fn
            })
            
            # 策略C: 分段抽取
            result_c = self.strategy_c_segmented_extraction(feature)
            strategy_c_entities = set(e.lower() for e in result_c['merged_entities'])
            
            # 计算策略C的TP, FP, FN
            strategy_c_tp = len(benchmark_mentions.intersection(strategy_c_entities))
            strategy_c_fp = len(strategy_c_entities - benchmark_mentions)
            strategy_c_fn = len(benchmark_mentions - strategy_c_entities)
            
            # 累加策略C指标
            metrics['strategy_c']['tp'] += strategy_c_tp
            metrics['strategy_c']['fp'] += strategy_c_fp
            metrics['strategy_c']['fn'] += strategy_c_fn
            
            # 记录策略C结果
            self.logger.info(f"\nStrategy C Entities ({len(strategy_c_entities)}): {', '.join(strategy_c_entities)}")
            self.logger.info(f"Strategy C - TP: {strategy_c_tp}, FP: {strategy_c_fp}, FN: {strategy_c_fn}")
            
            with open(detailed_results_file, 'a', encoding='utf-8') as f:
                f.write(f"--- Strategy C Results ---\n")
                f.write(f"Segment 1 Entities ({len(result_c['segment1_entities'])}): {', '.join(result_c['segment1_entities'])}\n")
                f.write(f"Segment 2 Entities ({len(result_c['segment2_entities'])}): {', '.join(result_c['segment2_entities'])}\n")
                f.write(f"Segment 3 Entities ({len(result_c['segment3_entities'])}): {', '.join(result_c['segment3_entities'])}\n")
                f.write(f"Merged Entities ({len(strategy_c_entities)}): {', '.join(strategy_c_entities)}\n")
                f.write(f"TP: {strategy_c_tp}, FP: {strategy_c_fp}, FN: {strategy_c_fn}\n\n")
            
            # 保存策略C结果
            feature_result['strategies'].append({
                'strategy': 'C - Segmented Extraction',
                'segment1_entities': result_c['segment1_entities'],
                'segment2_entities': result_c['segment2_entities'],
                'segment3_entities': result_c['segment3_entities'],
                'merged_entities': list(strategy_c_entities),
                'tp': strategy_c_tp,
                'fp': strategy_c_fp,
                'fn': strategy_c_fn
            })
            
            with open(detailed_results_file, 'a', encoding='utf-8') as f:
                f.write("-" * 80 + "\n\n")
            
            feature_results.append(feature_result)
        
        # 在所有特征处理完成后计算总体指标
        overall_metrics = self._calculate_overall_metrics(metrics, detailed_results_file)
        
        # 保存结果到JSON
        results = {
            'overall_metrics': overall_metrics,
            'feature_results': feature_results
        }
        
        with open(f'output/entity_extraction_strategies_results_{self.timestamp}.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        return results
    
    def _calculate_overall_metrics(self, metrics, detailed_results_file):
        """计算总体指标"""
        overall_metrics = {}
        
        for strategy, counts in metrics.items():
            tp = counts['tp']
            fp = counts['fp']
            fn = counts['fn']
            
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
            
            overall_metrics[strategy] = {
                'tp': tp,
                'fp': fp,
                'fn': fn,
                'precision': precision,
                'recall': recall,
                'f1': f1
            }
        
        # 记录总体指标
        self.logger.info("\n=== Overall Metrics ===")
        for strategy, metrics in overall_metrics.items():
            self.logger.info(f"{strategy.capitalize()} - Precision: {metrics['precision']:.4f}, Recall: {metrics['recall']:.4f}, F1: {metrics['f1']:.4f}")
        
        with open(detailed_results_file, 'a', encoding='utf-8') as f:
            f.write("=== Overall Metrics ===\n")
            for strategy, metrics in overall_metrics.items():
                f.write(f"{strategy.capitalize()}:\n")
                f.write(f"  TP: {metrics['tp']}, FP: {metrics['fp']}, FN: {metrics['fn']}\n")
                f.write(f"  Precision: {metrics['precision']:.4f}, Recall: {metrics['recall']:.4f}, F1: {metrics['f1']:.4f}\n\n")
        
        # 保存总体指标到CSV
        overall_df = pd.DataFrame([{
            'strategy': strategy.capitalize(),
            'tp': metrics['tp'],
            'fp': metrics['fp'],
            'fn': metrics['fn'],
            'precision': metrics['precision'],
            'recall': metrics['recall'],
            'f1': metrics['f1']
        } for strategy, metrics in overall_metrics.items()])
        
        overall_df.to_csv(f'output/entity_extraction_overall_metrics_{self.timestamp}.csv', index=False)
        self.logger.info(f"Overall metrics saved to CSV: output/entity_extraction_overall_metrics_{self.timestamp}.csv")
        
        return overall_metrics

def main():
    """主函数"""
    # 使用默认测试用例
    evaluator = EntityExtractionEvaluator("data/mention_extraction_benchmark_0310-1.xlsx")
    
    # 评估所有策略
    results = evaluator.evaluate_strategies()
    
    print("\nEvaluation completed. Results saved to output directory.")

if __name__ == "__main__":
    main() 