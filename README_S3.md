# S3-based RERA PDF Processor

Process RERA Karnataka PDFs stored in S3 buckets with advanced filtering capabilities.

## Features

- **S3 Integration**: Download PDFs from S3, process, upload JSONs back to S3
- **Serial Number Filtering**: Process specific file ranges (e.g., sno 1-25)
- **Timestamp Filtering**: Process files updated after a date or in last N hours
- **Filename Pattern Matching**: Filter by regex pattern
- **File List Storage**: Store and retrieve file lists with metadata
- **Resume Capability**: Skip already processed files

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure AWS credentials
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

# Or use AWS CLI
aws configure
```

## Usage

### Basic: List and Store File List

```bash
python process_rera_pdfs_s3.py \
  --bucket my-bucket \
  --pdf-path pdfs/ \
  --json-path json/ \
  --list-only
```

This will:
- List all PDFs in the specified PDF path
- Store the file list with metadata in your JSON path's metadata folder

### Filter by Serial Number Range

Process only files with serial numbers 1-25:

```bash
python process_rera_pdfs_s3.py \
  --bucket my-bucket \
  --pdf-path pdfs/ \
  --json-path json/ \
  --serial-range 1 25
```

### Filter by Timestamp

Process files updated in the last 4 hours:

```bash
python process_rera_pdfs_s3.py \
  --bucket my-bucket \
  --pdf-path pdfs/ \
  --json-path json/ \
  --last-hours 4
```

Process the last 10 most recently updated files:

```bash
python process_rera_pdfs_s3.py \
  --bucket my-bucket \
  --pdf-path pdfs/ \
  --json-path json/ \
  --last-n 10
```

Process files updated after a specific date:

```bash
python process_rera_pdfs_s3.py \
  --bucket my-bucket \
  --pdf-path pdfs/ \
  --json-path json/ \
  --updated-after "2025-12-01T00:00:00Z"
```

### Filter by Filename Pattern

Process files matching a regex pattern:

```bash
python process_rera_pdfs_s3.py \
  --bucket my-bucket \
  --pdf-path pdfs/ \
  --json-path json/ \
  --filename-pattern "PRM_KA_RERA_1250_301"
```

### Combined Filters

Combine multiple filters:

```bash
# Process files 1-50 that were updated in last 24 hours
python process_rera_pdfs_s3.py \
  --bucket my-bucket \
  --pdf-path pdfs/ \
  --json-path json/ \
  --serial-range 1 50 \
  --last-hours 24

# Process last 5 files matching a pattern
python process_rera_pdfs_s3.py \
  --bucket my-bucket \
  --pdf-path pdfs/ \
  --json-path json/ \
  --last-n 5 \
  --filename-pattern "PRM_KA_RERA"
```

### Custom Paths

Specify custom paths for all outputs:

```bash
python process_rera_pdfs_s3.py \
  --bucket my-bucket \
  --pdf-path data/pdfs \
  --json-path data/json \
  --projects-path data/projects \
  --metadata-path data/metadata
```

If `--projects-path` or `--metadata-path` are not specified, they default to:
- Projects: `{json-path}/projects/`
- Metadata: `{json-path}/metadata/`

### Reprocess All Files

Force reprocessing even if JSONs already exist:

```bash
python process_rera_pdfs_s3.py \
  --bucket my-bucket \
  --pdf-path pdfs/ \
  --json-path json/ \
  --no-skip
```

## Command Line Options

### S3 Configuration

- `--bucket`: S3 bucket name (required)
- `--pdf-path`: S3 path/prefix for input PDFs (required, e.g., "pdfs/" or "data/pdfs")
- `--json-path`: S3 path/prefix for output JSONs (required, e.g., "json/" or "data/json")
- `--projects-path`: Optional S3 path/prefix for project JSONs (default: `{json-path}/projects/`)
- `--metadata-path`: Optional S3 path/prefix for metadata files (default: `{json-path}/metadata/`)
- `--aws-region`: AWS region (default: "us-east-1")

### Filtering Options

- `--list-only`: Only list files and store list, do not process
- `--serial-range START END`: Process files with serial numbers in range (inclusive)
- `--updated-after DATETIME`: Only process files updated after this datetime (ISO format)
- `--last-hours N`: Only process files updated in last N hours (e.g., `--last-hours 4`)
- `--last-n N`: Only process the N most recently updated files (e.g., `--last-n 10`)
- `--filename-pattern PATTERN`: Only process files matching filename pattern (regex)

### Processing Options

- `--no-skip`: Reprocess all files (don't skip existing)
- `--quiet`: Reduce logging verbosity

## S3 Bucket Structure

Single bucket with custom paths (you specify both PDF and JSON paths):

Example structure:
```
s3://my-bucket/
  pdfs/                              # PDF input path (--pdf-path)
    PRM_KA_RERA_1250_301_PR_010422_004807.pdf
    PRM_KA_RERA_1250_304_PR_160522_004883.pdf
    ...
  json/                              # JSON output path (--json-path)
    PRM_KA_RERA_1250_301_PR_010422_004807.json  # Full adaptive JSON
    PRM_KA_RERA_1250_304_PR_160522_004883.json
    ...
    projects/                        # Projects subfolder (default: json-path/projects/)
      PRM_KA_RERA_1250_301_PR_010422_004807.json
      ...
    metadata/                        # Metadata subfolder (default: json-path/metadata/)
      file_list.json
```

Or with fully custom paths:
```
s3://my-bucket/
  data/
    pdfs/                            # Your PDF path
    json/                            # Your JSON path
    projects/                        # Your projects path
    metadata/                        # Your metadata path
```

## File List Metadata

The stored file list (`metadata/file_list.json`) contains:

```json
{
  "generated_at": "2025-12-16T12:00:00+00:00",
  "total_files": 100,
  "files": [
    {
      "key": "pdfs/file1.pdf",
      "filename": "file1.pdf",
      "size": 1234567,
      "last_modified": "2025-12-16T10:00:00+00:00",
      "serial_number": 1
    },
    ...
  ]
}
```

## Serial Number Extraction

The processor attempts to extract serial numbers from filenames using patterns:
- `sno_1`, `sno1`, `SNO 1`
- Leading numbers: `001_file.pdf`
- Underscore-separated numbers: `file_123.pdf`

If no serial number is found, the file will be sorted by filename.

## Error Handling

- Individual file failures don't stop batch processing
- Failed files are logged and counted in statistics
- Temporary files are automatically cleaned up
- S3 operations include retry logic via boto3

## Performance

- Downloads PDFs to temporary directory for processing
- Processes files sequentially (one at a time)
- Skips existing files by default (fast resume)
- Progress updates every 10 files
- Typical processing time: 2-5 seconds per PDF

## Logging

Logs are written to:
- Console (stdout)
- `rera_processing_s3.log` file

## Examples

### Daily Processing (Last 24 Hours)

```bash
python process_rera_pdfs_s3.py \
  --bucket rera-bucket \
  --pdf-path pdfs/ \
  --json-path json/ \
  --last-hours 24
```

### Batch Processing by Range

```bash
# Process files 1-100
python process_rera_pdfs_s3.py \
  --bucket rera-bucket \
  --pdf-path pdfs/ \
  --json-path json/ \
  --serial-range 1 100

# Process files 101-200
python process_rera_pdfs_s3.py \
  --bucket rera-bucket \
  --pdf-path pdfs/ \
  --json-path json/ \
  --serial-range 101 200
```

### Process Specific Project Type

```bash
python process_rera_pdfs_s3.py \
  --bucket rera-bucket \
  --pdf-path pdfs/ \
  --json-path json/ \
  --filename-pattern "PRM_KA_RERA_1250_301"
```

## Troubleshooting

**AWS Credentials Not Found:**
- Set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables
- Or run `aws configure`

**No Files Found:**
- Check bucket name and PDF path
- Verify PDF files exist in the specified path
- Check AWS permissions (s3:ListBucket, s3:GetObject)

**Processing Stuck:**
- Check `rera_processing_s3.log` for errors
- Some PDFs may take longer (large files, complex layouts)
- Verify S3 upload permissions (s3:PutObject)

**Serial Numbers Not Extracted:**
- Check filename patterns
- Serial numbers are optional - files will still be processed
- Files without serial numbers are sorted by filename

