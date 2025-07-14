document.addEventListener("DOMContentLoaded", () => {
  fetch("/api/mission")
    .then(r => r.json())
    .then(data => {
      document.getElementById("mission-title").textContent = data.mission;
    })
    .catch(console.error);
  
  // --- Map + Layers Setup ---
  const map = L.map("map").setView([0, 0], 2);
  L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    { attribution: "&copy; OpenStreetMap contributors", maxZoom: 19 }
  ).addTo(map);

  // Create a pane for highlighted tracks above markers/glyphs
  map.createPane('highlightTrackPane');
  map.getPane('highlightTrackPane').style.zIndex = 650;


  // Layer groups
  const clusterGroup = L.markerClusterGroup().addTo(map);
  const heatLayer = L.heatLayer([], { radius: 25 });
  const tracksGroup = L.layerGroup().addTo(map);
  // (playback and time-mask to add later)

  // --- Mobile Tracks: Progressive disclosure, accessible styling, animation ---
  // 1) 15-color, color-blind–friendly palette
  const trackColorPalette = [
      '#800000'
  ];
  const clusterThreshold = 12;     // zoom ≤12 → cluster; >12 → full tracks
  let mobileTracks = [];
  let activeTrackId = null;
  let activeTrackLatLng = null;

  // 2) separate marker-cluster for mobile-track centroids
  const trackClusterGroup = L.markerClusterGroup({
    disableClusteringAtZoom: clusterThreshold + 1,
    chunkedLoading: true
  }).addTo(map);

  const toggleMobile = document.getElementById("toggle-mobile-tracks");

  // 3) rebuild clusters vs. full polylines on zoom/move or toggle
  function updateMobileTracks() {
    if (!toggleMobile.checked) return;
    trackClusterGroup.clearLayers();
    tracksGroup.clearLayers();
    const zoom = map.getZoom();
    mobileTracks.forEach((track, idx) => {
      const coords = track.points.map(p => [p.lat, p.lon]);
      const bounds = L.latLngBounds(coords);
      const popupContent =
        `<strong>MAC:</strong> ${track.mac}${track.is_randomized? ' (randomized)':''}<br>`+
        `<strong>Type:</strong> ${track.device_type||'N/A'}<br>`+
        `<strong>SSID:</strong> ${track.ssid||'N/A'}<br>`+
        `<strong>Packets:</strong> ${track.n_obs}<br>`+
        `<strong># Points:</strong> ${track.points.length}<br>`+
        `<strong>First seen:</strong> ${new Date(track.points[0].ts*1000).toLocaleString()}<br>`+
        `<strong>Last seen:</strong> ${new Date(track.points.at(-1).ts*1000).toLocaleString()}<br>`+
        `<strong>Encryption:</strong> ${track.encryption||'N/A'}<br>`+
        `<strong>OUI:</strong> ${track.oui_manuf||'N/A'}`;
      // a) cluster when zoomed out & fully in view
      if (zoom <= clusterThreshold && map.getBounds().contains(bounds)) {
        const centroid = bounds.getCenter();
        L.marker(centroid)
          .bindPopup(popupContent)
          .addTo(trackClusterGroup);
      }
      // b) otherwise draw full polyline + start/end markers
      else {
        const color = trackColorPalette[idx % trackColorPalette.length];
        const isActive = track.mac === activeTrackId;
        const isFine = zoom > clusterThreshold;
        // Use custom pane for active track so it draws above everything
        const polyOptions = {
          color,
          dashArray: isActive ? '5 10' : null,
          opacity: isFine ? 0.7 : 1,
          weight: isFine ? 3 : 4,
          className: `track-polyline ${isActive ? 'track-polyline-highlighted' : 'track-polyline-normal'}`,
          pane: isActive ? 'highlightTrackPane' : undefined
        };
        const poly = L.polyline(coords, polyOptions)
          .addTo(tracksGroup)
          .bindPopup(popupContent);
        if (isActive) {
          poly.bringToFront();
          poly.openPopup(activeTrackLatLng);
        }

        // start/end
        L.circleMarker(coords[0], { radius:5, color, fill:false }).addTo(tracksGroup);
        L.circleMarker(coords.at(-1), { radius:5, color, fillColor:color, fillOpacity:1 }).addTo(tracksGroup);
        
        // click → mark this MAC active and re‐draw
        poly.on('click', e => {
          e.originalEvent.stopPropagation();
          activeTrackId = track.mac;
          activeTrackLatLng = e.latlng;
          updateMobileTracks();
        });
      }
    });
  }

  // 4) wire up map & toggle events
  map.on('zoomend moveend', updateMobileTracks);
  toggleMobile.addEventListener('change', updateMobileTracks);
  // clicking on the map (outside any track) clears selection
  map.on('click', () => {
    if (activeTrackId) {
      activeTrackId = null;
      updateMobileTracks();
    }
  });


  // --- Chart Setup ---
  const ctx = document.getElementById("statsChart").getContext("2d");
  const statsChart = new Chart(ctx, {
    type: "bar",
    data: { labels: [], datasets: [{ label: "Count", data: [], backgroundColor: "rgba(54,162,235,0.6)" }] },
    options: { responsive: true, scales: { y: { beginAtZero: true } } }
  });

  // --- noUiSliders ---
  const slider = noUiSlider.create(document.getElementById("time-slider"), {
    start: [0, 100],
    connect: true,
    range: { min: 0, max: 100 }
  });
  // (hook slider.on("update", ...) later)

  // --- UI Event Listeners ---
  document.getElementById("toggle-drawer").addEventListener("click", () => {
    document.getElementById("control-drawer").classList.toggle("collapsed");
  });

  document.getElementById("toggle-cluster").addEventListener("change", e => {
    e.target.checked ? map.addLayer(clusterGroup) : map.removeLayer(clusterGroup);
  });
  document.getElementById("toggle-heatmap").addEventListener("change", e => {
    e.target.checked ? heatLayer.addTo(map) : map.removeLayer(heatLayer);
  });
  document.getElementById("toggle-mobile-tracks").addEventListener("change", e => {
    e.target.checked ? map.addLayer(tracksGroup) : map.removeLayer(tracksGroup);
  });
  document.getElementById("btn-draw").addEventListener("click", () => {
    // TODO: enable Leaflet.draw
  });
  document.getElementById("btn-clear").addEventListener("click", () => {
    // TODO: clear filters and redraw defaults
  });
  document.getElementById("search-mac").addEventListener("input", e => {
    // TODO: filter/map-pan-to matching MAC/SSID
  });

  // --- Initial Data Loads (no filters applied yet) ---
  fetch("/api/drive-path")
    .then(r => r.json())
    .then(pathData => {
      const coords = pathData.map(pt => [pt.lat, pt.lon]);
      const poly = L.polyline(coords, { color: "red" }).addTo(map);
      if (coords.length) {
        L.marker(coords[0], { title: "Start" }).addTo(map).bindPopup("Start");
        L.marker(coords.at(-1), { title: "End" }).addTo(map).bindPopup("End");
      }
      map.fitBounds(poly.getBounds());
    })
    .catch(console.error);

  fetch("/api/static-ap")
    .then(r => r.json())
    .then(aps => {
      aps.forEach(ap => {
        const popupContent =
          `<strong>MAC:</strong> ${ap.mac} ${ap.is_randomized ? '(Randomized)' : ''}<br>` +
          `<strong>Type:</strong> ${ap.device_type || 'N/A'}<br>` +
          `<strong>SSID:</strong> ${ap.ssid || 'N/A'}<br>` +
          `<strong>Packets detected:</strong> ${ap.n_obs}<br>` +
          `<strong>First seen:</strong> ${new Date(ap.first_seen * 1000).toLocaleString()}<br>` +
          `<strong>Last seen:</strong> ${new Date(ap.last_seen * 1000).toLocaleString()}<br>` +
          `<strong>Encryption:</strong> ${ap.encryption || 'N/A'}<br>` +
          `<strong>OUI:</strong> ${ap.oui_manuf || 'N/A'}<br>`;
        const m = L.circleMarker([ap.lat_mean, ap.lon_mean], { radius: 5, color: "blue" })
          .bindPopup(popupContent);
        clusterGroup.addLayer(m);
      });
      const heatData = aps.map(ap => [ap.lat_mean, ap.lon_mean, ap.n_obs]);
      heatLayer.setLatLngs(heatData);
    })
    .catch(console.error);

    fetch("/api/mobile-track")
    .then(r => r.json())
    .then(tracks => {
      mobileTracks = tracks;
      updateMobileTracks();
    })
    .catch(console.error);

  // leave statsChart empty for now; will fetch + redraw later
});