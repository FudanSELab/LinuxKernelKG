from openai import OpenAI
from utils.base_llm import BaseLLM
import json
import os
import time

class BatchLLM(BaseLLM):
    def __init__(self, config: dict):
        super().__init__(config)
        self.client = OpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"]
        )
        self.model = config["model"]
        self.completion_window = config.get("completion_window", "24h")
        self.system_prompt = config.get("system_prompt", "You are a helpful assistant")
        self.max_tokens = config.get("max_tokens", 2000)
        self.temperature = config.get("temperature", 0.7)

    def get_response(self, prompt: str) -> str:
        """单个请求的处理方法，不适用于批量处理，仅作为兼容接口"""
        self.logger.warning("BatchLLM is designed for batch processing, not individual requests")
        # 调用普通API以保持兼容性
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )
        return response.choices[0].message.content

    def create_batch_file(self, prompts_list, custom_id_prefix="request", output_file="batch_requests.jsonl"):
        """
        创建批量推理任务的输入文件
        
        Args:
            prompts_list: 提示列表，每个元素是一个字符串
            custom_id_prefix: 自定义ID前缀
            output_file: 输出文件名
        
        Returns:
            输出文件路径
        """
        self.logger.info(f"Creating batch file with {len(prompts_list)} prompts")
        
        with open(output_file, "w") as f:
            for i, prompt in enumerate(prompts_list):
                request = {
                    "custom_id": f"{custom_id_prefix}-{i+1}",
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "stream": False,
                        "max_tokens": self.max_tokens,
                        "temperature": self.temperature
                    }
                }
                f.write(f"{json.dumps(request)}\n")
        
        self.logger.info(f"Batch file created: {output_file}")
        return output_file

    def submit_batch_job(self, input_file_path, job_description="Batch inference job"):
        """
        提交批量推理任务
        
        Args:
            input_file_path: 输入文件路径
            job_description: 任务描述
            
        Returns:
            batch_id: 批量任务ID
        """
        self.logger.info(f"Uploading batch file: {input_file_path}")
        
        # 上传输入文件
        with open(input_file_path, "rb") as f:
            batch_input_file = self.client.files.create(
                file=f,
                purpose="batch"
            )
        
        batch_input_file_id = batch_input_file.id
        self.logger.info(f"File uploaded with ID: {batch_input_file_id}")
        
        # 创建批量推理任务
        batch_job = self.client.batches.create(
            input_file_id=batch_input_file_id,
            endpoint="/v1/chat/completions",
            completion_window=self.completion_window,
            metadata={
                "description": job_description
            },
            extra_body={"replace": {"model": self.model}}
        )
        
        self.logger.info(f"Batch job created with ID: {batch_job.id}")
        return batch_job.id
    
    def check_batch_status(self, batch_id):
        """
        检查批量推理任务状态
        
        Args:
            batch_id: 批量任务ID
            
        Returns:
            batch_status: 批量任务状态信息
        """
        batch = self.client.batches.retrieve(batch_id)
        self.logger.info(f"Batch status: {batch.status}")
        return batch
    
    def cancel_batch_job(self, batch_id):
        """
        取消批量推理任务
        
        Args:
            batch_id: 批量任务ID
        """
        self.client.batches.cancel(batch_id)
        self.logger.info(f"Batch job {batch_id} cancellation requested")
    
    def list_batch_jobs(self):
        """
        获取所有批量推理任务列表
        
        Returns:
            batch_jobs: 批量任务列表
        """
        batch_jobs = self.client.batches.list()
        return batch_jobs
    
    def download_batch_results(self, batch_id, output_dir="./batch_results"):
        """
        下载批量推理结果
        
        Args:
            batch_id: 批量任务ID
            output_dir: 输出目录
            
        Returns:
            results_file_path: 结果文件路径
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        batch = self.client.batches.retrieve(batch_id)
        
        if batch.status != "completed":
            self.logger.warning(f"Batch job {batch_id} is not completed yet. Current status: {batch.status}")
            return None
            
        if not batch.output_file_id:
            self.logger.error(f"No output file available for batch job {batch_id}")
            return None
            
        output_file_path = os.path.join(output_dir, f"{batch_id}_results.jsonl")
        
        # 下载结果文件
        with open(output_file_path, "wb") as f:
            f.write(self.client.files.content(batch.output_file_id).read())
            
        self.logger.info(f"Batch results downloaded to: {output_file_path}")
        return output_file_path
    
    def parse_batch_results(self, results_file_path):
        """
        解析批量推理结果
        
        Args:
            results_file_path: 结果文件路径
            
        Returns:
            results_dict: 结果字典，键为custom_id，值为响应内容
        """
        results = {}
        
        with open(results_file_path, "r") as f:
            for line in f:
                result = json.loads(line)
                custom_id = result.get("custom_id")
                if custom_id and "body" in result and "choices" in result["body"]:
                    content = result["body"]["choices"][0]["message"]["content"]
                    results[custom_id] = content
                    
        return results 