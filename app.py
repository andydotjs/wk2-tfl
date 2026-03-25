import os
import requests
import re
from flask import Flask, render_template, request
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
TFL_API_KEY = os.getenv("TFL_API_KEY")

MODE_MAP = {
    'tube': 'NaptanMetroStation',
    'bus': 'NaptanPublicBusCoachTram',
    'train': 'NaptanRailStation'
}

def get_stops_by_coords(lat, lon, radius, selected_modes):
    type_list = [MODE_MAP[m] for m in selected_modes if m in MODE_MAP]
    if not type_list: return []
    
    url = "https://api.tfl.gov.uk/StopPoint/"
    params = {
        "lat": lat, "lon": lon,
        "stopTypes": ",".join(type_list),
        "radius": int(radius),
        "useStopPointHierarchy": "True"
    }
    try:
        resp = requests.get(url, params=params, headers={"app_key": TFL_API_KEY}, timeout=10)
        if resp.status_code == 200:
            return resp.json().get('stopPoints', [])
    except: pass
    return []

def get_bikes_by_coords(lat, lon, radius):
    url = "https://api.tfl.gov.uk/Place"
    params = {"type": "BikePoint", "lat": lat, "lon": lon, "radius": radius}
    clean_bikes = []
    try:
        resp = requests.get(url, params=params, headers={"app_key": TFL_API_KEY}, timeout=10)
        data = resp.json()
        bike_list = data.get('places', []) if isinstance(data, dict) else data if isinstance(data, list) else []

        for b in bike_list:
            props = {p.get('key'): p.get('value') for p in b.get('additionalProperties', [])}
            try:
                bikes = int(props.get('NbBikes') or props.get('nbBikes') or 0)
                docks = int(props.get('NbEmptyDocks') or props.get('nbEmptyDocks') or 0)
            except:
                bikes, docks = 0, 0

            clean_bikes.append({
                'commonName': b.get('commonName', 'Unknown Dock'),
                'lat': b.get('lat'),
                'lon': b.get('lon'),
                'distance': float(b.get('distance', 9999)),
                'modes': ['cycle-hire'],
                'status_msg': f"🚲 {bikes} bikes • 🅿️ {docks} empty docks",
                'is_bike': True
            })
    except: pass
    return clean_bikes

def resolve_search(query):
    query = query.strip()
    try:
        p_resp = requests.get(f"https://api.postcodes.io/postcodes/{query}", timeout=5)
        if p_resp.status_code == 200:
            res = p_resp.json()['result']
            return res['latitude'], res['longitude'], None
    except: pass
    coords = re.findall(r"-?\d+\.\d+", query)
    if len(coords) == 2: return coords[0], coords[1], None
    try:
        t_resp = requests.get(f"https://api.tfl.gov.uk/StopPoint/Search/{query}", headers={"app_key": TFL_API_KEY}, timeout=5)
        if t_resp.status_code == 200:
            matches = t_resp.json().get('matches', [])
            if matches: return matches[0]['lat'], matches[0]['lon'], None
    except: pass
    return None, None, "Location not found."

@app.route('/', methods=['GET'])
def index():
    query = request.args.get('query', '').strip()
    radius = request.args.get('radius', 800)
    limit = int(request.args.get('limit', 5))
    selected_modes = request.args.getlist('modes') or ['tube', 'bus']
    
    stops, error, lat, lon = [], None, None, None

    if query:
        lat, lon, s_error = resolve_search(query)
        if s_error:
            error = s_error
        elif lat and lon:
            # FIX: Only expecting one return value from get_stops_by_coords now
            if any(m in MODE_MAP for m in selected_modes):
                t_results = get_stops_by_coords(lat, lon, radius, selected_modes)
                stops.extend(t_results)
            
            if 'cycle' in selected_modes:
                stops.extend(get_bikes_by_coords(lat, lon, radius))
            
            stops = sorted(stops, key=lambda x: float(x.get('distance', 9999)))[:limit]
            
            for s in stops:
                s['walk_min'] = max(1, round(float(s.get('distance', 0)) / 80))
            
    return render_template('index.html', stops=stops, query=query, radius=radius, 
                           limit=limit, error=error, selected_modes=selected_modes,
                           search_lat=lat, search_lon=lon)

if __name__ == '__main__':
    # Use the port Railway provides, or 5000 for local testing
    port = int(os.environ.get("PORT", 5000))
    # '0.0.0.0' allows the app to be reachable externally
    app.run(host='0.0.0.0', port=port, debug=False)