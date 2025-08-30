#!/usr/bin/env python3
"""
Test script for the batch URDF to USD converter.
This script tests the functionality without requiring Isaac Sim.
"""

import os
import sys
import json
import argparse
from pathlib import Path

# Add the parent directory to the Python path to import the converter
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_converter_structure(processed_data_dir: str):
    """Test the converter without Isaac Sim dependencies."""
    
    print(f"=== Testing URDF to USD Converter Structure ===")
    print(f"Processed data directory: {processed_data_dir}")
    
    # Check if the processed data directory exists
    processed_data_path = Path(processed_data_dir)
    if not processed_data_path.exists():
        print(f"Error: Processed data directory does not exist: {processed_data_path}")
        return False
    
    # Check if stats.json exists
    stats_file = processed_data_path / "stats.json"
    if not stats_file.exists():
        print(f"Error: Stats file not found: {stats_file}")
        return False
    
    # Load and analyze stats
    with open(stats_file, 'r') as f:
        stats_data = json.load(f)
    
    print(f"✓ Stats file loaded successfully")
    print(f"Total categories: {len(stats_data.get('categories', {}))}")
    print(f"Total objects: {stats_data.get('total_well_formed_objects', 0)}")
    
    # Check some categories and objects
    categories = stats_data.get("categories", {})
    print(f"\nAvailable categories:")
    for i, (category, data) in enumerate(sorted(categories.items())[:10], 1):
        object_count = len(data.get("objects", []))
        print(f"  {i:2d}. {category}: {object_count} objects")
    
    if len(categories) > 10:
        print(f"  ... and {len(categories) - 10} more categories")
    
    # Test object structure
    print(f"\nTesting object directory structure:")
    test_count = 0
    for category, data in categories.items():
        if test_count >= 5:  # Test only first 5 categories
            break
        
        objects = data.get("objects", [])
        if not objects:
            continue
            
        test_object = objects[0]  # Test first object in category
        object_dir = processed_data_path / category / test_object
        urdf_file = object_dir / "mobility.urdf"
        
        print(f"  Testing {category}/{test_object}:")
        print(f"    Directory exists: {object_dir.exists()}")
        print(f"    URDF file exists: {urdf_file.exists()}")
        
        if urdf_file.exists():
            print(f"    ✓ Ready for USD conversion")
        else:
            print(f"    ✗ Missing URDF file")
        
        test_count += 1
    
    print(f"\n=== Structure Test Completed ===")
    return True

def simulate_conversion_modes(processed_data_dir: str):
    """Simulate different conversion modes without actually converting."""
    
    print(f"\n=== Simulating Conversion Modes ===")
    
    stats_file = Path(processed_data_dir) / "stats.json"
    with open(stats_file, 'r') as f:
        stats_data = json.load(f)
    
    categories = stats_data.get("categories", {})
    
    # Simulate "all" mode
    total_objects = sum(len(data.get("objects", [])) for data in categories.values())
    print(f"All mode: Would process {total_objects} objects across {len(categories)} categories")
    
    # Simulate "random" mode
    import random
    all_objects = []
    for category, data in categories.items():
        for obj_id in data.get("objects", []):
            all_objects.append((category, obj_id))
    
    random_sample = random.sample(all_objects, min(10, len(all_objects)))
    print(f"Random mode (N=10): Would process {len(random_sample)} objects:")
    for category, obj_id in random_sample[:5]:
        print(f"  - {category}/{obj_id}")
    if len(random_sample) > 5:
        print(f"  ... and {len(random_sample) - 5} more")
    
    # Simulate "category" mode
    test_category = list(categories.keys())[0] if categories else None
    if test_category:
        category_objects = len(categories[test_category].get("objects", []))
        print(f"Category mode ('{test_category}'): Would process {category_objects} objects")
    
    # Simulate "object" mode
    if all_objects:
        test_obj = all_objects[0]
        print(f"Object mode ('{test_obj[1]}'): Would process 1 object ({test_obj[0]}/{test_obj[1]})")
    
    print(f"=== Simulation Completed ===")

def main():
    """Main function for testing."""
    parser = argparse.ArgumentParser(description="Test the URDF to USD converter structure")
    parser.add_argument("processed_data_dir", help="Path to the processed data directory")
    
    args = parser.parse_args()
    
    if test_converter_structure(args.processed_data_dir):
        simulate_conversion_modes(args.processed_data_dir)
    else:
        print("Structure test failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
