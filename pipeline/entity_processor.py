from utils.logger import setup_logger
from pipeline.entity_linker import EntityLinker
from pipeline.entity_fusion import EntityFusion

class EntityProcessor:
    def __init__(self, config):
        self.logger = setup_logger('entity_processor')
        self.config = config
        self.entity_linker = EntityLinker(config)
        self.entity_fusion = EntityFusion(config)

    async def process_linking_batch(self, entities):
        results = []
        for entity in entities:
            result = await self.entity_linker.link_entity(entity)
            results.append(result)
        return results

    async def process_fusion(self, new_entities):
        return await self.entity_fusion.process_fusion(new_entities)