import streamlit as st
import requests
import json
from base64 import b64encode
import pandas as pd
import time

# -----------------
# Load credentials from Streamlit secrets
# -----------------
try:
    login = st.secrets["DATAFORSEO_LOGIN"]
    password = st.secrets["DATAFORSEO_PASSWORD"]
except KeyError:
    st.error("❌ Missing credentials in Streamlit secrets. Please add DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD to your secrets.")
    st.stop()

st.title("🔎 Local Keyword Volume Checker (DataForSEO)")
st.info("🔑 Using DataForSEO credentials from Streamlit secrets")

# Auth setup
auth = b64encode(f"{login}:{password}".encode()).decode()
headers = {
    "Authorization": f"Basic {auth}",
    "Content-Type": "application/json"
}

# -----------------
# Load ALL locations with session state caching (instead of file caching)
# -----------------
CACHE_HOURS = 24  # Refresh cache after 24 hours

def fetch_locations_from_api():
    """Fetch locations from DataForSEO API"""
    loc_url = "https://api.dataforseo.com/v3/app_data/google/locations"
    
    try:
        loc_resp = requests.get(loc_url, headers=headers)
        
        if loc_resp.status_code == 200:
            loc_data = loc_resp.json()
            locations = []
            
            for task in loc_data.get("tasks", []):
                for result in task.get("result", []):
                    locations.append({
                        "name": result["location_name"],
                        "code": result["location_code"],
                        "display": f"{result['location_name']} (code {result['location_code']})"
                    })
            
            return locations
        else:
            st.error(f"API Error: {loc_resp.status_code} - {loc_resp.text}")
            return []
            
    except Exception as e:
        st.error(f"Error fetching locations: {str(e)}")
        return []

def is_cache_fresh():
    """Check if the session state cache is fresh"""
    if 'locations_cache_time' not in st.session_state:
        return False
    
    cache_age_hours = (time.time() - st.session_state.locations_cache_time) / 3600
    return cache_age_hours < CACHE_HOURS

@st.cache_data(ttl=2592000)  # Cache for 30 days across all users
def load_all_locations(force_refresh=False):
    """Load locations with session state caching strategy"""
    
    # Check session state cache first (unless forced refresh)
    if not force_refresh and 'locations_data' in st.session_state and is_cache_fresh():
        cached_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.session_state.locations_cache_time))
        return st.session_state.locations_data, f"Using cached data from {cached_time}"
    
    # Fetch from API
    locations = fetch_locations_from_api()
    
    if locations:
        # Store in session state instead of file
        st.session_state.locations_data = locations
        st.session_state.locations_cache_time = time.time()
        
        return locations, f"Fresh data fetched and cached ({len(locations):,} locations)"
    else:
        # Fallback to session state cache even if expired
        if 'locations_data' in st.session_state:
            cached_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.session_state.locations_cache_time))
            return st.session_state.locations_data, f"API failed - using stale cache from {cached_time}"
        
        return [], "Failed to load locations from API and no cache available"

# Load all locations with caching
with st.spinner("Loading locations..."):
    all_locations, cache_status = load_all_locations()

# Show cache status
if cache_status:
    if "cached data" in cache_status:
        st.info(f"💾 {cache_status}")
    elif "Fresh data" in cache_status:
        st.success(f"🆕 {cache_status}")
    else:
        st.warning(f"⚠️ {cache_status}")

if not all_locations:
    st.error("Could not load locations. Please check your API credentials.")
    st.stop()

# -----------------
# User Inputs
# -----------------
keywords_input = st.text_area("Enter keywords (one per line)")

# Location search/filter
location_search = st.text_input("Search for a location (city, state, ZIP, country)...")

# Filter locations based on search
if location_search and len(location_search.strip()) >= 2:
    search_term = location_search.strip().lower()
    filtered_locations = [
        loc for loc in all_locations 
        if search_term in loc["name"].lower()
    ][:50]  # Limit to 50 results for performance
else:
    filtered_locations = all_locations[:50]  # Show first 50 by default

# Location selection dropdown
if filtered_locations:
    display_options = [loc["display"] for loc in filtered_locations]
    
    selected_display = st.selectbox(
        f"Select location ({len(filtered_locations)} matches):",
        [""] + display_options,  # Empty option first
        index=0
    )
    
    if selected_display:
        # Find the selected location
        selected_location = next(
            loc for loc in filtered_locations 
            if loc["display"] == selected_display
        )
        
        selected_location_name = selected_location["name"]
        selected_location_code = selected_location["code"]
        
        st.success(f"✅ Selected: **{selected_location_name}** (Code: {selected_location_code})")
    else:
        selected_location_code = None
        selected_location_name = None
else:
    st.warning("No locations found matching your search.")
    selected_location_code = None
    selected_location_name = None

language_code = st.text_input("Language Code", value="en")

# Add debug toggle
debug_mode = st.checkbox("Show API debug info")

# -----------------
# Run keyword volume check
# -----------------
if st.button("Get Search Volumes"):
    if not keywords_input.strip():
        st.error("Please enter keywords.")
        st.stop()
        
    if not selected_location_code:
        st.error("Please select a location.")
        st.stop()
    
    # Keyword volume lookup
    vol_url = "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live"
    keywords = [k.strip() for k in keywords_input.split("\n") if k.strip()]
    vol_payload = [{
        "keywords": keywords,
        "language_code": language_code,
        "location_code": selected_location_code
    }]
    
    # Debug: Show what we're sending
    if debug_mode:
        st.subheader("🔍 Debug: Request Payload")
        st.json(vol_payload[0])
    
    with st.spinner("Getting search volumes..."):
        vol_resp = requests.post(vol_url, headers=headers, data=json.dumps(vol_payload))
        
        if vol_resp.status_code != 200:
            st.error(f"Volume API Error: {vol_resp.status_code} – {vol_resp.text}")
            st.stop()
        
        vol_data = vol_resp.json()
        
        # Debug: Show raw API response
        if debug_mode:
            st.subheader("🔍 Debug: Raw API Response")
            st.json(vol_data)
        
        results = []
        
        # More detailed parsing with error checking
        if "tasks" in vol_data:
            for task_idx, task in enumerate(vol_data["tasks"]):
                if debug_mode:
                    st.write(f"Task {task_idx}: Status code = {task.get('status_code')}")
                
                if task.get("status_code") == 20000:  # Success code
                    result_items = task.get("result", [])
                    
                    if debug_mode:
                        st.write(f"Found {len(result_items)} keyword results")
                    
                    for item in result_items:
                        cpc_value = item.get('cpc', 0)
                        cpc_formatted = f"${cpc_value:.2f}" if cpc_value else "N/A"
                        
                        results.append({
                            "Keyword": item.get("keyword", "N/A"), 
                            "Search Volume": item.get("search_volume", 0),
                            "Competition": item.get("competition", "N/A"),
                            "CPC": cpc_formatted,
                            "Location": selected_location_name
                        })
                else:
                    st.warning(f"Task failed with status code: {task.get('status_code')} - {task.get('status_message', 'Unknown error')}")
        
        if results:
            st.subheader(f"📊 Results for {selected_location_name}")
            df = pd.DataFrame(results)
            st.dataframe(df)
            
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv_bytes, "keyword_volumes.csv", "text/csv")
        else:
            st.error("❌ No results returned. Check debug info above to see what went wrong.")

# -----------------
# Location refresh at bottom
# -----------------
st.markdown("---")
if st.button("🔄 Refresh Location Database"):
    st.cache_data.clear()  # Clear streamlit cache
    # Clear session state cache
    if 'locations_data' in st.session_state:
        del st.session_state.locations_data
    if 'locations_cache_time' in st.session_state:
        del st.session_state.locations_cache_time
    
    with st.spinner("Fetching fresh location data..."):
        all_locations, cache_status = load_all_locations(force_refresh=True)
    st.success("Location database refreshed!")
    st.rerun()
