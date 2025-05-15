import unittest
from unittest.mock import patch, MagicMock
from pipeline.entity_fusion import EntityFusion
from models.entity import Entity
import logging

class TestEntityFusion(unittest.TestCase):
    def setUp(self):
        # 设置日志
        logging.basicConfig(level=logging.INFO, 
                          format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
        
        # 创建 EntityFusion 实例，使用模拟配置
        self.config = {}
        self.fusion = EntityFusion(self.config)
        
        # 模拟 NameHandler
        self.name_handler_mock = MagicMock()
        self.fusion.name_handler = self.name_handler_mock
        
        # 模拟并查集方法
        self.parent = {}
        
        def find_mock(x, *args):
            if x in self.parent and self.parent[x] != x:
                self.parent[x] = find_mock(self.parent[x])
            elif x not in self.parent:
                self.parent[x] = x
            return self.parent[x]
        
        def union_mock(x, y):
            self.parent[find_mock(x)] = find_mock(y)
        
        # 将模拟函数注入到 EntityFusion 类中
        self.original_find = getattr(EntityFusion, 'find', None)
        self.original_union = getattr(EntityFusion, 'union', None)
        EntityFusion.find = find_mock
        EntityFusion.union = union_mock
        
    def tearDown(self):
        # 恢复原始方法
        if self.original_find:
            EntityFusion.find = self.original_find
        else:
            delattr(EntityFusion, 'find')
            
        if self.original_union:
            EntityFusion.union = self.original_union
        else:
            delattr(EntityFusion, 'union')
        
    def test_fusion_pool_preparation(self):
        self.logger.info("======== 测试融合池准备过程 ========")
        
        # 创建测试实体
        linked_entity1 = Entity(name="kvm_vcpu", feature_id=1)
        linked_entity1.id = "linked1"
        linked_entity1.entity_type = "component"
        linked_entity1.external_links = [{"reference_type": "wikidata", "references": ["https://wikidata.org/kvm_vcpu"]}]
        
        linked_entity2 = Entity(name="interrupt_controller", feature_id=2)
        linked_entity2.id = "linked2"
        linked_entity2.entity_type = "component"
        linked_entity2.external_links = [{"reference_type": "wikipedia", "references": ["https://en.wikipedia.org/wiki/Interrupt_controller"]}]
        
        ref_entity1 = Entity(name="kvm_vcpu_block", feature_id=3)
        ref_entity1.id = "ref1"
        ref_entity1.entity_type = "component"
        ref_entity1.external_links = [{"reference_type": "code", "references": ["https://elixir.bootlin.com/linux/v6.12.6/A/ident/kvm_vcpu_block"]}]
        
        # 测试 _prepare_fusion_pool_by_class 方法
        linked_entities = [linked_entity1, linked_entity2]
        entities_with_refs = [ref_entity1]
        
        fusion_pool_by_class = self.fusion._prepare_fusion_pool_by_class(linked_entities, entities_with_refs)
        
        # 验证结果
        self.assertIn("component", fusion_pool_by_class)
        self.assertEqual(len(fusion_pool_by_class["component"]), 3)
        entity_names = [e.name for e in fusion_pool_by_class["component"]]
        self.assertIn("kvm_vcpu", entity_names)
        self.assertIn("interrupt_controller", entity_names)
        self.assertIn("kvm_vcpu_block", entity_names)
        
        # 测试不同实体类别是否正确分类
        entity_other = Entity(name="memory_management", feature_id=4)
        entity_other.id = "other1"
        entity_other.entity_type = "concept"
        entity_other.external_links = [{"reference_type": "wikipedia", "references": ["https://en.wikipedia.org/wiki/Memory_management"]}]
        
        fusion_pool_by_class = self.fusion._prepare_fusion_pool_by_class(
            linked_entities + [entity_other], 
            entities_with_refs
        )
        
        # 验证概念类别是否存在且只包含一个实体
        self.assertIn("concept", fusion_pool_by_class)
        self.assertEqual(len(fusion_pool_by_class["concept"]), 1)
        self.assertEqual(fusion_pool_by_class["concept"][0].name, "memory_management")
        
    def test_prepare_fusion_pool_empty_inputs(self):
        self.logger.info("======== 测试空输入时的融合池准备 ========")
        
        # 测试空输入
        fusion_pool_by_class = self.fusion._prepare_fusion_pool_by_class([], [])
        
        # 验证结果 - 应该返回所有类别的空列表
        for class_name in Entity.ENTITY_TYPES:
            self.assertIn(class_name, fusion_pool_by_class)
            self.assertEqual(len(fusion_pool_by_class[class_name]), 0)
        
    def test_rule_based_fusion(self):
        self.logger.info("======== 测试基于规则的实体融合 ========")
        
        # 创建测试实体
        entity1 = Entity(name="kvm_vcpu", feature_id=1)
        entity1.id = "e1"
        entity1.entity_type = "component"
        
        entity2 = Entity(name="kvm_vcpu_block", feature_id=2)
        entity2.id = "e2"
        entity2.entity_type = "component"
        
        entity3 = Entity(name="process", feature_id=3)
        entity3.id = "e3"
        entity3.entity_type = "concept"
        
        entity4 = Entity(name="processes", feature_id=4)
        entity4.id = "e4"
        entity4.entity_type = "concept"
        
        entity5 = Entity(name="schedule", feature_id=5)
        entity5.id = "e5"
        entity5.entity_type = "operation"
        
        entity6 = Entity(name="scheduling", feature_id=6)
        entity6.id = "e6"
        entity6.entity_type = "operation"
        
        # 设置名称处理器模拟行为
        def check_synonym_side_effect(name1, name2):
            # 模拟 kvm_vcpu 和 kvm_vcpu_block 为同义词
            return (name1 == "kvm_vcpu" and name2 == "kvm_vcpu_block") or (name1 == "kvm_vcpu_block" and name2 == "kvm_vcpu")
        
        def check_abbr_side_effect(name1, name2):
            return False
        
        self.name_handler_mock.check_synonym.side_effect = check_synonym_side_effect
        self.name_handler_mock.check_abbr.side_effect = check_abbr_side_effect
        
        # 设置并查集初始化
        entities = [entity1, entity2, entity3, entity4, entity5, entity6]
        self.parent = {entity.id: entity.id for entity in entities}
        
        # 构建测试数据
        fusion_pool_by_class = {
            "component": [entity1, entity2],
            "concept": [entity3, entity4],
            "operation": [entity5, entity6]
        }
        
        # 测试 _perform_rule_based_fusion 方法
        fusion_groups = self.fusion._perform_rule_based_fusion(fusion_pool_by_class)
        
        # 验证结果
        self.assertEqual(len(fusion_groups), 3)  # 应该有三个融合组
        
        # 检查每个融合组
        for group in fusion_groups:
            entity_names = [e.name for e in group]
            
            if "kvm_vcpu" in entity_names:
                self.assertIn("kvm_vcpu_block", entity_names)
                self.assertEqual(len(group), 2)
            elif "process" in entity_names:
                self.assertIn("processes", entity_names)
                self.assertEqual(len(group), 2)
            elif "schedule" in entity_names:
                self.assertIn("scheduling", entity_names)
                self.assertEqual(len(group), 2)
            else:
                self.fail(f"出现了意外的融合组: {entity_names}")
    
    def test_rule_based_fusion_with_existing_entities(self):
        self.logger.info("======== 测试与已有实体的融合 ========")
        
        # 创建已有实体
        existing_entity = Entity(name="memory_allocation", feature_id=10)
        existing_entity.id = "existing"
        existing_entity.entity_type = "operation"

        existing_entity1 = Entity(name="architectures", feature_id=10)
        existing_entity1.id = "existing1"
        existing_entity1.entity_type = "operation"

        existing_entity2 = Entity(name="si2157", feature_id=10)
        existing_entity2.id = "existing2"
        existing_entity2.entity_type = "operation"
        
        # 在 fusion 对象中设置已有融合实体
        self.fusion.fused_entities_by_class = {
            "component": [],
            "concept": [],
            "operation": [existing_entity, existing_entity1, existing_entity2]
        }
        
        # 创建新实体
        new_entity = Entity(name="memory_allocator", feature_id=20)
        new_entity.id = "new1"
        new_entity.entity_type = "operation"

        new_entity2 = Entity(name="architecture", feature_id=20)
        new_entity2.id = "new2"
        new_entity2.entity_type = "operation"
        
        # 设置名称处理器模拟行为，让new_entity与existing_entity匹配
        def check_synonym_side_effect(name1, name2):
            return (name1 == "memory_allocation" and name2 == "memory_allocator") or \
                   (name1 == "memory_allocator" and name2 == "memory_allocation")
        
        self.name_handler_mock.check_synonym.side_effect = check_synonym_side_effect
        self.name_handler_mock.check_abbr.side_effect = lambda x, y: False
        
        # 设置并查集初始化
        self.parent = {existing_entity.id: existing_entity.id, new_entity.id: new_entity.id}
        
        # 构建测试数据
        fusion_pool_by_class = {
            "component": [],
            "concept": [],
            "operation": [new_entity, new_entity2]
        }
        
        # 测试 _perform_rule_based_fusion 方法
        fusion_groups = self.fusion._perform_rule_based_fusion(fusion_pool_by_class)
        
        # 验证结果
        self.assertEqual(len(fusion_groups), 3)  # 应该有一个融合组
        
        group = fusion_groups[0]
        entity_names = [e.name for e in group]
        self.assertEqual(len(group), 2)
        self.assertIn("memory_allocation", entity_names)
        self.assertIn("memory_allocator", entity_names)
        
        group = fusion_groups[1]
        entity_names = [e.name for e in group]
        self.assertEqual(len(group), 2)
        self.assertIn("architectures", entity_names)
        self.assertIn("architecture", entity_names)
        
        
        # 验证根节点映射关系
        self.assertEqual(self.fusion.find(new_entity.id), self.fusion.find(existing_entity.id))
        
    def test_rule_based_fusion_with_naming_conventions(self):
        self.logger.info("======== 测试命名约定融合 ========")
        
        # 创建使用不同命名约定的实体
        entity1 = Entity(name="memory_manager", feature_id=1)
        entity1.id = "e1"
        entity1.entity_type = "component"
        
        entity2 = Entity(name="MemoryManager", feature_id=2)
        entity2.id = "e2"
        entity2.entity_type = "component"
        
        # 修改 _check_naming_convention_relation 方法的行为
        original_check_naming = self.fusion._check_naming_convention_relation
        
        def patched_check_naming(name1, name2):
            # 模拟 memory_manager 和 MemoryManager 为相同命名约定的变体
            if (name1 == "memory_manager" and name2 == "MemoryManager") or \
               (name1 == "MemoryManager" and name2 == "memory_manager"):
                return True
            return original_check_naming(name1, name2)
        
        # 应用补丁
        self.fusion._check_naming_convention_relation = patched_check_naming
        
        # 设置名称处理器模拟行为，确保其他规则不匹配
        self.name_handler_mock.check_synonym.return_value = False
        self.name_handler_mock.check_abbr.return_value = False
        
        # 设置并查集初始化
        entities = [entity1, entity2]
        self.parent = {entity.id: entity.id for entity in entities}
        
        # 构建测试数据
        fusion_pool_by_class = {
            "component": [entity1, entity2],
            "concept": [],
            "operation": []
        }
        
        # 测试 _perform_rule_based_fusion 方法
        fusion_groups = self.fusion._perform_rule_based_fusion(fusion_pool_by_class)
        
        # 验证结果
        self.assertEqual(len(fusion_groups), 1)  # 应该有一个融合组
        
        group = fusion_groups[0]
        entity_names = [e.name for e in group]
        self.assertEqual(len(group), 2)
        self.assertIn("memory_manager", entity_names)
        self.assertIn("MemoryManager", entity_names)
        
        # 恢复原始方法
        self.fusion._check_naming_convention_relation = original_check_naming
        
    def test_rule_based_fusion_empty_pools(self):
        self.logger.info("======== 测试空融合池 ========")
        
        # 构建空的测试数据
        fusion_pool_by_class = {
            "component": [],
            "concept": [],
            "operation": []
        }
        
        # 测试 _perform_rule_based_fusion 方法
        fusion_groups = self.fusion._perform_rule_based_fusion(fusion_pool_by_class)
        
        # 验证结果
        self.assertEqual(len(fusion_groups), 0)  # 应该没有融合组

if __name__ == "__main__":
    unittest.main()