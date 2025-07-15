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
  const toggleStaticAP = document.getElementById("toggle-static-aps");

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
        `<strong>MAC:</strong> ${track.mac}${track.is_randomized ? ' (randomized)' : ''}<br>` +
        `<strong>Type:</strong> ${track.device_type || 'N/A'}<br>` +
        `<strong>SSID:</strong> ${track.ssid || 'N/A'}<br>` +
        `<strong>Packets:</strong> ${track.n_obs}<br>` +
        `<strong># Points:</strong> ${track.points.length}<br>` +
        `<strong>First seen:</strong> ${new Date(track.points[0].ts * 1000).toLocaleString()}<br>` +
        `<strong>Last seen:</strong> ${new Date(track.points.at(-1).ts * 1000).toLocaleString()}<br>` +
        `<strong>Encryption:</strong> ${track.encryption || 'N/A'}<br>` +
        `<strong>OUI:</strong> ${track.oui_manuf || 'N/A'}`;
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
        L.circleMarker(coords[0], { radius: 5, color, fill: false }).addTo(tracksGroup);
        L.circleMarker(coords.at(-1), { radius: 5, color, fillColor: color, fillOpacity: 1 }).addTo(tracksGroup);

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
  const ctxEncryptionChart = document.getElementById("encryption-bar-chart").getContext("2d");
  const encryptionChart = new Chart(ctxEncryptionChart, {
    type: "bar",
    data: { labels: [], datasets: [{ label: "Count", data: [], backgroundColor: "rgba(54,162,235,0.6)" }] },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      scales: { x: { beginAtZero: true } }
    }
  });
  const ctxOuiChart = document.getElementById("oui-bar-chart").getContext("2d");
  const ouiChart = new Chart(ctxOuiChart, {
    type: "bar",
    data: { labels: [], datasets: [{ label: "Count", data: [], backgroundColor: "rgba(75,192,192,0.6)" }] },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      scales: { x: { beginAtZero: true } }
    },
  });

  // --- noUiSliders ---
  function formatTimestamp(value) {
    const date = new Date(value * 1000);
    const pad = n => n.toString().padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
      + `<br>${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  }

  const timeSlider = noUiSlider.create(document.getElementById("time-slider"), {
    start: [0, 100],
    connect: true,
    range: { min: 0, max: 100 },
    tooltips: [
      { to: formatTimestamp },
      { to: formatTimestamp }
    ],
    format: {
      from: function (value) {
        return parseInt(value);
      },
      to: function (value) {
        return parseInt(value);
      }
    }
  });
  const packetSlider = noUiSlider.create(document.getElementById("packet-slider"), {
    start: [0, 100],
    connect: true,
    range: { min: 0, max: 100 },
    tooltips: true,
    format: {
      from: function (value) {
        return parseInt(value);
      },
      to: function (value) {
        return parseInt(value);
      }
    }
  });
  const pointsSlider = noUiSlider.create(document.getElementById("points-slider"), {
    start: [0, 100],
    connect: true,
    range: { min: 0, max: 100 },
    tooltips: true,
    format: {
      from: function (value) {
        return parseInt(value);
      },
      to: function (value) {
        return parseInt(value);
      }
    }
  });

  // get ranges for sliders before other data calls that use them in filters
  const sliderPromises = [
    fetch("/api/max-packets")
      .then(r => r.json())
      .then(({ max_packets }) => {
        packetSlider.updateOptions({
          start: [0, max_packets],
          range: { min: 0, max: max_packets },
        });
      })
      .catch(console.error),
    fetch("/api/max-points")
      .then(r => r.json())
      .then(({ max_points }) => {
        pointsSlider.updateOptions({
          start: [0, max_points],
          range: { min: 0, max: max_points },
        });
      })
      .catch(console.error),
    fetch("/api/time-range")
      .then(r => r.json())
      .then(({ min_ts, max_ts }) => {
        timeSlider.updateOptions({
          start: [min_ts, max_ts],
          range: { min: min_ts, max: max_ts },
        });
      })
      .catch(console.error)
  ]

  // (hook slider.on("update", ...) later)

  // --- UI Event Listeners ---
  document.getElementById("toggle-drawer").addEventListener("click", () => {
    document.getElementById("control-drawer").classList.toggle("collapsed");
  });

  document.getElementById("toggle-static-aps").addEventListener("change", e => {
    e.target.checked ? map.addLayer(clusterGroup) : map.removeLayer(clusterGroup);
  });
  document.getElementById("toggle-heatmap").addEventListener("change", e => {
    e.target.checked ? heatLayer.addTo(map) : map.removeLayer(heatLayer);
  });
  document.getElementById("toggle-mobile-tracks").addEventListener("change", e => {
    e.target.checked ? map.addLayer(tracksGroup) : map.removeLayer(tracksGroup);
  });
  document.getElementById("btn-apply").addEventListener("click", () => {
    // TODO: enable Leaflet.draw
  });
  document.getElementById("btn-reset").addEventListener("click", () => {
    // TODO: clear filters and redraw defaults
  });
  document.getElementById("search-mac").addEventListener("input", e => {
    // TODO: filter/map-pan-to matching MAC/SSID
  });

  // --- Initial Data Loads (no filters applied yet) ---
  fetch("/api/drive-path", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      time_range: null,
      packet_count: null,
      points_count: null,
      exclude_static: !toggleStaticAP.checked,
      exclude_mobile: !toggleMobile.checked,
    }),
  })
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

  fetch("/api/static-ap", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      time_range: null,
      packet_count: null,
      points_count: null,
      exclude_static: !toggleStaticAP.checked,
      exclude_mobile: !toggleMobile.checked,
    }),
  })
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

  fetch("/api/mobile-track", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      time_range: null,
      packet_count: null,
      points_count: null,
      exclude_static: !toggleStaticAP.checked,
      exclude_mobile: !toggleMobile.checked,
    }),
  })
    .then(r => r.json())
    .then(tracks => {
      mobileTracks = tracks;
      updateMobileTracks();
    })
    .catch(console.error);

  // --- Fetch Atmospherics Data ---
  function fetchAtmos() {
    fetch("/api/atmos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        time_range: timeSlider.get().map(v => Number(v)),
        packet_count: packetSlider.get().map(v => Number(v)),
        points_count: pointsSlider.get().map(v => Number(v)),
        exclude_static: !toggleStaticAP.checked,
        exclude_mobile: !toggleMobile.checked,
      }),
    })
      .then(r => r.json())
      .then(data => {
        // Update summary stats
        document.getElementById("unique-macs").textContent = data.unique_mac_count;
        document.getElementById("unique-ssids").textContent = data.unique_ssid_count;

        // Encryption chart
        encryptionChart.data.labels = data.encryption_counts.map(e => e[0]);
        encryptionChart.data.datasets[0].data = data.encryption_counts.map(e => e[1]);
        encryptionChart.update();

        // OUI Manufacturers chart
        ouiChart.data.labels = data.oui_counts.map(o => o[0]);
        ouiChart.data.datasets[0].data = data.oui_counts.map(o => o[1]);
        ouiChart.update();

        // repopulate Top-MACs table
        const tbody = document.querySelector('#mac-counts-table tbody');
        tbody.innerHTML = '';
        data.mac_counts.forEach(([mac, ssid, cnt]) => {
          const tr = document.createElement('tr');
          const tdMac = document.createElement('td');
          tdMac.textContent = mac;
          const tdSsid = document.createElement('td');
          tdSsid.textContent = ssid || '';
          const tdCnt = document.createElement('td');
          tdCnt.textContent = cnt;
          tr.append(tdMac, tdSsid, tdCnt);
          tbody.append(tr);
        });
      })
      .catch(console.error);
  }
  // Hook up filters
  document.getElementById("time-slider").noUiSlider.on('set', fetchAtmos);
  document.getElementById("packet-slider").noUiSlider.on('set', fetchAtmos);
  document.getElementById("points-slider").noUiSlider.on('set', fetchAtmos);
  document.getElementById("toggle-static-aps").addEventListener("change", fetchAtmos);
  document.getElementById("toggle-mobile-tracks").addEventListener("change", fetchAtmos);
  // Initial load
  Promise.all(sliderPromises).then(() => {
    fetchAtmos();
  })
});
