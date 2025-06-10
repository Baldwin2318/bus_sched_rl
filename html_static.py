from critical_data import vehicle_api_endpoint, route_api_endpoint_template

# Turn html_val into an f-string so to inject Python variables into the JS
html_val = f'''
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/><title>Real-time Bus Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
</head>
<body><div id="map" style="width:100%; height:100vh;"></div>
  <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
  <script src="https://unpkg.com/leaflet-rotatedmarker/leaflet.rotatedMarker.js"></script>
  <script src="https://unpkg.com/leaflet.marker.slideto/Leaflet.Marker.SlideTo.js"></script>
  <script>
    // Map heading angles to compass directions
    function compassLabel(angle) {{
      if (angle === null || angle === undefined) return '';
      angle = (angle + 360) % 360;
      if (angle >= 337.5 || angle < 22.5) return 'north';
      if (angle < 67.5) return 'northeast';
      if (angle < 112.5) return 'east';
      if (angle < 157.5) return 'southeast';
      if (angle < 202.5) return 'south';
      if (angle < 247.5) return 'southwest';
      if (angle < 292.5) return 'west';
      return 'northwest';
    }}
  </script>
  <script>
    const map = L.map('map').setView([45.5, -73.6], 12);
    // Add user's live location if available
    if (navigator.geolocation) {{
      navigator.geolocation.getCurrentPosition(pos => {{
        const userLatLng = [pos.coords.latitude, pos.coords.longitude];
        // Add a distinct marker for user location
        const userIcon = L.icon({{
          iconUrl: '/static/user-marker.png',
          iconSize: [30, 30],
          iconAnchor: [12, 41]
        }});
        L.marker(userLatLng, {{icon: userIcon}}).addTo(map)
          .bindPopup('You are here')
          .openPopup();
        map.panTo(userLatLng);
      }}, err => {{
        console.warn(`Geolocation error: ${{err.message}}`);
      }});
    }}
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);
    const markers = {{}};
    let routeLayer = null;
    async function refresh() {{
      const res = await fetch('{vehicle_api_endpoint}');
      const data = await res.json();
      data.features.forEach(f => {{
        const id = f.properties.id;
        const [lon, lat] = f.geometry.coordinates;
        const heading = f.properties.heading;
        if (!markers[id]) {{
            const icon = L.icon({{ iconUrl: '/static/bus.png', iconSize: [30,30] }});
            markers[id] = L.marker([lat, lon], {{icon, rotationAngle: heading}}).addTo(map)
              .bindPopup(`$ {{f.properties.route}} ${{compassLabel(f.properties.heading)}}`)
              .on('click', function() {{
                  const routeId = f.properties.route;
                  console.log("Marker clicked. routeId =", routeId);
                  if (routeId) {{
                      fetch(`{route_api_endpoint_template}/${{routeId}}?direction=${{f.properties.direction}}`)
                        .then(res => {{
                          console.log("Fetch status:", res.status);
                          return res.json();
                        }})
                        .then(data => {{
                          console.log("Full GeoJSON data for route", routeId, data);
                          const numCoords = (data.features[0] && data.features[0].geometry.coordinates.length) || 0;
                          console.log(`Route ${{routeId}} has ${{numCoords}} coordinates`);
                          if (routeLayer) {{
                            map.removeLayer(routeLayer);
                          }}
                          if (numCoords > 0) {{
                            routeLayer = L.geoJSON(data, {{ style: {{ color: '#0000ff', weight: 3 }} }}).addTo(map);
                            map.fitBounds(routeLayer.getBounds(), {{ padding: [20, 20] }});
                            console.log(`Drew route layer for ${{routeId}}`);
                          }} else {{
                            console.warn(`No shape data for route ${{routeId}}`);
                          }}
                        }})
                        .catch(err => console.error("Error fetching/drawing route:", err));
                  }}
              }});
        }} else {{
          markers[id]
            .slideTo([lat, lon], {{duration: 10000}})
            .setRotationAngle(heading);
          markers[id].getPopup().setContent(`${{f.properties.route}} ${{compassLabel(f.properties.heading)}}`);
        }}
      }});
    }}
    refresh();
    setInterval(refresh, 5000);
  </script>
</body>
</html>
'''