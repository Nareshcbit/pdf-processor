# RERA PDF Processor - Usage Guide

## Overview

`process_rera_pdfs.py` is a modular, refactored script that:
1. Converts PDFs to adaptive JSON format
2. Extracts structured project data
3. Saves individual project JSON files
4. Provides detailed logging throughout

## Features

- **Modular Design**: Clean class-based architecture with separate methods for each step
- **Progress Tracking**: Real-time logging with progress updates every 10 files
- **Resume Capability**: Skips already processed files by default
- **Error Handling**: Continues processing even if individual files fail
- **Statistics**: Tracks processing stats (processed, skipped, failed, etc.)
- **Dual Logging**: Logs to both console and `rera_processing.log` file

## Usage

### Basic Usage (Process all PDFs, skip existing)

```bash
python process_rera_pdfs.py
```

### Command Line Options

```bash
python process_rera_pdfs.py [OPTIONS]
```

**Options:**
- `--inputs DIR` - Input directory with PDFs (default: `inputs`)
- `--outputs DIR` - Output directory for JSON files (default: `outputs`)
- `--projects DIR` - Directory for project JSON files (default: `outputs/projects`)
- `--no-skip` - Reprocess all files (don't skip existing)
- `--reprocess-failed` - Reprocess failed/incomplete projects only
- `--quiet` - Reduce logging verbosity

### Examples

**Process all PDFs (skip existing):**
```bash
python process_rera_pdfs.py
```

**Reprocess everything:**
```bash
python process_rera_pdfs.py --no-skip
```

**Reprocess only failed/incomplete projects:**
```bash
python process_rera_pdfs.py --reprocess-failed
```

**Custom directories:**
```bash
python process_rera_pdfs.py --inputs my_pdfs --outputs my_outputs --projects my_projects
```

**Run in background (Linux/Mac):**
```bash
nohup python process_rera_pdfs.py > processing.log 2>&1 &
```

**Check progress:**
```bash
tail -f rera_processing.log
```

## Architecture

### Class: `RERAPDFProcessor`

**Main Methods:**
- `find_pdf_files()` - Find all PDFs in inputs directory
- `convert_pdf_to_json()` - Convert single PDF to JSON
- `extract_project_data()` - Extract structured data from JSON
- `save_project_file()` - Save project to individual JSON file
- `process_single_pdf()` - Complete workflow for one PDF
- `process_all_pdfs()` - Process all PDFs with progress tracking
- `reprocess_failed()` - Reprocess incomplete projects

**Statistics Tracking:**
- `pdfs_found` - Total PDFs discovered
- `pdfs_processed` - Successfully converted
- `pdfs_skipped` - Already existed (skipped)
- `pdfs_failed` - Failed conversions
- `projects_extracted` - Projects extracted
- `projects_with_coords` - Projects with latitude/longitude
- `projects_missing_coords` - Projects without coordinates

## Output Structure

```
outputs/
├── PRM_KA_RERA_1250_303_PR_240925_008116.json  # Full adaptive JSON
├── PRM_KA_RERA_1250_303_PR_250222_004734.json
└── projects/
    ├── PRM_KA_RERA_1250_303_PR_240925_008116.json  # Structured project data
    ├── PRM_KA_RERA_1250_303_PR_250222_004734.json
    └── ...

rera_processing.log  # Processing log file
```

## Logging

The script logs to:
1. **Console** - Real-time progress updates
2. **rera_processing.log** - Complete log file

**Log Levels:**
- `INFO` - Normal processing, progress updates
- `WARNING` - Non-critical issues
- `ERROR` - Failed operations
- `DEBUG` - Detailed debugging (when enabled)

## Error Handling

- Individual PDF failures don't stop the batch process
- Failed files are logged and counted in statistics
- You can reprocess failed files with `--reprocess-failed`
- Missing coordinates are tracked separately

## Performance

- Processes PDFs sequentially (one at a time)
- Skips existing files by default (fast resume)
- Progress updates every 10 files
- Typical processing time: 2-5 seconds per PDF

## Dependencies

- `adaptive_pdf_to_json.py` - PDF to JSON conversion
- `extract_project_data.py` - Project data extraction
- Standard libraries: `json`, `logging`, `pathlib`, `typing`

## Troubleshooting

**No PDFs found:**
- Check that PDFs are in the `inputs/` directory
- Verify file extensions are `.pdf` (lowercase)

**Processing stuck:**
- Check `rera_processing.log` for errors
- Some PDFs may take longer (large files, complex layouts)
- Use `--reprocess-failed` to continue from failures

**Missing coordinates:**
- Some PDFs may not have lat/long data
- Check the PDF source - coordinates may be in images or missing
- Tracked in statistics as `projects_missing_coords`

**Memory issues:**
- Process in smaller batches
- Clear old JSON files if needed
- Consider processing during off-peak hours

