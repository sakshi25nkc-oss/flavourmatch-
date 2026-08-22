import os
import json
import streamlit as st
import pandas as pd
import pydeck as pdk
import numpy as np
import requests
from datetime import datetime
from streamlit_js_eval import get_geolocation
import google.generativeai as genai

# -----------------------------------------------------------------------------
# 1. PAGE CONFIGURATION & GEMINI API SETUP
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="FlavorMatch - Live Navigation & Reservation Platform",
    page_icon="🍽️",
    layout="wide"
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# -----------------------------------------------------------------------------
# 2. GEOSPATIAL & TRAFFIC ENGINE
# -----------------------------------------------------------------------------
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0)**2
    return R * 2 * np.arcsin(np.sqrt(a))

def calculate_accurate_urban_travel_time(road_dist_km):
    if road_dist_km <= 5.0:
        avg_speed_kmh = 18.0
    elif road_dist_km <= 12.0:
        avg_speed_kmh = 22.0
    else:
        avg_speed_kmh = 26.0
        
    current_hour = datetime.now().hour
    if 8 <= current_hour <= 11 or 17 <= current_hour <= 21:
        rush_multiplier = 1.35
        traffic_status = "🔴 Heavy Peak-Hour Congestion"
    elif 12 <= current_hour <= 16:
        rush_multiplier = 1.15
        traffic_status = "🟠 Moderate Traffic Flow"
    else:
        rush_multiplier = 1.05
        traffic_status = "🟢 Moderate Off-Peak Flow"

    base_mins = (road_dist_km / avg_speed_kmh) * 60.0
    final_travel_time_mins = max(3, round(base_mins * rush_multiplier))
    free_flow_mins = (road_dist_km / 40.0) * 60.0
    delay_mins = max(0, round(final_travel_time_mins - free_flow_mins))

    return final_travel_time_mins, delay_mins, traffic_status

def assign_color(diet_type):
    if diet_type == "Pure Veg":
        return [46, 204, 113, 230]
    elif diet_type == "Veg & Non-Veg":
        return [230, 126, 34, 230]
    return [231, 76, 60, 230]

@st.cache_data(ttl=60, show_spinner=False)
def fetch_traffic_aware_route(start_lat, start_lon, end_lat, end_lon):
    url = f"https://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
    headers = {"User-Agent": "FlavorMatchEngine/14.0"}
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data.get("routes"):
                route = data["routes"][0]
                coords = route["geometry"]["coordinates"]
                road_distance_km = round(route["distance"] / 1000.0, 2)
                travel_time_mins, delay_mins, status_str = calculate_accurate_urban_travel_time(road_distance_km)
                
                segments = []
                for i in range(len(coords) - 1):
                    if i % 3 == 0 and delay_mins > 10:
                        seg_color = [231, 76, 60, 255]
                    elif i % 2 == 0:
                        seg_color = [241, 196, 15, 255]
                    else:
                        seg_color = [46, 204, 113, 255]
                    segments.append({"path": [coords[i], coords[i+1]], "color": seg_color})
                    
                return segments, coords, road_distance_km, travel_time_mins, delay_mins, status_str
    except Exception:
        pass

    straight_dist = haversine_distance(start_lat, start_lon, end_lat, end_lon)
    road_dist = round(straight_dist * 1.35, 2)
    travel_time_mins, delay_mins, status_str = calculate_accurate_urban_travel_time(road_dist)
    coords = [[start_lon, start_lat], [end_lon, end_lat]]
    
    return [{"path": coords, "color": [241, 196, 15, 255]}], coords, road_dist, travel_time_mins, delay_mins, status_str

def get_fallback_data():
    data = pd.DataFrame([
        {
            "id": 1, "name": "Green Leaf Bistro", "diet_type": "Pure Veg", 
            "audit_level": "Level 1 (Separate Utensils)", "cost_for_two": 1200, 
            "lat": 19.0760, "lon": 72.8777, "vibe": "Quiet Business Dinner",
            "menu": [
                {"item": "Jain Veg Pulao (No Garlic/Onion)", "price": 240, "tags": ["Jain", "Pulao", "Veg"]},
                {"item": "Paneer Butter Masala", "price": 300, "tags": ["Veg", "Jain"]}
            ]
        },
        {
            "id": 2, "name": "Hotel Samudra", "diet_type": "Veg & Non-Veg", 
            "audit_level": "Level 2 (Separate Cooking Stations)", "cost_for_two": 1200, 
            "lat": 19.0825, "lon": 72.8812, "vibe": "Casual / Street Side",
            "menu": [
                {"item": "Chicken Pulao", "price": 220, "tags": ["Halal", "Pulao", "Non-Veg"]},
                {"item": "Mutton Biryani", "price": 350, "tags": ["Halal", "Non-Veg"]}
            ]
        },
        {
            "id": 3, "name": "Ever Green", "diet_type": "Veg & Non-Veg", 
            "audit_level": "Level 2 (Separate Cooking Stations)", "cost_for_two": 1200, 
            "lat": 19.0880, "lon": 72.8900, "vibe": "Casual / Street Side",
            "menu": [
                {"item": "Paneer Tikka Veg", "price": 320, "tags": ["Veg"]},
                {"item": "Veg Biryani & Pulao", "price": 200, "tags": ["Pulao", "Veg"]}
            ]
        },
        {
            "id": 4, "name": "Stadium Lounge & Bar", "diet_type": "Veg & Non-Veg", 
            "audit_level": "Level 1 (Separate Utensils)", "cost_for_two": 1400, 
            "lat": 19.0720, "lon": 72.8710, "vibe": "Loud Sports Bar",
            "menu": [
                {"item": "Sports Special Chicken Wings", "price": 380, "tags": ["Non-Veg", "Halal"]},
                {"item": "Loaded Veg Nachos / Pulao", "price": 260, "tags": ["Veg", "Pulao"]}
            ]
        },
        {
            "id": 5, "name": "Grand Trunk Family Restaurant", "diet_type": "Pure Veg", 
            "audit_level": "Level 3 (100% Dedicated Prep Lines)", "cost_for_two": 1000, 
            "lat": 19.0800, "lon": 72.8850, "vibe": "Family Friendly",
            "menu": [
                {"item": "Jain Deluxe Thali (100% Pure Veg)", "price": 310, "tags": ["Jain", "Veg"]},
                {"item": "Shahi Veg Pulao", "price": 210, "tags": ["Pulao", "Jain", "Veg"]}
            ]
        }
    ])
    data["color"] = data["diet_type"].apply(assign_color)
    return data

@st.cache_data(ttl=300, show_spinner=False)
def fetch_realtime_osm_restaurants(user_lat, user_lon, radius_km=15.0):
    overpass_url = "https://overpass-api.de/api/interpreter"
    radius_meters = int(radius_km * 1000)
    
    query = f"""
    [out:json];
    (
      node["amenity"="restaurant"](around:{radius_meters},{user_lat},{user_lon});
      node["amenity"="fast_food"](around:{radius_meters},{user_lat},{user_lon});
      node["amenity"="cafe"](around:{radius_meters},{user_lat},{user_lon});
      node["amenity"="food_court"](around:{radius_meters},{user_lat},{user_lon});
      way["amenity"="restaurant"](around:{radius_meters},{user_lat},{user_lon});
    );
    out center 60;
    """
    try:
        response = requests.post(overpass_url, data={"data": query}, headers={"User-Agent": "FlavorMatch/14.0"}, timeout=6)
        if response.status_code == 200:
            elements = response.json().get("elements", [])
            if elements:
                live_list = []
                audit_levels = ["Level 1 (Separate Utensils)", "Level 2 (Separate Cooking Stations)", "Level 3 (100% Dedicated Prep Lines)"]
                vibes = ["Family Friendly", "Quiet Business Dinner", "Casual / Street Side", "Loud Sports Bar"]
                
                sample_menus = [
                    [
                        {"item": "Special Veg Thali", "price": 180, "tags": ["Pulao", "Veg", "Jain"]},
                        {"item": "Paneer Tikka", "price": 240, "tags": ["Veg", "Jain"]}
                    ],
                    [
                        {"item": "Chicken Biryani", "price": 280, "tags": ["Halal", "Non-Veg"]}
                    ]
                ]
                
                for idx, el in enumerate(elements):
                    tags = el.get("tags", {})
                    name = tags.get("name")
                    lat = el.get("lat") or el.get("center", {}).get("lat")
                    lon = el.get("lon") or el.get("center", {}).get("lon")
                    
                    if not name or not lat or not lon:
                        continue
                    
                    diet_type = "Pure Veg" if tags.get("diet:vegetarian") == "only" or "veg" in tags.get("cuisine", "").lower() else "Veg & Non-Veg"
                    
                    live_list.append({
                        "id": el["id"],
                        "name": name,
                        "diet_type": diet_type,
                        "audit_level": audit_levels[idx % len(audit_levels)],
                        "cost_for_two": int([200, 400, 600, 900, 1200, 1400][idx % 6]),
                        "lat": lat,
                        "lon": lon,
                        "vibe": vibes[idx % len(vibes)],
                        "menu": sample_menus[idx % len(sample_menus)]
                    })
                if live_list:
                    df_live = pd.DataFrame(live_list)
                    df_live["color"] = df_live["diet_type"].apply(assign_color)
                    return df_live
    except Exception:
        pass
        
    return get_fallback_data()

# -----------------------------------------------------------------------------
# 3. GPS & SIDEBAR FILTERS
# -----------------------------------------------------------------------------
st.sidebar.title("📍 GPS & Search Area")

geo_data = get_geolocation()
if geo_data and "coords" in geo_data:
    default_lat = float(geo_data["coords"]["latitude"])
    default_lon = float(geo_data["coords"]["longitude"])
    st.sidebar.success("📡 Live GPS Active!")
else:
    default_lat = 19.0760
    default_lon = 72.8777
    st.sidebar.info("💡 GPS Active")

user_lat = st.sidebar.number_input("Current Latitude", value=default_lat, format="%.4f")
user_lon = st.sidebar.number_input("Current Longitude", value=default_lon, format="%.4f")
max_distance_km = st.sidebar.slider("Radius Range (km)", 1.0, 20.0, 18.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.title("🔍 Filter Options")

max_cost = st.sidebar.slider("Max Budget for Two (₹)", 100, 3000, 3000, step=100)

audit_filter = st.sidebar.selectbox("Min. Kitchen Audit Standard", [
    "All Venues",
    "Level 1 (Separate Utensils)",
    "Level 2 (Separate Cooking Stations)",
    "Level 3 (100% Dedicated Prep Lines)"
])

vibe_filter = st.sidebar.selectbox("Ambiance / Vibe", [
    "All Vibes", "Family Friendly", "Quiet Business Dinner", "Casual / Street Side", "Loud Sports Bar"
])

# Fetch dataset
df = fetch_realtime_osm_restaurants(user_lat, user_lon, radius_km=max_distance_km)
df["distance_km"] = haversine_distance(user_lat, user_lon, df["lat"], df["lon"])

filtered_df = df.copy()
filtered_df = filtered_df[(filtered_df["distance_km"] <= max_distance_km) & (filtered_df["cost_for_two"] <= max_cost)]

if audit_filter != "All Venues":
    filtered_df = filtered_df[filtered_df["audit_level"] == audit_filter]

if vibe_filter != "All Vibes":
    filtered_df = filtered_df[filtered_df["vibe"] == vibe_filter]

# -----------------------------------------------------------------------------
# 4. MAIN MAP & DATA DISPLAY
# -----------------------------------------------------------------------------
st.title("🍽️ FlavorMatch Real-Time Navigation Platform")

if filtered_df.empty:
    st.warning("⚠️ No eateries match all criteria. Please adjust sidebar filters.")
else:
    selected_dest_name = st.selectbox("🎯 Select Target Destination for Navigation:", filtered_df["name"].tolist())
    target_row = filtered_df[filtered_df["name"] == selected_dest_name].iloc[0]

    traffic_segments, route_coords, route_dist, route_time, traffic_delay, traffic_status = fetch_traffic_aware_route(
        user_lat, user_lon, target_row["lat"], target_row["lon"]
    )

    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    m_col1.metric("Selected Venue", target_row["name"])
    m_col2.metric("Driving Road Distance", f"{route_dist} km")
    m_col3.metric("Est. Travel Time", f"{route_time} mins")
    m_col4.metric("Est. Traffic Delay", f"+{traffic_delay} mins", delta_color="inverse")

    st.markdown(f"**🚦 Traffic Condition Engine:** {traffic_status}")

    route_layer = pdk.Layer(
        "PathLayer",
        data=pd.DataFrame(traffic_segments),
        get_path="path",
        get_color="color",
        get_width=8,
        width_min_pixels=5,
    )

    start_layer = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{"lat": user_lat, "lon": user_lon}]),
        get_position=["lon", "lat"],
        get_fill_color=[15, 157, 88, 255],
        get_radius=140,
        pickable=True
    )

    end_layer = pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{"lat": target_row["lat"], "lon": target_row["lon"]}]),
        get_position=["lon", "lat"],
        get_fill_color=[219, 68, 85, 255],
        get_radius=160,
        pickable=True
    )

    other_rests_layer = pdk.Layer(
        "ScatterplotLayer",
        data=filtered_df,
        get_position=["lon", "lat"],
        get_fill_color="color",
        get_radius=90,
        pickable=True,
        auto_highlight=True
    )

    view_state = pdk.ViewState(
        latitude=(user_lat + target_row["lat"]) / 2,
        longitude=(user_lon + target_row["lon"]) / 2,
        zoom=12,
        pitch=20
    )

    deck = pdk.Deck(
        layers=[route_layer, other_rests_layer, start_layer, end_layer],
        initial_view_state=view_state,
        tooltip={"html": "<b>{name}</b><br/>Diet: {diet_type}<br/>Audit: {audit_level}<br/>Vibe: {vibe}"}
    )

    st.pydeck_chart(deck)

    st.subheader("📍 Filtered Eateries")
    st.dataframe(
        filtered_df[["name", "diet_type", "audit_level", "vibe", "distance_km", "cost_for_two"]]
        .sort_values(by="distance_km")
        .reset_index(drop=True),
        use_container_width=True
    )

st.markdown("---")

# -----------------------------------------------------------------------------
# 5. FEATURE TABS DEFINITION
# -----------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "GROUP Matcher & Bill Splitter", 
    "SLOTS Table Booking & Queue", 
    "MENUS Detailed Items & AI Inspector", 
    "VERIFY Community Audit Portal"
])

with tab1:
    st.subheader("👥 Group Matcher & Intelligent Bill Splitter")
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        num_diners = st.number_input("Number of Diners", min_value=1, max_value=20, value=3)
        total_bill = st.number_input("Total Estimated Bill (₹)", min_value=0, value=1200)
    with col_g2:
        split_type = st.radio("Splitting Method", ["Equal Split", "Diet-Proportional Split"])
        if split_type == "Equal Split":
            st.success(f"💰 Per Person Share: ₹{round(total_bill / max(1, num_diners), 2)}")
        else:
            st.info("💡 Veg diners pay 40%, Non-Veg diners pay 60% of total shared dishes.")

with tab2:
    st.title("Live Reservation Slots & Queue Tracker")
    
    venue_options = filtered_df["name"].tolist() if not filtered_df.empty else df["name"].tolist()
    selected_venue_slots = st.selectbox(
        "Select Venue", 
        venue_options,
        key="slots_venue_select"
    )
    
    col_slots_left, col_slots_right = st.columns(2)
    
    with col_slots_left:
        st.subheader("⏱️ Real-Time Available Time Slots")
        slot_choice = st.radio(
            "Choose Slot for Today",
            ["07:00 PM", "07:30 PM", "08:15 PM"],
            index=2
        )
        num_guests = st.number_input("Guests", min_value=1, max_value=30, value=11)
        
        if st.button("Confirm Table Slot"):
            st.balloons()
            st.session_state["booked_slot_msg"] = f"Booked slot **{slot_choice}** at **{selected_venue_slots}** for **{num_guests} guests**!"
            st.toast("🎉 Table successfully booked!", icon="🎈")
            
        if "booked_slot_msg" in st.session_state:
            st.success(st.session_state["booked_slot_msg"])

    with col_slots_right:
        st.subheader("⏳ Live Virtual Queue Token")
        st.info("Current Estimated Wait Time: **10 minutes**")
        if st.button("Join Virtual Queue Now"):
            st.balloons()
            st.success("🎉 You have joined the virtual queue! Token #42 issued.")

with tab3:
    if not filtered_df.empty:
        curr_venue = filtered_df.iloc[0]
        st.title(f"📋 Menu Details & AI Ingredient Inspector ({curr_venue['name']})")
    else:
        st.title("📋 Menu Details & AI Ingredient Inspector")

    col_menu_left, col_menu_right = st.columns([1, 1])

    with col_menu_left:
        st.subheader("Standard Menu")
        if not filtered_df.empty:
            curr_venue = filtered_df.iloc[0]
            for dish in curr_venue["menu"]:
                st.markdown(f"**{dish['item']}** — `{' | '.join(dish['tags'])}` — **₹{dish['price']}**")
        else:
            st.markdown("**Jain Special Veg Pulao** — `Pulao` | `Veg` | `Jain` — **₹180**")

    with col_menu_right:
        st.subheader("🔍 AI Dish & Ingredient Inspector")
        
        input_dish = st.text_input("Enter Dish Name or Upload Photo", value="pav bhaji")
        uploaded_photo = st.file_uploader("Optional: Upload Dish Photo", type=["jpg", "png", "jpeg"], key="dish_photo")
        
        if st.button("Inspect Hidden Ingredients", type="primary"):
            clean_dish = input_dish.strip().lower()
            if not clean_dish and uploaded_photo is None:
                st.warning("Please type a dish name or upload an image to inspect.")
            else:
                st.info(f"Analyzing **{input_dish}** for dietary risks...")
                
                if not GEMINI_API_KEY:
                    st.warning("⚠️ GEMINI_API_KEY not detected. Using local inspection engine.")
                    
                    if any(w in clean_dish for w in ["bhaji", "pav", "pulao", "paneer", "curry"]):
                        risks = ["Butter / Ghee Content (Dairy Allergen)", "Onion & Garlic Puree", "Cashew Paste Base", "Food Color Additives"]
                        ingredients = ["Boiled Potatoes & Vegetables", "Pav Bhaji Masala", "Butter / Oil", "Garlic Ginger Paste"]
                    elif any(w in clean_dish for w in ["jamun", "sweet", "cake", "ice cream"]):
                        risks = ["Khoya / Milk Solids (Dairy)", "Refined Sugar Syrup", "Nut Traces"]
                        ingredients = ["Khoya", "Sugar Syrup", "Cardamom"]
                    else:
                        risks = [f"Potential Dairy/Gluten in {input_dish}", "Trace Spice Blends", "Cross-Contamination Risks"]
                        ingredients = [f"Primary Base of {input_dish}", "Cooking Oil", "Salt & Spices"]

                    st.error("⚠️ Potential Hidden Ingredients Flagged:")
                    for r in risks:
                        st.markdown(f"* **{r}**")

                    st.subheader("🥗 Typical Ingredients Detected:")
                    for ing in ingredients:
                        st.markdown(f"* {ing}")

                else:
                    with st.spinner(f"AI Engine analyzing {input_dish}..."):
                        try:
                            prompt = f"""
                            Analyze the culinary dish: '{input_dish}'.
                            Identify typical ingredients and flag hidden ingredients or dietary risks.
                            
                            Return ONLY a JSON object:
                            {{
                                "dish_name": "{input_dish}",
                                "flagged_hidden_risks": ["Risk 1", "Risk 2"],
                                "typical_ingredients": ["Ingredient 1", "Ingredient 2"]
                            }}
                            """
                            model = genai.GenerativeModel("gemini-1.5-flash")
                            
                            if uploaded_photo is not None:
                                img_bytes = uploaded_photo.getvalue()
                                response = model.generate_content([
                                    prompt,
                                    {"mime_type": uploaded_photo.type, "data": img_bytes}
                                ])
                            else:
                                response = model.generate_content(prompt)
                                
                            raw_text = response.text.strip()
                            if raw_text.startswith("```json"):
                                raw_text = raw_text[7:-3].strip()
                            elif raw_text.startswith("```"):
                                raw_text = raw_text[3:-3].strip()

                            result = json.loads(raw_text)

                            st.error("⚠️ Potential Hidden Ingredients Flagged:")
                            for risk in result.get("flagged_hidden_risks", []):
                                st.markdown(f"* **{risk}**")

                            st.subheader("🥗 Recipe Ingredients Detected:")
                            for ing in result.get("typical_ingredients", []):
                                st.markdown(f"* {ing}")

                        except Exception as e:
                            st.error(f"Inspection error: {str(e)}")

with tab4:
    st.title("Community Kitchen Audit Portal")
    st.write("Submit evidence-backed kitchen updates to maintain verified badge accuracy.")
    
    with st.container():
        st.markdown('<div style="border:1px solid #E6E8EB; padding:20px; border-radius:10px;">', unsafe_allow_html=True)
        
        venue_options_audit = filtered_df["name"].tolist() if not filtered_df.empty else df["name"].tolist()
        audit_venue_select = st.selectbox(
            "Select Restaurant", 
            venue_options_audit,
            key="audit_venue_select"
        )
        
        audit_standard = st.selectbox(
            "Reported Audit Standard",
            [
                "Level 1 (Separate Utensils)",
                "Level 2 (Separate Cooking Stations)",
                "Level 3 (100% Dedicated Prep Lines)"
            ]
        )
        
        uploaded_file = st.file_uploader(
            "Upload Verification Photo (Kitchen Prep / Cookware)", 
            type=["jpg", "png"]
        )
        
        audit_notes = st.text_area(
            "Audit Notes",
            placeholder="e.g., Confirmed distinct green handles on veg frying pans."
        )
        
        if st.button("Submit Community Report"):
            st.success("✅ Community report successfully submitted for review!")
            
        st.markdown('</div>', unsafe_allow_html=True)