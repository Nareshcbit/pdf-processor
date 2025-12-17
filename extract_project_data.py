#!/usr/bin/env python3
"""
Extract structured project data from adaptive PDF JSON files for Google Maps visualization.
Intelligently parses the adaptive JSON to extract key project information.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

def clean_text(text: str) -> str:
    """Clean and normalize text."""
    if not text:
        return ""
    # Remove extra whitespace and newlines
    text = re.sub(r'\s+', ' ', text.strip())
    return text

def extract_number(text: str) -> Optional[int]:
    """Extract first number from text."""
    if not text:
        return None
    match = re.search(r'(\d+)', str(text).replace(',', ''))
    return int(match.group(1)) if match else None

def extract_float(text: str) -> Optional[float]:
    """Extract first float from text."""
    if not text:
        return None
    match = re.search(r'([\d.]+)', str(text))
    return float(match.group(1)) if match else None

def extract_date(text: str) -> Optional[str]:
    """Extract date in DD-MM-YYYY format."""
    if not text:
        return None
    match = re.search(r'(\d{2}-\d{2}-\d{4})', str(text))
    return match.group(1) if match else None

def parse_project_from_json(json_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse adaptive JSON structure to extract structured project data.
    Handles various formats and missing fields gracefully.
    """
    project = {
        "filename": json_data.get("source_file", ""),
        "project_name": "",
        "description": "",
        "type": "",
        "status": "",
        "start_date": "",
        "completion_date": "",
        "address": "",
        "district": "",
        "taluk": "",
        "pin_code": "",
        "latitude": None,
        "longitude": None,
        "approving_authority": "",
        "plan_number": "",
        "approval_date": "",
        "total_plots": 0,
        "covered_area": 0,
        "parks_count": 0,
        "parks_area": 0,
        "ca_sites_count": 0,
        "ca_area": 0,
        "roads_area": 0,
        "open_area": 0,
        "land_area": 0,
        "cost_land": 0,
        "cost_development": 0,
        "total_cost": 0,
        "water_source": "",
        "plot_types": [],
        "plots": []
    }
    
    # Combine all text for regex searching
    all_text = ""
    key_value_pairs = {}
    
    # Collect key-value pairs from top level and pages
    if "key_value_pairs" in json_data:
        key_value_pairs.update(json_data["key_value_pairs"])
    
    # Collect text from all pages
    if "raw_text_by_page" in json_data:
        all_text = "\n".join(json_data["raw_text_by_page"])
    
    # Also check extracted_pages for additional key-value pairs
    if "extracted_pages" in json_data:
        for page in json_data["extracted_pages"]:
            if "key_value_pairs" in page:
                key_value_pairs.update(page["key_value_pairs"])
            if "paragraphs" in page:
                all_text += "\n" + "\n".join(page["paragraphs"])
    
    # Extract from key_value_pairs first (most reliable)
    kv = key_value_pairs
    
    # Project name
    if "project_name" in kv:
        project["project_name"] = clean_text(kv["project_name"]).split("Project Description")[0].strip()
    elif "project_name" in json_data:
        project["project_name"] = clean_text(json_data["project_name"])
    
    # Description
    desc_match = re.search(r'Project Description[:\s]+(.*?)(?:Project Type|Project Status|$)', all_text, re.IGNORECASE | re.DOTALL)
    if desc_match:
        project["description"] = clean_text(desc_match.group(1))
    elif "description" in kv:
        project["description"] = clean_text(kv["description"])
    
    # Type
    type_match = re.search(r'Project Type[:\s]+(.*?)(?:Project Status|$)', all_text, re.IGNORECASE)
    if type_match:
        project["type"] = clean_text(type_match.group(1))
    elif "project_type" in kv:
        project["type"] = clean_text(kv["project_type"]).split("Project Status")[0].strip()
    
    # Status
    status_match = re.search(r'Project Status[:\s]+(.*?)(?:Start Date|Proposed|$)', all_text, re.IGNORECASE)
    if status_match:
        project["status"] = clean_text(status_match.group(1))
    elif "project_status" in kv:
        project["status"] = clean_text(kv["project_status"])
    
    # Dates
    if "project_start_date" in kv:
        date_str = kv["project_start_date"]
        project["start_date"] = extract_date(date_str) or ""
        project["completion_date"] = extract_date(date_str.split("Proposed Completion Date")[-1] if "Proposed Completion Date" in date_str else "") or ""
    
    start_match = re.search(r'Start Date[:\s]+(?:At the time of Registration[:\s]+)?(\d{2}-\d{2}-\d{4})', all_text, re.IGNORECASE)
    if start_match:
        project["start_date"] = start_match.group(1)
    
    completion_match = re.search(r'Proposed Completion Date[:\s]+(\d{2}-\d{2}-\d{4})', all_text, re.IGNORECASE)
    if completion_match:
        project["completion_date"] = completion_match.group(1)
    
    # Address components
    if "project_address" in kv:
        project["address"] = clean_text(kv["project_address"])
    
    if "district" in kv:
        project["district"] = clean_text(kv["district"])
    
    if "taluk" in kv:
        project["taluk"] = clean_text(kv["taluk"])
    
    if "pin_code" in kv:
        project["pin_code"] = clean_text(kv["pin_code"])
    
    # Coordinates - Handle multiple formats
    # Format 1: Simple latitude/longitude
    # Format 2: Boundary coordinates (North/East/West/South latitude/longitude)
    # Format 3: Combined strings like "0North Longitude:0"
    
    def is_valid_coord(value: float, coord_type: str) -> bool:
        """Check if coordinate is valid (not 0.0 and within Karnataka range)."""
        if not value or value == 0.0:
            return False
        if coord_type == "lat":
            return 10 < value < 17  # Karnataka latitude range
        elif coord_type == "lon":
            return 73 < value < 79  # Karnataka longitude range
        return False
    
    def parse_combined_coord(text: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Parse combined coordinate strings like "0North Longitude:0" or "13.2East Longitude:77.5"
        Format: "latValueDirection Longitude:lonValue" where first number is lat, second is lon
        Returns (latitude, longitude) or (None, None) if not found or invalid
        """
        if not text:
            return None, None
        
        # Pattern: "numberNorth Longitude:number" or "numberEast Longitude:number"
        # First number is latitude, second (after Longitude:) is longitude
        pattern = r'^([\d.]+)\s*(?:North|East|West|South)\s*Longitude[:\s]*([\d.]+)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            lat_val = extract_float(match.group(1))
            lon_val = extract_float(match.group(2))
            # Validate both are non-zero and in valid ranges
            if lat_val and lon_val and lat_val != 0.0 and lon_val != 0.0:
                if is_valid_coord(lat_val, "lat") and is_valid_coord(lon_val, "lon"):
                    return lat_val, lon_val
        
        return None, None
    
    # Try simple latitude/longitude first
    if "latitude" in kv:
        lat = extract_float(kv["latitude"])
        if lat and is_valid_coord(lat, "lat"):
            project["latitude"] = lat
    
    if "longitude" in kv:
        lon = extract_float(kv["longitude"])
        if lon and is_valid_coord(lon, "lon"):
            project["longitude"] = lon
    
    # Try boundary coordinates (North/East/West/South)
    boundary_coords = {
        'north_lat': None,
        'north_lon': None,
        'east_lat': None,
        'east_lon': None,
        'west_lat': None,
        'west_lon': None,
        'south_lat': None,
        'south_lon': None
    }
    
    # Extract boundary coordinates from key_value_pairs
    for key, value in kv.items():
        if not value:
            continue
        
        # Handle combined format like "0North Longitude:0" or "13.2North Longitude:77.5"
        # Format: "latValueNorth Longitude:lonValue" where first number is lat, second is lon
        if isinstance(value, str) and 'longitude' in value.lower():
            # Pattern: "numberNorth Longitude:number" or "numberEast Longitude:number"
            pattern = r'^([\d.]+)\s*(?:North|East|West|South)\s*Longitude[:\s]*([\d.]+)'
            match = re.search(pattern, value, re.IGNORECASE)
            if match:
                lat_val = extract_float(match.group(1))
                lon_val = extract_float(match.group(2))
                
                # Determine which boundary based on key name
                if 'north' in key.lower() and 'latitude' in key.lower():
                    if lat_val and lat_val != 0.0 and is_valid_coord(lat_val, "lat"):
                        boundary_coords['north_lat'] = lat_val
                    if lon_val and lon_val != 0.0 and is_valid_coord(lon_val, "lon"):
                        boundary_coords['north_lon'] = lon_val
                elif 'east' in key.lower() and 'latitude' in key.lower():
                    if lat_val and lat_val != 0.0 and is_valid_coord(lat_val, "lat"):
                        boundary_coords['east_lat'] = lat_val
                    if lon_val and lon_val != 0.0 and is_valid_coord(lon_val, "lon"):
                        boundary_coords['east_lon'] = lon_val
                elif 'west' in key.lower() and 'latitude' in key.lower():
                    if lat_val and lat_val != 0.0 and is_valid_coord(lat_val, "lat"):
                        boundary_coords['west_lat'] = lat_val
                    if lon_val and lon_val != 0.0 and is_valid_coord(lon_val, "lon"):
                        boundary_coords['west_lon'] = lon_val
                elif 'south' in key.lower() and 'latitude' in key.lower():
                    if lat_val and lat_val != 0.0 and is_valid_coord(lat_val, "lat"):
                        boundary_coords['south_lat'] = lat_val
                    if lon_val and lon_val != 0.0 and is_valid_coord(lon_val, "lon"):
                        boundary_coords['south_lon'] = lon_val
        
        # Handle separate fields
        if 'north_latitude' in key.lower():
            val = extract_float(str(value))
            if val and is_valid_coord(val, "lat"):
                boundary_coords['north_lat'] = val
        elif 'north_longitude' in key.lower():
            val = extract_float(str(value))
            if val and is_valid_coord(val, "lon"):
                boundary_coords['north_lon'] = val
        elif 'east_latitude' in key.lower():
            val = extract_float(str(value))
            if val and is_valid_coord(val, "lat"):
                boundary_coords['east_lat'] = val
        elif 'east_longitude' in key.lower():
            val = extract_float(str(value))
            if val and is_valid_coord(val, "lon"):
                boundary_coords['east_lon'] = val
        elif 'west_latitude' in key.lower():
            val = extract_float(str(value))
            if val and is_valid_coord(val, "lat"):
                boundary_coords['west_lat'] = val
        elif 'west_longitude' in key.lower():
            val = extract_float(str(value))
            if val and is_valid_coord(val, "lon"):
                boundary_coords['west_lon'] = val
        elif 'south_latitude' in key.lower():
            val = extract_float(str(value))
            if val and is_valid_coord(val, "lat"):
                boundary_coords['south_lat'] = val
        elif 'south_longitude' in key.lower():
            val = extract_float(str(value))
            if val and is_valid_coord(val, "lon"):
                boundary_coords['south_lon'] = val
    
    # Calculate center point from boundary coordinates if available
    lats = [v for v in [boundary_coords['north_lat'], boundary_coords['south_lat'], 
                        boundary_coords['east_lat'], boundary_coords['west_lat']] if v]
    lons = [v for v in [boundary_coords['north_lon'], boundary_coords['south_lon'], 
                        boundary_coords['east_lon'], boundary_coords['west_lon']] if v]
    
    if lats and lons and not project["latitude"]:
        # Calculate center as average of min/max
        center_lat = (min(lats) + max(lats)) / 2
        center_lon = (min(lons) + max(lons)) / 2
        if is_valid_coord(center_lat, "lat") and is_valid_coord(center_lon, "lon"):
            project["latitude"] = center_lat
            project["longitude"] = center_lon
    
    # Also try regex from text for simple format
    if not project["latitude"]:
        lat_match = re.search(r'(?:^|\s)Latitude[:\s]+([\d.]+)', all_text, re.IGNORECASE | re.MULTILINE)
        if lat_match:
            lat_val = float(lat_match.group(1))
            if is_valid_coord(lat_val, "lat"):
                project["latitude"] = lat_val
    
    if not project["longitude"]:
        lon_match = re.search(r'(?:^|\s)Longitude[:\s]+([\d.]+)', all_text, re.IGNORECASE | re.MULTILINE)
        if lon_match:
            lon_val = float(lon_match.group(1))
            if is_valid_coord(lon_val, "lon"):
                project["longitude"] = lon_val
    
    # Try to extract boundary coordinates from text
    if not project["latitude"] or not project["longitude"]:
        # Look for patterns like "North Latitude : 13.2 North Longitude : 77.5"
        boundary_patterns = [
            (r'North\s+Latitude[:\s]+([\d.]+)', 'north_lat'),
            (r'North\s+Longitude[:\s]+([\d.]+)', 'north_lon'),
            (r'East\s+Latitude[:\s]+([\d.]+)', 'east_lat'),
            (r'East\s+Longitude[:\s]+([\d.]+)', 'east_lon'),
            (r'West\s+Latitude[:\s]+([\d.]+)', 'west_lat'),
            (r'West\s+Longitude[:\s]+([\d.]+)', 'west_lon'),
            (r'South\s+Latitude[:\s]+([\d.]+)', 'south_lat'),
            (r'South\s+Longitude[:\s]+([\d.]+)', 'south_lon'),
        ]
        
        for pattern, coord_key in boundary_patterns:
            match = re.search(pattern, all_text, re.IGNORECASE)
            if match:
                val = extract_float(match.group(1))
                if val:
                    if 'lat' in coord_key and is_valid_coord(val, "lat"):
                        boundary_coords[coord_key] = val
                    elif 'lon' in coord_key and is_valid_coord(val, "lon"):
                        boundary_coords[coord_key] = val
        
        # Recalculate center if we found boundary coordinates
        lats = [v for v in [boundary_coords['north_lat'], boundary_coords['south_lat'], 
                            boundary_coords['east_lat'], boundary_coords['west_lat']] if v]
        lons = [v for v in [boundary_coords['north_lon'], boundary_coords['south_lon'], 
                            boundary_coords['east_lon'], boundary_coords['west_lon']] if v]
        
        if lats and lons:
            center_lat = (min(lats) + max(lats)) / 2
            center_lon = (min(lons) + max(lons)) / 2
            if is_valid_coord(center_lat, "lat") and is_valid_coord(center_lon, "lon"):
                project["latitude"] = center_lat
                project["longitude"] = center_lon
    
    # Approving authority
    if "approving_authority" in kv:
        project["approving_authority"] = clean_text(kv["approving_authority"])
    
    # Plan number and approval date
    if "approved_plan_number" in kv:
        plan_text = kv["approved_plan_number"]
        plan_match = re.search(r'([A-Z0-9/_-]+)', plan_text)
        if plan_match:
            project["plan_number"] = plan_match.group(1)
        approval_match = re.search(r'Plan Approval Date[:\s]+(\d{2}-\d{2}-\d{4})', plan_text)
        if approval_match:
            project["approval_date"] = approval_match.group(1)
    
    # Water source
    if "source_of_water" in kv:
        project["water_source"] = clean_text(kv["source_of_water"]).rstrip(',').strip()
    
    water_match = re.search(r'Source of Water[:\s]+(.*?)(?:,|\n|$)', all_text, re.IGNORECASE)
    if water_match and not project["water_source"]:
        project["water_source"] = clean_text(water_match.group(1)).rstrip(',').strip()
    
    # Extract numbers from text using regex
    # Total plots
    plots_match = re.search(r'Total Number of Sites/Plots[:\s]*(\d+)', all_text, re.IGNORECASE)
    if plots_match:
        project["total_plots"] = int(plots_match.group(1))
    elif "number_of_plots" in kv:
        project["total_plots"] = extract_number(kv["number_of_plots"]) or 0
    
    # Areas
    covered_match = re.search(r'Total Covered Area[^A]*A[:\s]*(\d+)', all_text, re.IGNORECASE)
    if covered_match:
        project["covered_area"] = int(covered_match.group(1))
    
    parks_count_match = re.search(r'Total Number of Parks[^0-9]*(\d+)', all_text, re.IGNORECASE)
    if parks_count_match:
        project["parks_count"] = int(parks_count_match.group(1))
    
    parks_area_match = re.search(r'Total Area of Parks[^B]*B1[:\s]*(\d+)', all_text, re.IGNORECASE)
    if parks_area_match:
        project["parks_area"] = int(parks_area_match.group(1))
    
    ca_count_match = re.search(r'Total Number of CA Sites[:\s]*(\d+)', all_text, re.IGNORECASE)
    if ca_count_match:
        project["ca_sites_count"] = int(ca_count_match.group(1))
    
    ca_area_match = re.search(r'Total Area of CA Sites[^B]*B2[:\s]*(\d+)', all_text, re.IGNORECASE)
    if ca_area_match:
        project["ca_area"] = int(ca_area_match.group(1))
    
    roads_match = re.search(r'Total Area of Roads[^B]*B3[:\s]*(\d+)', all_text, re.IGNORECASE)
    if roads_match:
        project["roads_area"] = int(roads_match.group(1))
    
    open_match = re.search(r'Total Open Area[^=]*=[:\s]*(\d+)', all_text, re.IGNORECASE)
    if open_match:
        project["open_area"] = int(open_match.group(1))
    
    land_match = re.search(r'Total Area Land[^+]*\+[:\s]*(\d+)', all_text, re.IGNORECASE)
    if land_match:
        project["land_area"] = int(land_match.group(1))
    
    # Costs
    cost_land_match = re.search(r'Cost of Land[^0-9]*\(C1\)[:\s]*(\d+)', all_text, re.IGNORECASE)
    if cost_land_match:
        project["cost_land"] = int(cost_land_match.group(1))
    else:
        # Try to find in sections
        for section_key, section in json_data.get("sections", {}).items():
            if "cost_of_land" in section_key.lower():
                content = " ".join(section.get("content", []))
                num = extract_number(content)
                if num:
                    project["cost_land"] = num
                    break
    
    cost_dev_match = re.search(r'Cost of Layout Development[^0-9]*\(C2\)[:\s]*(\d+)', all_text, re.IGNORECASE)
    if cost_dev_match:
        project["cost_development"] = int(cost_dev_match.group(1))
    
    total_cost_match = re.search(r'Total Project Cost[^:]*\(C1\+C2\)[:\s]*(\d+)', all_text, re.IGNORECASE)
    if total_cost_match:
        project["total_cost"] = int(total_cost_match.group(1))
    
    # Extract plot types from tables
    for table in json_data.get("detected_tables", []):
        if table.get("has_header") and table.get("data"):
            headers = list(table["data"][0].keys()) if table["data"] else []
            # Look for plot type table
            if any("plot" in h.lower() or "type" in h.lower() or "dimension" in h.lower() for h in headers):
                for row in table["data"][1:]:  # Skip header row
                    if isinstance(row, dict):
                        plot_type = {
                            "sl_no": row.get("Sl No.", row.get("sl_no", "")),
                            "type": row.get("Plot Type", row.get("type", row.get("Site Dimension", ""))),
                            "number": extract_number(str(row.get("Number of Sites", row.get("number", row.get("Number", 0))))) or 0,
                            "area": extract_number(str(row.get("Total Area", row.get("area", row.get("Area", 0))))) or 0
                        }
                        if plot_type["type"] and plot_type["number"] > 0:
                            project["plot_types"].append(plot_type)
    
    # Extract individual plots from tables
    for table in json_data.get("detected_tables", []):
        if table.get("has_header") and table.get("data"):
            headers = list(table["data"][0].keys()) if table["data"] else []
            # Look for individual plot table
            if any("plot no" in h.lower() for h in headers) and any("north" in h.lower() or "schedule" in h.lower() for h in headers):
                for row in table["data"][1:]:  # Skip header row
                    if isinstance(row, dict):
                        plot = {
                            "sl_no": str(row.get("Sl No.", row.get("sl_no", ""))),
                            "plot_no": str(row.get("Plot No.", row.get("plot_no", row.get("Plot No", "")))),
                            "type": str(row.get("Plot Type", row.get("type", ""))),
                            "size": str(row.get("Plot Size", row.get("size", row.get("Plot Size", "")))),
                            "area": extract_float(str(row.get("Plot Area", row.get("area", row.get("Area", 0))))) or 0.0,
                            "north": str(row.get("North Schedule", row.get("north", row.get("North", "")))),
                            "south": str(row.get("South Schedule", row.get("south", row.get("South", "")))),
                            "east": str(row.get("East Schedule", row.get("east", row.get("East", "")))),
                            "west": str(row.get("West Schedule", row.get("west", row.get("West", ""))))
                        }
                        if plot["plot_no"]:
                            project["plots"].append(plot)
    
    # Clean up project name if it's still empty
    if not project["project_name"]:
        # Try to extract from filename or first heading
        filename = project["filename"].replace(".pdf", "").replace("_", " ")
        project["project_name"] = filename
    
    return project


def extract_all_projects(input_dir: str = "outputs", output_dir: str = "outputs/projects", create_consolidated: bool = False):
    """
    Extract structured project data from all JSON files in input_dir.
    Saves each project as an individual JSON file.
    Optionally creates all_projects.json for map visualization.
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    if not input_path.exists():
        print(f"Error: Input directory '{input_dir}' not found")
        return
    
    # Find all JSON files (excluding all_projects.json and project files)
    json_files = [f for f in input_path.glob("*.json") 
                  if f.name != "all_projects.json" and not f.parent.name == "projects"]
    
    if not json_files:
        print(f"No JSON files found in '{input_dir}'")
        return
    
    print(f"Found {len(json_files)} JSON file(s) to process...")
    
    # Create output directory for individual project files
    output_path.mkdir(parents=True, exist_ok=True)
    
    all_projects = []
    
    for json_file in json_files:
        try:
            print(f"Processing: {json_file.name}")
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            project = parse_project_from_json(json_data)
            
            # Save individual project file using the original PDF filename
            # Extract PDF filename from the source_file field or use JSON filename
            pdf_filename = project.get('filename', json_file.stem)
            # Remove .pdf extension if present
            if pdf_filename.endswith('.pdf'):
                pdf_filename = pdf_filename[:-4]
            # Use the PDF filename as the JSON filename
            project_filename = f"{pdf_filename}.json"
            
            project_file_path = output_path / project_filename
            
            with open(project_file_path, 'w', encoding='utf-8') as f:
                json.dump(project, f, indent=2, ensure_ascii=False)
            
            all_projects.append(project)
            
            print(f"  ✓ Extracted: {project['project_name']}")
            print(f"    Saved to: {project_file_path.name}")
            print(f"    Location: {project['latitude']}, {project['longitude']}")
            print(f"    Plots: {project['total_plots']}, Cost: ₹{project['total_cost']:,}")
            
        except Exception as e:
            print(f"  ✗ Error processing {json_file.name}: {e}")
    
    # Optionally create consolidated file for map
    if create_consolidated:
        consolidated_path = Path(input_dir) / "all_projects.json"
        with open(consolidated_path, 'w', encoding='utf-8') as f:
            json.dump(all_projects, f, indent=2, ensure_ascii=False)
        print(f"\n✓ Also created consolidated file: {consolidated_path} (for map visualization)")
    
    print(f"\n✓ Saved {len(all_projects)} individual project file(s) to {output_path}/")
    print(f"  Projects with coordinates: {sum(1 for p in all_projects if p['latitude'] and p['longitude'])}")


if __name__ == "__main__":
    # Extract to individual files
    # Set create_consolidated=True only if you need all_projects.json for map visualization
    extract_all_projects(create_consolidated=False)  # Individual files only

