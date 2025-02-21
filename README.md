# LinuxKernelKG

运行时需要把项目目录添加到环境变量 `PYTHONPATH`。例如 windows cmd 下：`set PYTHONPATH=%CD%;%PYTHONPATH%`

运行时确保ide能够连接外网，因为过程中会访问wikipedia、bootlin等国外网站。

通过修改knowledge_graph.py文件中的self.fixed_entities来修改需要验证的概念。
