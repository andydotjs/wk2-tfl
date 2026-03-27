import os
import requests
import re
from flask import Flask, render_template, request
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

TFL_API_KEY = os.getenv("TFL_API_KEY")

# Standard V10 StopTypes - reliable and fast
MODE_MAP = {
    'tube': 'NaptanMetroStation',
    'bus': 'NaptanPublicBusCoachTram',
    'train': 'NaptanRailStation'
}

TFL_COLORS = {
    'Bakerloo': '#B26300', 'Central': '#E32017', 'Circle': '#FFD300',
    'District': '#00782A', 'Hammersmith & City': '#F3A9BB', 'Jubilee': '#A0A5A9',
    'Metropolitan': '#9B0056', 'Northern': '#000000', 'Piccadilly': '#003688',
    'Victoria': '#0098D4', 'Waterloo & City': '#95CDBA', 'Elizabeth line': '#6950A1',
    'London Overground': 'special-overground',
    'DLR': '#00AFAD', 'Tram': 'special-tram',
    'National Rail': '#003399', 'Bus': '#DC241F'
}

def get_nearby_transport(lat, lon, radius, selected_modes, limit):
    all_results = []
    type_list = [MODE_MAP[m] for m in selected_modes if m in MODE_MAP]
    
    if type_list:
        url = "https://api.tfl.gov.uk/StopPoint/"
        params = {
            "lat": lat, 
            "lon": lon, 
            "stopTypes": ",".join(type_list), 
            "radius": int(radius), 
            "app_key": TFL_API_KEY
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                stops = data.get('stopPoints', [])
                for s in stops:
                    modes = s.get('modes', [])
                    if any(m in ['tube', 'elizabeth-line', 'dlr'] for m in modes): primary = 'tube'
                    elif any(m in ['national-rail', 'overground', 'train'] for m in modes): primary = 'train'
                    else: primary = 'bus'
                    
                    line_data = []
                    seen_lines = set()
                    for l in s.get('lines', []):
                        name = l.get('name')
                        if name and name not in seen_lines:
                            line_data.append({'name': name, 'color': TFL_COLORS.get(name, '#0019a8')})
                            seen_lines.add(name)

                    all_results.append({
                        'id': s.get('id'), 'commonName': s.get('commonName'),
                        'lat': s.get('lat'), 'lon': s.get('lon'),
                        'distance': float(s.get('distance', 0)),
                        'lines': line_data, 'primary_mode': primary, 'is_bike': False
                    })
        except: pass

    if 'cycle' in selected_modes:
        url = "https://api.tfl.gov.uk/Place"
        params = {"type": "BikePoint", "lat": lat, "lon": lon, "radius": radius, "app_key": TFL_API_KEY}
        try:
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()
            bike_list = data if isinstance(data, list) else data.get('places', [])
            for b in bike_list:
                props = {p.get('key'): p.get('value') for p in b.get('additionalProperties', [])}
                all_results.append({
                    'id': b.get('id'), 'commonName': b.get('commonName'),
                    'lat': b.get('lat'), 'lon': b.get('lon'),
                    'distance': float(b.get('distance', 9999)),
                    'status_msg': f"{props.get('NbBikes', 0)} bikes available",
                    'is_bike': True, 'primary_mode': 'cycle'
                })
        except: pass

    return sorted(all_results, key=lambda x: x['distance'])[:int(limit)]

def resolve_search(query):
    query = query.strip()
    coords = re.findall(r"-?\d+\.\d+", query)
    if len(coords) == 2: return coords[0], coords[1], None
    try:
        p_resp = requests.get(f"https://api.postcodes.io/postcodes/{query}", timeout=5)
        if p_resp.status_code == 200:
            res = p_resp.json()['result']
            return res['latitude'], res['longitude'], None
    except: pass
    try:
        t_resp = requests.get(f"https://api.tfl.gov.uk/StopPoint/Search/{query}", params={"app_key": TFL_API_KEY}, timeout=5)
        if t_resp.status_code == 200:
            matches = t_resp.json().get('matches', [])
            if matches: return matches[0]['lat'], matches[0]['lon'], None
    except: pass
    return None, None, "Location not found."

@app.route('/', methods=['GET'])
def index():
    query = request.args.get('query', '').strip()
    radius = int(request.args.get('radius', 1000))
    limit = int(request.args.get('limit', 10))
    
    # Default selection includes 'cycle' now
    selected_modes = request.args.getlist('modes')
    if not selected_modes:
        selected_modes = ['tube', 'bus', 'train', 'cycle']

    stops, error, lat, lon = [], None, None, None
    if query:
        lat, lon, error = resolve_search(query)
        if lat and lon:
            stops = get_nearby_transport(lat, lon, radius, selected_modes, limit)
            for s in stops:
                s['walk_min'] = max(1, round((s['distance'] * 1.3) / 80))
                
    return render_template('index.html', stops=stops, query=query, radius=radius, limit=limit, 
                           error=error, selected_modes=selected_modes, search_lat=lat, search_lon=lon)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)