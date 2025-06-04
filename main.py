import requests
from critical_data import api_key, api_url
from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import MessageToJson
import json
import csv
import folium
from html_static import html_val

from flask import Flask, jsonify, Response, request

# --- GTFS static loader for route shapes (download and extract GTFS) ---
import os
import csv
import io
import zipfile

GTFS_ZIP_URL = "http://www.stm.info/sites/default/files/gtfs/gtfs_stm.zip"

def download_and_extract_gtfs():
    resp = requests.get(GTFS_ZIP_URL, stream=True)
    resp.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    gtfs_folder = os.path.join(os.path.dirname(__file__), 'gtfs_temp')
    if not os.path.exists(gtfs_folder):
        os.makedirs(gtfs_folder)
    z.extractall(gtfs_folder)
    return os.path.join(gtfs_folder, 'trips.txt'), os.path.join(gtfs_folder, 'shapes.txt')

trips_csv_path, shapes_csv_path = download_and_extract_gtfs()

# Map to one or more shape_ids via trips.txt
route_to_shape_ids = {}
if os.path.exists(trips_csv_path):
    with open(trips_csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            route = row.get('route_id')
            direction = row.get('direction_id', '0')
            shape = row.get('shape_id')
            if route and shape:
                key = (route, direction)
                route_to_shape_ids.setdefault(key, set()).add(shape)

shapes = {}
if os.path.exists(shapes_csv_path):
    with open(shapes_csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row.get('shape_id')
            lat = row.get('shape_pt_lat')
            lon = row.get('shape_pt_lon')
            seq = row.get('shape_pt_sequence')
            if sid and lat and lon and seq:
                shapes.setdefault(sid, []).append((int(seq), float(lat), float(lon)))
    # Sort coordinates by sequence and store only (lat, lon)
    for sid, pts in shapes.items():
        pts.sort(key=lambda x: x[0])
        shapes[sid] = [(pt[1], pt[2]) for pt in pts]

route_shapes = {}
for (route, direction), shape_ids in route_to_shape_ids.items():
    for sid in shape_ids:
        if sid in shapes:
            route_shapes.setdefault(route, {})[direction] = shapes[sid]
            break

def fetch_realtime_data(api_url, api_key):
    headers = {'apiKey': api_key}
    try:
        resp = requests.get(api_url, headers=headers, timeout=10)
        resp.raise_for_status()
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(resp.content)
        return feed
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None


# Helper function to plot a trip on a map using GTFS static stops.txt
def plot_trip_on_map(json_str, stops_csv_path, trip_id):
    data = json.loads(json_str)
    stop_updates = None
    for entity in data.get('entity', []):
        tu = entity.get('tripUpdate', {})
        if tu.get('trip', {}).get('tripId') == trip_id:
            stop_updates = tu.get('stopTimeUpdate', [])
            break
    if not stop_updates:
        print(f"No stop updates found for trip {trip_id}")
        return
    # Load stop coordinates from GTFS static stops.txt
    stops = {}
    with open(stops_csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stops[row['stop_id']] = (float(row['stop_lat']), float(row['stop_lon']))
    # Build list of coordinates in order
    coords = []
    for upd in stop_updates:
        sid = upd.get('stopId')
        if sid in stops:
            coords.append(stops[sid])
    if not coords:
        print("No matching stops with coordinates.")
        return
    # Create a folium map centered on the first stop
    m = folium.Map(location=coords[0], zoom_start=13)
    # Draw the route line
    folium.PolyLine(coords).add_to(m)
    # Add markers for each stop
    for sid, coord in zip([u.get('stopId') for u in stop_updates], coords):
        folium.Marker(location=coord, popup=sid).add_to(m)
    # Save to HTML
    map_file = f"trip_{trip_id}_map.html"
    m.save(map_file)
    # print(f"Map saved to {map_file}")


# Convert GTFS-rt VehiclePositions feed to GeoJSON FeatureCollection
def get_vehicle_positions_geojson(api_url, api_key):
    # Fetch and parse the GTFS-rt VehiclePositions feed
    headers = {'apiKey': api_key}
    resp = requests.get(api_url.replace('tripUpdates', 'vehiclePositions'), headers=headers, timeout=10)
    resp.raise_for_status()
    vp_feed = gtfs_realtime_pb2.FeedMessage()
    vp_feed.ParseFromString(resp.content)
    # Build GeoJSON FeatureCollection
    features = []
    for entity in vp_feed.entity:
        vp = entity.vehicle
        if not (vp.HasField('position') and vp.position.latitude and vp.position.longitude):
            continue
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [vp.position.longitude, vp.position.latitude]
            },
            "properties": {
                "id": vp.vehicle.id,
                "route": vp.trip.route_id if vp.HasField('trip') else None,
                "direction": vp.trip.direction_id if vp.HasField('trip') else None,
                "heading": vp.position.HasField('bearing') and vp.position.bearing or 0
            }
        }
        features.append(feature)
    return {
        "type": "FeatureCollection",
        "features": features
    }



app = Flask(__name__)
@app.route('/api/vehicles')
def vehicles():
    gj = get_vehicle_positions_geojson(api_url, api_key)
    return jsonify(gj)

# --- Route shape GeoJSON endpoint ---
@app.route('/api/route/<route_id>')
def route_geojson(route_id):
    """Return GeoJSON LineString for the given route_id and optional direction."""
    direction = request.args.get('direction', None)
    coords = None
    if route_id in route_shapes:
        available_dirs = list(route_shapes[route_id].keys())
        print(f"[DEBUG] Available directions for route {route_id}: {available_dirs}")
        if direction and direction in route_shapes[route_id]:
            coords = route_shapes[route_id][direction]
        else:
            # Fallback to the first available direction if the requested one isn't found
            first_dir = available_dirs[0]
            coords = route_shapes[route_id][first_dir]
            print(f"[DEBUG] Falling back to direction {first_dir} for route {route_id}")
    print(f"[DEBUG] route_geojson called for route_id={route_id}, direction={direction}, num_points={len(coords) if coords else 0}")
    if not coords:
        return jsonify({"type": "FeatureCollection", "features": []})
    # Convert list of (lat, lon) to GeoJSON-friendly [lon, lat]
    line_coords = [[lon, lat] for lat, lon in coords]
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": line_coords
        },
        "properties": {
            "route": route_id,
            "direction": direction
        }
    }
    return jsonify({"type": "FeatureCollection", "features": [feature]})

@app.route('/')
def index():
    return Response(html_val, mimetype='text/html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)