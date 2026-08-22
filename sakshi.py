import streamlit as st
import pandas as pd
import pydeck as pdk
import numpy as np
import requests
import random
from datetime import datetime
from streamlit_js_eval import get_geolocation

# -----------------------------------------------------------------------------
# 1. PAGE CONFIGURATION
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="FlavorMatch - Live Navigation & Reservation Platform",
    page_icon="🍽️",
    layout="wide"
)

# Initialize Session State Variables
if "group_votes" not in st.session_state:
    st.session_state["group_votes"] = {}
if "preorder_cart" not in st.session_state:
    st.session_state["preorder_cart"] = []

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

def compute_safety_score(audit_level, diet_type):
    """Calculates Cross-Contamination Risk Score Index (0-100%)."""
    base = 100 if diet_type == "Pure Veg" else 70
    if "Level 3" in audit_level:
        return min(100, base + 15)
    elif "Level 2" in audit_level:
        return base
    else:
        return max(50, base - 15)

@st.cache_data(ttl=60, show_spinner=False)
def fetch_traffic_aware_route(start_lat, start_lon, end_lat, end_lon):
    url = f"https://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
    headers = {"User-Agent": "FlavorMatchEngine/15.0"}
    
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
                {"item": "Jain Veg Pulao (No Garlic/Onion)", "price": 240, "tags": ["Jain", "Pulao", "Veg", "No Onion No Garlic"]},
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
                {"item": "Jain Deluxe Thali (100% Pure Veg)", "price": 310, "tags": ["Jain", "Veg", "No Onion No Garlic"]},
                {"item": "Shahi Veg Pulao", "price": 210, "tags": ["Pulao", "Jain", "Veg"]}
            ]
        }
    ])
    data["color"] = data["diet_type"].apply(assign_color)
    data["safety_score"] = data.apply(lambda r: compute_safety_score(r["audit_level"], r["diet_type"]), axis=1)
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
        response = requests.post(overpass_url, data={"data": query}, headers={"User-Agent": "FlavorMatch/15.0"}, timeout=6)
        if response.status_code == 200:
            elements = response.json().get("elements", [])
            if elements:
                live_list = []
                audit_levels = ["Level 1 (Separate Utensils)", "Level 2 (Separate Cooking Stations)", "Level 3 (100% Dedicated Prep Lines)"]
                vibes = ["Family Friendly", "Quiet Business Dinner", "Casual / Street Side", "Loud Sports Bar"]
                
                sample_menus = [
                    [
                        {"item": "Jain Special Veg Pulao", "price": 180, "tags": ["Pulao", "Veg", "Jain", "No Onion No Garlic"]},
                        {"item": "Paneer Tikka (Jain)", "price": 240, "tags": ["Veg", "Jain"]}
                    ],
                    [
                        {"item": "Mutton Pulao", "price": 320, "tags": ["Halal", "Pulao", "Non-Veg"]},
                        {"item": "Chicken Biryani", "price": 280, "tags": ["Halal", "Non-Veg"]}
                    ],
                    [
                        {"item": "Jain Special Thali", "price": 250, "tags": ["Jain", "Veg", "No Onion No Garlic"]},
                        {"item": "Veg Pulao", "price": 160, "tags": ["Pulao", "Veg"]}
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
                    aud_lvl = audit_levels[idx % len(audit_levels)]
                    
                    live_list.append({
                        "id": el["id"],
                        "name": name,
                        "diet_type": diet_type,
                        "audit_level": aud_lvl,
                        "cost_for_two": int([200, 400, 600, 900, 1200, 1400][idx % 6]),
                        "lat": lat,
                        "lon": lon,
                        "vibe": vibes[idx % len(vibes)],
                        "menu": sample_menus[idx % len(sample_menus)],
                        "safety_score": compute_safety_score(aud_lvl, diet_type)
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

dish_query = st.sidebar.text_input("Search Dish/Tag (e.g. Jain, Halal, Pulao)", "").strip().lower()
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

min_safety_score = st.sidebar.slider("🛡️ Min. Cross-Contamination Safety Index", 50, 100, 50, step=5)

# Fetch dataset
df = fetch_realtime_osm_restaurants(user_lat, user_lon, radius_km=max_distance_km)
df["distance_km"] = haversine_distance(user_lat, user_lon, df["lat"], df["lon"])

# --- FILTERING LOGIC ---
filtered_df = df.copy()

filtered_df = filtered_df[
    (filtered_df["distance_km"] <= max_distance_km) & 
    (filtered_df["cost_for_two"] <= max_cost) &
    (filtered_df["safety_score"] >= min_safety_score)
]

if audit_filter != "All Venues":
    filtered_df = filtered_df[filtered_df["audit_level"] == audit_filter]

if vibe_filter != "All Vibes":
    filtered_df = filtered_df[filtered_df["vibe"] == vibe_filter]

if dish_query:
    if "jain" in dish_query:
        filtered_df = filtered_df[filtered_df["diet_type"] == "Pure Veg"]
        
    def matches_search(row):
        if dish_query in row["name"].lower() or dish_query in row["diet_type"].lower():
            return True
        for item in row["menu"]:
            if dish_query in item["item"].lower():
                return True
            for tag in item.get("tags", []):
                if dish_query in tag.lower():
                    return True
        return False
        
    filtered_df = filtered_df[filtered_df.apply(matches_search, axis=1)]

# -----------------------------------------------------------------------------
# 4. MAIN MAP & DATA DISPLAY
# -----------------------------------------------------------------------------
st.title("🍽️ FlavorMatch Real-Time Navigation Platform")

if filtered_df.empty:
    st.warning(f"⚠️ No eateries match all criteria (Vibe: '{vibe_filter}', Search: '{dish_query}'). Please adjust sidebar filters.")
else:
    selected_dest_name = st.selectbox("🎯 Select Target Destination for Navigation:", filtered_df["name"].tolist())
    target_row = filtered_df[filtered_df["name"] == selected_dest_name].iloc[0]

    traffic_segments, route_coords, route_dist, route_time, traffic_delay, traffic_status = fetch_traffic_aware_route(
        user_lat, user_lon, target_row["lat"], target_row["lon"]
    )

    m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
    m_col1.metric("Selected Venue", target_row["name"])
    m_col2.metric("Road Distance", f"{route_dist} km")
    m_col3.metric("Est. Travel Time", f"{route_time} mins")
    m_col4.metric("Traffic Delay", f"+{traffic_delay} mins", delta_color="inverse")
    m_col5.metric("🛡️ Safety Score", f"{target_row['safety_score']}%")

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
        tooltip={"html": "<b>{name}</b><br/>Diet: {diet_type}<br/>Audit: {audit_level}<br/>Safety Index: {safety_score}%<br/>Vibe: {vibe}"}
    )

    st.pydeck_chart(deck)

    st.subheader("📍 Filtered Eateries")
    st.dataframe(
        filtered_df[["name", "diet_type", "safety_score", "audit_level", "vibe", "distance_km", "cost_for_two"]]
        .sort_values(by="distance_km")
        .reset_index(drop=True),
        use_container_width=True
    )

st.markdown("---")

# -----------------------------------------------------------------------------
# 5. FEATURE TABS
# -----------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "GROUP Matcher & Bill Splitter", 
    "SLOTS Table Booking & Queue", 
    "3D Table & Floor Plan",
    "MENUS & AI Inspector", 
    "Group Swipe Lobby",
    "VERIFY Community Audit Portal"
])

# --- TAB 1: GROUP MATCHER & BILL SPLITTER ---
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

# --- TAB 2: SLOTS TABLE BOOKING, QUEUE & PRE-ORDERING ---
with tab2:
    st.title("Live Reservation Slots, Queue & Pre-Ordering Engine")
    
    venue_options = filtered_df["name"].tolist() if not filtered_df.empty else df["name"].tolist()
    selected_venue_slots = st.selectbox(
        "Select Venue", 
        venue_options,
        key="slots_venue_select"
    )
    
    col_slots_left, col_slots_right = st.columns(2)
    
    with col_slots_left:
        st.subheader("⏱️ Real-Time Available Time Slots")
        st.write("Choose Slot for Today")
        
        slot_choice = st.radio(
            "Choose Slot for Today",
            ["07:00 PM", "07:30 PM", "08:15 PM"],
            index=2,
            label_visibility="collapsed"
        )
        
        st.write("Guests")
        num_guests = st.number_input("Guests", min_value=1, max_value=30, value=11, label_visibility="collapsed")
        
        if st.button("Confirm Table Slot"):
            st.balloons()
            st.session_state["booked_slot_msg"] = f"Booked slot **{slot_choice}** at **{selected_venue_slots}** for **{num_guests} guests**!"
            st.toast("🎉 Table successfully booked!", icon="🎈")
            
        if "booked_slot_msg" in st.session_state:
            st.success(st.session_state["booked_slot_msg"])

    with col_slots_right:
        st.subheader("⏳ Live Virtual Queue & Kitchen Pre-Ordering Engine")
        
        pred_wait = random.randint(8, 22)
        st.info(f"⚡ Predictive Engine Wait Time: **{pred_wait} minutes** (Kitchen Load: Moderate)")
        
        st.markdown("**🚀 Pre-Order Dishes to Save Kitchen Wait Time:**")
        
        selected_venue_row = df[df["name"] == selected_venue_slots].iloc[0]
        for idx, item in enumerate(selected_venue_row["menu"]):
            c1, c2 = st.columns([3, 1])
            c1.write(f"• {item['item']} (₹{item['price']})")
            if c2.button(f"Add", key=f"preorder_{idx}"):
                st.session_state["preorder_cart"].append(item['item'])
                st.toast(f"Added {item['item']} to Pre-Order Cart!")
                
        if st.session_state["preorder_cart"]:
            st.write("🛒 **Pre-Order Items:** " + ", ".join(st.session_state["preorder_cart"]))

        if st.button("Join Virtual Queue Now"):
            st.balloons()
            pre_msg = f" with {len(st.session_state['preorder_cart'])} pre-ordered items!" if st.session_state["preorder_cart"] else "."
            st.success(f"🎉 You have joined the virtual queue! Token #{random.randint(10, 99)} issued{pre_msg}")

# --- TAB 3: 3D TABLE & FLOOR PLAN VIEWER ---
with tab3:
    st.subheader("📐 Interactive 3D Floor Plan & Table Selection")
    st.write("Choose your exact preferred seating location inside the restaurant.")
    
    col_fp1, col_fp2 = st.columns([1, 2])
    
    with col_fp1:
        table_zone = st.radio("Select Preferred Seating Zone", [
            "🪟 Window View (Quiet & Bright)",
            "👑 VIP Private Booth",
            "🎉 Main Dining Center (Social)",
            "🍸 Outdoor Patio / Terrace"
        ])
        selected_table_num = st.selectbox("Select Table Number", [f"Table #{i}" for i in range(1, 11)])
        if st.button("Reserve Exact Table"):
            st.balloons()
            st.success(f"✅ Reserved {selected_table_num} in **{table_zone}** zone!")

    with col_fp2:
        # Create visual PyDeck 3D layout simulation of restaurant interior
        tables_data = pd.DataFrame([
            {"table": "Table #1", "lat": 0.001, "lon": 0.001, "height": 30, "zone": "Window View"},
            {"table": "Table #2", "lat": 0.001, "lon": 0.003, "height": 30, "zone": "Window View"},
            {"table": "Table #3", "lat": 0.002, "lon": 0.002, "height": 50, "zone": "VIP Booth"},
            {"table": "Table #4", "lat": 0.003, "lon": 0.001, "height": 20, "zone": "Main Dining"},
            {"table": "Table #5", "lat": 0.003, "lon": 0.003, "height": 20, "zone": "Main Dining"},
            {"table": "Table #6", "lat": 0.004, "lon": 0.002, "height": 15, "zone": "Terrace"},
        ])
        
        column_layer = pdk.Layer(
            "ColumnLayer",
            data=tables_data,
            get_position=["lon", "lat"],
            get_elevation="height",
            elevation_scale=10,
            radius=0.3,
            get_fill_color=[46, 134, 193, 220],
            pickable=True,
            auto_highlight=True
        )
        
        floor_view = pdk.ViewState(latitude=0.0025, longitude=0.002, zoom=16, pitch=45)
        st.pydeck_chart(pdk.Deck(layers=[column_layer], initial_view_state=floor_view, tooltip={"text": "{table}\nZone: {zone}"}))

# --- TAB 4: MENUS & AI INGREDIENT INSPECTOR ---
with tab4:
    if not filtered_df.empty:
        curr_venue = filtered_df.iloc[0]
        st.subheader(f"📋 Menu Details & AI Ingredient Inspector ({curr_venue['name']})")
        
        col_m1, col_m2 = st.columns([2, 1])
        
        with col_m1:
            st.write("### Standard Menu")
            for dish in curr_venue["menu"]:
                st.markdown(f"**{dish['item']}** — `{' | '.join(dish['tags'])}` — **₹{dish['price']}**")

        with col_m2:
            st.write("### 🔍 AI Dish & Ingredient Inspector")
            dish_input = st.text_input("Enter Dish Name or Upload Photo", "Paneer Butter Masala")
            if st.button("Inspect Hidden Ingredients"):
                st.info(f"Analyzing `{dish_input}` for dietary risks...")
                if "jain" in dish_input.lower():
                    st.success("✅ **Jain Verified**: Free of garlic, onions, root vegetables, and non-veg stock.")
                else:
                    st.warning("⚠️ **Potential Hidden Ingredients Flagged**:\n- Cashew Gravy (Nut Allergen)\n- Butter/Cream (Dairy)\n- Onion & Garlic Base")

# --- TAB 5: GROUP SWIPE MATCHING LOBBY ---
with tab5:
    st.title("📲 Pareto-Optimal Group Preference Voting")
    st.write("Invite friends to swipe or vote on restaurants to find the optimal venue for everyone.")
    
    col_sw1, col_sw2 = st.columns(2)
    
    with col_sw1:
        st.subheader("1. Cast Member Votes")
        member_name = st.text_input("Your Name", "Alex")
        vote_venue = st.selectbox("Vote Candidate Venue", df["name"].tolist(), key="swipe_venue")
        vote_choice = st.radio("Your Preference", ["💚 Yes / Love It", "❌ No / Skip"])
        
        if st.button("Submit Vote"):
            if member_name not in st.session_state["group_votes"]:
                st.session_state["group_votes"][member_name] = {}
            st.session_state["group_votes"][member_name][vote_venue] = vote_choice
            st.success(f"Recorded vote for {member_name}!")

    with col_sw2:
        st.subheader("2. Group Pareto Consensus Results")
        if st.session_state["group_votes"]:
            st.json(st.session_state["group_votes"])
            
            # Simple Pareto Winner logic
            scores = {}
            for member, votes in st.session_state["group_votes"].items():
                for venue, pref in votes.items():
                    if "Yes" in pref:
                        scores[venue] = scores.get(venue, 0) + 1
            
            if scores:
                best_venue = max(scores, key=scores.get)
                st.success(f"🏆 **Pareto-Optimal Consensus Winner:** {best_venue} ({scores[best_venue]} positive votes)")
        else:
            st.info("No votes cast yet. Add diner votes above!")

# --- TAB 6: COMMUNITY KITCHEN AUDIT PORTAL ---
with tab6:
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
        
        st.write("Upload Verification Photo (Kitchen Prep / Cookware)")
        uploaded_file = st.file_uploader(
            "Upload Verification Photo (Kitchen Prep / Cookware)", 
            type=["jpg", "png"],
            help="200MB per file • JPG, PNG",
            label_visibility="collapsed"
        )
        
        audit_notes = st.text_area(
            "Audit Notes",
            placeholder="e.g., Confirmed distinct green handles on veg frying pans."
        )
        
        if st.button("Submit Community Report"):
            st.success("✅ Community report successfully submitted for review!")
            
        st.markdown('</div>', unsafe_allow_html=True)