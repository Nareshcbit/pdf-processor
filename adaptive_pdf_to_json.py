#!/usr/bin/env python3
"""
Fully Adaptive PDF-to-JSON Converter for RERA Karnataka PDFs
No fixed schema - adapts to any PDF layout, structure, and content type.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def is_scanned_pdf(pdf_path: str) -> bool:
    """
    Detect if PDF is scanned (image-based) by checking if it has extractable text.
    Returns True if PDF appears to be scanned (no/minimal text layer).
    """
    try:
        if pdfplumber:
            with pdfplumber.open(pdf_path) as pdf:
                # Check first few pages for text
                text_found = False
                pages_to_check = min(3, len(pdf.pages))
                for i in range(pages_to_check):
                    page = pdf.pages[i]
                    text = page.extract_text()
                    if text and len(text.strip()) > 50:  # Reasonable amount of text
                        text_found = True
                        break
                return not text_found
        elif fitz:
            doc = fitz.open(pdf_path)
            text_found = False
            pages_to_check = min(3, len(doc))
            for i in range(pages_to_check):
                page = doc[i]
                text = page.get_text()
                if text and len(text.strip()) > 50:
                    text_found = True
                    break
            doc.close()
            return not text_found
    except Exception as e:
        logger.warning(f"Error detecting scanned PDF: {e}")
        return False
    return True


def extract_with_ocr(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extract text from scanned PDF using OCR (pytesseract).
    Returns list of page dictionaries with extracted text.
    """
    if not fitz or not pytesseract or not Image:
        raise ImportError("PyMuPDF and pytesseract required for OCR")
    
    pages_data = []
    doc = fitz.open(pdf_path)
    
    logger.info(f"Running OCR on {len(doc)} pages...")
    for page_num in range(len(doc)):
        page = doc[page_num]
        # Convert page to image
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better OCR
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Run OCR
        try:
            ocr_text = pytesseract.image_to_string(img, lang='eng')
            pages_data.append({
                "page_number": page_num + 1,
                "text": ocr_text,
                "extraction_method": "OCR"
            })
            logger.info(f"  Page {page_num + 1}: Extracted {len(ocr_text)} characters via OCR")
        except Exception as e:
            logger.warning(f"  Page {page_num + 1}: OCR failed - {e}")
            pages_data.append({
                "page_number": page_num + 1,
                "text": "",
                "extraction_method": "OCR_FAILED"
            })
    
    doc.close()
    return pages_data


def extract_key_value_pairs(text: str) -> Dict[str, str]:
    """
    Extract key-value pairs from text using various patterns:
    - "Key: Value"
    - "Key - Value"
    - "Key → Value"
    - Bold text followed by regular text
    """
    kv_pairs = {}
    
    # Pattern 1: "Key: Value"
    pattern1 = r'([^:\n]+?)\s*:\s*([^\n]+?)(?=\n|$)'
    matches = re.findall(pattern1, text, re.MULTILINE)
    for key, value in matches:
        key = key.strip()
        value = value.strip()
        if key and value and len(key) < 100:  # Reasonable key length
            # Clean up key (remove special chars, convert to snake_case)
            clean_key = re.sub(r'[^\w\s]', '', key).strip().lower().replace(' ', '_')
            if clean_key:
                kv_pairs[clean_key] = value
    
    # Pattern 2: "Key - Value"
    pattern2 = r'([^-\n]+?)\s+-\s+([^\n]+?)(?=\n|$)'
    matches = re.findall(pattern2, text, re.MULTILINE)
    for key, value in matches:
        key = key.strip()
        value = value.strip()
        if key and value and len(key) < 100:
            clean_key = re.sub(r'[^\w\s]', '', key).strip().lower().replace(' ', '_')
            if clean_key and clean_key not in kv_pairs:
                kv_pairs[clean_key] = value
    
    return kv_pairs


def detect_heading(text: str, font_size: Optional[float] = None, is_bold: bool = False) -> bool:
    """
    Detect if a text line is likely a heading.
    Criteria: short line, possibly bold, possibly larger font, or ALL CAPS.
    """
    text = text.strip()
    if not text:
        return False
    
    # Short lines are often headings
    if len(text) < 80:
        # ALL CAPS is often a heading
        if text.isupper() and len(text) > 3:
            return True
        # Bold text is often a heading
        if is_bold:
            return True
        # Large font is often a heading
        if font_size and font_size > 12:
            return True
    
    return False


def normalize_section_name(heading: str) -> str:
    """
    Convert heading text to a clean section key (lower_snake_case, no special chars).
    """
    # Remove special characters, keep only alphanumeric and spaces
    clean = re.sub(r'[^\w\s]', '', heading)
    # Convert to lowercase and replace spaces with underscores
    clean = clean.lower().strip().replace(' ', '_')
    # Remove multiple underscores
    clean = re.sub(r'_+', '_', clean)
    # Remove leading/trailing underscores
    clean = clean.strip('_')
    return clean if clean else "unnamed_section"


def extract_tables_pdfplumber(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extract all tables from PDF using pdfplumber.
    Returns list of table dictionaries.
    """
    tables = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_tables = page.extract_tables()
                if page_tables:
                    logger.info(f"  Page {page_num}: Found {len(page_tables)} table(s)")
                    for table_idx, table in enumerate(page_tables):
                        if table and len(table) > 0:
                            # Try to detect if first row is header
                            has_header = False
                            table_data = []
                            
                            if len(table) > 1:
                                # Check if first row looks like headers (short, non-numeric values)
                                first_row = table[0]
                                if first_row and all(
                                    cell and isinstance(cell, str) and 
                                    len(cell.strip()) < 50 and 
                                    not re.match(r'^\d+[.,]?\d*$', cell.strip())
                                    for cell in first_row[:5] if cell
                                ):
                                    has_header = True
                                    headers = [str(cell).strip() if cell else f"col_{i}" 
                                              for i, cell in enumerate(first_row)]
                                    # Convert remaining rows to dicts
                                    for row in table[1:]:
                                        if row and any(cell for cell in row):
                                            row_dict = {}
                                            for i, cell in enumerate(row):
                                                key = headers[i] if i < len(headers) else f"col_{i}"
                                                row_dict[key] = str(cell).strip() if cell else ""
                                            table_data.append(row_dict)
                                else:
                                    # No clear header, use list of lists
                                    for row in table:
                                        if row and any(cell for cell in row):
                                            table_data.append([str(cell).strip() if cell else "" for cell in row])
                            
                            tables.append({
                                "page_number": page_num,
                                "table_index": table_idx,
                                "has_header": has_header,
                                "data": table_data,
                                "row_count": len(table_data),
                                "extraction_method": "pdfplumber"
                            })
    except Exception as e:
        logger.error(f"Error extracting tables with pdfplumber: {e}")
    
    return tables


def extract_text_with_structure_pdfplumber(pdf_path: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Extract text from PDF using pdfplumber, preserving structure.
    Returns (raw_text_by_page, structured_data).
    """
    raw_text_by_page = []
    structured_data = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract raw text
                page_text = page.extract_text() or ""
                raw_text_by_page.append(page_text)
                
                # Extract characters with position and formatting info
                chars = page.chars
                if chars:
                    # Group characters into words/lines with formatting
                    lines_data = []
                    current_line = []
                    current_y = None
                    
                    for char in chars:
                        char_y = round(char['top'], 1)  # Round to group nearby lines
                        
                        if current_y is None:
                            current_y = char_y
                        
                        # If Y position changed significantly, start new line
                        if abs(char_y - current_y) > 2:
                            if current_line:
                                line_text = ''.join([c['text'] for c in current_line])
                                font_size = current_line[0]['size'] if current_line else None
                                is_bold = any(c.get('fontname', '').lower().find('bold') >= 0 for c in current_line)
                                
                                lines_data.append({
                                    "text": line_text.strip(),
                                    "y_position": current_y,
                                    "font_size": font_size,
                                    "is_bold": is_bold,
                                    "is_heading": detect_heading(line_text, font_size, is_bold)
                                })
                                current_line = []
                            current_y = char_y
                        
                        current_line.append(char)
                    
                    # Add last line
                    if current_line:
                        line_text = ''.join([c['text'] for c in current_line])
                        font_size = current_line[0]['size'] if current_line else None
                        is_bold = any(c.get('fontname', '').lower().find('bold') >= 0 for c in current_line)
                        lines_data.append({
                            "text": line_text.strip(),
                            "y_position": current_y,
                            "font_size": font_size,
                            "is_bold": is_bold,
                            "is_heading": detect_heading(line_text, font_size, is_bold)
                        })
                    
                    structured_data.append({
                        "page_number": page_num,
                        "lines": lines_data,
                        "extraction_method": "pdfplumber"
                    })
                    
                    logger.info(f"  Page {page_num}: Extracted {len(lines_data)} lines, "
                              f"{sum(1 for l in lines_data if l['is_heading'])} headings detected")
    
    except Exception as e:
        logger.error(f"Error extracting text with pdfplumber: {e}")
    
    return raw_text_by_page, structured_data


def build_json_structure(
    pdf_path: str,
    raw_text_by_page: List[str],
    structured_data: List[Dict[str, Any]],
    tables: List[Dict[str, Any]],
    is_scanned: bool
) -> Dict[str, Any]:
    """
    Build the final JSON structure from extracted data.
    Intelligently organizes content into sections, key-value pairs, etc.
    """
    pdf_name = Path(pdf_path).name
    
    result = {
        "source_file": pdf_name,
        "extracted_pages": [],
        "raw_text_by_page": raw_text_by_page,
        "detected_tables": tables,
        "key_value_pairs": {},
        "sections": {},
        "unstructured_text": [],
        "metadata": {
            "total_pages": len(raw_text_by_page),
            "is_scanned": is_scanned,
            "extraction_date": datetime.now().isoformat()
        }
    }
    
    # Process structured data to build sections and key-value pairs
    current_section = None
    current_section_key = None
    
    for page_data in structured_data:
        page_num = page_data.get("page_number", 0)
        lines = page_data.get("lines", [])
        
        page_content = {
            "page_number": page_num,
            "headings": [],
            "key_value_pairs": {},
            "paragraphs": [],
            "lists": []
        }
        
        current_paragraph = []
        current_list = []
        in_list = False
        
        for line_info in lines:
            text = line_info.get("text", "").strip()
            if not text:
                continue
            
            is_heading = line_info.get("is_heading", False)
            
            # Detect headings and create sections
            if is_heading:
                # Save current paragraph/list before starting new section
                if current_paragraph:
                    page_content["paragraphs"].append(" ".join(current_paragraph))
                    current_paragraph = []
                if current_list:
                    page_content["lists"].append(current_list)
                    current_list = []
                in_list = False
                
                # Create or switch to section
                section_key = normalize_section_name(text)
                if section_key not in result["sections"]:
                    result["sections"][section_key] = {
                        "heading": text,
                        "content": [],
                        "key_value_pairs": {},
                        "tables": []
                    }
                
                current_section = result["sections"][section_key]
                current_section_key = section_key
                page_content["headings"].append(text)
                logger.info(f"    Detected heading: '{text}' → section '{section_key}'")
            
            # Detect key-value pairs
            elif ":" in text or " - " in text or "→" in text:
                kv_pairs = extract_key_value_pairs(text)
                if kv_pairs:
                    for key, value in kv_pairs.items():
                        if current_section:
                            current_section["key_value_pairs"][key] = value
                        else:
                            result["key_value_pairs"][key] = value
                        page_content["key_value_pairs"][key] = value
            
            # Detect lists (lines starting with bullet, number, or dash)
            elif re.match(r'^[\s]*[•\-\*\d+\.]\s+', text) or text.startswith("- ") or text.startswith("•"):
                in_list = True
                current_list.append(text)
                if current_paragraph:
                    page_content["paragraphs"].append(" ".join(current_paragraph))
                    current_paragraph = []
            
            # Regular paragraph text
            else:
                if in_list and current_list:
                    page_content["lists"].append(current_list)
                    current_list = []
                in_list = False
                current_paragraph.append(text)
        
        # Save remaining paragraph/list
        if current_paragraph:
            page_content["paragraphs"].append(" ".join(current_paragraph))
        if current_list:
            page_content["lists"].append(current_list)
        
        # Add paragraphs to current section or unstructured
        for para in page_content["paragraphs"]:
            if current_section:
                current_section["content"].append(para)
            else:
                result["unstructured_text"].append({
                    "page": page_num,
                    "text": para
                })
        
        result["extracted_pages"].append(page_content)
    
    # Associate tables with sections based on proximity
    for table in tables:
        table_page = table.get("page_number", 0)
        # Try to find a section that was created on the same page
        table_added = False
        for section_key, section in result["sections"].items():
            # Simple heuristic: if table is on a page with a section, add it
            # (In a more sophisticated version, we'd check actual Y positions)
            if not table_added:
                section["tables"].append(table)
                table_added = True
                break
        
        if not table_added:
            # Keep table at top level
            pass
    
    return result


def adaptive_pdf_to_json(pdf_path: str) -> dict:
    """
    Main function: Convert PDF to adaptive JSON structure.
    Tries pdfplumber first, falls back to PyMuPDF + OCR if needed.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {pdf_path.name}")
    logger.info(f"{'='*60}")
    
    # Detect if scanned
    is_scanned = is_scanned_pdf(str(pdf_path))
    logger.info(f"PDF type: {'SCANNED (image-based)' if is_scanned else 'TEXT-BASED'}")
    
    raw_text_by_page = []
    structured_data = []
    tables = []
    
    # Try pdfplumber first
    if pdfplumber and not is_scanned:
        try:
            logger.info("Using pdfplumber for extraction...")
            raw_text_by_page, structured_data = extract_text_with_structure_pdfplumber(str(pdf_path))
            tables = extract_tables_pdfplumber(str(pdf_path))
            logger.info(f"Successfully extracted {len(raw_text_by_page)} pages with pdfplumber")
        except Exception as e:
            logger.warning(f"pdfplumber failed: {e}, trying PyMuPDF...")
            is_scanned = True  # Force OCR path
    
    # Fallback to PyMuPDF + OCR for scanned PDFs
    if is_scanned or not raw_text_by_page:
        if fitz and pytesseract:
            try:
                logger.info("Using PyMuPDF + OCR for extraction...")
                ocr_pages = extract_with_ocr(str(pdf_path))
                raw_text_by_page = [page["text"] for page in ocr_pages]
                
                # Convert OCR results to structured format
                for page_data in ocr_pages:
                    page_num = page_data["page_number"]
                    text = page_data["text"]
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    structured_data.append({
                        "page_number": page_num,
                        "lines": [{"text": line, "y_position": 0, "font_size": None, 
                                  "is_bold": False, "is_heading": detect_heading(line)} 
                                 for line in lines],
                        "extraction_method": "OCR"
                    })
                logger.info(f"Successfully extracted {len(raw_text_by_page)} pages with OCR")
            except Exception as e:
                logger.error(f"OCR extraction failed: {e}")
                raise
        else:
            raise ImportError("PyMuPDF and pytesseract required for scanned PDFs")
    
    # Build JSON structure
    logger.info("Building JSON structure...")
    result = build_json_structure(
        str(pdf_path),
        raw_text_by_page,
        structured_data,
        tables,
        is_scanned
    )
    
    logger.info(f"✓ Extraction complete:")
    logger.info(f"  - Pages: {result['metadata']['total_pages']}")
    logger.info(f"  - Sections: {len(result['sections'])}")
    logger.info(f"  - Tables: {len(result['detected_tables'])}")
    logger.info(f"  - Key-value pairs: {len(result['key_value_pairs'])}")
    
    return result


def batch_convert(folder_in: str, folder_out: str):
    """
    Batch convert all PDFs in folder_in to JSON files in folder_out.
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
    
    for pdf_file in pdf_files:
        try:
            # Convert to JSON
            json_data = adaptive_pdf_to_json(pdf_file)
            
            # Save JSON file
            json_filename = pdf_file.stem + ".json"
            json_path = folder_out / json_filename
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✓ Saved: {json_path}\n")
            successful += 1
            
        except Exception as e:
            logger.error(f"✗ Failed to process {pdf_file.name}: {e}\n")
            failed += 1
    
    logger.info(f"\n{'#'*60}")
    logger.info(f"BATCH CONVERSION COMPLETE")
    logger.info(f"  Successful: {successful}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"{'#'*60}\n")


if __name__ == "__main__":
    batch_convert("inputs/", "outputs/")

