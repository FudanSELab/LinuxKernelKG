#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Entity Linking Database Demo

This script demonstrates how to use the new MySQL database storage functionality
for entity linking. It shows both the basic usage and advanced features.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from database.mysql_manager import MySQLManager
from config.pipeline_config import PipelineConfig
from models.entity import Entity

async def demo_database_operations():
    """Demonstrate database operations for entity linking"""
    
    print("🚀 Entity Linking Database Demo")
    print("=" * 50)
    
    # Initialize database manager
    print("\n1️⃣ Initializing Database Manager...")
    db_manager = MySQLManager(PipelineConfig)
    
    # Test connection
    print("\n2️⃣ Testing Database Connection...")
    if not db_manager.test_connection():
        print("❌ Database connection failed!")
        return False
    print("✅ Database connection successful!")
    
    # Show current database status
    print("\n3️⃣ Current Database Status...")
    last_feature_id = db_manager.get_last_processed_feature_id()
    print(f"📊 Last processed feature_id: {last_feature_id}")
    
    if last_feature_id is not None:
        count = db_manager.get_entity_count_by_feature_id(last_feature_id)
        print(f"📊 Entity count for feature_id {last_feature_id}: {count}")
    
    # Create sample entities
    print("\n4️⃣ Creating Sample Entities...")
    
    # Entity 1: Basic entity
    entity1 = Entity(
        name="Linux Kernel",
        feature_id=999991,
        description="The Linux kernel is a free and open-source, monolithic, modular, multitasking, Unix-like operating system kernel."
    )
    entity1.add_external_link('wikipedia', ['https://en.wikipedia.org/wiki/Linux_kernel'])
    entity1.set_context_by_feature_description("Core kernel functionality")
    
    # Entity 2: Entity with aliases
    entity2 = Entity(
        name="TCP",
        feature_id=999991,
        description="Transmission Control Protocol is one of the main protocols of the Internet protocol suite."
    )
    entity2.add_alias("Transmission Control Protocol")
    entity2.add_alias("TCP/IP")
    entity2.add_external_link('wikipedia', ['https://en.wikipedia.org/wiki/Transmission_Control_Protocol'])
    entity2.set_context_by_feature_description("Network protocol implementation")
    
    # Entity 3: Entity with multiple aliases
    entity3 = Entity(
        name="USB",
        feature_id=999992,
        description="Universal Serial Bus is an industry standard that establishes specifications for cables and connectors."
    )
    entity3.add_alias("Universal Serial Bus")
    entity3.add_alias("USB Interface")
    entity3.add_alias("USB Port")
    entity3.add_external_link('wikipedia', ['https://en.wikipedia.org/wiki/USB'])
    entity3.set_context_by_feature_description("Hardware interface support")
    
    sample_entities = [entity1, entity2, entity3]
    
    print(f"📝 Created {len(sample_entities)} sample entities:")
    for i, entity in enumerate(sample_entities, 1):
        print(f"   {i}. {entity.name} (feature_id: {entity.feature_id})")
        if entity.aliases:
            print(f"      Aliases: {', '.join(entity.aliases)}")
    
    # Insert entities (Demo only - using high feature_ids to avoid conflicts)
    print("\n5️⃣ Inserting Sample Entities into Database...")
    results = db_manager.insert_entities_batch(sample_entities)
    
    successful_insertions = 0
    for entity, eid in results:
        if eid is not None:
            print(f"✅ Inserted '{entity.name}' with eid: {eid}")
            successful_insertions += 1
        else:
            print(f"⚠️  Failed to insert or already exists: '{entity.name}'")
    
    print(f"\n📊 Summary: {successful_insertions}/{len(sample_entities)} entities successfully processed")
    
    # Show updated database status
    print("\n6️⃣ Updated Database Status...")
    new_last_feature_id = db_manager.get_last_processed_feature_id()
    print(f"📊 New last processed feature_id: {new_last_feature_id}")
    
    # Count entities by feature_id for our demo data
    for feature_id in [999991, 999992]:
        count = db_manager.get_entity_count_by_feature_id(feature_id)
        if count > 0:
            print(f"📊 Entity count for feature_id {feature_id}: {count}")
    
    print("\n🎉 Demo completed successfully!")
    print("\n" + "=" * 50)
    print("📚 What we demonstrated:")
    print("• Database connection and testing")
    print("• Entity creation with descriptions and aliases") 
    print("• Batch insertion with duplicate checking")
    print("• Resume capability (tracking last processed feature_id)")
    print("• Error handling and logging")
    print("\n💡 Next steps:")
    print("• Run the full entity linking pipeline with:")
    print("  python scripts/run_entity_link_db.py")
    print("• Monitor the process with database queries")
    print("• Use --resume flag to continue from where you left off")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(demo_database_operations())
    sys.exit(0 if success else 1) 