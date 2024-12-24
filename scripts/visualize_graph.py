import sys
from pathlib import Path
import argparse

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from utils.neo4j_handler import EnhancedNeo4jHandler, KnowledgeGraphConfig
from visualization.graph_visualizer import GraphVisualizer
from utils.logger import setup_logger

def visualize_knowledge_graph(output_file=None, query_filter=None):
    """
    从Neo4j数据库生成知识图谱可视化
    
    Args:
        output_file: 输出HTML文件路径，默认为当前时间戳
        query_filter: 可选的查询过滤条件
    """
    logger = setup_logger()
    logger.info("Starting knowledge graph visualization")
    
    # 初始化配置
    kg_config = KnowledgeGraphConfig()
    
    # 设置默认输出文件
    if output_file is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = Path("output") / f"knowledge_graph_{timestamp}.html"
    else:
        output_file = Path(output_file)
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # 初始化Neo4j处理器
        neo4j_handler = EnhancedNeo4jHandler(**kg_config.neo4j_config)
        
        # 初始化可视化器
        visualizer = GraphVisualizer()
        
        # 从Neo4j获取数据并创建可视化
        visualizer.visualize_from_neo4j(
            neo4j_handler.driver,
            output_file,
            query_filter
        )
        
        logger.info(f"Knowledge graph visualization saved to {output_file}")
        
    except Exception as e:
        logger.error(f"Visualization failed: {str(e)}")
        raise
    finally:
        neo4j_handler.close()

def main():
    parser = argparse.ArgumentParser(description='Generate knowledge graph visualization')
    parser.add_argument('--output', '-o', help='Output HTML file path')
    parser.add_argument('--filter', '-f', help='Query filter (e.g., entity type)')
    
    args = parser.parse_args()
    visualize_knowledge_graph(args.output, args.filter)

if __name__ == "__main__":
    main() 