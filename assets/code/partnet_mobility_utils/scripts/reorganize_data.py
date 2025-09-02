#!/usr/bin/env python3
"""
PartNet Mobility Dataset Reorganization Script

This script reorganizes well-formed objects by category into the processed_data directory.
Only objects that exist in both category files and filter.txt will be copied.
"""

import shutil
import json
from pathlib import Path
from typing import Set, Dict
import typer


def load_filter_ids(filter_file: Path) -> Set[str]:
    """Load set of well-formed object IDs"""
    filter_ids = set()
    if filter_file.exists():
        with open(filter_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and ',' in line:
                    obj_id = line.split(',')[0]
                    filter_ids.add(obj_id)
                elif line.isdigit():
                    filter_ids.add(line)
    return filter_ids


def load_category_files(category_dir: Path) -> Dict[str, Set[str]]:
    """Load all category files, return {category_name: {object_id_set}}"""
    categories = {}
    
    for category_file in category_dir.glob("*.txt"):
        category_name = category_file.stem  # filename without extension
        obj_ids = set()
        
        with open(category_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and ',' in line:
                    obj_id = line.split(',')[0]
                    obj_ids.add(obj_id)
        
        categories[category_name] = obj_ids
        print(f"Category {category_name}: Found {len(obj_ids)} objects")
    
    return categories


def main(
    raw_data_dir: Path = typer.Argument(..., help="Raw data directory path"),
    filter_file: Path = typer.Argument(..., help="filter.txt file path"),
    category_dir: Path = typer.Argument(..., help="Category files directory path"),
    output_dir: Path = typer.Argument(..., help="Output processed_data directory path")
):
    """
    Reorganize PartNet Mobility Dataset
    
    Args:
        raw_data_dir: Directory containing raw data (e.g., .../partnet_mobility/raw_data)
        filter_file: Path to filter.txt file
        category_dir: Directory containing category files (e.g., .../output/category)
        output_dir: Output directory (e.g., .../partnet_mobility/processed_data)
    """
    
    # Validate input directories and files
    if not raw_data_dir.exists():
        print(f"Error: Raw data directory does not exist: {raw_data_dir}")
        return
    
    if not filter_file.exists():
        print(f"Error: filter.txt file does not exist: {filter_file}")
        return
        
    if not category_dir.exists():
        print(f"Error: Category directory does not exist: {category_dir}")
        return
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load well-formed object IDs
    print("Loading well-formed object IDs...")
    filter_ids = load_filter_ids(filter_file)
    print(f"Found {len(filter_ids)} well-formed objects")
    
    # Load category files
    print("Loading category files...")
    categories = load_category_files(category_dir)
    
    # Statistics for JSON output
    stats = {
        "total_filter_objects": len(filter_ids),
        "total_categories": len(categories),
        "categories": {}
    }
    
    # Process each category
    total_copied = 0
    for category_name, category_ids in categories.items():
        print(f"\nProcessing category: {category_name}")
        
        # Find objects that are both in category and well-formed
        valid_ids = category_ids.intersection(filter_ids)
        print(f"  Found {len(valid_ids)} valid objects")
        
        if not valid_ids:
            print(f"  Skipping category {category_name} (no valid objects)")
            stats["categories"][category_name] = {
                "total_in_category": len(category_ids),
                "valid_objects": 0,
                "copied_objects": 0,
                "objects": []
            }
            continue
        
        # Create category directory
        category_output_dir = output_dir / category_name
        category_output_dir.mkdir(exist_ok=True)
        
        # Copy each valid object
        copied_count = 0
        copied_objects = []
        for obj_id in sorted(valid_ids):
            src_dir = raw_data_dir / obj_id
            dst_dir = category_output_dir / obj_id
            
            if src_dir.exists() and src_dir.is_dir():
                try:
                    if dst_dir.exists():
                        print(f"    Skipping {obj_id} (destination already exists)")
                        continue
                    
                    shutil.copytree(src_dir, dst_dir)
                    copied_count += 1
                    copied_objects.append(obj_id)
                    print(f"    Copied: {obj_id}")
                    
                except Exception as e:
                    print(f"    Error: Failed to copy {obj_id}: {e}")
            else:
                print(f"    Warning: Source directory does not exist: {src_dir}")
        
        print(f"  Category {category_name}: Successfully copied {copied_count} objects")
        total_copied += copied_count
        
        # Update statistics
        stats["categories"][category_name] = {
            "total_in_category": len(category_ids),
            "valid_objects": len(valid_ids),
            "copied_objects": copied_count,
            "objects": copied_objects
        }
    
    # Save statistics to JSON file
    stats_file = output_dir / "stats.json"
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    
    print(f"\nCompleted! Total copied {total_copied} objects to {output_dir}")
    print(f"Statistics saved to: {stats_file}")


if __name__ == "__main__":
    typer.run(main)