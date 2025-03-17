# coding: utf-8
import json
import os
import sys
from pathlib import Path
import datetime
import pandas as pd
from typing import List, Dict, Any, Optional, Union
from config.llm_config import LLMType
from collections import defaultdict
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
    """实体抽取评估器"""
    
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
    
    def multi_model_extraction(self, feature):
        """多模型并行抽取+启发式过滤"""
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
        
        # 合并结果并应用过滤
        merged_entities = self.extractor.merge_entities([entities1, entities2])
        filtered_entities = self.filter_entities(merged_entities)
        
        return {
            'strategy': 'Multi-Model Parallel with Filtering',
            'model1_entities': entities1,
            'model2_entities': entities2,
            'merged_entities': merged_entities,
            'filtered_entities': filtered_entities
        }
    
    def filter_entities(self, entities):
        """应用启发式规则过滤实体（从策略B移植）"""
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
    
    def evaluate_extraction(self, sample_size=None):
        """评估抽取方法"""
        metrics = {'multi_model': {'tp': 0, 'fp': 0, 'fn': 0}}
        error_counter = {
            'false_positives': defaultdict(int),
            'false_negatives': defaultdict(int)
        }
        
        feature_results = []
        detailed_results_file = f'output/entity_extraction_details_{self.timestamp}.txt'
        
        # 获取所有特征ID
        feature_ids = list(self.benchmark_features.keys())
        if sample_size:
            feature_ids = feature_ids[:sample_size]

        with open(detailed_results_file, 'w', encoding='utf-8') as f:
            f.write("实体抽取评估详细报告\n")
            f.write("="*50 + "\n\n")

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
            
            # 处理多模型方法
            result = self.multi_model_extraction(feature)
            extracted_entities = set(e.lower() for e in result['filtered_entities'])
            
            # 统计误报和漏报
            for fp_entity in extracted_entities - benchmark_mentions:
                error_counter['false_positives'][fp_entity] += 1
            for fn_entity in benchmark_mentions - extracted_entities:
                error_counter['false_negatives'][fn_entity] += 1
            
            # 计算指标
            tp = len(benchmark_mentions.intersection(extracted_entities))
            fp = len(extracted_entities - benchmark_mentions)
            fn = len(benchmark_mentions - extracted_entities)
            
            metrics['multi_model']['tp'] += tp
            metrics['multi_model']['fp'] += fp
            metrics['multi_model']['fn'] += fn
            
            # 新增对比分析
            correct_entities = benchmark_mentions.intersection(extracted_entities)
            false_positives = extracted_entities - benchmark_mentions
            missing_entities = benchmark_mentions - extracted_entities
            
            # 控制台日志
            self.logger.info(f"\n【实体对比】{feature_id}")
            self.logger.info(f"✅ 正确识别 ({len(correct_entities)}): {', '.join(correct_entities)}")
            self.logger.info(f"❗ 误报实体 ({len(false_positives)}): {', '.join(false_positives)}")
            self.logger.info(f"❌ 漏报实体 ({len(missing_entities)}): {', '.join(missing_entities)}")
            
            # 详细结果文件记录
            with open(detailed_results_file, 'a', encoding='utf-8') as f:
                f.write(f"### 测试用例: {feature_id} ###\n")
                f.write(f"功能描述: {feature_data['feature_description']}\n")
                f.write(f"基准版本: {feature_data.get('version', '')}\n")
                f.write("\n【基准实体列表】\n")
                f.write('\n'.join(f'- {e}' for e in benchmark_mentions) + '\n')
                
                f.write("\n【抽取结果分析】\n")
                f.write(f"模型1原始抽取: {', '.join(result['model1_entities'])}\n")
                f.write(f"模型2原始抽取: {', '.join(result['model2_entities'])}\n")
                f.write(f"合并后实体: {', '.join(result['merged_entities'])}\n")
                f.write(f"过滤后实体: {', '.join(result['filtered_entities'])}\n")
                
                f.write("\n【准确率分析】\n")
                f.write("✅ 正确识别:\n")
                f.write('\n'.join(f'- {e}' for e in correct_entities) + '\n')
                f.write("❗ 误报实体:\n") 
                f.write('\n'.join(f'- {e}' for e in false_positives) + '\n')
                f.write("❌ 漏报实体:\n")
                f.write('\n'.join(f'- {e}' for e in missing_entities) + '\n')
                f.write("\n" + "="*50 + "\n\n")

            # 保存结果
            feature_result = {
                'feature_id': feature_id,
                'benchmark_mentions': list(benchmark_mentions),
                'extraction_result': {
                    'model1_entities': result['model1_entities'],
                    'model2_entities': result['model2_entities'],
                    'filtered_entities': result['filtered_entities'],
                    'tp': tp,
                    'fp': fp,
                    'fn': fn
                }
            }
            feature_result['extraction_result'].update({
                'correct_entities': list(correct_entities),
                'false_positives': list(false_positives),
                'missing_entities': list(missing_entities)
            })
            feature_results.append(feature_result)
        
        # 展示统计结果
        self._show_error_stats(error_counter)
        
        return {
            'overall_metrics': self._calculate_overall_metrics(metrics),
            'error_stats': {
                'false_positives': sorted(error_counter['false_positives'].items(), key=lambda x: -x[1]),
                'false_negatives': sorted(error_counter['false_negatives'].items(), key=lambda x: -x[1])
            }
        }
    
    def _show_error_stats(self, counter):
        """在控制台展示错误统计"""
        def print_top(title, items, top_n=5):
            print(f"\n=== {title}统计 ===")
            print(f"共发现 {len(items)} 个独特实体")
            if items:
                top = sorted(items, key=lambda x: x[1], reverse=True)[:top_n]
                for entity, count in top:
                    print(f"  {entity}: 出现 {count} 次")

        print_top("误报实体", counter['false_positives'].items())
        print_top("漏报实体", counter['false_negatives'].items())

    def _calculate_overall_metrics(self, metrics):
        """计算总体指标"""
        overall_metrics = {}
        
        # 在方法参数中添加error_counter参数
        error_counter = metrics.get('error_stats', {})  # 新增错误计数器获取
        
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
        
        # 在日志中添加误报统计（修改后的部分）
        false_positive_counter = dict(error_counter.get('false_positives', {}))  # 从error_counter获取
        self.logger.info("\n=== 误报实体统计 ===")
        self.logger.info(f"共发现 {len(false_positive_counter)} 个独特误报实体")
        if len(false_positive_counter) > 0:
            top_5 = sorted(
                false_positive_counter.items(),
                key=lambda x: x[1],
                reverse=True
            )[:20]
            self.logger.info("Top 20 最常见误报实体:")
            for entity, count in top_5:
                self.logger.info(f"  {entity}: {count} 次")
        
        return overall_metrics

def main():
    """主函数"""
    evaluator = EntityExtractionEvaluator("data/mention_extraction_benchmark_0310.xlsx")
    results = evaluator.evaluate_extraction()  # 更新方法名
    print("\nEvaluation completed. Results saved to output directory.")

if __name__ == "__main__":
    main() 