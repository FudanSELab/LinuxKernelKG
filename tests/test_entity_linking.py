import sys
from pathlib import Path
import asyncio
import json
import pandas as pd
from datetime import datetime
import numpy as np

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from config.pipeline_config import PipelineConfig
from pipeline.entity_processor import EntityProcessor
from utils.logger import setup_logger
from utils.db import DB
from models.entity import Entity

class EntityLinkBenchmarkLoader:
    """
    导入 entity_link_benchmark 数据文件中的数据
    """
    def __init__(self, data_file, logger):
        self.data_file = data_file
        self.data = pd.read_excel(self.data_file)
        self.db = DB(PipelineConfig())
        self.logger = logger

        # 预处理数据，填充空值
        self._preprocess_data()
        
        # 检查数据格式并适配新的字段
        self._adapt_data_format()

        """预处理得到每个实体的 context"""
        contexts = []
        for idx, row in self.data.iterrows():
            # 直接从表格中获取信息，不通过数据库
            # 添加h1和h2到上下文
            h1 = row.get('h1', "")
            h2 = row.get('h2', "")
            
            feature_id = row.get('feature_id', "")
            # 添加feature_description到上下文
            feature_description = row.get('feature_description', "")
            
            # 构建上下文
            context_parts = []
            if feature_id and not pd.isna(feature_id):
                context_parts.append(f"feature_id: {feature_id}")
            if h1 and not pd.isna(h1):
                context_parts.append(f"h1: {h1}")
            if h2 and not pd.isna(h2):
                context_parts.append(f"h2: {h2}")
            if feature_description and not pd.isna(feature_description):
                context_parts.append(f"feature_description: {feature_description}")
            
            # 添加代码和文档引用
            code_reference = row.get('reference(code)', "")
            doc_reference = row.get('reference(doc)', "")
            
            if code_reference and not pd.isna(code_reference):
                context_parts.append(f"code_reference: {code_reference}")
            if doc_reference and not pd.isna(doc_reference):
                context_parts.append(f"doc_reference: {doc_reference}")
            
            # 添加描述信息
            # description = row.get('descripition', "")  # 注意原始字段名可能有拼写错误
            # if description and not pd.isna(description):
            #     context_parts.append(f"description: {description}")
            
            context = "\n\n".join(context_parts)
            contexts.append(context)
        
        self.data['context'] = contexts

    def _preprocess_data(self):
        """
        预处理数据，填充空值
        对于分组数据，将第一行的信息向下填充到同一组的其他行
        """
        # 获取所有列名
        columns = self.data.columns.tolist()
        
        # 需要向下填充的列（除了mention相关的列）
        fill_columns = [col for col in columns if col not in ['mention_id', 'mention', 'wikipedia_link']]
        
        # 向下填充空值
        self.data[fill_columns] = self.data[fill_columns].fillna(method='ffill')
        
        self.logger.info("预处理数据完成，已填充空值")

    def _adapt_data_format(self):
        """适配新的数据格式"""
        # 检查并映射必要的字段
        field_mapping = {
            'mention': 'original_mention',
            'wikipedia_link': 'overall_wikipedia_link'
        }
        
        # 添加必要的字段
        for new_field, old_field in field_mapping.items():
            if new_field in self.data.columns and old_field not in self.data.columns:
                self.data[old_field] = self.data[new_field]
        
        # 如果没有overall_linkable字段，根据wikipedia_link创建
        if 'overall_linkable' not in self.data.columns and 'wikipedia_link' in self.data.columns:
            self.data['overall_linkable'] = self.data['wikipedia_link'].notna() & (self.data['wikipedia_link'] != '')
        
        # 如果没有ngram相关字段，添加默认值
        if 'ngram_linkable' not in self.data.columns:
            self.data['ngram_linkable'] = False
        
        if 'ngram_wikipedia_link' not in self.data.columns:
            self.data['ngram_wikipedia_link'] = '[]'
        
        # 确保commit_ids字段存在
        if 'commit_ids' not in self.data.columns:
            self.data['commit_ids'] = '[]'
            
        self.logger.info(f"Adapted data format. Available columns: {self.data.columns.tolist()}")

    def calculate_metric(self, results):
        """
        计算实体链接的指标。将能否链接作为一个二分类问题来计算，同时考虑返回的链接本身是否正确。
        首先匹配mention名称，然后基于匹配结果评估链接准确性。
        
        Args:
            results: 可以是Entity对象列表或已格式化的结果字典列表
        """

        # 统计指标
        tp_ol = 0  # 正确预测有链接，且链接URL正确
        fp_ol = 0  # 错误预测有链接，或链接URL不正确
        tn_ol = 0  # 正确预测无链接
        fn_ol = 0  # 错误预测无链接
        
        # 用于存储已处理的mention
        processed_mentions = set()
        
        # 处理结果列表，将Entity对象转换为标准格式
        processed_results = {}  # 使用字典以便按mention名称查找
        for result in results:
            if isinstance(result, Entity):
                # 从Entity对象提取信息
                mention = result.name.lower()
                processed_result = {'mention': mention, 'matches': []}
                
                # 提取主链接
                for link in result.external_links:
                    if link.get('url_type') == 'wikipedia' and link.get('url'):
                        processed_result['matches'].append({
                            'wikipedia_url': link['url'][0]
                        })
                
                processed_results[mention] = processed_result
            else:
                # 如果已经是字典格式，直接添加
                mention = result.get('mention', '').lower()
                if mention:
                    processed_results[mention] = result
        
        # 遍历数据集中的每个mention
        for i in range(len(self.data)):
            row = self.data.iloc[i]
            gt_mention = row.get('original_mention', '').lower()
            if not gt_mention or pd.isna(gt_mention):
                continue
                
            # 检查该mention是否已处理
            if gt_mention in processed_mentions:
                continue
                
            processed_mentions.add(gt_mention)
            
            gt_overall_linkable = row['overall_linkable']
            gt_overall_wikipedia_link = row['overall_wikipedia_link'] if gt_overall_linkable else None

            # 在处理结果中查找对应的mention
            result = processed_results.get(gt_mention)
            
            if result:
                # 找到了对应的mention，评估链接结果
                overall_linkable = False
                overall_wikipedia_link = None

                for match in result.get('matches', []):
                    if 'wikipedia_url' in match:
                        overall_linkable = True
                        overall_wikipedia_link = match['wikipedia_url']
                        break

                # 评估链接结果
                if overall_linkable and gt_overall_linkable:
                    # 比较链接时需要标准化URL，移除可能的尾部斜杠和协议差异
                    # predicted_url = self._normalize_url(overall_wikipedia_link)
                    # ground_truth_url = self._normalize_url(gt_overall_wikipedia_link)
                    # if predicted_url == ground_truth_url:
                    #     tp_ol += 1
                    # else:
                    #     # 有链接但URL不匹配，算作FP
                    #     fp_ol += 1
                    tp_ol += 1
                else:
                    fp_ol += 1
            else:
                # 未找到对应的mention
                if gt_overall_linkable:
                    # 数据集中有链接但未找到结果，算作FN
                    fn_ol += 1
                else:
                    # 数据集中无链接且未找到结果，算作TN
                    tn_ol += 1
        
        # 计算指标
        total = tp_ol + fp_ol + tn_ol + fn_ol
        ol_accuracy = (tp_ol + tn_ol) / total if total > 0 else 0
        ol_precision = tp_ol / (tp_ol + fp_ol) if (tp_ol + fp_ol) > 0 else 0
        ol_recall = tp_ol / (tp_ol + fn_ol) if (tp_ol + fn_ol) > 0 else 0
        f1_score = 2 * (ol_precision * ol_recall) / (ol_precision + ol_recall) if (ol_precision + ol_recall) > 0 else 0

        self.logger.info(f"\n===== 共评估 {total} 个实体 =====")
        self.logger.info(f"链接评估: tp={tp_ol}, fp={fp_ol}, tn={tn_ol}, fn={fn_ol}")
        self.logger.info(f"链接准确率(Accuracy): {ol_accuracy:.2f}")
        self.logger.info(f"链接精确度(Precision): {ol_precision:.2f}")
        self.logger.info(f"链接召回率(Recall): {ol_recall:.2f}")
        self.logger.info(f"F1分数: {f1_score:.2f}")
        self.logger.info(f"链接正确数量: {tp_ol} (占总样本 {total} 的 {tp_ol/total*100:.1f}%)")

    def _normalize_url(self, url):
        """标准化URL，移除可能的尾部斜杠和协议差异"""
        if url:
            # 移除尾部斜杠
            url = url.rstrip('/')
            # 移除协议差异
            url = url.split('//')[1] if '//' in url else url
        return url

def entity_to_dict(entity):
    """将Entity对象转换为可JSON序列化的字典"""
    result = {'mention': entity.name, 'matches': []}
    
    # 添加Wikipedia链接
    for link in entity.external_links:
        if link.get('url_type') == 'wikipedia' and link.get('url'):
            result['matches'].append({
                'wikipedia_url': link['url'][0]
            })
    
    return result

async def test_entity_linking(input_file, eval_only=False, result_file=None, previous_result_file=None):
    logger = setup_logger('test_entity_linking', file_output=True)
    config = PipelineConfig()
    
    # 从数据文件中加载测试数据
    loader = EntityLinkBenchmarkLoader(input_file, logger)
    
    # 先过滤掉 mention 为 NaN 的行
    valid_data = loader.data[~pd.isna(loader.data['original_mention'])]
    logger.info(f"过滤前数据行数: {len(loader.data)}, 过滤后数据行数: {len(valid_data)}")
    loader.data = valid_data  # 更新为有效数据
    
    if eval_only and result_file:
        logger.info(f"Loading existing results from {result_file}")
        
        with open(result_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            all_results = data['results']
        logger.info("Calculating metrics for existing results...")
        loader.calculate_metric(all_results)
        return
     
    # 加载已处理的mention（如果提供了previous_result_file）
    processed_mentions = set()
    processed_results = []
    # 创建结果字典，以mention为键，结果对象为值
    result_dict = {}
    
    if previous_result_file and Path(previous_result_file).exists():
        logger.info(f"Loading previously processed mentions from {previous_result_file}")
        try:
            with open(previous_result_file, 'r', encoding='utf-8') as f:
                previous_data = json.load(f)
                for result in previous_data.get('results', []):
                    mention = result.get('mention', '').lower()
                    if mention:
                        processed_mentions.add(mention)
                        processed_results.append(result)
                        result_dict[mention] = result
            logger.info(f"Loaded {len(processed_mentions)} previously processed mentions")
        except Exception as e:
            logger.error(f"Error loading previous results: {str(e)}")
            # 继续执行，不中断流程
     
    BATCH_SIZE = 5
    
    # 添加时间戳到文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H')
    output_file = f'output/test/linking_test/entity_linking_test_results_{timestamp}.json'
    Path('output/test/linking_test').mkdir(parents=True, exist_ok=True)

    logger.info("Starting entity linking test")

    # 初始化处理器
    processor = EntityProcessor(config)
    
    # 用于存储所有结果
    all_results = []
    # 用于存储格式化后的结果
    formatted_results = processed_results.copy() if processed_results else []
    
    # 记录跳过的实体数
    skipped_count = 0
    
    # 分批处理实体链接
    for i in range(0, len(loader.data), BATCH_SIZE):
        try:
            batch_data = loader.data.iloc[i:i+BATCH_SIZE]
            
            # 创建 Entity 对象列表
            batch_entities = []
            for _, row in batch_data.iterrows():
                # 检查该mention是否已处理过
                mention = row.get('original_mention', '').lower()
                if mention in processed_mentions:
                    skipped_count += 1
                    continue
                    
                # 确保 feature_id 是整数，处理可能的 NaN 或 float
                feature_id = row.get('feature_id')
                if pd.isna(feature_id):
                    # 或者设置一个默认值，或者跳过？根据业务逻辑决定
                    # 这里暂时跳过 feature_id 为空的行，或者你可以抛出错误或设置默认值
                    logger.warning(f"Skipping row due to missing feature_id: {row.get('original_mention')}")
                    continue  # 或者 feature_id = -1 或其他默认值
                try:
                    feature_id_int = int(feature_id)
                except (ValueError, TypeError):
                    logger.warning(f"Could not convert feature_id '{feature_id}' to int for mention: {row.get('original_mention')}. Skipping.")
                    continue

                entity = Entity(
                    name=row['original_mention'],
                    feature_id=feature_id_int,
                    # 可以根据需要添加其他属性，例如 description, aliases 等
                    # description=row.get('description', ''),
                    # aliases=json.loads(row.get('aliases', '[]')) if pd.notna(row.get('aliases')) else []
                )
                entity.set_context(row['h1'],row['h2'],row['feature_description'])
                batch_entities.append(entity)
                
            if not batch_entities: # 如果这个批次的所有行都被跳过了
                logger.warning(f"Batch {i//BATCH_SIZE + 1} is empty after filtering missing/invalid feature_ids.")
                continue

            logger.info(f"\nProcessing batch {i//BATCH_SIZE + 1}, entities: {[e.name for e in batch_entities]}")
            # 调用更新后的接口
            batch_results = await processor.process_linking_batch(batch_entities)
            
            all_results.extend(batch_results)
            
            # 转换当前批次的结果并添加到格式化结果列表
            batch_formatted = []
            for result in batch_results:
                if isinstance(result, Entity):
                    formatted_result = {'mention': result.name, 'matches': []}
                    
                    # 添加主链接
                    for link in result.external_links:
                        if link.get('url_type') == 'wikipedia':
                            urls = link.get('url', [])
                            if urls:
                                primary_match = {
                                    'wikipedia_url': urls[0],
                                }
                                formatted_result['matches'].append(primary_match)
                    
                    batch_formatted.append(formatted_result)
                    # 添加到结果字典
                    result_dict[formatted_result['mention'].lower()] = formatted_result
                else:
                    # 如果已经是字典格式，直接添加
                    batch_formatted.append(result)
                    if 'mention' in result:
                        result_dict[result['mention'].lower()] = result
            
            formatted_results.extend(batch_formatted)
            
            # 每批处理完成后立即计算一次指标
            logger.info("\n================ 批次指标计算 ================")
            # 直接使用batch_results (Entity对象列表) 进行指标计算
            loader.calculate_metric(batch_results)
            
            # 按照原始数据顺序重新生成结果列表
            ordered_results = []
            # 创建已处理的mention集合，避免重复
            processed_for_order = set()
            
            # 遍历loader.data获取原始顺序
            for _, row in loader.data.iterrows():
                mention = row.get('original_mention', '').lower()
                if mention and mention not in processed_for_order and mention in result_dict:
                    ordered_results.append(result_dict[mention])
                    processed_for_order.add(mention)
            
            # 添加任何可能未包含在loader.data中但已处理的mention
            for mention, result in result_dict.items():
                if mention not in processed_for_order:
                    ordered_results.append(result)
                    processed_for_order.add(mention)
            
            # 每个批次完成后立即保存结果
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'input': {
                        'entities': list(loader.data['original_mention']),
                        'context': list(loader.data['context'])
                    },
                    'results': ordered_results,
                    'completed_batches': (i + BATCH_SIZE) // BATCH_SIZE,
                    'total_batches': len(loader.data) // BATCH_SIZE + 1,
                    'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'skipped_mentions': skipped_count
                }, f, ensure_ascii=False, indent=4)
                
        except Exception as e:
            logger.error(f"Test failed at batch {i//BATCH_SIZE + 1}: {str(e)}")
            raise

    # 打印详细结果
    logger.info("\nDetailed Results:")
    for result in all_results:
        # 假设 result 现在是一个 Entity 对象
        if isinstance(result, Entity):
            mention = result.name
            linked_to = None

            # 从Entity的external_links中提取Wikipedia链接
            for link in result.external_links:
                if link.get('url_type') == 'wikipedia':
                    urls = link.get('url', [])
                    if urls:
                        linked_to = urls[0]
                        break

        # 打印结果
        if linked_to:
            logger.info(f"Entity: {mention:25} -> {linked_to:30}")
        else:
            logger.info(f"Entity: {mention:25} -> LINKING FAILED")
    
    # 显示跳过的实体数量
    if skipped_count > 0:
        logger.info(f"\n跳过了 {skipped_count} 个已处理的mention")
    
    # 最终结果计算 (此时已经完成了每批次的实时计算)
    logger.info("\n================ 最终指标计算 ================")
    # 使用all_results (Entity对象列表) 进行最终指标计算
    loader.calculate_metric(all_results)

if __name__ == "__main__":
    # 直接设置参数，不再使用命令行参数
    eval_only = True  # 是否只进行评估
    # 如果eval_only为True，这里可以指定结果文件路径
    result_file = 'output/test/linking_test/entity_linking_test_results_20250508_14.json'    # 初始版本
    # result_file = 'output/test/entity_linking_test_results_20250104_1525.json'  # 使用srctoolkit
    # result_file = 'output/test/entity_linking_test_results_20250104_2242.json'  # 使用gpt-4omini
    
    # 添加已有的结果文件，用于跳过已处理的mention
    previous_result_file = 'output/test/linking_test/entity_linking_test_results_20250508_11.json'
    
    # input_file = 'data/features_output_20250102.xlsx'  # 测试数据文件路径
    input_file = 'data/mention_extraction_benchmark_0428.xlsx'

    asyncio.run(test_entity_linking(input_file=input_file, eval_only=eval_only, result_file=result_file, previous_result_file=previous_result_file))