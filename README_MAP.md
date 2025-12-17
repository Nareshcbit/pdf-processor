# RERA Karnataka Projects - Google Maps Visualization

This project visualizes RERA Karnataka real estate projects on an interactive Google Map.

## Setup Instructions

### 1. Get Google Maps API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Maps JavaScript API**
4. Go to **Credentials** → **Create Credentials** → **API Key**
5. Copy your API key

### 2. Configure the Map

1. Open `map.html` in a text editor
2. Find this line (around line 200):
   ```html
   <script src="https://maps.googleapis.com/maps/api/js?key=YOUR_API_KEY&callback=initMap" async defer></script>
   ```
3. Replace `YOUR_API_KEY` with your actual API key:
   ```html
   <script src="https://maps.googleapis.com/maps/api/js?key=AIzaSy...your-key-here...&callback=initMap" async defer></script>
   ```

### 3. Extract Project Data

Make sure you've extracted project data from PDFs:

```bash
# Extract structured data from PDF JSON files
python extract_project_data.py
```

This creates individual JSON files in `outputs/projects/` for each project.

### 4. View the Map

**Option A: Local File (Limited)**
- Simply open `map.html` in a web browser
- Note: Due to CORS restrictions, you may need to serve it via a local server

**Option B: Local Server (Recommended)**
```bash
# Using Python 3
python -m http.server 8000

# Or using Node.js
npx http-server

# Then open: http://localhost:8000/map.html
```

**Option C: Deploy Online**
- Upload to GitHub Pages, Netlify, or any static hosting
- The map will work from any URL

## Features

- **Interactive Map**: Click markers to see project details
- **Search**: Filter projects by name
- **Status Filter**: Filter by project status (Ongoing, New Launch, etc.)
- **District/Taluk Filter**: Filter by location
- **Statistics**: See total projects, plots, and investment
- **Info Windows**: Detailed project information including:
  - Project name, description, type, status
  - Total plots, completion date
  - Location (district, taluk)
  - Land area, total cost
  - Water source
  - Plot type breakdown

## File Structure

```
pdf-processor/
├── inputs/              # PDF files
├── outputs/
│   ├── projects/        # Individual project JSON files
│   │   ├── Prestige_Autumn_Leaves.json
│   │   ├── SWARAM_PHASE-1.json
│   │   └── ...
│   └── all_projects.json  # Optional: consolidated file
├── extract_project_data.py  # Extract structured data
├── map.html             # Google Maps interface
└── README_MAP.md        # This file
```

## Adding New Projects

1. Place new PDF files in `inputs/` folder
2. Run the adaptive PDF converter:
   ```bash
   python adaptive_pdf_to_json.py
   ```
3. Extract structured project data:
   ```bash
   python extract_project_data.py
   ```
4. The new projects will automatically appear in `outputs/projects/`
5. Refresh the map page to see new markers

## Troubleshooting

**Map not loading?**
- Check that your Google Maps API key is correct
- Ensure the API is enabled in Google Cloud Console
- Check browser console for errors

**No markers showing?**
- Verify JSON files exist in `outputs/projects/`
- Check that projects have valid latitude/longitude
- Open browser console to see any loading errors

**CORS errors?**
- Use a local server (Option B above) instead of opening file directly
- Or deploy to a web server

## API Key Security

⚠️ **Important**: For production use, restrict your API key:
1. Go to Google Cloud Console → APIs & Services → Credentials
2. Click on your API key
3. Under "Application restrictions", add your domain
4. Under "API restrictions", limit to "Maps JavaScript API"

For development, you can use the key without restrictions, but be careful not to commit it to public repositories.

## Cost

Google Maps JavaScript API has a free tier:
- $200 free credit per month
- Typically covers ~28,000 map loads
- See [Google Maps Pricing](https://developers.google.com/maps/billing-and-pricing/pricing) for details

