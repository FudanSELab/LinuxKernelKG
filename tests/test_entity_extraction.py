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
from utils.llm_factory import LLMFactory
from utils.batch_llm import BatchLLM
import time
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
    
    def __init__(self, benchmark_file=None, use_batch=False):
        """初始化评估器"""
        self.logger = setup_logger()
        self.pipeline_config = PipelineConfig()
        
        # 是否使用批量处理
        self.use_batch = use_batch
        
        if use_batch:
            # 使用批量处理模型
            self.batch_llm = LLMFactory.create_llm(LLMType.BATCH)
            self.logger.info("Using batch processing for entity extraction")
        else:
            # 使用常规模型
            self.llm1 = LLMFactory.create_llm(LLMType.DEEPSEEK)  # 主模型
            self.llm2 = LLMFactory.create_llm(LLMType.OPENAI)  # 辅助模型
        
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
        # 添加常规词及其变体形式
        generic_nouns = {
            'type', 'types', 'part', 'parts', 'option', 'options', 'attribute', 'attributes',
             'field', 'fields', 'case', 'cases', 'example', 'examples','operations','custom','credit',
             ''
        }
        
        for entity in entities:
            # 规则9：过滤单独形容词/副词
            if self.is_standalone_adjective_adverb(entity):
                continue
                
            # 规则10-11：过滤通用动词和形容词
            if self.is_forbidden_word(entity, forbidden_verbs, generic_adjectives):
                continue
            
            # 规则12：过滤常规名词及其变体
            if entity.lower() in generic_nouns:
                continue
            
            # 规则13：过滤单个字母或数字
            if len(entity.strip()) <= 1:
                continue
            
            # 规则14：过滤纯数字
            if entity.strip().isdigit():
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
        
        # 检查是否是通用词的一部分
        words = text.lower().split()
        if len(words) == 1 and len(text) <= 3:  # 过滤单个短词
            return True
            
        return False
    
    def batch_entity_extraction(self, features):
        """批量实体抽取处理
        
        Args:
            features: 特征列表，每个特征包含h1, h2, feature_description等字段
            
        Returns:
            results: 批量处理结果，键为feature_id，值为抽取结果
        """
        self.logger.info(f"Starting batch entity extraction for {len(features)} features")
        
        # 准备批量处理的提示
        prompts = []
        feature_ids = []
        
        for feature_id, feature in features.items():
            # 为每个特征创建两个提示（一个用于模型1，一个用于模型2）
            prompt1 = self.extractor.format_original_prompt(
                feature['h1'], feature['h2'], feature['feature_description']
            )
            prompt2 = self.extractor.format_original_prompt(
                feature['h1'], feature['h2'], feature['feature_description']
            )
            
            prompts.append(prompt1)
            prompts.append(prompt2)
            feature_ids.append(f"{feature_id}_model1")
            feature_ids.append(f"{feature_id}_model2")
        
        # 创建批量文件
        batch_file = self.batch_llm.create_batch_file(
            prompts, 
            custom_id_prefix="entity_extraction",
            output_file=f"output/batch_requests_{self.timestamp}.jsonl"
        )
        
        # 提交批量任务
        batch_id = self.batch_llm.submit_batch_job(
            batch_file, 
            job_description=f"Entity extraction batch job {self.timestamp}"
        )
        
        self.logger.info(f"Batch job submitted with ID: {batch_id}")
        
        # 等待批量任务完成
        # 注意：在实际应用中，您可能需要实现更复杂的等待逻辑或异步处理
        max_wait_time = 3600  # 最长等待时间（秒）
        wait_interval = 60    # 检查间隔（秒）
        total_wait_time = 0
        
        while total_wait_time < max_wait_time:
            status = self.batch_llm.check_batch_status(batch_id)
            if status.status == "completed":
                self.logger.info("Batch job completed successfully")
                break
            elif status.status in ["failed", "cancelled"]:
                self.logger.error(f"Batch job failed with status: {status.status}")
                return {}
            
            self.logger.info(f"Batch job still in progress. Status: {status.status}. Waiting {wait_interval} seconds...")
            time.sleep(wait_interval)
            total_wait_time += wait_interval
        
        if total_wait_time >= max_wait_time:
            self.logger.warning("Batch job did not complete within the maximum wait time")
            return {}
        
        # 下载并解析结果
        results_file = self.batch_llm.download_batch_results(
            batch_id, 
            output_dir=f"output/batch_results_{self.timestamp}"
        )
        
        if not results_file:
            self.logger.error("Failed to download batch results")
            return {}
        
        # 解析结果
        raw_results = self.batch_llm.parse_batch_results(results_file)
        
        # 整理结果
        processed_results = {}
        for i, custom_id in enumerate(raw_results.keys()):
            # 从custom_id中提取feature_id和模型类型
            parts = custom_id.split('-')[1].split('_')  # 例如：entity_extraction-test1_model1
            if len(parts) >= 2:
                feature_id = parts[0]
                model_type = parts[1]
                
                if feature_id not in processed_results:
                    processed_results[feature_id] = {}
                
                # 解析LLM响应
                entities = self.parse_llm_response(raw_results[custom_id])
                
                if model_type == "model1":
                    processed_results[feature_id]['model1_entities'] = entities
                elif model_type == "model2":
                    processed_results[feature_id]['model2_entities'] = entities
        
        # 对每个特征应用合并和过滤
        final_results = {}
        for feature_id, result in processed_results.items():
            if 'model1_entities' in result and 'model2_entities' in result:
                merged_entities = self.extractor.merge_entities([
                    result['model1_entities'], 
                    result['model2_entities']
                ])
                filtered_entities = self.filter_entities(merged_entities)
                
                final_results[feature_id] = {
                    'strategy': 'Multi-Model Parallel with Filtering',
                    'model1_entities': result['model1_entities'],
                    'model2_entities': result['model2_entities'],
                    'merged_entities': merged_entities,
                    'filtered_entities': filtered_entities
                }
        
        return final_results
    
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
        
        # 准备要处理的特征
        features_to_process = {fid: self.benchmark_features[fid] for fid in feature_ids}

        with open(detailed_results_file, 'w', encoding='utf-8') as f:
            f.write("实体抽取评估详细报告\n")
            f.write("="*50 + "\n\n")
        
        # 根据处理模式选择不同的处理方法
        if self.use_batch:
            # 批量处理所有特征
            batch_results = self.batch_entity_extraction(features_to_process)
            
            # 处理批量结果
            for feature_id in feature_ids:
                if feature_id not in batch_results:
                    self.logger.warning(f"No batch results for feature ID: {feature_id}")
                    continue
                
                feature_data = self.benchmark_features[feature_id]
                result = batch_results[feature_id]
                
                # 获取benchmark中的mentions
                benchmark_mentions = set(mention.lower() for mention in feature_data['mentions'])
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
                
                # 记录详细结果
                self._record_detailed_results(
                    feature_id, feature_data, result, 
                    correct_entities, false_positives, missing_entities,
                    detailed_results_file
                )
                
                # 保存结果
                feature_result = self._create_feature_result(
                    feature_id, benchmark_mentions, result,
                    tp, fp, fn, correct_entities, false_positives, missing_entities
                )
                feature_results.append(feature_result)
        else:
            # 逐个处理特征（原有逻辑）
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
    
    def _record_detailed_results(self, feature_id, feature_data, result, correct_entities, false_positives, missing_entities, detailed_results_file):
        """记录详细结果到文件"""
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
            benchmark_mentions = set(mention.lower() for mention in feature_data['mentions'])
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
    
    def _create_feature_result(self, feature_id, benchmark_mentions, result, tp, fp, fn, correct_entities, false_positives, missing_entities):
        """创建特征结果字典"""
        return {
            'feature_id': feature_id,
            'benchmark_mentions': list(benchmark_mentions),
            'extraction_result': {
                'model1_entities': result['model1_entities'],
                'model2_entities': result['model2_entities'],
                'filtered_entities': result['filtered_entities'],
                'tp': tp,
                'fp': fp,
                'fn': fn,
                'correct_entities': list(correct_entities),
                'false_positives': list(false_positives),
                'missing_entities': list(missing_entities)
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
    start_time = datetime.datetime.now()
    
    # 添加命令行参数解析
    import argparse
    parser = argparse.ArgumentParser(description='Entity Extraction Evaluation')
    parser.add_argument('--benchmark', type=str, default="data/mention_extraction_benchmark_0317-1.xlsx",
                        help='Path to benchmark file')
    parser.add_argument('--batch', action='store_true', 
                        help='Use batch processing mode')
    parser.add_argument('--sample', type=int, default=None,
                        help='Number of samples to process (default: all)')
    
    args = parser.parse_args()
    
    # 使用参数初始化评估器
    evaluator = EntityExtractionEvaluator(
        benchmark_file=args.benchmark,
        use_batch=args.batch
    )
    
    # 执行评估
    results = evaluator.evaluate_extraction(sample_size=args.sample)
    
    end_time = datetime.datetime.now()
    execution_time = end_time - start_time
    print("\nEvaluation completed. Results saved to output directory.")
    print(f"Total execution time: {execution_time}")

if __name__ == "__main__":
    main() 