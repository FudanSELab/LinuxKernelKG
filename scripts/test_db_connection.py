#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Database Connection Test Script

This script tests the MySQL database connection and basic operations
for the entity linking database storage functionality.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.mysql_manager import MySQLManager
from config.pipeline_config import PipelineConfig
from models.entity import Entity
import logging

def test_database_connection():
    """Test database connection and basic operations"""
    print("🔄 Testing MySQL database connection...")
    
    try:
        # Initialize database manager
        db_manager = MySQLManager(PipelineConfig)
        
        # Test basic connection
        if db_manager.test_connection():
            print("✅ Database connection successful!")
        else:
            print("❌ Database connection failed!")
            return False
            
        # Test getting last processed feature_id
        print("\n🔄 Testing get_last_processed_feature_id...")
        last_feature_id = db_manager.get_last_processed_feature_id()
        print(f"📊 Last processed feature_id: {last_feature_id}")
        
        # Test entity count by feature_id (if we have data)
        if last_feature_id is not None:
            print(f"\n🔄 Testing entity count for feature_id {last_feature_id}...")
            count = db_manager.get_entity_count_by_feature_id(last_feature_id)
            print(f"📊 Entity count for feature_id {last_feature_id}: {count}")
        
        # Create a test entity (don't actually insert to avoid test data)
        print("\n🔄 Testing entity data preparation...")
        test_entity = Entity(
            name="test_entity",
            feature_id=99999,  # Use a high number to avoid conflicts
            description="This is a test entity for database connection testing"
        )
        test_entity.add_alias("test_alias")
        test_entity.add_external_link('wikipedia', ['https://en.wikipedia.org/wiki/Test'])
        test_entity.set_context_by_feature_description("Test feature description")
        
        # Test data preparation (without actual insertion)
        entity_data = db_manager._prepare_entity_data(test_entity)
        print("✅ Entity data preparation successful!")
        print(f"📊 Prepared entity data keys: {list(entity_data.keys())}")
        
        print("\n🎉 All database tests passed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Database test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_database_connection()
    sys.exit(0 if success else 1) 