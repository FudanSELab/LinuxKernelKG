from pyvis.network import Network
import networkx as nx
from neo4j import GraphDatabase
import json

class GraphVisualizer:
    def __init__(self):
        self.net = Network(
            height="750px",
            width="100%",
            bgcolor="#ffffff",
            font_color="black"
        )
        self.net.toggle_physics(True)
        self._setup_options()
    
    def _setup_options(self):
        """设置可视化选项"""
        self.net.set_options("""
        {
          "nodes": {
            "shape": "dot",
            "size": 25,
            "font": {
              "size": 14
            }
          },
          "edges": {
            "font": {
              "size": 12
            },
            "smooth": false
          },
          "physics": {
            "forceAtlas2Based": {
              "gravitationalConstant": -100,
              "springLength": 100
            },
            "minVelocity": 0.75,
            "solver": "forceAtlas2Based"
          }
        }
        """)
    
    def visualize_from_neo4j(self, driver, output_file, query_filter=None):
        """从 Neo4j 数据库创建可视化"""
        output_file = str(output_file)  # Convert Path to string if needed
        
        with driver.session() as session:
            # 构建查询
            query = """
                MATCH (n)-[r]->(m)
                {where_clause}
                RETURN n, r, m
            """
            
            # 添加过滤条件
            where_clause = ""
            if query_filter:
                where_clause = f"WHERE {query_filter}"
            
            query = query.format(where_clause=where_clause)
            
            # 执行查询
            result = session.run(query)
            
            # 处理结果
            for record in result:
                source = record['n']
                target = record['m']
                relation = record['r']
                
                # 添加节点
                self.net.add_node(source.id, 
                                label=source['name'],
                                title=source.get('description', ''),
                                color=self._get_node_color(source))
                                
                self.net.add_node(target.id,
                                label=target['name'],
                                title=target.get('description', ''),
                                color=self._get_node_color(target))
                
                # 添加边
                self.net.add_edge(source.id, target.id,
                                label=relation.type,
                                title=relation.get('description', ''))
        
        # 保存可视化结果
        self.net.save_graph(output_file)
    
    def _get_node_color(self, node):
        """根据节点类型返回颜色"""
        colors = {
            'Concept': '#ff7675',
            'Function': '#74b9ff',
            'Module': '#55efc4',
            'Component': '#ffeaa7'
        }
        return colors.get(node.get('type', 'Concept'), '#ff7675')