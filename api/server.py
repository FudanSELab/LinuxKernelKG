from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import json
from pathlib import Path
from typing import List, Dict
import uvicorn
import logging

# 添加日志配置
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 获取输出目录中的所有JSON文件
def get_available_files() -> List[Dict]:
    output_dir = Path("output")
    json_files = list(output_dir.glob("kg_results_*.json"))
    # 添加日志
    logger.debug(f"Found {len(json_files)} files in output directory")
    return [
        {
            "id": i,
            "filename": f.name,
            "timestamp": f.stem.split("_")[2:4],
            "path": str(f)
        }
        for i, f in enumerate(sorted(json_files, key=lambda x: x.stat().st_mtime, reverse=True))
    ]

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("static/index.html") as f:
        return f.read()

@app.get("/api/files")
async def get_files():
    return get_available_files()

@app.get("/api/graph/{file_id}")
async def get_graph(file_id: int):
    files = get_available_files()
    if not files or file_id >= len(files):
        raise HTTPException(status_code=404, detail="File not found")
    
    file_path = files[file_id]["path"]
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 直接返回linking数组
            linking_data = data.get('linking', [])
            logger.debug(f"Loaded {len(linking_data)} linking entries from {file_path}")
            return linking_data
    except Exception as e:
        logger.error(f"Error reading file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 