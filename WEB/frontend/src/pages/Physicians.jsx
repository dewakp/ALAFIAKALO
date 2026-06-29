import { useState, useEffect, useRef, useCallback } from 'react';
import { apiErrorMessage } from '../utils/apiError';
import api from '../services/api';
import {
  Search, Plus, MapPin, Star, Heart, Trash2, Edit3, X,
  Phone, Globe, Clock, ChevronDown, ChevronRight, Navigation,
  Stethoscope, Filter, BookmarkPlus, BookmarkCheck, MessageSquare,
  Building, Shield, Video, Users, Globe2, ShieldCheck,
} from 'lucide-react';
import BackButton from '../components/BackButton';
import ChoroplethMap from '../components/ChoroplethMap';
import { flagEmoji } from '../data/isoCountries';
// Leaflet bundled (not CDN) so the Map View renders reliably offline / without unpkg.
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import 'leaflet.markercluster';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import 'leaflet.markercluster/dist/MarkerCluster.Default.css';

const PAGE_SIZE = 10;

const RELATIONSHIP_TYPES = ['PCP', 'Specialist', 'Dentist', 'Therapist', 'Surgeon', 'Pharmacist', 'Other'];

export default function Physicians() {

  // ── State ──
  const [physicians, setPhysicians] = useState([]);
  const [savedPhysicians, setSavedPhysicians] = useState([]);
  const [specialties, setSpecialties] = useState({});
  const [reviews, setReviews] = useState({});
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('directory'); // directory | saved | discover | map

  // Search / Filter
  const [searchQ, setSearchQ] = useState('');
  const [filterSpecialty, setFilterSpecialty] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [filterCity, setFilterCity] = useState('');
  const [showFilters, setShowFilters] = useState(false);

  // Nearby / Map
  const [userLat, setUserLat] = useState(null);
  const [userLon, setUserLon] = useState(null);
  const [nearbyResults, setNearbyResults] = useState([]);
  const [osmResults, setOsmResults] = useState([]);
  const [directoryPoints, setDirectoryPoints] = useState([]);
  const [facilityPoints, setFacilityPoints] = useState([]);
  const [mapRole, setMapRole] = useState('');
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [radiusKm, setRadiusKm] = useState(50);
  const [placeType, setPlaceType] = useState('all');
  const [geocodeQuery, setGeocodeQuery] = useState('');
  const [geocodeResults, setGeocodeResults] = useState([]);

  // Forms
  const [showAddForm, setShowAddForm] = useState(false);
  const [showSaveDialog, setShowSaveDialog] = useState(null);
  const [showReviewDialog, setShowReviewDialog] = useState(null);
  const [selectedPhysician, setSelectedPhysician] = useState(null);

  // Map
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const overlayRef = useRef([]);   // layers to clear/replace on each redraw
  const fitDoneRef = useRef(false); // fit bounds only once (no re-animation)

  // ── Load ──
  useEffect(() => {
    loadAll();
    getUserLocation();
  }, []);

  // Directory list — server-side paginated at PAGE_SIZE (10) records/page.
  const loadDirectory = useCallback(async (pg = 0) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (searchQ) params.set('q', searchQ);
      if (filterSpecialty) params.set('specialty', filterSpecialty);
      if (filterCategory) params.set('specialty_category', filterCategory);
      if (filterCity) params.set('city', filterCity);
      params.set('limit', PAGE_SIZE);
      params.set('offset', pg * PAGE_SIZE);
      const { data } = await api.get(`/physicians/?${params}`);
      setPhysicians(data);
      setHasMore(data.length === PAGE_SIZE);
      setPage(pg);
    } catch (err) { console.error(err); }
    setLoading(false);
  }, [searchQ, filterSpecialty, filterCategory, filterCity]);

  async function loadAll() {
    setLoading(true);
    try {
      const [savedRes, specRes] = await Promise.all([
        api.get('/physicians/saved/'),
        api.get('/physicians/specialties'),
      ]);
      setSavedPhysicians(savedRes.data);
      setSpecialties(specRes.data.categories || {});
    } catch (err) { console.error(err); }
    await loadDirectory(0);
  }

  function getUserLocation() {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => { setUserLat(pos.coords.latitude); setUserLon(pos.coords.longitude); },
        () => { /* permission denied — use manual geocode */ }
      );
    }
  }

  // ── Search ── (resets to first page)
  async function handleSearch() {
    await loadDirectory(0);
  }

  // Resolve a search center: explicit coords → my location → geocode the typed address.
  async function resolveCenter(center) {
    if (center && center.lat != null) return center;
    if (userLat && userLon) return { lat: userLat, lon: userLon };
    if (geocodeQuery) return await handleGeocode();
    return null;
  }

  // ── Nearby (our directory) ──
  async function searchNearby(center) {
    const c = await resolveCenter(center);
    if (!c) { alert('Enter an address to locate, or allow location access.'); return; }
    setLoading(true);
    try {
      const { data } = await api.get(`/physicians/nearby?lat=${c.lat}&lon=${c.lon}&radius_km=${radiusKm}`);
      setNearbyResults(data.results || []);
    } catch (err) { alert(apiErrorMessage(err, 'Nearby search failed')); }
    setLoading(false);
  }

  // ── OSM Discover ──
  async function discoverOSM(center) {
    const c = await resolveCenter(center);
    if (!c) { alert('Enter an address to locate, or allow location access.'); return; }
    setLoading(true);
    try {
      const { data } = await api.get(
        `/physicians/osm-discover?lat=${c.lat}&lon=${c.lon}&radius_km=${radiusKm}&place_type=${placeType}`,
        { timeout: 90000 });
      const results = data.results || [];
      setOsmResults(results);
      if (!results.length) alert('No OpenStreetMap healthcare places found in this area — try a larger radius.');
    } catch (err) { alert(apiErrorMessage(err, 'OSM discovery failed')); }
    setLoading(false);
  }

  // ── Geocode ── (returns {lat, lon} | null and sets the map center)
  async function handleGeocode() {
    if (!geocodeQuery) { alert('Type a place or address first.'); return null; }
    try {
      const { data } = await api.get(`/physicians/geocode?address=${encodeURIComponent(geocodeQuery)}`);
      setGeocodeResults(data);
      if (data.length > 0) {
        const c = { lat: data[0].latitude, lon: data[0].longitude };
        setUserLat(c.lat);
        setUserLon(c.lon);
        return c;
      }
      alert('Location not found — try a more specific address.');
      return null;
    } catch (err) { alert(apiErrorMessage(err, 'Geocoding failed')); return null; }
  }

  // ── Save / Unsave ──
  const savedIds = new Set(savedPhysicians.map(s => s.physician_id));

  async function savePhysician(physicianId, opts = {}) {
    try {
      await api.post('/physicians/saved/', { physician_id: physicianId, ...opts });
      const { data } = await api.get('/physicians/saved/');
      setSavedPhysicians(data);
    } catch (err) { console.error(err); }
  }

  async function unsavePhysician(savedId) {
    try {
      await api.delete(`/physicians/saved/${savedId}`);
      setSavedPhysicians(prev => prev.filter(s => s.id !== savedId));
    } catch (err) { console.error(err); }
  }

  // ── Reviews ──
  async function loadReviews(physicianId) {
    const { data } = await api.get(`/physicians/${physicianId}/reviews`);
    setReviews(prev => ({ ...prev, [physicianId]: data }));
  }

  async function submitReview(physicianId, reviewData) {
    await api.post(`/physicians/${physicianId}/reviews`, reviewData);
    await loadReviews(physicianId);
    const { data } = await api.get('/physicians/');
    setPhysicians(data);
  }

  // ── Add Physician ──
  async function addPhysician(formData) {
    await api.post('/physicians/', formData);
    await loadAll();
    setShowAddForm(false);
  }

  // ── Delete ──
  async function deletePhysician(id) {
    if (!confirm('Delete this physician from the directory?')) return;
    try {
      await api.delete(`/physicians/${id}`);
      setPhysicians(prev => prev.filter(p => p.id !== id));
    } catch (err) { alert(apiErrorMessage(err, 'Cannot delete')); }
  }

  // ── Map ──
  const updateMap = useCallback(() => {
    if (!mapRef.current) return;

    if (!mapInstanceRef.current) {
      mapInstanceRef.current = L.map(mapRef.current, { preferCanvas: true })
        .setView([userLat || 39.5, userLon || -98.35], userLat ? 11 : 4);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://osm.org/copyright">OpenStreetMap</a>',
        maxZoom: 19, crossOrigin: true,
      }).addTo(mapInstanceRef.current);
    }

    const map = mapInstanceRef.current;
    // Container is sized only once the tab is visible — recompute so tiles render.
    map.invalidateSize();

    // Clear previous overlay layers.
    overlayRef.current.forEach(layer => map.removeLayer(layer));
    overlayRef.current = [];

    const fitPts = [];

    // Clinicians → CLUSTERED (handles thousands of approximate points; clusters and
    // individual markers are both clickable).
    const clinicianCluster = L.markerClusterGroup({
      chunkedLoading: true, maxClusterRadius: 55,
      animate: false, animateAddingMarkers: false,
    });
    directoryPoints.forEach(p => {
      const approx = p.location_precision !== 'exact';
      clinicianCluster.addLayer(
        L.circleMarker([p.latitude, p.longitude], {
          radius: 6, color: '#1d4ed8', weight: 1, fillColor: '#3b82f6',
          fillOpacity: approx ? 0.55 : 0.9,
        }).bindPopup(
          `<b>${p.full_name}</b><br>${p.specialty || p.clinician_role || ''}` +
          `<br>${[p.city, p.state_province].filter(Boolean).join(', ')}` +
          `<br>✓ Verified clinician${approx ? ' · approx. location' : ''}`)
      );
      fitPts.push([p.latitude, p.longitude]);
    });
    map.addLayer(clinicianCluster);
    overlayRef.current.push(clinicianCluster);

    // Facilities (exact) + live OSM + you → individual clickable markers.
    const overlay = L.layerGroup();
    facilityPoints.forEach(f => {
      const n = f.clinician_count || 0;
      L.circleMarker([f.latitude, f.longitude], {
        radius: n > 0 ? Math.min(6 + Math.sqrt(n) * 1.5, 16) : 6,
        color: '#6d28d9', weight: 1, fillColor: '#a78bfa', fillOpacity: 0.85,
      }).bindPopup(
        `<b>${f.name}</b><br>${f.facility_type}<br>${[f.city, f.state_province].filter(Boolean).join(', ')}` +
        (n > 0 ? `<br>👥 ${n} clinician${n !== 1 ? 's' : ''} practice here` : '')
      ).addTo(overlay);
      fitPts.push([f.latitude, f.longitude]);
    });
    osmResults.forEach(r => {
      L.circleMarker([r.latitude, r.longitude], { radius: 6, color: '#6d28d9', weight: 1, fillColor: '#c4b5fd', fillOpacity: 0.6 })
        .bindPopup(`<b>${r.name}</b><br>${r.amenity_type}${r.distance_km != null ? `<br>${r.distance_km} km` : ''}`)
        .addTo(overlay);
    });
    if (userLat && userLon) {
      L.circleMarker([userLat, userLon], { radius: 8, color: '#15803d', fillColor: '#22c55e', fillOpacity: 0.95 })
        .bindPopup('📍 You are here').addTo(overlay);
    }
    map.addLayer(overlay);
    overlayRef.current.push(overlay);

    // Fit to the data once (no animation, so it doesn't "swim" on every reload).
    if (fitPts.length && !fitDoneRef.current && !(userLat && userLon)) {
      try { map.fitBounds(fitPts, { padding: [30, 30], maxZoom: 11, animate: false }); } catch { /* single point */ }
      fitDoneRef.current = true;
    }
  }, [userLat, userLon, directoryPoints, facilityPoints, osmResults]);

  // Clinician map points (verified). Optional bbox limits to a searched area.
  const loadDirectoryPoints = useCallback(async (bbox) => {
    try {
      const params = { limit: 2000, ...(mapRole ? { role: mapRole } : {}) };
      if (bbox) params.bbox = bbox;
      const { data } = await api.get('/physicians/directory/points', { params });
      setDirectoryPoints(data);
    } catch { setDirectoryPoints([]); }
  }, [mapRole]);

  // Facility map points from the directory DB (fast/reliable; no live Overpass).
  const loadFacilityPoints = useCallback(async (bbox) => {
    try {
      const params = { limit: 2000 };
      if (bbox) params.bbox = bbox;
      const { data } = await api.get('/facilities/points', { params });
      setFacilityPoints(data);
    } catch { setFacilityPoints([]); }
  }, []);

  // On-demand: ingest OSM facilities for wherever the map is centered into the
  // facilities DB, then re-plot. Uses the live map center if available.
  const [discovering, setDiscovering] = useState(false);
  async function discoverFacilitiesHere() {
    let c = null;
    if (mapInstanceRef.current) {
      const ctr = mapInstanceRef.current.getCenter();
      c = { lat: ctr.lat, lon: ctr.lng };
    } else if (userLat && userLon) {
      c = { lat: userLat, lon: userLon };
    } else {
      c = await resolveCenter();
    }
    if (!c) { alert('Pan the map or search a place first.'); return; }
    setDiscovering(true);
    try {
      const { data } = await api.post('/facilities/discover-here', null, {
        params: { lat: c.lat, lon: c.lon, radius_km: Math.min(radiusKm, 25), place_type: placeType },
        timeout: 120000,
      });
      await loadFacilityPoints(bboxAround(c));
      const added = (data.inserted || 0);
      alert(`Discovered ${data.fetched || 0} facilities here (${added} new, ${data.updated || 0} updated).`);
    } catch (err) {
      alert(apiErrorMessage(err, 'Facility discovery failed — OpenStreetMap may be busy; try again.'));
    } finally { setDiscovering(false); }
  }

  // Bounding box (minLat,minLon,maxLat,maxLon) around a center for the current radius.
  function bboxAround(c) {
    const dLat = radiusKm / 111;
    const dLon = radiusKm / (111 * Math.cos((c.lat * Math.PI) / 180) || 1);
    return `${c.lat - dLat},${c.lon - dLon},${c.lat + dLat},${c.lon + dLon}`;
  }

  // Load data when entering the Map tab (or role changes) — NOT on every redraw,
  // so updating the data doesn't retrigger loading (that loop made it "animate").
  useEffect(() => {
    if (tab === 'map') { loadDirectoryPoints(); loadFacilityPoints(); }
  }, [tab, loadDirectoryPoints, loadFacilityPoints]);

  // Redraw only when the data actually changes.
  useEffect(() => {
    if (tab !== 'map') return;
    const t = setTimeout(updateMap, 120);
    return () => clearTimeout(t);
  }, [tab, updateMap]);

  // ── Render ──
  if (loading && physicians.length === 0) {
    return <div style={{ padding: '2rem', textAlign: 'center' }}><div className="loading">Loading physicians...</div></div>;
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-left">
          <BackButton />
          <h1 className="page-title"><Stethoscope size={24} /> Physician Directory</h1>
        </div>
        <button className="btn btn-primary" onClick={() => setShowAddForm(true)}>
          <Plus size={18} /> Add Physician
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        {[
          { key: 'directory', label: 'Directory', icon: <Users size={16} /> },
          { key: 'saved', label: `Saved (${savedPhysicians.length})`, icon: <Heart size={16} /> },
          { key: 'discover', label: 'Discover (OSM)', icon: <Navigation size={16} /> },
          { key: 'map', label: 'Map View', icon: <MapPin size={16} /> },
          { key: 'globalmap', label: 'Global Map', icon: <Globe2 size={16} /> },
        ].map(t => (
          <button key={t.key} className={`btn ${tab === t.key ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setTab(t.key)} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* ── DIRECTORY TAB ── */}
      {tab === 'directory' && (
        <div>
          {/* Search Bar */}
          <div className="card" style={{ marginBottom: '1rem', padding: '1rem' }}>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <input className="form-input" style={{ flex: 1, minWidth: '200px' }}
                placeholder="Search by name..." value={searchQ}
                onChange={e => setSearchQ(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()} />
              <button className="btn btn-primary" onClick={handleSearch}><Search size={16} /> Search</button>
              <button className="btn btn-secondary" onClick={() => setShowFilters(!showFilters)}>
                <Filter size={16} /> Filters {showFilters ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </button>
            </div>
            {showFilters && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0.5rem', marginTop: '0.75rem' }}>
                <select className="form-input" value={filterCategory} onChange={e => { setFilterCategory(e.target.value); setFilterSpecialty(''); }}>
                  <option value="">All Categories</option>
                  {Object.keys(specialties).map(c => <option key={c} value={c}>{c}</option>)}
                </select>
                <select className="form-input" value={filterSpecialty} onChange={e => setFilterSpecialty(e.target.value)}>
                  <option value="">All Specialties</option>
                  {(filterCategory ? specialties[filterCategory] || [] : Object.values(specialties).flat()).map(s =>
                    <option key={s} value={s}>{s}</option>)}
                </select>
                <input className="form-input" placeholder="City" value={filterCity} onChange={e => setFilterCity(e.target.value)} />
                <button className="btn btn-secondary" onClick={() => { setSearchQ(''); setFilterSpecialty(''); setFilterCategory(''); setFilterCity(''); loadAll(); }}>
                  Clear
                </button>
              </div>
            )}
          </div>

          {/* Results */}
          {physicians.length === 0 ? (
            <div className="card" style={{ padding: '3rem', textAlign: 'center', color: '#888' }}>
              <Stethoscope size={48} style={{ marginBottom: '1rem', opacity: 0.3 }} />
              <h3>No physicians found</h3>
              <p>Add a physician or adjust your search filters</p>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: '1rem' }}>
              {physicians.map(p => (
                <PhysicianCard key={p.id} physician={p} isSaved={savedIds.has(p.id)}
                  onSave={() => setShowSaveDialog(p)} onUnsave={() => {
                    const s = savedPhysicians.find(sp => sp.physician_id === p.id);
                    if (s) unsavePhysician(s.id);
                  }}
                  onReview={() => { loadReviews(p.id); setShowReviewDialog(p); }}
                  onDelete={() => deletePhysician(p.id)}
                  onSelect={() => setSelectedPhysician(p)} />
              ))}
            </div>
          )}

          {/* Pagination — 10 records per page (server-side) */}
          {(page > 0 || hasMore) && (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '1rem', marginTop: '1.25rem' }}>
              <button className="btn btn-secondary btn-sm" disabled={page === 0 || loading}
                onClick={() => loadDirectory(page - 1)}>
                <ChevronRight size={14} style={{ transform: 'rotate(180deg)' }} /> Prev
              </button>
              <span style={{ fontSize: '0.85rem', color: '#666' }}>Page {page + 1}</span>
              <button className="btn btn-secondary btn-sm" disabled={!hasMore || loading}
                onClick={() => loadDirectory(page + 1)}>
                Next <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── SAVED TAB ── */}
      {tab === 'saved' && (
        <div>
          {savedPhysicians.length === 0 ? (
            <div className="card" style={{ padding: '3rem', textAlign: 'center', color: '#888' }}>
              <Heart size={48} style={{ marginBottom: '1rem', opacity: 0.3 }} />
              <h3>No saved physicians</h3>
              <p>Bookmark physicians from the directory to quickly access them here</p>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: '1rem' }}>
              {savedPhysicians.map(s => (
                <div key={s.id} className="card" style={{ padding: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                        <h3 style={{ margin: 0 }}>{s.physician?.full_name || 'Unknown'}</h3>
                        {s.is_primary_care && <span style={{ background: '#22c55e', color: '#fff', padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem' }}>PCP</span>}
                        {s.relationship_type && <span style={{ background: '#f97316', color: '#fff', padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem' }}>{s.relationship_type}</span>}
                      </div>
                      <p style={{ margin: '0.25rem 0', color: '#666' }}>{s.physician?.specialty} {s.physician?.credentials ? `• ${s.physician.credentials}` : ''}</p>
                      {s.physician?.facility_name && <p style={{ margin: '0.25rem 0', color: '#888', fontSize: '0.9rem' }}><Building size={14} /> {s.physician.facility_name}</p>}
                      {s.nickname && <p style={{ margin: '0.25rem 0', fontSize: '0.85rem' }}>Nickname: {s.nickname}</p>}
                      {s.notes && <p style={{ margin: '0.25rem 0', fontSize: '0.85rem', fontStyle: 'italic' }}>{s.notes}</p>}
                    </div>
                    <button className="btn btn-danger btn-sm" onClick={() => unsavePhysician(s.id)}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── DISCOVER TAB ── */}
      {tab === 'discover' && (
        <div>
          <div className="card" style={{ padding: '1rem', marginBottom: '1rem' }}>
            <h3 style={{ margin: '0 0 0.25rem' }}><Navigation size={18} /> Discover Healthcare Facilities Nearby (OpenStreetMap)</h3>
            <p style={{ margin: '0 0 0.75rem', fontSize: '0.82rem', color: '#888' }}>
              Facilities (hospitals, clinics, pharmacies) — places, not individual clinicians.
            </p>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
              <input className="form-input" style={{ flex: 1, minWidth: '200px' }}
                placeholder="Enter address to search near..." value={geocodeQuery}
                onChange={e => setGeocodeQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleGeocode()} />
              <button className="btn btn-primary" onClick={handleGeocode}><MapPin size={16} /> Locate</button>
            </div>
            {geocodeResults.length > 0 && (
              <div style={{ marginBottom: '0.75rem', fontSize: '0.85rem', color: '#666' }}>
                📍 Location: {geocodeResults[0].display_name?.substring(0, 80)}...
                ({geocodeResults[0].latitude?.toFixed(4)}, {geocodeResults[0].longitude?.toFixed(4)})
              </div>
            )}
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
              <select className="form-input" style={{ width: 'auto' }} value={placeType} onChange={e => setPlaceType(e.target.value)}>
                <option value="all">All Healthcare</option>
                <option value="hospital">Hospitals</option>
                <option value="clinic">Clinics</option>
                <option value="pharmacy">Pharmacies</option>
                <option value="dentist">Dentists</option>
                <option value="doctors">Doctors</option>
              </select>
              <select className="form-input" style={{ width: 'auto' }} value={radiusKm} onChange={e => setRadiusKm(Number(e.target.value))}>
                <option value={5}>5 km</option>
                <option value={10}>10 km</option>
                <option value={25}>25 km</option>
                <option value={50}>50 km</option>
                <option value={100}>100 km</option>
              </select>
              <button className="btn btn-primary" onClick={() => discoverOSM()} disabled={loading}>
                <Search size={16} /> Discover
              </button>
              {!userLat && <span style={{ fontSize: '0.85rem', color: '#999' }}>Uses the address above (click Locate) or your location</span>}
            </div>
          </div>

          {osmResults.length > 0 && (
            <div>
              <h4 style={{ marginBottom: '0.5rem' }}>Found {osmResults.length} facilities</h4>
              <div style={{ display: 'grid', gap: '0.75rem' }}>
                {osmResults.map((r, i) => (
                  <div key={i} className="card" style={{ padding: '1rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div>
                        <h4 style={{ margin: '0 0 0.25rem' }}>{r.name}</h4>
                        <p style={{ margin: '0.25rem 0', color: '#666', fontSize: '0.9rem' }}>
                          {r.amenity_type} • {r.distance_km} km away
                        </p>
                        {r.address && <p style={{ margin: '0.25rem 0', fontSize: '0.85rem', color: '#888' }}><MapPin size={12} /> {r.address}</p>}
                        {r.phone && <p style={{ margin: '0.25rem 0', fontSize: '0.85rem' }}><Phone size={12} /> {r.phone}</p>}
                        {r.opening_hours && <p style={{ margin: '0.25rem 0', fontSize: '0.85rem' }}><Clock size={12} /> {r.opening_hours}</p>}
                      </div>
                      <button className="btn btn-primary btn-sm" onClick={() => {
                        setShowAddForm(true);
                        // Pre-fill from OSM data — the add form will pick these up
                        window.__osmPrefill = { full_name: r.name, city: r.address?.split(',')[1]?.trim(), latitude: r.latitude, longitude: r.longitude, phone: r.phone, website: r.website, specialty: r.healthcare_specialty || '' };
                      }}>
                        <Plus size={14} /> Add to Directory
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── MAP TAB ── */}
      {tab === 'map' && (
        <div>
          <div className="card" style={{ padding: '1rem', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <input className="form-input" style={{ flex: 1, minWidth: '200px' }}
                placeholder="Search location..." value={geocodeQuery}
                onChange={e => setGeocodeQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleGeocode()} />
              <button className="btn btn-primary" onClick={async () => {
                const c = await handleGeocode();
                if (!c) return;
                if (mapInstanceRef.current) mapInstanceRef.current.setView([c.lat, c.lon], 12);
                const bb = bboxAround(c);
                loadDirectoryPoints(bb);  // clinicians in this area (DB)
                loadFacilityPoints(bb);   // facilities in this area (DB)
              }}>
                <Search size={16} /> Search Area
              </button>
              <select className="form-input" value={mapRole} onChange={e => setMapRole(e.target.value)} style={{ maxWidth: 180 }}>
                {DIRECTORY_ROLES.map(([val, label]) => <option key={val} value={val}>{label}</option>)}
              </select>
              <button className="btn btn-secondary" onClick={discoverFacilitiesHere} disabled={discovering}
                title="Find healthcare facilities (OpenStreetMap) for the current map area and add them to the directory">
                <Navigation size={16} /> {discovering ? 'Discovering…' : 'Discover facilities here'}
              </button>
            </div>
          </div>
          <div ref={mapRef} style={{ height: '500px', borderRadius: '12px', overflow: 'hidden', border: '1px solid #e5e7eb' }} />
          <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: '#999' }}>
            <strong>{directoryPoints.length}</strong> verified clinician{directoryPoints.length !== 1 ? 's' : ''}
            {facilityPoints.length ? <> · <strong>{facilityPoints.length}</strong> facilities</> : null} &nbsp;·&nbsp;
            🟢 You &nbsp; 🔵 Clinicians (filled = exact, hollow = approx.) &nbsp; 🟣 Facilities (OSM) &nbsp;·&nbsp;
            Map data © <a href="https://osm.org" target="_blank" rel="noreferrer">OpenStreetMap</a>
          </div>
        </div>
      )}

      {/* ── GLOBAL MAP TAB ── */}
      {tab === 'globalmap' && <GlobalDirectoryMap />}

      {/* ── Detail Panel ── */}
      {selectedPhysician && (
        <PhysicianDetail physician={selectedPhysician}
          onClose={() => setSelectedPhysician(null)}
          reviews={reviews[selectedPhysician.id] || []}
          onLoadReviews={() => loadReviews(selectedPhysician.id)} />
      )}

      {/* ── Add Form Dialog ── */}
      {showAddForm && <AddPhysicianDialog specialties={specialties} onSave={addPhysician} onClose={() => { setShowAddForm(false); window.__osmPrefill = null; }} />}

      {/* ── Save Dialog ── */}
      {showSaveDialog && <SaveDialog physician={showSaveDialog} onSave={(opts) => { savePhysician(showSaveDialog.id, opts); setShowSaveDialog(null); }} onClose={() => setShowSaveDialog(null)} />}

      {/* ── Review Dialog ── */}
      {showReviewDialog && <ReviewDialog physician={showReviewDialog} onSubmit={(data) => { submitReview(showReviewDialog.id, data); setShowReviewDialog(null); }} onClose={() => setShowReviewDialog(null)} />}
    </div>
  );
}


// ── Physician Card ────────────────────────────────────────────────
function PhysicianCard({ physician: p, isSaved, onSave, onUnsave, onReview, onDelete, onSelect }) {
  return (
    <div className="card" style={{ padding: '1rem', cursor: 'pointer' }} onClick={onSelect}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem', flexWrap: 'wrap' }}>
            <h3 style={{ margin: 0 }}>{p.full_name}</h3>
            {p.credentials && <span style={{ color: '#666', fontSize: '0.85rem' }}>{p.credentials}</span>}
            <VerificationBadge physician={p} />
            {p.telehealth_available && <span style={{ background: '#14b8a6', color: '#fff', padding: '2px 6px', borderRadius: '12px', fontSize: '0.7rem' }} title="Telehealth available"><Video size={10} /></span>}
          </div>
          <p style={{ margin: '0.25rem 0', color: '#f97316', fontWeight: 500 }}>{p.specialty} {p.specialty_category ? `• ${p.specialty_category}` : ''}</p>
          <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', fontSize: '0.85rem', color: '#666', marginTop: '0.25rem' }}>
            {p.facility_name && <span><Building size={13} /> {p.facility_name}</span>}
            {p.city && <span><MapPin size={13} /> {p.city}{p.state_province ? `, ${p.state_province}` : ''}</span>}
            {p.phone && <span><Phone size={13} /> {p.phone}</span>}
          </div>
          {p.review_count > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', marginTop: '0.35rem', fontSize: '0.85rem' }}>
              <Star size={14} fill="#f59e0b" color="#f59e0b" />
              <span style={{ fontWeight: 600 }}>{p.average_rating?.toFixed(1)}</span>
              <span style={{ color: '#888' }}>({p.review_count} review{p.review_count > 1 ? 's' : ''})</span>
            </div>
          )}
          <div style={{ display: 'flex', gap: '0.25rem', marginTop: '0.35rem', flexWrap: 'wrap' }}>
            {p.accepting_new_patients && <span style={{ background: '#dcfce7', color: '#166534', padding: '2px 8px', borderRadius: '12px', fontSize: '0.75rem' }}>Accepting patients</span>}
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }} onClick={e => e.stopPropagation()}>
          <button className={`btn btn-sm ${isSaved ? 'btn-success' : 'btn-secondary'}`}
            onClick={isSaved ? onUnsave : onSave}
            disabled={!isSaved && !p.credential_verified}
            title={isSaved ? 'Remove from care team'
              : p.credential_verified ? 'Add to care team'
              : 'License not verified — cannot add to your care team'}>
            {isSaved ? <BookmarkCheck size={14} /> : <BookmarkPlus size={14} />}
          </button>
          <button className="btn btn-sm btn-secondary" onClick={onReview} title="Review">
            <MessageSquare size={14} />
          </button>
          <button className="btn btn-sm btn-danger" onClick={onDelete} title="Delete">
            <Trash2 size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Verification badge — reflects the patient-association license gate ──
function VerificationBadge({ physician: p }) {
  const pill = (bg, label, title) => (
    <span title={title} style={{ background: bg, color: '#fff', padding: '2px 8px', borderRadius: '12px', fontSize: '0.7rem', whiteSpace: 'nowrap' }}>{label}</span>
  );
  if (p.credential_verified) return pill('#22c55e', '✓ Verified', 'Licensed & verified — can be added to a care team');
  if (p.verification_status === 'license_on_record') return pill('#f59e0b', 'License on record', 'License present — awaiting admin verification; cannot be added yet');
  if (p.verification_status === 'rejected') return pill('#ef4444', 'Rejected', 'Verification rejected');
  return pill('#9ca3af', 'Unverified', 'Not verified — cannot be added to a care team');
}

const DIRECTORY_ROLES = [
  ['', 'All'], ['physician', 'Physicians'], ['nurse', 'Nurses'],
  ['nurse_practitioner', 'NPs'], ['dietitian', 'Dietitians'],
  ['pharmacist', 'Pharmacists'], ['therapist', 'Therapists'], ['mental_health', 'Mental health'],
];

// ── Global directory overlay — verified clinicians on a drill-down choropleth ──
function GlobalDirectoryMap() {
  const [data, setData] = useState(null);
  const [role, setRole] = useState('');
  const [selected, setSelected] = useState(null);
  const [list, setList] = useState(null);
  const [listLoading, setListLoading] = useState(false);

  useEffect(() => {
    setData(null);
    api.get('/physicians/directory/map', { params: role ? { role } : {} })
      .then(({ data }) => setData(data))
      .catch(() => setData({ countries: [], total_verified: 0, by_role: {} }));
  }, [role]);

  async function pick(iso2) {
    setSelected(iso2); setList(null); setListLoading(true);
    try {
      const { data } = await api.get(`/physicians/directory/country/${iso2}`, { params: role ? { role } : {} });
      setList(data);
    } catch { setList([]); } finally { setListLoading(false); }
  }

  const mapData = {};
  (data?.countries || []).forEach((c) => {
    mapData[c.iso2] = { level: c.level, name: c.name, label: `${c.count} verified clinician${c.count !== 1 ? 's' : ''}` };
  });

  return (
    <div>
      <div className="card" style={{ padding: '1rem', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <ShieldCheck size={16} color="#22c55e" />
          <span style={{ fontWeight: 600 }}>Verified clinicians only.</span>
          <span style={{ color: '#666', fontSize: '0.85rem' }}>Unverified / unlicensed records are held and never shown here or linked to patients.</span>
        </div>
        <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', marginTop: '0.75rem' }}>
          {DIRECTORY_ROLES.map(([val, label]) => (
            <button key={val} className={`btn btn-sm ${role === val ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => { setRole(val); setSelected(null); setList(null); }}>{label}</button>
          ))}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.6fr) minmax(260px, 1fr)', gap: '1rem', alignItems: 'start' }}>
        <div className="card" style={{ padding: '1.25rem' }}>
          {data == null
            ? <div style={{ padding: '3rem', textAlign: 'center', color: '#999' }}>Loading directory map…</div>
            : <ChoroplethMap data={mapData} selected={selected} onSelect={pick} />}
          <div style={{ fontSize: '0.78rem', color: '#999', marginTop: '0.6rem' }}>
            {data ? <><strong>{data.total_verified}</strong> verified clinicians across <strong>{data.countries.length}</strong> countries. Click a country to drill down.</> : null}
          </div>
        </div>

        <div className="card" style={{ padding: '1.25rem', minHeight: 200 }}>
          {!selected && (
            <div style={{ color: '#666' }}>
              <h4 style={{ marginTop: 0 }}><Globe2 size={16} style={{ verticalAlign: -3 }} /> By country</h4>
              {(data?.countries || []).slice(0, 12).map((c) => (
                <button key={c.iso2} onClick={() => pick(c.iso2)}
                  style={{ display: 'flex', width: '100%', justifyContent: 'space-between', padding: '0.4rem 0.5rem', border: 'none', background: 'none', cursor: 'pointer', borderBottom: '1px solid #eee' }}>
                  <span>{flagEmoji(c.iso2)} {c.name}</span><strong>{c.count}</strong>
                </button>
              ))}
              {data && !data.countries.length && <p>No verified clinicians yet. Seed from CMS in the admin tools.</p>}
            </div>
          )}
          {selected && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ margin: 0 }}>{flagEmoji(selected)} {data?.countries.find((c) => c.iso2 === selected)?.name || selected}</h3>
                <button className="btn btn-sm btn-secondary" onClick={() => { setSelected(null); setList(null); }}><X size={14} /></button>
              </div>
              {listLoading && <p style={{ color: '#999' }}>Loading…</p>}
              {list && list.length === 0 && !listLoading && <p style={{ color: '#999' }}>No verified clinicians listed.</p>}
              {list && list.map((c) => (
                <div key={c.id} style={{ padding: '0.5rem 0', borderBottom: '1px solid #eee' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem' }}>
                    <strong>{c.full_name}</strong>
                    <span style={{ fontSize: '0.72rem', background: '#eef2ff', color: '#4338ca', padding: '1px 7px', borderRadius: 10, textTransform: 'capitalize', whiteSpace: 'nowrap' }}>{c.clinician_role.replace('_', ' ')}</span>
                  </div>
                  <div style={{ fontSize: '0.82rem', color: '#666' }}>
                    {c.specialty}{c.city ? ` · ${c.city}${c.state_province ? `, ${c.state_province}` : ''}` : ''}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Physician Detail Panel ────────────────────────────────────────
function PhysicianDetail({ physician: p, onClose, reviews, onLoadReviews }) {
  useEffect(() => { onLoadReviews(); }, []);
  return (
    <div style={{ position: 'fixed', top: 0, right: 0, width: '400px', height: '100vh', background: '#fff', boxShadow: '-4px 0 20px rgba(0,0,0,0.1)', zIndex: 1000, overflowY: 'auto', padding: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
        <h2 style={{ margin: 0 }}>{p.full_name}</h2>
        <button className="btn btn-sm btn-secondary" onClick={onClose}><X size={16} /></button>
      </div>
      <div style={{ marginBottom: '1rem' }}>
        <p style={{ color: '#f97316', fontWeight: 600 }}>{p.specialty} {p.credentials ? `• ${p.credentials}` : ''}</p>
        {p.facility_name && <p><Building size={14} /> {p.facility_name}</p>}
        {p.city && <p><MapPin size={14} /> {[p.address_line1, p.city, p.state_province, p.country].filter(Boolean).join(', ')}</p>}
        {p.phone && <p><Phone size={14} /> {p.phone}</p>}
        {p.email && <p>✉️ {p.email}</p>}
        {p.website && <p><Globe size={14} /> <a href={p.website} target="_blank" rel="noreferrer">{p.website}</a></p>}
        {p.languages_spoken && <p>🗣 {p.languages_spoken}</p>}
        {p.operating_hours && <p><Clock size={14} /> {p.operating_hours}</p>}
        {p.insurance_accepted && <p><Shield size={14} /> {p.insurance_accepted}</p>}
      </div>
      <h3>Reviews ({reviews.length})</h3>
      {reviews.length === 0 ? <p style={{ color: '#888' }}>No reviews yet</p> : reviews.map(r => (
        <div key={r.id} style={{ borderBottom: '1px solid #eee', padding: '0.75rem 0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {[...Array(5)].map((_, i) => <Star key={i} size={14} fill={i < r.rating ? '#f59e0b' : '#e5e7eb'} color={i < r.rating ? '#f59e0b' : '#e5e7eb'} />)}
            <span style={{ color: '#888', fontSize: '0.85rem' }}>{r.reviewer_name}</span>
          </div>
          {r.title && <p style={{ fontWeight: 600, margin: '0.25rem 0' }}>{r.title}</p>}
          {r.review_text && <p style={{ margin: '0.25rem 0', fontSize: '0.9rem' }}>{r.review_text}</p>}
        </div>
      ))}
    </div>
  );
}

// ── Add Physician Dialog ──────────────────────────────────────────
function AddPhysicianDialog({ specialties, onSave, onClose }) {
  const prefill = window.__osmPrefill || {};
  const [form, setForm] = useState({
    full_name: prefill.full_name || '', specialty: prefill.specialty || '', credentials: '',
    phone: prefill.phone || '', email: '', website: prefill.website || '',
    address_line1: '', city: prefill.city || '', state_province: '', postal_code: '', country: '',
    latitude: prefill.latitude || null, longitude: prefill.longitude || null,
    facility_name: '', accepting_new_patients: true, telehealth_available: false,
    languages_spoken: '', npi_number: '',
  });
  const set = (k, v) => setForm(prev => ({ ...prev, [k]: v }));

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
      <div className="card" style={{ width: '600px', maxHeight: '90vh', overflowY: 'auto', padding: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <h2 style={{ margin: 0 }}>Add Physician</h2>
          <button className="btn btn-sm btn-secondary" onClick={onClose}><X size={16} /></button>
        </div>
        <form onSubmit={e => { e.preventDefault(); onSave(form); }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            <div style={{ gridColumn: '1/3' }}>
              <label className="form-label">Full Name *</label>
              <input className="form-input" required value={form.full_name} onChange={e => set('full_name', e.target.value)} />
            </div>
            <div>
              <label className="form-label">Specialty *</label>
              <select className="form-input" required value={form.specialty} onChange={e => set('specialty', e.target.value)}>
                <option value="">Select...</option>
                {Object.entries(specialties).map(([cat, specs]) => (
                  <optgroup key={cat} label={cat}>
                    {specs.map(s => <option key={s} value={s}>{s}</option>)}
                  </optgroup>
                ))}
              </select>
            </div>
            <div>
              <label className="form-label">Credentials</label>
              <input className="form-input" placeholder="MD, DO, NP..." value={form.credentials} onChange={e => set('credentials', e.target.value)} />
            </div>
            <div>
              <label className="form-label">Facility Name</label>
              <input className="form-input" value={form.facility_name} onChange={e => set('facility_name', e.target.value)} />
            </div>
            <div>
              <label className="form-label">NPI Number</label>
              <input className="form-input" value={form.npi_number} onChange={e => set('npi_number', e.target.value)} />
            </div>
            <div>
              <label className="form-label">Phone</label>
              <input className="form-input" value={form.phone} onChange={e => set('phone', e.target.value)} />
            </div>
            <div>
              <label className="form-label">Email</label>
              <input className="form-input" type="email" value={form.email} onChange={e => set('email', e.target.value)} />
            </div>
            <div style={{ gridColumn: '1/3' }}>
              <label className="form-label">Address</label>
              <input className="form-input" value={form.address_line1} onChange={e => set('address_line1', e.target.value)} />
            </div>
            <div>
              <label className="form-label">City</label>
              <input className="form-input" value={form.city} onChange={e => set('city', e.target.value)} />
            </div>
            <div>
              <label className="form-label">State / Province</label>
              <input className="form-input" value={form.state_province} onChange={e => set('state_province', e.target.value)} />
            </div>
            <div>
              <label className="form-label">Country</label>
              <input className="form-input" value={form.country} onChange={e => set('country', e.target.value)} />
            </div>
            <div>
              <label className="form-label">Languages</label>
              <input className="form-input" placeholder="English, Spanish..." value={form.languages_spoken} onChange={e => set('languages_spoken', e.target.value)} />
            </div>
            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
              <label><input type="checkbox" checked={form.accepting_new_patients} onChange={e => set('accepting_new_patients', e.target.checked)} /> Accepting patients</label>
              <label><input type="checkbox" checked={form.telehealth_available} onChange={e => set('telehealth_available', e.target.checked)} /> Telehealth</label>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '1rem' }}>
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary"><Plus size={16} /> Add Physician</button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Save Dialog ───────────────────────────────────────────────────
function SaveDialog({ physician, onSave, onClose }) {
  const [nickname, setNickname] = useState('');
  const [notes, setNotes] = useState('');
  const [isPrimary, setIsPrimary] = useState(false);
  const [relType, setRelType] = useState('');
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1001, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
      <div className="card" style={{ width: '400px', padding: '1.5rem' }}>
        <h3 style={{ margin: '0 0 1rem' }}>Save {physician.full_name}</h3>
        <div style={{ display: 'grid', gap: '0.75rem' }}>
          <div>
            <label className="form-label">Nickname (optional)</label>
            <input className="form-input" placeholder="e.g. My kidney doctor" value={nickname} onChange={e => setNickname(e.target.value)} />
          </div>
          <div>
            <label className="form-label">Relationship</label>
            <select className="form-input" value={relType} onChange={e => setRelType(e.target.value)}>
              <option value="">Select...</option>
              {RELATIONSHIP_TYPES.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label">Notes</label>
            <textarea className="form-input" rows={3} value={notes} onChange={e => setNotes(e.target.value)} />
          </div>
          <label><input type="checkbox" checked={isPrimary} onChange={e => setIsPrimary(e.target.checked)} /> Primary Care Provider</label>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '1rem' }}>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={() => onSave({ nickname, notes, is_primary_care: isPrimary, relationship_type: relType })}>
            <Heart size={16} /> Save
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Review Dialog ─────────────────────────────────────────────────
function ReviewDialog({ physician, onSubmit, onClose }) {
  const [rating, setRating] = useState(5);
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [anon, setAnon] = useState(false);
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1001, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
      <div className="card" style={{ width: '400px', padding: '1.5rem' }}>
        <h3 style={{ margin: '0 0 1rem' }}>Review {physician.full_name}</h3>
        <div style={{ display: 'grid', gap: '0.75rem' }}>
          <div>
            <label className="form-label">Rating</label>
            <div style={{ display: 'flex', gap: '0.25rem' }}>
              {[1, 2, 3, 4, 5].map(n => (
                <Star key={n} size={24} style={{ cursor: 'pointer' }}
                  fill={n <= rating ? '#f59e0b' : '#e5e7eb'} color={n <= rating ? '#f59e0b' : '#e5e7eb'}
                  onClick={() => setRating(n)} />
              ))}
            </div>
          </div>
          <div>
            <label className="form-label">Title</label>
            <input className="form-input" value={title} onChange={e => setTitle(e.target.value)} />
          </div>
          <div>
            <label className="form-label">Review</label>
            <textarea className="form-input" rows={4} value={text} onChange={e => setText(e.target.value)} />
          </div>
          <label><input type="checkbox" checked={anon} onChange={e => setAnon(e.target.checked)} /> Post anonymously</label>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '1rem' }}>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={() => onSubmit({ rating, title, review_text: text, is_anonymous: anon })}>
            <Star size={16} /> Submit Review
          </button>
        </div>
      </div>
    </div>
  );
}
