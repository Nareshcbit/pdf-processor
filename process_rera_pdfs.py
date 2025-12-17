#!/usr/bin/env python3
"""
Modular RERA PDF Processor
Converts PDFs to JSON and extracts structured project data for map visualization.

This script:
1. Converts PDFs to adaptive JSON format
2. Extracts structured project data from JSON
3. Saves individual project files
4. Provides detailed logging throughout
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Import from existing modules
from adaptive_pdf_to_json import adaptive_pdf_to_json
from extract_project_data import parse_project_from_json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('rera_processing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class RERAPDFProcessor:
    """Main processor class for RERA PDFs."""
    
    def __init__(self, inputs_dir: str = "inputs", outputs_dir: str = "outputs", 
                 projects_dir: str = "outputs/projects"):
        """
        Initialize the processor.
        
        Args:
            inputs_dir: Directory containing PDF files
            outputs_dir: Directory for JSON output files
            projects_dir: Directory for structured project JSON files
        """
        self.inputs_dir = Path(inputs_dir)
        self.outputs_dir = Path(outputs_dir)
        self.projects_dir = Path(projects_dir)
        
        # Create directories if they don't exist
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        
        # Statistics
        self.stats = {
            'pdfs_found': 0,
            'pdfs_processed': 0,
            'pdfs_skipped': 0,
            'pdfs_failed': 0,
            'projects_extracted': 0,
            'projects_with_coords': 0,
            'projects_missing_coords': 0
        }
    
    def find_pdf_files(self) -> List[Path]:
        """
        Find all PDF files in the inputs directory.
        
        Returns:
            List of PDF file paths
        """
        pdf_files = list(self.inputs_dir.glob("*.pdf"))
        self.stats['pdfs_found'] = len(pdf_files)
        logger.info(f"Found {len(pdf_files)} PDF file(s) in {self.inputs_dir}")
        return sorted(pdf_files)
    
    def pdf_already_processed(self, pdf_file: Path) -> bool:
        """
        Check if a PDF has already been converted to JSON.
        
        Args:
            pdf_file: Path to PDF file
            
        Returns:
            True if JSON file already exists
        """
        json_file = self.outputs_dir / f"{pdf_file.stem}.json"
        return json_file.exists()
    
    def convert_pdf_to_json(self, pdf_file: Path, skip_existing: bool = True) -> Optional[Path]:
        """
        Convert a single PDF to JSON format.
        
        Args:
            pdf_file: Path to PDF file
            skip_existing: If True, skip if JSON already exists
            
        Returns:
            Path to created JSON file, or None if skipped/failed
        """
        json_file = self.outputs_dir / f"{pdf_file.stem}.json"
        
        if skip_existing and json_file.exists():
            logger.debug(f"Skipping {pdf_file.name} - JSON already exists")
            self.stats['pdfs_skipped'] += 1
            return json_file
        
        try:
            logger.info(f"Converting PDF: {pdf_file.name}")
            json_data = adaptive_pdf_to_json(str(pdf_file))
            
            # Save JSON file
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✓ Saved JSON: {json_file.name}")
            self.stats['pdfs_processed'] += 1
            return json_file
            
        except Exception as e:
            logger.error(f"✗ Failed to convert {pdf_file.name}: {e}")
            self.stats['pdfs_failed'] += 1
            return None
    
    def extract_project_data(self, json_file: Path) -> Optional[Dict[str, Any]]:
        """
        Extract structured project data from JSON file.
        
        Args:
            json_file: Path to JSON file
            
        Returns:
            Project data dictionary, or None if extraction failed
        """
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            project = parse_project_from_json(json_data)
            
            # Track statistics
            if project.get('latitude') and project.get('longitude'):
                self.stats['projects_with_coords'] += 1
            else:
                self.stats['projects_missing_coords'] += 1
            
            self.stats['projects_extracted'] += 1
            return project
            
        except Exception as e:
            logger.error(f"✗ Failed to extract project data from {json_file.name}: {e}")
            return None
    
    def save_project_file(self, project: Dict[str, Any]) -> Optional[Path]:
        """
        Save project data to individual JSON file.
        
        Args:
            project: Project data dictionary
            
        Returns:
            Path to saved project file, or None if failed
        """
        try:
            # Use PDF filename (without extension) as JSON filename
            pdf_filename = project.get('filename', 'unknown')
            if pdf_filename.endswith('.pdf'):
                pdf_filename = pdf_filename[:-4]
            
            project_file = self.projects_dir / f"{pdf_filename}.json"
            
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(project, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved project file: {project_file.name}")
            return project_file
            
        except Exception as e:
            logger.error(f"✗ Failed to save project file: {e}")
            return None
    
    def process_single_pdf(self, pdf_file: Path, skip_existing: bool = True) -> bool:
        """
        Process a single PDF: convert to JSON and extract project data.
        
        Args:
            pdf_file: Path to PDF file
            skip_existing: If True, skip if already processed
            
        Returns:
            True if successful, False otherwise
        """
        # Step 1: Convert PDF to JSON
        json_file = self.convert_pdf_to_json(pdf_file, skip_existing)
        if not json_file:
            return False
        
        # Step 2: Extract project data
        project = self.extract_project_data(json_file)
        if not project:
            return False
        
        # Step 3: Save project file
        project_file = self.save_project_file(project)
        if not project_file:
            return False
        
        # Log project summary
        name = project.get('project_name', 'Unknown')
        lat = project.get('latitude', 'N/A')
        lon = project.get('longitude', 'N/A')
        plots = project.get('total_plots', 0)
        cost = project.get('total_cost', 0)
        
        logger.info(f"  Project: {name}")
        logger.info(f"    Location: {lat}, {lon}")
        logger.info(f"    Plots: {plots}, Cost: ₹{cost:,}")
        
        return True
    
    def process_all_pdfs(self, skip_existing: bool = True, show_progress: bool = True) -> Dict[str, int]:
        """
        Process all PDFs in the inputs directory.
        
        Args:
            skip_existing: If True, skip already processed files
            show_progress: If True, show progress updates
            
        Returns:
            Dictionary with processing statistics
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"RERA PDF PROCESSOR - Starting Batch Processing")
        logger.info(f"{'='*70}")
        logger.info(f"Input directory: {self.inputs_dir}")
        logger.info(f"Output directory: {self.outputs_dir}")
        logger.info(f"Projects directory: {self.projects_dir}")
        logger.info(f"Skip existing: {skip_existing}")
        logger.info(f"{'='*70}\n")
        
        # Find all PDFs
        pdf_files = self.find_pdf_files()
        
        if not pdf_files:
            logger.warning("No PDF files found!")
            return self.stats
        
        # Process each PDF
        for idx, pdf_file in enumerate(pdf_files, 1):
            try:
                logger.info(f"\n[{idx}/{len(pdf_files)}] Processing: {pdf_file.name}")
                self.process_single_pdf(pdf_file, skip_existing)
                
                # Progress update every 10 files
                if show_progress and idx % 10 == 0:
                    self._log_progress(idx, len(pdf_files))
                    
            except Exception as e:
                logger.error(f"Unexpected error processing {pdf_file.name}: {e}")
                self.stats['pdfs_failed'] += 1
        
        # Final summary
        self._log_final_summary()
        
        return self.stats
    
    def _log_progress(self, current: int, total: int):
        """Log progress statistics."""
        percentage = (current * 100) // total
        logger.info(f"\n{'─'*70}")
        logger.info(f"📊 Progress: {current}/{total} ({percentage}%)")
        logger.info(f"  ✓ Processed: {self.stats['pdfs_processed']}")
        logger.info(f"  ⏭️  Skipped: {self.stats['pdfs_skipped']}")
        logger.info(f"  ✗ Failed: {self.stats['pdfs_failed']}")
        logger.info(f"  📍 Projects with coordinates: {self.stats['projects_with_coords']}")
        logger.info(f"{'─'*70}\n")
    
    def _log_final_summary(self):
        """Log final processing summary."""
        logger.info(f"\n{'='*70}")
        logger.info(f"BATCH PROCESSING COMPLETE")
        logger.info(f"{'='*70}")
        logger.info(f"PDF Files:")
        logger.info(f"  Total found: {self.stats['pdfs_found']}")
        logger.info(f"  Processed: {self.stats['pdfs_processed']}")
        logger.info(f"  Skipped: {self.stats['pdfs_skipped']}")
        logger.info(f"  Failed: {self.stats['pdfs_failed']}")
        logger.info(f"\nProjects:")
        logger.info(f"  Extracted: {self.stats['projects_extracted']}")
        logger.info(f"  With coordinates: {self.stats['projects_with_coords']}")
        logger.info(f"  Missing coordinates: {self.stats['projects_missing_coords']}")
        logger.info(f"{'='*70}\n")
    
    def reprocess_failed(self) -> Dict[str, int]:
        """
        Reprocess PDFs that failed previously.
        Finds JSON files without corresponding project files.
        
        Returns:
            Dictionary with processing statistics
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"REPROCESSING FAILED/INCOMPLETE PROJECTS")
        logger.info(f"{'='*70}\n")
        
        # Find JSON files
        json_files = list(self.outputs_dir.glob("*.json"))
        json_files = [f for f in json_files if f.name != "all_projects.json"]
        
        logger.info(f"Found {len(json_files)} JSON file(s)")
        
        # Check which ones don't have project files
        to_reprocess = []
        for json_file in json_files:
            pdf_name = json_file.stem
            project_file = self.projects_dir / f"{pdf_name}.json"
            if not project_file.exists():
                to_reprocess.append(json_file)
        
        logger.info(f"Found {len(to_reprocess)} JSON file(s) without project files")
        
        # Reprocess
        for json_file in to_reprocess:
            logger.info(f"Reprocessing: {json_file.name}")
            project = self.extract_project_data(json_file)
            if project:
                self.save_project_file(project)
        
        self._log_final_summary()
        return self.stats


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Process RERA Karnataka PDFs')
    parser.add_argument('--inputs', default='inputs', help='Input directory with PDFs')
    parser.add_argument('--outputs', default='outputs', help='Output directory for JSON files')
    parser.add_argument('--projects', default='outputs/projects', help='Directory for project JSON files')
    parser.add_argument('--no-skip', action='store_true', help='Reprocess all files (don\'t skip existing)')
    parser.add_argument('--reprocess-failed', action='store_true', help='Reprocess failed/incomplete projects')
    parser.add_argument('--quiet', action='store_true', help='Reduce logging verbosity')
    
    args = parser.parse_args()
    
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    
    # Create processor
    processor = RERAPDFProcessor(
        inputs_dir=args.inputs,
        outputs_dir=args.outputs,
        projects_dir=args.projects
    )
    
    # Run processing
    if args.reprocess_failed:
        processor.reprocess_failed()
    else:
        processor.process_all_pdfs(skip_existing=not args.no_skip)


if __name__ == "__main__":
    main()

