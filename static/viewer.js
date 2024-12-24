class GraphViewer {
    constructor() {
        this.network = null;
        this.currentFileId = null;
        this.init();
    }

    async init() {
        await this.loadFileList();
        this.initNetwork();
    }

    async loadFileList() {
        try {
            const response = await fetch('/api/files');
            const files = await response.json();
            console.log('Available files:', files);
            
            const fileList = document.getElementById('file-list');
            fileList.innerHTML = files.map(file => `
                <div class="file-item" data-id="${file.id}">
                    ${file.filename}
                </div>
            `).join('');

            fileList.addEventListener('click', (e) => {
                const fileItem = e.target.closest('.file-item');
                if (fileItem) {
                    this.loadGraph(fileItem.dataset.id);
                    document.querySelectorAll('.file-item').forEach(item => {
                        item.classList.remove('active');
                    });
                    fileItem.classList.add('active');
                }
            });

            // 自动加载第一个文件
            if (files.length > 0) {
                this.loadGraph(files[0].id);
                fileList.querySelector('.file-item').classList.add('active');
            }
        } catch (error) {
            console.error('Error loading file list:', error);
        }
    }

    initNetwork() {
        const container = document.getElementById('mynetwork');
        const options = {
            nodes: {
                shape: "dot",
                size: 20,
                font: {
                    size: 14,
                    face: 'Arial'
                },
                borderWidth: 2,
                shadow: true
            },
            edges: {
                width: 2,
                color: {
                    inherit: 'both'
                },
                smooth: {
                    type: 'continuous'
                }
            },
            physics: {
                stabilization: {
                    iterations: 100
                },
                barnesHut: {
                    gravitationalConstant: -80000,
                    centralGravity: 0.3,
                    springLength: 200,
                    springConstant: 0.05,
                    damping: 0.09,
                    avoidOverlap: 0.1
                }
            }
        };
        this.network = new vis.Network(container, { nodes: [], edges: [] }, options);
    }

    async loadGraph(fileId) {
        try {
            console.log(`Loading graph for file ID: ${fileId}`);
            const response = await fetch(`/api/graph/${fileId}`);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Received data:', data);
            
            if (!Array.isArray(data)) {
                console.error('Expected array of linking data, received:', typeof data);
                return;
            }
            
            // 处理数据，创建节点和边
            const { nodes, edges } = this.processGraphData(data);
            console.log(`Processed ${nodes.length} nodes and ${edges.length} edges`);
            
            // 更新网络图
            if (nodes.length === 0) {
                console.warn('No nodes to display');
                return;
            }
            
            this.network.setData({
                nodes: new vis.DataSet(nodes),
                edges: new vis.DataSet(edges)
            });
        } catch (error) {
            console.error('Error loading graph:', error);
        }
    }

    processGraphData(data) {
        const nodes = new Set();
        const edges = [];
        const colors = {
            'mention': '#ff7675',    // 原始提及
            'wiki': '#55efc4'        // 维基百科实体
        };

        console.log('Processing data:', data);

        // 处理 linking 数组
        data.forEach(item => {
            console.log('Processing item:', item);
            
            if (item.mention) {
                // 添加mention节点
                nodes.add({
                    id: item.mention,
                    label: item.mention,
                    color: colors.mention,
                    title: `Mention: ${item.mention}`
                });

                // 如果有linked_entity，添加实体节点和边
                if (item.linked_entity) {
                    nodes.add({
                        id: item.linked_entity,
                        label: item.linked_entity,
                        color: colors.wiki,
                        title: item.wikipedia_url || item.linked_entity,
                        url: item.wikipedia_url
                    });

                    edges.push({
                        from: item.mention,
                        to: item.linked_entity,
                        label: 'links_to',
                        title: `Confidence: ${item.confidence.toFixed(2)}`,
                        width: Math.max(1, item.confidence * 3)
                    });
                }
            }
        });

        const nodesArray = Array.from(nodes);
        console.log('Created nodes:', nodesArray);
        console.log('Created edges:', edges);

        return {
            nodes: nodesArray,
            edges: edges
        };
    }
}

// 初始化查看器
document.addEventListener('DOMContentLoaded', () => {
    new GraphViewer();
}); 