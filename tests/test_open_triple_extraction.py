import sys
from pathlib import Path
import unittest
from prompts.extractTripleOpen import extractTripleOpenPrompt
import json
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))
from utils.deepseek import deepseek
from scripts.entity_extraction_processor import collect_features_with_mentions
from config.pipeline_config import PipelineConfig
from utils.logger import setup_logger
import datetime

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
    
class TestOpenTripleExtraction(unittest.TestCase):
    """进行开放三元组抽取测试，暂无 ground truth"""

    def setUp(self):
        """初始化测试环境"""
        self.logger = setup_logger()
        self.pipeline_config = PipelineConfig()
        self.benchmark_file = "data/mention_extraction_benchmark_short_0407.xlsx"
        self.llm = deepseek()
        # 加载 benchmark 数据
        self.benchmark_features = collect_features_with_mentions(self.benchmark_file)
        self.logger.info(f"Loaded {len(self.benchmark_features)} features with mentions from benchmark")

    def test_open_triple_extraction(self):
        """进行开放三元组抽取"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        feature_results = []
        results_file = f'output/open_triple_extraction/open_triple_extraction_results_{timestamp}.json'

        # 处理每个 feature
        for feature_id, feature_data in self.benchmark_features.items():

            # 准备feature数据
            feature = {
                'feature_id': feature_id,
                'h1': feature_data['h1'],
                'h2': feature_data['h2'],
                'feature_description': feature_data['feature_description'],
                'version': feature_data['version']
            }

            # 执行抽取步骤
            extraction_result = self.extract_open_triples_from_benchmark([feature])
            feature_results.extend(extraction_result)

        # 保存结果
        with open(results_file, "w", encoding='utf-8') as f:
            json.dump(feature_results, f, ensure_ascii=True, indent=4)


    def extract_open_triples_from_benchmark(self, features):
        """
        从基准测试数据中抽取开放关系三元组。

        Args:
            features: list[dict]
        Returns:
            features_output: list[dict]
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
                
                # 构建提示词执行开放关系抽取
                prompt_triple = extractTripleOpenPrompt(
                    feature_description=full_description,
                    h1=h1,
                    h2=h2
                ).format()

                response_triples = self.llm.get_response(prompt_triple)
                object_triples = json.loads(strip_json(response_triples))

                if 'output' in object_triples:
                    object_triples = object_triples['output']

                self.logger.info(f"extracted object_triples={object_triples}")
                feature_extracted = {
                    "feature_id": feature_id,
                    "feature_description": feature_description,
                    "version": version,
                    "triples": object_triples['triples'],
                }

                features_output.append(feature_extracted)
            return features_output
        
        except Exception as e:
            self.logger.error(f"Failed to extract triples from benchmark: {e}")
            raise e
        
if __name__ == '__main__':
    unittest.main()