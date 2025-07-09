#!/bin/bash

# Wikipedia API 优化测试脚本
# 用于快速验证429错误是否得到解决

echo "=================================================="
echo "Wikipedia API 优化测试"
echo "=================================================="

# 检查Python环境
echo "检查Python环境..."
python3 --version
if [ $? -ne 0 ]; then
    echo "错误: 未找到Python 3"
    exit 1
fi

# 创建日志目录
mkdir -p logs

echo ""
echo "选择测试类型:"
echo "1. 网络连接测试 (检查Wikipedia API访问)"
echo "2. 快速测试 (2个实体，约1-2分钟)"
echo "3. 完整测试 (多个测试，约10-15分钟)"
echo "4. 示例演示 (演示优化功能)"
echo ""

read -p "请输入选择 (1-4): " choice

case $choice in
    1)
        echo "运行网络连接测试..."
        python3 scripts/test_network_connectivity.py
        echo ""
        echo "如果网络连接测试失败，请："
        echo "1. 检查网络设置和代理配置"
        echo "2. 确保可以访问Wikipedia"
        echo "3. 必要时设置HTTP_PROXY和HTTPS_PROXY环境变量"
        ;;
    2)
        echo "运行快速测试..."
        echo "注意: 如果遇到连接超时，请先运行网络连接测试(选项1)"
        python3 scripts/quick_test_wikipedia.py
        ;;
    3)
        echo "运行完整测试..."
        echo "注意: 如果遇到连接超时，请先运行网络连接测试(选项1)"
        python3 tests/test_wikipedia_rate_limiting.py
        ;;
    4)
        echo "运行示例演示..."
        echo "注意: 如果遇到连接超时，请先运行网络连接测试(选项1)"
        python3 examples/entity_linking_rate_limited.py
        ;;
    *)
        echo "无效选择，运行网络连接测试..."
        python3 scripts/test_network_connectivity.py
        ;;
esac

echo ""
echo "=================================================="
echo "测试完成！"
echo ""
echo "如果遇到网络连接问题："
echo "  python3 scripts/test_network_connectivity.py"
echo ""
echo "查看详细日志："
echo "  tail -f logs/entity_linker.log"
echo ""
echo "检查429错误："
echo "  grep '429' logs/entity_linker.log"
echo ""
echo "查看连接超时错误："
echo "  grep 'timeout' logs/entity_linker.log"
echo ""
echo "查看测试指南："
echo "  cat TESTING_GUIDE.md"
echo "==================================================" 