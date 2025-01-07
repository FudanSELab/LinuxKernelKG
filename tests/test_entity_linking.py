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

class EntityLinkBenchmarkLoader:
    """
    导入 data/entity_link_benchmark.xlsx 中的数据
    """
    def __init__(self, data_file, logger):
        self.data_file = data_file
        self.data = pd.read_excel(self.data_file)
        self.db = DB(PipelineConfig())
        self.logger = logger

        """预处理得到每个实体的 context"""
        contexts = []
        for idx, row in self.data.iterrows():
            feature_id = row['feature_id']
            commit_ids_str = row['commit_ids']
            # 将单引号替换为双引号
            commit_ids_str = commit_ids_str.replace("'", '"')
            try:
                commit_ids = json.loads(commit_ids_str)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON for row {idx}: {e}")
                continue  # 跳过此行，继续处理下一行

            feature_name = self.db.get_features_info([feature_id])[0]
            commits = "\n".join(self.db.get_commits_info(commit_ids))
            context = f"feature_name: {feature_name}\n\n{commits}"
            contexts.append(context)
        
        self.data['context'] = contexts

    def calculate_metric(self, results):
        """
        计算实体链接的指标。分为两部分。第一部分是把能否链接作为一个二分类问题来计算，第二部分是考虑返回的链接本身是否正确。
        对于每个部分，都分开考虑直接链接和部分链接。
        """

        # ol for overall linkable, nl for ngram linkable
        tp_ol, fp_ol, tn_ol, fn_ol = 0, 0, 0, 0
        tp_nl, fp_nl, tn_nl, fn_nl = 0, 0, 0, 0
        # 分类为 true positive 的情况下，链接也正确的数量
        ol_correct, nl_correct = 0, 0

        for i in range(len(self.data)):
            row = self.data.iloc[i]
            gt_overall_linkable = row['overall_linkable']
            gt_overall_wikipedia_link = row['overall_wikipedia_link'] if gt_overall_linkable else None
            gt_ngram_linkable = row['ngram_linkable']
            gt_ngram = json.loads(row['ngram_wikipedia_link'].replace("'", '"')) if gt_ngram_linkable else None
            gt_ngram = [(item['ngram_mention'], item['wikipedia_link']) for item in gt_ngram] if gt_ngram else None

            result = results[i]
            overall_linkable = False
            overall_wikipedia_link = None
            ngram_linkable = False
            ngram_wikipedia_link = None
            ngram_matched_ngram = None

            for match in result['matches']:
                if match['match_type'] == 'primary':
                    overall_linkable = True
                    overall_wikipedia_link = match['wikipedia_url']
                elif match['match_type'] == 'ngram':
                    ngram_linkable = True
                    ngram_wikipedia_link = match['wikipedia_url']
                    ngram_matched_ngram = match['matched_ngram']

            # 1. 直接链接
            if overall_linkable and gt_overall_linkable:
                tp_ol += 1
                if overall_wikipedia_link == gt_overall_wikipedia_link:
                    ol_correct += 1
            elif overall_linkable and not gt_overall_linkable:
                fp_ol += 1
            elif not overall_linkable and not gt_overall_linkable:
                tn_ol += 1
            elif not overall_linkable and gt_overall_linkable:
                fn_ol += 1

            # 2. 部分链接
            if ngram_linkable and gt_ngram_linkable:
                tp_nl += 1
                if (ngram_matched_ngram, ngram_wikipedia_link) in gt_ngram:
                    nl_correct += 1
            elif ngram_linkable and not gt_ngram_linkable:
                fp_nl += 1
            elif not ngram_linkable and not gt_ngram_linkable:
                tn_nl += 1
            elif not ngram_linkable and gt_ngram_linkable:
                fn_nl += 1
        
        # 计算指标

        ol_accuracy = (tp_ol + tn_ol) / (tp_ol + fp_ol + tn_ol + fn_ol) if (tp_ol + fp_ol + tn_ol + fn_ol) > 0 else 0
        ol_precision = tp_ol / (tp_ol + fp_ol) if (tp_ol + fp_ol) > 0 else 0
        ol_recall = tp_ol / (tp_ol + fn_ol) if (tp_ol + fn_ol) > 0 else 0

        nl_accuracy = (tp_nl + tn_nl) / (tp_nl + fp_nl + tn_nl + fn_nl) if (tp_nl + fp_nl + tn_nl + fn_nl) > 0 else 0
        nl_precision = tp_nl / (tp_nl + fp_nl) if (tp_nl + fp_nl) > 0 else 0
        nl_recall = tp_nl / (tp_nl + fn_nl) if (tp_nl + fn_nl) > 0 else 0

        self.logger.info(f"Overall Linkable: tp={tp_ol}, fp={fp_ol}, tn={tn_ol}, fn={fn_ol}")
        self.logger.info(f"Overall Linkable Accuracy: {ol_accuracy:.2f}")
        self.logger.info(f"Overall Linkable Precision: {ol_precision:.2f}")
        self.logger.info(f"Overall Linkable Recall: {ol_recall:.2f}")
        self.logger.info(f"Overall Linkable Correct Count: {ol_correct}")
        self.logger.info(f"Ngram Linkable: tp={tp_nl}, fp={fp_nl}, tn={tn_nl}, fn={fn_nl}")
        self.logger.info(f"Ngram Linkable Accuracy: {nl_accuracy:.2f}")
        self.logger.info(f"Ngram Linkable Precision: {nl_precision:.2f}")
        self.logger.info(f"Ngram Linkable Recall: {nl_recall:.2f}")
        self.logger.info(f"Ngram Linkable Correct Count: {nl_correct}")

async def test_entity_linking(input_file, eval_only=False, result_file=None):
    logger = setup_logger('test_entity_linking', file_output=True)
    config = PipelineConfig()
    
    # 从数据文件中加载测试数据
    loader = EntityLinkBenchmarkLoader(input_file, logger)
    
    if eval_only and result_file:
        logger.info(f"Loading existing results from {result_file}")
        try:
            with open(result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                all_results = data['results']
            logger.info("Calculating metrics for existing results...")
            loader.calculate_metric(all_results)
            return
        except Exception as e:
            logger.error(f"Failed to load results file: {str(e)}")
            return
    
    BATCH_SIZE = 5
    
    # 添加时间戳到文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    output_file = f'output/test/entity_linking_test_results_{timestamp}.json'
    Path('output/test').mkdir(parents=True, exist_ok=True)

    logger.info("Starting entity linking test")

    # 初始化处理器
    processor = EntityProcessor(config)
    
    # 用于存储所有结果
    all_results = []
    
    # 分批处理实体链接
    for i in range(0, len(loader.data), BATCH_SIZE):
        try:
            test_entities = loader.data['original_mention'][i:i+BATCH_SIZE]
            test_context = loader.data['context'][i:i+BATCH_SIZE]
            
            # 修改这部分以正确处理 feature_ids 和 commit_ids
            batch_data = loader.data.iloc[i:i+BATCH_SIZE]
            test_feature_ids = batch_data['feature_id'].tolist()
            test_commit_ids = [
                json.loads(commit_ids_str.replace("'", '"'))
                for commit_ids_str in batch_data['commit_ids']
            ]
            
            logger.info(f"\nProcessing batch {i//BATCH_SIZE + 1}, entities: {test_entities}")
            batch_results = await processor.process_linking_batch(
                test_entities, 
                test_context,
                feature_ids=test_feature_ids,
                commit_ids_list=test_commit_ids
            )
            all_results.extend(batch_results)
            
            # 每个批次完成后立即保存结果
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'input': {
                        'entities': list(loader.data['original_mention']),
                        'context': list(loader.data['context'])
                    },
                    'results': all_results,
                    'completed_batches': (i + BATCH_SIZE) // BATCH_SIZE,
                    'total_batches': len(loader.data) // BATCH_SIZE + 1,
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }, f, ensure_ascii=False, indent=4)
                
        except Exception as e:
            logger.error(f"Test failed at batch {i//BATCH_SIZE + 1}: {str(e)}")
            raise

    # 打印详细结果
    logger.info("\nDetailed Results:")
    for result in all_results:
        # result: {'mention': str, 'matches': {'linked_entity': str, 'match_type': 'primary'|'ngram', ['matched_ngram': str]}, 'total_candicates_count': int}
        mention = result['mention']
        linked_to_primary = None
        confidence_primary = None
        linked_to_ngram = None
        confidence_ngram = None
        matched_ngram = None

        for match in result['matches']:
            if match['match_type'] == 'primary':
                linked_to_primary = match['linked_entity']
                confidence_primary = match['confidence']
            elif match['match_type'] == 'ngram':
                linked_to_ngram = match['linked_entity']
                confidence_ngram = match['confidence']
                matched_ngram = match['matched_ngram']


        # primary link
        if linked_to_primary and confidence_primary:
            logger.info(f"Entity: {mention:25} -> {linked_to_primary:30} (confidence: {confidence_primary:.2f})")
        else:
            logger.info(f"Entity: {mention:25} -> LINKING FAILED")

        # ngram link
        if linked_to_ngram and confidence_ngram:
            logger.info(f"Entity: {mention:25} matched ngram: {matched_ngram} -> {linked_to_ngram:30} (confidence: {confidence_ngram:.2f})")
        else:
            logger.info(f"Entity: {mention:25} -> ngram LINKING FAILED")
        
    # loader.calculate_metric(all_results)

if __name__ == "__main__":
    # 直接设置参数，不再使用命令行参数
    eval_only = False  # 是否只进行评估
    # 如果eval_only为True，这里可以指定结果文件路径
    result_file = 'output/test/entity_linking_test_results_20241227_1723.json'    # 初始版本
    # result_file = 'output/test/entity_linking_test_results_20250104_1525.json'  # 使用srctoolkit
    # result_file = 'output/test/entity_linking_test_results_20250104_2242.json'  # 使用gpt-4omini
    
    
    # input_file = 'data/features_output_20250102.xlsx'  # 测试数据文件路径
    input_file = 'data/entity_link_benchmark_0103.xlsx'

    asyncio.run(test_entity_linking(input_file=input_file, eval_only=eval_only, result_file=result_file))