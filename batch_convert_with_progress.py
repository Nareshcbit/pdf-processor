#!/usr/bin/env python3
"""
Batch convert PDFs to JSON with progress tracking and resume capability.
Skips already processed files.
"""

import json
import logging
from pathlib import Path
from adaptive_pdf_to_json import adaptive_pdf_to_json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def batch_convert_with_progress(folder_in: str = "inputs", folder_out: str = "outputs", skip_existing: bool = True):
    """
    Batch convert all PDFs with progress tracking.
    Can resume from where it left off by skipping existing JSON files.
    """
    folder_in = Path(folder_in)
    folder_out = Path(folder_out)
    
    # Create output folder if it doesn't exist
    folder_out.mkdir(parents=True, exist_ok=True)
    
    # Find all PDFs
    pdf_files = list(folder_in.glob("*.pdf"))
    if not pdf_files:
        logger.warning(f"No PDF files found in {folder_in}")
        return
    
    logger.info(f"\n{'#'*60}")
    logger.info(f"BATCH CONVERSION: Found {len(pdf_files)} PDF file(s)")
    logger.info(f"{'#'*60}\n")
    
    successful = 0
    failed = 0
    skipped = 0
    
    for idx, pdf_file in enumerate(pdf_files, 1):
        # Check if output already exists
        json_filename = pdf_file.stem + ".json"
        json_path = folder_out / json_filename
        
        if skip_existing and json_path.exists():
            logger.info(f"[{idx}/{len(pdf_files)}] ⏭️  Skipped (already exists): {pdf_file.name}")
            skipped += 1
            continue
        
        try:
            logger.info(f"[{idx}/{len(pdf_files)}] Processing: {pdf_file.name}")
            # Convert to JSON
            json_data = adaptive_pdf_to_json(pdf_file)
            
            # Save JSON file
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"  ✓ Saved: {json_path.name}")
            successful += 1
            
            # Progress update every 10 files
            if idx % 10 == 0:
                logger.info(f"\n📊 Progress: {idx}/{len(pdf_files)} ({idx*100//len(pdf_files)}%) | "
                          f"✓ {successful} | ✗ {failed} | ⏭️  {skipped}\n")
            
        except Exception as e:
            logger.error(f"  ✗ Failed: {pdf_file.name} - {e}")
            failed += 1
    
    logger.info(f"\n{'#'*60}")
    logger.info(f"BATCH CONVERSION COMPLETE")
    logger.info(f"  Total: {len(pdf_files)}")
    logger.info(f"  Successful: {successful}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Skipped: {skipped}")
    logger.info(f"{'#'*60}\n")


if __name__ == "__main__":
    batch_convert_with_progress()

