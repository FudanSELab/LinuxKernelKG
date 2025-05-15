# coding: utf-8
import sys
import os
import json
import datetime
import pandas as pd
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parents[1]
sys.path.append(str(project_root))

from utils.logger import setup_logger
from config.pipeline_config import PipelineConfig
# from pipeline.data_collector import DataCollector
from prompts.extractTripleOpen import extractTripleOpenPrompt
from utils.deepseek import deepseek
from utils.utils import strip_json
from models.feature import Feature

class OpenTripleExtractionRunner:
    """实体提取任务执行器"""
    
    def __init__(self, batch_size=100, start_index=0, resume_file=None):
        """
        初始化实体提取执行器
        
        Args:
            batch_size: 每批处理的特性数量
            start_index: 开始处理的索引位置
            resume_file: 恢复执行的文件路径，如果提供则从该文件恢复执行状态
        """
        self.logger = setup_logger()
        self.pipeline_config = PipelineConfig()
        self.batch_size = batch_size
        self.start_index = start_index
        self.llm = deepseek()
        
        # 创建输出目录
        os.makedirs('output/open_triple_extraction', exist_ok=True)
        
        # 获取当前时间戳
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        
        # 初始化数据收集器
        # self.collector = DataCollector(self.pipeline_config)
        
        # 从数据库加载特性数据
        self.logger.info("Loading features from database...")
        
        temp_json_object = json.load(open('data/open_triple_extraction/mm_features.json', 'r', encoding='utf-8'))
        self.features = []
        for feature in temp_json_object:
            self.features.append(
                Feature(
                    feature_id=feature['feature_id'],
                    h1=feature['h1'],
                    h2=feature['h2'],
                    feature_description=feature['text'],
                    version=feature['version']
                )
            )

        # 随机取 1000 个
        # TODO: 改成大规模抽取
        # import random
        # random.seed(42)  # 设置随机种子以确保可重复性
        # random.shuffle(self.features)
        # self.features = self.features[:1000]

        self.logger.info(f"Loaded {len(self.features)} features from database")
        
        # 如果提供了恢复文件，从该文件恢复执行状态
        self.results_file = None
        self.stats_file = None
        self.stats = None
        
        if resume_file:
            self._resume_execution(resume_file)
    
    def _resume_execution(self, resume_file):
        """从统计文件恢复执行状态"""
        try:
            self.logger.info(f"Attempting to resume execution from {resume_file}")
            
            # 修正: 判断文件扩展名，确保使用正确的文件类型
            if resume_file.endswith('.jsonl'):
                self.logger.error(f"错误: 提供的是结果文件(.jsonl)而不是统计文件(.json)。请提供统计文件路径。")
                self.logger.info("Starting a new open triple extraction run")
                self.stats = None
                return
                
            with open(resume_file, 'r', encoding='utf-8') as f:
                self.stats = json.load(f)
            
            # 获取最后处理的索引
            if self.stats['batches']:
                last_batch = self.stats['batches'][-1]
                self.start_index = last_batch['end_index'] + 1
                
                # 恢复文件路径 - 修正文件名替换逻辑
                dir_path = os.path.dirname(resume_file)
                base_name = os.path.basename(resume_file)
                if 'stats' in base_name:
                    results_file_name = base_name.replace('stats', 'results')
                else:
                    # 如果文件名中没有'stats'，使用时间戳部分构建
                    timestamp_part = base_name.split('_', 1)[-1].rsplit('.', 1)[0]
                    results_file_name = f'open_triple_extraction_results_{timestamp_part}.jsonl'
                
                self.results_file = os.path.join(dir_path, results_file_name)
                self.stats_file = resume_file
                
                # 检查结果文件是否存在
                if not os.path.exists(self.results_file):
                    self.logger.warning(f"结果文件 {self.results_file} 不存在，将创建新文件")
                
                self.logger.info(f"Resuming from index {self.start_index}")
                self.logger.info(f"Using results file: {self.results_file}")
            else:
                self.logger.warning("No completed batches found in resume file, starting from beginning")
                
        except Exception as e:
            self.logger.error(f"Failed to resume execution: {e}")
            self.logger.info("Starting a new extraction run")
            self.stats = None
    
    def run_extraction(self):
        """运行实体提取任务"""
        # 如果没有恢复现有的运行，初始化新的运行
        if not self.stats:
            start_time = datetime.datetime.now()
            self.logger.info(f"Starting open triple extraction at {start_time}")
            
            # 创建结果文件
            self.results_file = f'output/open_triple_extraction/open_triple_extraction_results_{self.timestamp}.jsonl'
            self.stats_file = f'output/open_triple_extraction/open_triple_extraction_stats_{self.timestamp}.json'
            
            # 初始化统计数据
            self.stats = {
                'total_features': len(self.features) - self.start_index,
                'processed_features': 0,
                'total_triples': 0,
                'start_time': start_time.isoformat(),
                'batches': []
            }
        else:
            # 从现有的stats恢复
            start_time = datetime.datetime.fromisoformat(self.stats['start_time'])
            self.logger.info(f"Resuming open triple extraction that started at {start_time}")
            
        self.logger.info(f"Processing from index {self.start_index} with batch size {self.batch_size}")
        
        # 获取要处理的特性
        features_to_process = self.features[self.start_index:]
        
        # 分批处理
        for batch_idx, i in enumerate(range(0, len(features_to_process), self.batch_size)):
            batch_start_time = datetime.datetime.now()
            batch_features = features_to_process[i:i+self.batch_size]
            current_index = i + self.start_index
            self.logger.info(f"Processing batch {batch_idx+1}: features {current_index} to {current_index+len(batch_features)-1}")
            
            batch_results = []
            batch_triples_count = 0
            
            # 处理每个特性，添加错误处理
            for feature_idx, feature in enumerate(batch_features):
                feature_id = feature.feature_id
                
                try:
                    # 调用提取函数
                    extraction_result = self._open_triple_extraction(feature)
                    
                    # 记录详细的提取信息到日志
                    self.logger.info(f"Feature {feature_id} extraction details:")
                    self.logger.info("triples:\n" + "\n".join([f"{head} ------ {relation} ------ {tail}  (tail_type = {tail_type})" for head, relation, tail, tail_type in extraction_result]))

                    # 记录结果
                    result = {
                        'feature_id': feature_id,
                        'feature': feature.to_dict(),
                        'extraction_result': extraction_result
                    }
                    batch_results.append(result)
                    
                    # 更新统计信息
                    batch_triples_count += len(extraction_result)
                    
                    # 将结果写入JSONL文件
                    with open(self.results_file, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(result, ensure_ascii=False) + '\n')
                    
                    self.logger.info(f"Feature {feature_id} processed successfully, extracted {len(extraction_result)} triples")
                        
                except Exception as e:
                    self.logger.error(f"Error processing feature {feature_id} at index {current_index + feature_idx}: {e}")
                    # 记录失败的特性以便后续重试
                    with open(f'output/open_triple_extraction/failed_features_{self.timestamp}.jsonl', 'a', encoding='utf-8') as f:
                        f.write(json.dumps({
                            'feature_id': feature_id,
                            'feature': feature.to_dict(),
                            'error': str(e),
                            'index': current_index + feature_idx
                        }, ensure_ascii=False) + '\n')
                    
                # 每5个特性保存一次状态，防止批次中途中断
                if (feature_idx + 1) % 5 == 0:
                    self._save_progress_state(batch_idx, current_index, feature_idx, batch_triples_count, batch_start_time)
            
            # 更新批次统计信息
            batch_end_time = datetime.datetime.now()
            batch_duration = (batch_end_time - batch_start_time).total_seconds()
            
            batch_stats = {
                'batch_index': len(self.stats['batches']),
                'start_index': current_index,
                'end_index': current_index + len(batch_features) - 1,
                'features_count': len(batch_features),
                'triples_count': batch_triples_count,
                'duration_seconds': batch_duration,
                'start_time': batch_start_time.isoformat(),
                'end_time': batch_end_time.isoformat()
            }
            
            self.stats['batches'].append(batch_stats)
            self.stats['processed_features'] += len(batch_features)
            self.stats['total_triples'] += batch_triples_count
            
            # 更新并保存统计信息
            self.stats['end_time'] = batch_end_time.isoformat()
            self.stats['duration_seconds'] = (batch_end_time - datetime.datetime.fromisoformat(self.stats['start_time'])).total_seconds()
            
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"Batch {batch_idx+1} completed: {len(batch_features)} features, {batch_triples_count} triples extracted")
            self.logger.info(f"Batch duration: {batch_duration:.2f} seconds")
            self.logger.info(f"Total progress: {self.stats['processed_features']}/{self.stats['total_features']} features processed")
        
        # 完成所有处理
        end_time = datetime.datetime.now()
        total_duration = (end_time - datetime.datetime.fromisoformat(self.stats['start_time'])).total_seconds()
        
        self.logger.info(f"Open Triple extraction completed at {end_time}")
        self.logger.info(f"Total duration: {total_duration:.2f} seconds")
        self.logger.info(f"Total features processed: {self.stats['processed_features']}")
        self.logger.info(f"Total triples extracted: {self.stats['total_triples']}")
        self.logger.info(f"Results saved to {self.results_file}")
        self.logger.info(f"Statistics saved to {self.stats_file}")
        
        return {
            'results_file': self.results_file,
            'stats_file': self.stats_file,
            'stats': self.stats
        }
    
    def _open_triple_extraction(self, feature):
        """
        从单个 feature 调用模型提取三元组
        Args:
            feature: Feature
        Returns:
            extraction_result: list[triple]
        """
        hierarchy = feature.feature_description.split('<sep>')
        parents = hierarchy[:-1]
        parents = [feature.h2] + parents if feature.h2 else parents
        parents = [feature.h1] + parents if feature.h1 else parents

        self.logger.info(f"Extracting triples for feature {feature.feature_id} with parents: {parents}")

        prompt_triple = extractTripleOpenPrompt(
            feature_description=hierarchy[-1],
            parents=parents
        ).format()

        response_triples = self.llm.get_response(prompt_triple)
        extraction_result = json.loads(strip_json(response_triples))
        if 'output' in extraction_result:
            extraction_result = extraction_result['output']
        extraction_result = [triples for triples in extraction_result['triples'] if len(triples) == 4]
        return extraction_result
    


    def _save_progress_state(self, batch_idx, current_index, feature_idx, batch_triples_count, batch_start_time):
        """保存中间进度状态"""
        now = datetime.datetime.now()
        temp_stats = self.stats.copy()
        
        # 创建临时批次信息
        temp_batch = {
            'batch_index': len(self.stats['batches']),
            'start_index': current_index,
            'current_progress': feature_idx + 1,  # 当前处理的特性索引
            'features_count': feature_idx + 1,    # 已处理的特性数量
            'triples_count': batch_triples_count,
            'duration_seconds': (now - batch_start_time).total_seconds(),
            'start_time': batch_start_time.isoformat(),
            'checkpoint_time': now.isoformat()
        }
        
        # 更新临时统计信息
        temp_stats['checkpoint'] = {
            'batch_idx': batch_idx,
            'feature_idx': feature_idx,
            'current_index': current_index + feature_idx
        }
        temp_stats['checkpoint_time'] = now.isoformat()
        
        # 保存临时状态
        checkpoint_file = f'output/open_triple_extraction/checkpoint_{self.timestamp}.json'
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(temp_stats, f, ensure_ascii=False, indent=2)

def export_triples_to_csv(results_file, output_file=None):
    """
    将提取的实体导出为CSV格式
    
    Args:
        results_file: JSONL结果文件路径
        output_file: 输出CSV文件路径
    """
    logger = setup_logger()
    
    if output_file is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        output_file = f'output/open_triple_extraction/triples_{timestamp}.csv'
    
    # 读取JSONL文件
    triples_data = []
    with open(results_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                result = json.loads(line)
                feature = result['feature']
                triples = result['extraction_result']
                
                # 为每个三元组创建一条记录
                for triple in triples:
                    triples_data.append({
                        'feature_id': feature['feature_id'],
                        'h1': feature['h1'],
                        'h2': feature['h2'],
                        'feature_description': feature['feature_description'],
                        'version': feature['version'],
                        'head': triple[0],
                        'relation': triple[1],
                        'tail': triple[2]
                    })
            except Exception as e:
                logger.error(f"Error processing line: {e}")
    
    # 创建DataFrame并保存为CSV
    df = pd.DataFrame(triples_data)
    df.to_csv(output_file, index=False, encoding='utf-8')
    
    logger.info(f"Exported {len(triples_data)} triples to {output_file}")
    return output_file

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run open triple extraction on features from database')
    parser.add_argument('--batch-size', '-b', type=int, default=100, help='Batch size for processing')
    parser.add_argument('--start-index', '-s', type=int, default=0, help='Start index for processing')
    parser.add_argument('--export-csv', '-e', action='store_true', help='Export triples to CSV after extraction')
    parser.add_argument('--resume', '-r', help='Resume from a previous stats file (.json)')
    parser.add_argument('--start-from', type=int, help='Start from a specific feature index (overrides resume file)')
    parser.add_argument('--results-file', help='Specify an existing results file to append to (for manual resume)')
    
    args = parser.parse_args()
    
    # 处理从特定索引恢复的情况
    if args.start_from is not None:
        print(f"将从索引 {args.start_from} 开始处理...")
        start_index = args.start_from
        resume_file = None
    else:
        start_index = args.start_index
        resume_file = args.resume
    
    # 运行实体提取
    runner = OpenTripleExtractionRunner(
        batch_size=args.batch_size,
        start_index=start_index,
        resume_file=resume_file
    )
    
    # 手动设置结果文件（如果指定）
    if args.results_file and not runner.results_file:
        runner.results_file = args.results_file
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        runner.stats_file = f'output/open_triple_extraction/extraction_stats_{timestamp}.json'
        print(f"将使用现有结果文件: {runner.results_file}")
        print(f"统计信息将保存至: {runner.stats_file}")
    
    result = runner.run_extraction()
    
    # 导出为CSV（如果需要）
    if args.export_csv:
        export_triples_to_csv(result['results_file'])

if __name__ == "__main__":
    main() 