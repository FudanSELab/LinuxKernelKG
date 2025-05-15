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
from prompts.ngramClassifyRelation import ngramClassifyRelationPrompt
from utils.deepseek import deepseek
from utils.utils import strip_json

class TripleClassifer:
    
    def __init__(self, input_file, batch_size=10):
        self.input_file = input_file
        self.batch_size = batch_size
        self.logger = setup_logger("TripleClassifer")
        self.llm = deepseek()
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")

    def classify_triples(self):
        # 读取输入文件
        with open(self.input_file, 'r', encoding='utf-8') as f:
            # data: list[[str, str]]
            data = json.load(f)
        
        # 处理数据
        results = []
        for i in range(0, len(data), self.batch_size):
            batch = data[i:i + self.batch_size]
            prompt = ngramClassifyRelationPrompt(input=batch).format()
            self.logger.info(f"Processing batch {i // self.batch_size + 1} / {len(data) // self.batch_size + 1}:")
            response = self.llm.get_response(prompt)
            classify_result = json.loads(strip_json(response))
            if type(classify_result) == dict and "output" in classify_result:
                classify_result = classify_result["output"]
            concatenated_result = list(zip(batch, classify_result))
            self.logger.info(f"Batch {i // self.batch_size + 1} results: {concatenated_result}")
            results.extend(concatenated_result)
            
            # 保存结果
            output_file = f"output/open_triple_extraction/classification_results_{self.timestamp}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=4)
        
        self.logger.info(f"Results saved to {output_file}")

if __name__ == "__main__":
    input_file = "data/open_triple_extraction/head&tail_20250424.json"
    classifier = TripleClassifer(input_file)
    classifier.classify_triples()