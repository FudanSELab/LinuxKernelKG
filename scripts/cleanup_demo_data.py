#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Demo Data Cleanup Script

This script helps clean up demo and test data created during development
and testing of the MySQL database storage functionality.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.mysql_manager import MySQLManager
from config.pipeline_config import PipelineConfig
import argparse

def cleanup_demo_data(feature_ids_to_clean=None, confirm=True):
    """
    Clean up demo and test data from the database
    
    Args:
        feature_ids_to_clean: List of feature_ids to clean (default: demo feature_ids)
        confirm: Whether to ask for confirmation before deletion
    """
    
    if feature_ids_to_clean is None:
        # Default demo feature_ids used in our examples
        feature_ids_to_clean = [99999, 999991, 999992]
    
    print("🧹 Demo Data Cleanup Script")
    print("=" * 40)
    
    # Initialize database manager
    print("\n1️⃣ Initializing Database Manager...")
    db_manager = MySQLManager(PipelineConfig)
    
    # Test connection
    if not db_manager.test_connection():
        print("❌ Database connection failed!")
        return False
    print("✅ Database connection successful!")
    
    # Check what data exists
    print("\n2️⃣ Checking for Demo Data...")
    entities_to_delete = []
    total_entities = 0
    total_aliases = 0
    
    try:
        with db_manager.get_db_connection() as conn:
            cursor = conn.cursor()
            
            for feature_id in feature_ids_to_clean:
                # Count entities for this feature_id
                cursor.execute(
                    "SELECT eid, name_en FROM entities_extraction WHERE feature_id = %s",
                    (feature_id,)
                )
                entities = cursor.fetchall()
                
                if entities:
                    print(f"📊 Found {len(entities)} entities for feature_id {feature_id}:")
                    for entity in entities:
                        print(f"   - {entity['name_en']} (eid: {entity['eid']})")
                        entities_to_delete.append(entity['eid'])
                        
                        # Count aliases for this entity
                        cursor.execute(
                            "SELECT COUNT(*) as count FROM entity_aliases WHERE eid = %s",
                            (entity['eid'],)
                        )
                        alias_count = cursor.fetchone()['count']
                        if alias_count > 0:
                            print(f"     └─ {alias_count} aliases")
                            total_aliases += alias_count
                
                total_entities += len(entities)
    
    except Exception as e:
        print(f"❌ Error checking demo data: {e}")
        return False
    
    # Show summary
    print(f"\n📊 Summary:")
    print(f"   Total entities to delete: {total_entities}")
    print(f"   Total aliases to delete: {total_aliases}")
    print(f"   Feature IDs: {feature_ids_to_clean}")
    
    if total_entities == 0:
        print("✅ No demo data found to clean up!")
        return True
    
    # Confirmation
    if confirm:
        print("\n⚠️  This will permanently delete the above data!")
        response = input("Do you want to continue? (yes/no): ").lower().strip()
        if response not in ['yes', 'y']:
            print("🚫 Cleanup cancelled by user.")
            return False
    
    # Perform cleanup
    print("\n3️⃣ Cleaning up Demo Data...")
    
    try:
        with db_manager.get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Delete from entity_aliases first (foreign key constraint)
            for eid in entities_to_delete:
                cursor.execute("DELETE FROM entity_aliases WHERE eid = %s", (eid,))
                affected = cursor.rowcount
                if affected > 0:
                    print(f"✅ Deleted {affected} aliases for entity eid: {eid}")
            
            # Delete from entities_extraction
            for feature_id in feature_ids_to_clean:
                cursor.execute("DELETE FROM entities_extraction WHERE feature_id = %s", (feature_id,))
                affected = cursor.rowcount
                if affected > 0:
                    print(f"✅ Deleted {affected} entities for feature_id: {feature_id}")
            
            conn.commit()
            print("\n🎉 Cleanup completed successfully!")
            
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        return False
    
    return True

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Clean up demo data from MySQL database')
    parser.add_argument('--feature-ids', nargs='+', type=int,
                        help='Specific feature_ids to clean (default: demo feature_ids)')
    parser.add_argument('--yes', '-y', action='store_true',
                        help='Skip confirmation prompt')
    
    args = parser.parse_args()
    
    success = cleanup_demo_data(
        feature_ids_to_clean=args.feature_ids,
        confirm=not args.yes
    )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 