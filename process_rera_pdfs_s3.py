#!/usr/bin/env python3
"""
S3-based RERA PDF Processor with Advanced Filtering
Downloads PDFs from S3, converts to JSON, uploads back to S3.

Features:
- Filter by serial number range (e.g., sno 1-25)
- Filter by timestamp (updated after X, last N hours)
- Store file list and metadata
- Process only filtered files
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from adaptive_pdf_to_json import adaptive_pdf_to_json
from extract_project_data import parse_project_from_json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('rera_processing_s3.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class S3RERAPDFProcessor:
    """S3-based processor for RERA PDFs with filtering capabilities."""
    
    def __init__(
        self,
        bucket: str,
        pdf_path: str,
        json_path: str,
        projects_path: Optional[str] = None,
        metadata_path: Optional[str] = None,
        aws_region: str = "us-east-1",
        temp_dir: Optional[str] = None
    ):
        """
        Initialize S3 processor.
        
        Args:
            bucket: S3 bucket name
            pdf_path: S3 path/prefix for input PDFs (e.g., "pdfs/" or "data/pdfs/")
            json_path: S3 path/prefix for output JSONs (e.g., "json/" or "data/json/")
            projects_path: Optional S3 path/prefix for project JSONs (if None, uses json_path/projects/)
            metadata_path: Optional S3 path/prefix for metadata files (if None, uses json_path/metadata/)
            aws_region: AWS region
            temp_dir: Temporary directory for downloads (default: system temp)
        """
        self.bucket = bucket
        self.pdf_path = pdf_path.rstrip('/')
        self.json_path = json_path.rstrip('/')
        self.projects_path = (projects_path.rstrip('/') if projects_path else f"{self.json_path}/projects")
        self.metadata_path = (metadata_path.rstrip('/') if metadata_path else f"{self.json_path}/metadata")
        
        # Initialize S3 client
        try:
            self.s3_client = boto3.client('s3', region_name=aws_region)
            logger.info(f"Initialized S3 client for region: {aws_region}")
        except NoCredentialsError:
            logger.error("AWS credentials not found. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
            raise
        
        # Create temp directory
        self.temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.mkdtemp(prefix="rera_pdf_"))
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using temp directory: {self.temp_dir}")
        
        # Statistics
        self.stats = {
            'pdfs_found': 0,
            'pdfs_filtered': 0,
            'pdfs_processed': 0,
            'pdfs_skipped': 0,
            'pdfs_failed': 0,
            'projects_extracted': 0,
            'projects_with_coords': 0,
            'projects_missing_coords': 0
        }
        
        # File list cache
        self.file_list: List[Dict[str, Any]] = []
    
    def list_pdf_files(self, store_list: bool = True) -> List[Dict[str, Any]]:
        """
        List all PDF files in S3 input bucket.
        
        Args:
            store_list: If True, store the list internally
            
        Returns:
            List of file metadata dictionaries with keys:
            - key: S3 object key
            - filename: File name
            - size: File size in bytes
            - last_modified: Last modified datetime
            - serial_number: Extracted serial number (if available)
        """
        pdf_prefix = f"{self.pdf_path}/" if self.pdf_path else ""
        logger.info(f"Listing PDFs from s3://{self.bucket}/{pdf_prefix}")
        
        files = []
        paginator = self.s3_client.get_paginator('list_objects_v2')
        
        try:
            for page in paginator.paginate(
                Bucket=self.bucket,
                Prefix=pdf_prefix
            ):
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    key = obj['Key']
                    
                    # Only process PDF files
                    if not key.lower().endswith('.pdf'):
                        continue
                    
                    # Extract filename
                    filename = Path(key).name
                    
                    # Extract serial number from filename if possible
                    # Common patterns: "PRM_KA_RERA_1250_301_PR_010422_004807.pdf"
                    serial_number = self._extract_serial_number(filename)
                    
                    file_info = {
                        'key': key,
                        'filename': filename,
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'],
                        'serial_number': serial_number,
                        'etag': obj.get('ETag', '').strip('"')
                    }
                    files.append(file_info)
            
            # Sort by serial number if available, else by filename
            files.sort(key=lambda x: (x['serial_number'] or 0, x['filename']))
            
            self.stats['pdfs_found'] = len(files)
            logger.info(f"Found {len(files)} PDF file(s)")
            
            if store_list:
                self.file_list = files
                self._save_file_list()
            
            return files
            
        except ClientError as e:
            logger.error(f"Error listing S3 objects: {e}")
            raise
    
    def _extract_serial_number(self, filename: str) -> Optional[int]:
        """Extract serial number from filename if present."""
        # Try to extract number from filename
        # Pattern: filename with numbers that might be serial
        import re
        # Look for patterns like "001", "1", "sno_1", etc.
        patterns = [
            r'sno[_\s]*(\d+)',
            r'^(\d+)',
            r'_(\d{3,})',  # 3+ digit numbers
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue
        
        return None
    
    def filter_files(
        self,
        serial_range: Optional[Tuple[int, int]] = None,
        updated_after: Optional[datetime] = None,
        updated_in_last_hours: Optional[float] = None,
        last_n_files: Optional[int] = None,
        filename_pattern: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Filter file list based on criteria.
        
        Args:
            serial_range: Tuple of (start, end) serial numbers (inclusive)
            updated_after: Only files updated after this datetime
            updated_in_last_hours: Only files updated in last N hours
            last_n_files: Only process the N most recently updated files
            filename_pattern: Filename pattern to match (regex)
            
        Returns:
            Filtered list of file metadata
        """
        if not self.file_list:
            logger.warning("File list is empty. Call list_pdf_files() first.")
            return []
        
        filtered = self.file_list.copy()
        
        # Filter by serial number range
        if serial_range:
            start, end = serial_range
            filtered = [
                f for f in filtered
                if f['serial_number'] is not None
                and start <= f['serial_number'] <= end
            ]
            logger.info(f"Filtered by serial range {start}-{end}: {len(filtered)} files")
        
        # Filter by timestamp
        if updated_after:
            filtered = [
                f for f in filtered
                if f['last_modified'] > updated_after
            ]
            logger.info(f"Filtered by updated_after {updated_after}: {len(filtered)} files")
        
        if updated_in_last_hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=updated_in_last_hours)
            filtered = [
                f for f in filtered
                if f['last_modified'] > cutoff
            ]
            logger.info(f"Filtered by last {updated_in_last_hours} hours: {len(filtered)} files")
        
        # Filter by filename pattern
        if filename_pattern:
            import re
            pattern = re.compile(filename_pattern, re.IGNORECASE)
            filtered = [
                f for f in filtered
                if pattern.search(f['filename'])
            ]
            logger.info(f"Filtered by pattern '{filename_pattern}': {len(filtered)} files")
        
        # Filter by last N files (most recently updated)
        if last_n_files:
            # Sort by last_modified descending and take first N
            filtered.sort(key=lambda x: x['last_modified'], reverse=True)
            filtered = filtered[:last_n_files]
            logger.info(f"Filtered to last {last_n_files} most recently updated files")
        
        self.stats['pdfs_filtered'] = len(filtered)
        return filtered
    
    def _save_file_list(self):
        """Save file list to S3 metadata."""
        if not self.file_list:
            return
        
        metadata = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'total_files': len(self.file_list),
            'files': [
                {
                    'key': f['key'],
                    'filename': f['filename'],
                    'size': f['size'],
                    'last_modified': f['last_modified'].isoformat(),
                    'serial_number': f['serial_number']
                }
                for f in self.file_list
            ]
        }
        
        metadata_key = f"{self.metadata_path}/file_list.json".lstrip('/')
        
        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=metadata_key,
                Body=json.dumps(metadata, indent=2),
                ContentType='application/json'
            )
            logger.info(f"Saved file list to s3://{self.bucket}/{metadata_key}")
        except ClientError as e:
            logger.error(f"Failed to save file list: {e}")
    
    def download_pdf(self, file_info: Dict[str, Any]) -> Optional[Path]:
        """
        Download PDF from S3 to temp directory.
        
        Args:
            file_info: File metadata dictionary
            
        Returns:
            Path to downloaded file, or None if failed
        """
        s3_key = file_info['key']
        filename = file_info['filename']
        local_path = self.temp_dir / filename
        
        try:
            logger.debug(f"Downloading s3://{self.bucket}/{s3_key}")
            self.s3_client.download_file(
                self.bucket,
                s3_key,
                str(local_path)
            )
            logger.info(f"✓ Downloaded: {filename}")
            return local_path
        except ClientError as e:
            logger.error(f"✗ Failed to download {filename}: {e}")
            return None
    
    def upload_json(self, json_data: Dict[str, Any], filename: str, path: str = None) -> bool:
        """
        Upload JSON data to S3.
        
        Args:
            json_data: JSON data dictionary
            filename: Output filename
            path: S3 path/prefix (default: json_path)
            
        Returns:
            True if successful
        """
        if path is None:
            path = self.json_path
        
        # Ensure .json extension
        if not filename.endswith('.json'):
            filename = f"{Path(filename).stem}.json"
        
        s3_key = f"{path}/{filename}".lstrip('/')
        
        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=json.dumps(json_data, indent=2, ensure_ascii=False),
                ContentType='application/json'
            )
            logger.info(f"✓ Uploaded JSON: s3://{self.bucket}/{s3_key}")
            return True
        except ClientError as e:
            logger.error(f"✗ Failed to upload {filename}: {e}")
            return False
    
    def json_exists_in_s3(self, filename: str, path: str = None) -> bool:
        """Check if JSON file already exists in S3."""
        if path is None:
            path = self.json_path
        
        if not filename.endswith('.json'):
            filename = f"{Path(filename).stem}.json"
        
        s3_key = f"{path}/{filename}".lstrip('/')
        
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise
    
    def process_single_pdf(
        self,
        file_info: Dict[str, Any],
        skip_existing: bool = True
    ) -> bool:
        """
        Process a single PDF: download, convert, extract, upload.
        
        Args:
            file_info: File metadata dictionary
            skip_existing: If True, skip if JSON already exists in S3
            
        Returns:
            True if successful
        """
        filename = file_info['filename']
        json_filename = f"{Path(filename).stem}.json"
        
        # Check if already processed
        if skip_existing and self.json_exists_in_s3(json_filename):
            logger.debug(f"Skipping {filename} - JSON already exists in S3")
            self.stats['pdfs_skipped'] += 1
            return True
        
        # Step 1: Download PDF
        pdf_path = self.download_pdf(file_info)
        if not pdf_path:
            self.stats['pdfs_failed'] += 1
            return False
        
        try:
            # Step 2: Convert PDF to JSON
            logger.info(f"Converting PDF: {filename}")
            json_data = adaptive_pdf_to_json(str(pdf_path))
            json_data['source_s3_key'] = file_info['key']
            json_data['source_bucket'] = self.bucket
            json_data['processed_at'] = datetime.now(timezone.utc).isoformat()
            
            # Step 3: Upload full JSON
            if not self.upload_json(json_data, json_filename):
                self.stats['pdfs_failed'] += 1
                return False
            
            # Step 4: Extract project data
            project = parse_project_from_json(json_data)
            if project:
                # Track statistics
                if project.get('latitude') and project.get('longitude'):
                    self.stats['projects_with_coords'] += 1
                else:
                    self.stats['projects_missing_coords'] += 1
                
                self.stats['projects_extracted'] += 1
                
                # Step 5: Upload project JSON
                project_filename = f"{Path(filename).stem}.json"
                self.upload_json(project, project_filename, self.projects_path)
                
                # Log project summary
                name = project.get('project_name', 'Unknown')
                logger.info(f"  Project: {name}")
            
            self.stats['pdfs_processed'] += 1
            return True
            
        except Exception as e:
            logger.error(f"✗ Error processing {filename}: {e}")
            self.stats['pdfs_failed'] += 1
            return False
        
        finally:
            # Clean up downloaded file
            if pdf_path and pdf_path.exists():
                pdf_path.unlink()
    
    def process_filtered_files(
        self,
        filtered_files: List[Dict[str, Any]],
        skip_existing: bool = True,
        show_progress: bool = True
    ) -> Dict[str, int]:
        """
        Process filtered list of files.
        
        Args:
            filtered_files: List of file metadata dictionaries
            skip_existing: If True, skip already processed files
            show_progress: If True, show progress updates
            
        Returns:
            Dictionary with processing statistics
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"S3 RERA PDF PROCESSOR - Processing {len(filtered_files)} file(s)")
        logger.info(f"{'='*70}")
        logger.info(f"Bucket: s3://{self.bucket}")
        logger.info(f"PDF path: {self.pdf_path}")
        logger.info(f"JSON path: {self.json_path}")
        logger.info(f"Projects path: {self.projects_path}")
        logger.info(f"Skip existing: {skip_existing}")
        logger.info(f"{'='*70}\n")
        
        if not filtered_files:
            logger.warning("No files to process!")
            return self.stats
        
        # Process each file
        for idx, file_info in enumerate(filtered_files, 1):
            try:
                logger.info(f"\n[{idx}/{len(filtered_files)}] Processing: {file_info['filename']}")
                if file_info.get('serial_number'):
                    logger.info(f"  Serial #: {file_info['serial_number']}")
                logger.info(f"  Last modified: {file_info['last_modified']}")
                
                self.process_single_pdf(file_info, skip_existing)
                
                # Progress update every 10 files
                if show_progress and idx % 10 == 0:
                    self._log_progress(idx, len(filtered_files))
                    
            except Exception as e:
                logger.error(f"Unexpected error processing {file_info['filename']}: {e}")
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
        logger.info(f"  Filtered: {self.stats['pdfs_filtered']}")
        logger.info(f"  Processed: {self.stats['pdfs_processed']}")
        logger.info(f"  Skipped: {self.stats['pdfs_skipped']}")
        logger.info(f"  Failed: {self.stats['pdfs_failed']}")
        logger.info(f"\nProjects:")
        logger.info(f"  Extracted: {self.stats['projects_extracted']}")
        logger.info(f"  With coordinates: {self.stats['projects_with_coords']}")
        logger.info(f"  Missing coordinates: {self.stats['projects_missing_coords']}")
        logger.info(f"{'='*70}\n")
    
    def cleanup_temp(self):
        """Clean up temporary directory."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            logger.info(f"Cleaned up temp directory: {self.temp_dir}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Process RERA Karnataka PDFs from S3 with filtering',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all files and store list
  python process_rera_pdfs_s3.py --list-only --bucket my-bucket --pdf-path pdfs/ --json-path json/
  
  # Process files 1-25
  python process_rera_pdfs_s3.py --bucket my-bucket --pdf-path pdfs/ --json-path json/ --serial-range 1 25
  
  # Process files updated in last 4 hours
  python process_rera_pdfs_s3.py --bucket my-bucket --pdf-path pdfs/ --json-path json/ --last-hours 4
  
  # Process last 10 most recently updated files
  python process_rera_pdfs_s3.py --bucket my-bucket --pdf-path pdfs/ --json-path json/ --last-n 10
  
  # Process files updated after specific date
  python process_rera_pdfs_s3.py --bucket my-bucket --pdf-path pdfs/ --json-path json/ --updated-after "2025-12-01T00:00:00Z"
  
  # Custom paths
  python process_rera_pdfs_s3.py --bucket my-bucket --pdf-path data/pdfs --json-path data/json --projects-path data/projects --metadata-path data/metadata
        """
    )
    
    # S3 configuration
    parser.add_argument('--bucket', required=True, help='S3 bucket name')
    parser.add_argument('--pdf-path', required=True, help='S3 path/prefix for input PDFs (e.g., "pdfs/" or "data/pdfs")')
    parser.add_argument('--json-path', required=True, help='S3 path/prefix for output JSONs (e.g., "json/" or "data/json")')
    parser.add_argument('--projects-path', help='S3 path/prefix for project JSONs (default: json-path/projects/)')
    parser.add_argument('--metadata-path', help='S3 path/prefix for metadata files (default: json-path/metadata/)')
    parser.add_argument('--aws-region', default='us-east-1', help='AWS region')
    
    # Filtering options
    parser.add_argument('--list-only', action='store_true', help='Only list files and store list, do not process')
    parser.add_argument('--serial-range', nargs=2, type=int, metavar=('START', 'END'),
                       help='Process files with serial numbers in range (e.g., --serial-range 1 25)')
    parser.add_argument('--updated-after', type=str,
                       help='Only process files updated after this datetime (ISO format, e.g., 2025-12-01T00:00:00Z)')
    parser.add_argument('--last-hours', type=float,
                       help='Only process files updated in last N hours (e.g., --last-hours 4)')
    parser.add_argument('--last-n', type=int, metavar='N',
                       help='Only process the N most recently updated files (e.g., --last-n 10)')
    parser.add_argument('--filename-pattern', type=str,
                       help='Only process files matching filename pattern (regex)')
    
    # Processing options
    parser.add_argument('--no-skip', action='store_true', help='Reprocess all files (don\'t skip existing)')
    parser.add_argument('--quiet', action='store_true', help='Reduce logging verbosity')
    
    args = parser.parse_args()
    
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    
    # Create processor
    processor = S3RERAPDFProcessor(
        bucket=args.bucket,
        pdf_path=args.pdf_path,
        json_path=args.json_path,
        projects_path=args.projects_path,
        metadata_path=args.metadata_path,
        aws_region=args.aws_region
    )
    
    try:
        # List files
        files = processor.list_pdf_files(store_list=True)
        
        if args.list_only:
            logger.info(f"File list stored. Found {len(files)} files.")
            return
        
        # Apply filters
        filtered_files = files
        if args.serial_range or args.updated_after or args.last_hours or args.last_n or args.filename_pattern:
            updated_after = None
            if args.updated_after:
                updated_after = datetime.fromisoformat(args.updated_after.replace('Z', '+00:00'))
            
            filtered_files = processor.filter_files(
                serial_range=tuple(args.serial_range) if args.serial_range else None,
                updated_after=updated_after,
                updated_in_last_hours=args.last_hours,
                last_n_files=args.last_n,
                filename_pattern=args.filename_pattern
            )
        
        # Process filtered files
        if filtered_files:
            processor.process_filtered_files(
                filtered_files,
                skip_existing=not args.no_skip
            )
        else:
            logger.warning("No files match the filter criteria!")
    
    finally:
        # Cleanup
        processor.cleanup_temp()


if __name__ == "__main__":
    main()

