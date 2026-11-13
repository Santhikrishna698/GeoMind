import { CommonModule } from '@angular/common';
import { AfterViewInit, ChangeDetectorRef, Component, OnDestroy, OnInit,computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import OlMap from 'ol/Map';
import View from 'ol/View';
import Overlay from 'ol/Overlay';
import Feature from 'ol/Feature';
import TileLayer from 'ol/layer/Tile';
import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector';
import OSM from 'ol/source/OSM';
import TileWMS from 'ol/source/TileWMS';
import GeoJSON from 'ol/format/GeoJSON';
import { defaults as defaultControls } from 'ol/control/defaults';
import { Point } from 'ol/geom';
import { fromLonLat, toLonLat } from 'ol/proj';
import { Extent,extend, isEmpty } from 'ol/extent';
import { Circle as CircleStyle, Fill, Stroke, Style, Text } from 'ol/style';
import { finalize } from 'rxjs';
import { AskResponse, GisService } from '../services/gis.service';
import BaseLayer from 'ol/layer/Base';
import { bbox as bboxStrategy } from 'ol/loadingstrategy';

interface HistoryItem {
  query: string;
  at: number;
  status: 'ok' | 'empty' | 'unclear';
  total: number | null;
}
interface QueryStat {
  query: string;
  at: number;
  ms: number;
  total: number | null;
  status: 'ok' | 'empty' | 'unclear' | 'error';
}

interface SymbologyStyle {
  icon: string;
  color: string;
  label: string;
}

const HISTORY_KEY = 'geomind.history';
const HISTORY_MAX = 30;
const STATS_KEY = 'geomind.stats';
const STATS_MAX = 100;

// The layer becomes visible from this zoom level and above (map starts at 13)
const LAYER_ZOOM = { poi: 17, buildings: 17, roads: 16 };
const zmin = (z: number) => z - 0.01;   // OpenLayers minZoom is exclusive, so this makes "from z" inclusive


// Category-grouped symbology covering all 140 POI fclass values + buildings + roads
const FCLASS_STYLES: Record<string, SymbologyStyle> = {
  // Healthcare
  hospital: { icon: '🏥', color: '#dc2626', label: 'Hospital' },
  clinic: { icon: '🩺', color: '#ef4444', label: 'Clinic' },
  doctors: { icon: '⚕️', color: '#f87171', label: 'Doctors' },
  dentist: { icon: '🦷', color: '#fb7185', label: 'Dentist' },
  pharmacy: { icon: '💊', color: '#e11d48', label: 'Pharmacy' },
  chemist: { icon: '🧪', color: '#be123c', label: 'Chemist' },
  optician: { icon: '👓', color: '#f43f5e', label: 'Optician' },
  nursing_home: { icon: '🛏️', color: '#9f1239', label: 'Nursing Home' },
  veterinary: { icon: '🐾', color: '#db2777', label: 'Veterinary' },

  // Education
  school: { icon: '🏫', color: '#2563eb', label: 'School' },
  college: { icon: '🎓', color: '#1d4ed8', label: 'College' },
  university: { icon: '🏛️', color: '#1e40af', label: 'University' },
  kindergarten: { icon: '🧸', color: '#3b82f6', label: 'Kindergarten' },
  library: { icon: '📚', color: '#60a5fa', label: 'Library' },

  // Finance
  bank: { icon: '🏦', color: '#059669', label: 'Bank' },
  atm: { icon: '🏧', color: '#10b981', label: 'ATM' },

  // Food & Drink
  restaurant: { icon: '🍽️', color: '#ea580c', label: 'Restaurant' },
  cafe: { icon: '☕', color: '#d97706', label: 'Cafe' },
  fast_food: { icon: '🍔', color: '#f97316', label: 'Fast Food' },
  bakery: { icon: '🥐', color: '#f59e0b', label: 'Bakery' },
  food_court: { icon: '🍜', color: '#fb923c', label: 'Food Court' },
  bar: { icon: '🍸', color: '#9333ea', label: 'Bar' },
  pub: { icon: '🍺', color: '#7e22ce', label: 'Pub' },
  biergarten: { icon: '🍻', color: '#a855f7', label: 'Biergarten' },
  nightclub: { icon: '🎵', color: '#6b21a8', label: 'Nightclub' },
  beverages: { icon: '🥤', color: '#fdba74', label: 'Beverages' },
  butcher: { icon: '🥩', color: '#b91c1c', label: 'Butcher' },
  greengrocer: { icon: '🥬', color: '#16a34a', label: 'Greengrocer' },
  drinking_water: { icon: '🚰', color: '#0284c7', label: 'Drinking Water' },

  // Accommodation
  hotel: { icon: '🏨', color: '#4f46e5', label: 'Hotel' },
  hostel: { icon: '🛌', color: '#6366f1', label: 'Hostel' },
  guesthouse: { icon: '🏡', color: '#818cf8', label: 'Guesthouse' },
  motel: { icon: '🏩', color: '#4338ca', label: 'Motel' },
  chalet: { icon: '🛖', color: '#7c3aed', label: 'Chalet' },
  alpine_hut: { icon: '⛰️', color: '#5b21b6', label: 'Alpine Hut' },
  wilderness_hut: { icon: '🏕️', color: '#6d28d9', label: 'Wilderness Hut' },
  camp_site: { icon: '⛺', color: '#15803d', label: 'Camp Site' },
  caravan_site: { icon: '🚐', color: '#166534', label: 'Caravan Site' },

  // Emergency, Civic & Government
  police: { icon: '🚓', color: '#1e3a8a', label: 'Police' },
  fire_station: { icon: '🚒', color: '#b91c1c', label: 'Fire Station' },
  courthouse: { icon: '⚖️', color: '#334155', label: 'Courthouse' },
  town_hall: { icon: '🏛️', color: '#475569', label: 'Town Hall' },
  public_building: { icon: '🏢', color: '#64748b', label: 'Public Building' },
  embassy: { icon: '🏳️', color: '#0f172a', label: 'Embassy' },
  consulate: { icon: '🏢', color: '#1e293b', label: 'Consulate' },
  prison: { icon: '🔒', color: '#374151', label: 'Prison' },
  post_office: { icon: '📮', color: '#dc2626', label: 'Post Office' },
  post_box: { icon: '✉️', color: '#ef4444', label: 'Post Box' },
  community_centre: { icon: '🤝', color: '#0d9488', label: 'Community Centre' },
  toilet: { icon: '🚻', color: '#0369a1', label: 'Public Toilet' },

  // Worship & Heritage (including building types)
  temple: { icon: '🛕', color: '#d97706', label: 'Temple' },
  mosque: { icon: '🕌', color: '#059669', label: 'Mosque' },
  church: { icon: '⛪', color: '#4f46e5', label: 'Church' },
  wayside_shrine: { icon: '⛩️', color: '#b45309', label: 'Wayside Shrine' },
  wayside_cross: { icon: '✝️', color: '#4338ca', label: 'Wayside Cross' },
  graveyard: { icon: '🪦', color: '#4b5563', label: 'Graveyard' },
  archaeological: { icon: '🏺', color: '#92400e', label: 'Archaeological Site' },
  monument: { icon: '🗿', color: '#78350f', label: 'Monument' },
  memorial: { icon: '🎗️', color: '#713f12', label: 'Memorial' },
  castle: { icon: '🏰', color: '#854d0e', label: 'Castle' },
  fort: { icon: '🏯', color: '#a16207', label: 'Fort' },
  ruins: { icon: '🧱', color: '#78716c', label: 'Ruins' },
  battlefield: { icon: '⚔️', color: '#991b1b', label: 'Battlefield' },
  museum: { icon: '🏛️', color: '#86198f', label: 'Museum' },
  arts_centre: { icon: '🎨', color: '#a21caf', label: 'Arts Centre' },
  artwork: { icon: '🖼️', color: '#c026d3', label: 'Artwork' },

  // Shopping & Retail
  supermarket: { icon: '🛒', color: '#0d9488', label: 'Supermarket' },
  mall: { icon: '🏬', color: '#0f766e', label: 'Mall' },
  department_store: { icon: '🛍️', color: '#115e59', label: 'Department Store' },
  convenience: { icon: '🏪', color: '#14b8a6', label: 'Convenience Store' },
  marketplace: { icon: '🧺', color: '#ca8a04', label: 'Marketplace' },
  clothes: { icon: '👕', color: '#ec4899', label: 'Clothes' },
  shoe_shop: { icon: '👟', color: '#db2777', label: 'Shoe Shop' },
  jeweller: { icon: '💎', color: '#06b6d4', label: 'Jeweller' },
  bookshop: { icon: '📖', color: '#2563eb', label: 'Bookshop' },
  stationery: { icon: '✏️', color: '#3b82f6', label: 'Stationery' },
  mobile_phone_shop: { icon: '📱', color: '#4f46e5', label: 'Mobile Shop' },
  computer_shop: { icon: '💻', color: '#4338ca', label: 'Computer Shop' },
  furniture_shop: { icon: '🛋️', color: '#b45309', label: 'Furniture Shop' },
  doityourself: { icon: '🔨', color: '#d97706', label: 'Hardware / DIY' },
  garden_centre: { icon: '🪴', color: '#16a34a', label: 'Garden Centre' },
  florist: { icon: '💐', color: '#f43f5e', label: 'Florist' },
  gift_shop: { icon: '🎁', color: '#e11d48', label: 'Gift Shop' },
  toy_shop: { icon: '🧸', color: '#f97316', label: 'Toy Shop' },
  sports_shop: { icon: '⚽', color: '#0284c7', label: 'Sports Shop' },
  outdoor_shop: { icon: '🎒', color: '#15803d', label: 'Outdoor Shop' },
  beauty_shop: { icon: '💄', color: '#ec4899', label: 'Beauty Shop' },
  hairdresser: { icon: '💇', color: '#d946ef', label: 'Hairdresser' },
  laundry: { icon: '🧺', color: '#0ea5e9', label: 'Laundry' },
  kiosk: { icon: '🗞️', color: '#64748b', label: 'Kiosk' },
  newsagent: { icon: '📰', color: '#475569', label: 'Newsagent' },
  video_shop: { icon: '📀', color: '#6366f1', label: 'Video Shop' },
  travel_agent: { icon: '✈️', color: '#0284c7', label: 'Travel Agent' },
  vending_machine: { icon: '🎰', color: '#64748b', label: 'Vending Machine' },
  general: { icon: '🏪', color: '#2F8F72', label: 'General Store' },

  // Automotive & Transport
  car_dealership: { icon: '🚗', color: '#334155', label: 'Car Dealership' },
  car_rental: { icon: '🔑', color: '#475569', label: 'Car Rental' },
  car_sharing: { icon: '🚘', color: '#0284c7', label: 'Car Sharing' },
  car_wash: { icon: '🚿', color: '#0ea5e9', label: 'Car Wash' },
  bicycle_rental: { icon: '🚲', color: '#10b981', label: 'Bicycle Rental' },
  bicycle_shop: { icon: '🚲', color: '#059669', label: 'Bicycle Shop' },
  vending_parking: { icon: '🅿️', color: '#1d4ed8', label: 'Parking Meter' },

  // Recreation, Sports & Nature
  park: { icon: '🌳', color: '#16a34a', label: 'Park' },
  playground: { icon: '🛝', color: '#22c55e', label: 'Playground' },
  dog_park: { icon: '🐕', color: '#15803d', label: 'Dog Park' },
  picnic_site: { icon: '🧺', color: '#65a30d', label: 'Picnic Site' },
  viewpoint: { icon: '🔭', color: '#0284c7', label: 'Viewpoint' },
  attraction: { icon: '⭐', color: '#eab308', label: 'Attraction' },
  theme_park: { icon: '🎡', color: '#e11d48', label: 'Theme Park' },
  zoo: { icon: '🦁', color: '#ca8a04', label: 'Zoo' },
  cinema: { icon: '🎬', color: '#7c3aed', label: 'Cinema' },
  theatre: { icon: '🎭', color: '#9333ea', label: 'Theatre' },
  stadium: { icon: '🏟️', color: '#0369a1', label: 'Stadium' },
  sports_centre: { icon: '🏋️', color: '#0284c7', label: 'Sports Centre' },
  sports_hall: { icon: '🏀', color: '#0ea5e9', label: 'Sports Hall' },
  fitness_centre: { icon: '💪', color: '#2563eb', label: 'Fitness Centre' },
  swimming_pool: { icon: '🏊', color: '#06b6d4', label: 'Swimming Pool' },
  golf_course: { icon: '⛳', color: '#16a34a', label: 'Golf Course' },
  ice_rink: { icon: '⛸️', color: '#38bdf8', label: 'Ice Rink' },
  pitch: { icon: '⚽', color: '#22c55e', label: 'Sports Pitch' },
  track: { icon: '🏃', color: '#f97316', label: 'Track' },
  fountain: { icon: '⛲', color: '#0ea5e9', label: 'Fountain' },
  bench: { icon: '🪑', color: '#78716c', label: 'Bench' },
  shelter: { icon: '🛖', color: '#57534e', label: 'Shelter' },
  hunting_stand: { icon: '🦌', color: '#3f6212', label: 'Hunting Stand' },

  // Utilities, Towers & Water Infrastructure
  comms_tower: { icon: '📡', color: '#475569', label: 'Comms Tower' },
  tower: { icon: '🗼', color: '#64748b', label: 'Tower' },
  observation_tower: { icon: '🗼', color: '#0284c7', label: 'Observation Tower' },
  lighthouse: { icon: '🚨', color: '#dc2626', label: 'Lighthouse' },
  water_tower: { icon: '💧', color: '#0284c7', label: 'Water Tower' },
  water_well: { icon: '🪣', color: '#0369a1', label: 'Water Well' },
  water_works: { icon: '🚰', color: '#075985', label: 'Water Works' },
  water_mill: { icon: '⚙️', color: '#0e7490', label: 'Water Mill' },
  windmill: { icon: '🌬️', color: '#0891b2', label: 'Windmill' },
  wastewater_plant: { icon: '🏭', color: '#4b5563', label: 'Wastewater Plant' },
  camera_surveillance: { icon: '📹', color: '#1e293b', label: 'CCTV Camera' },
  telephone: { icon: '📞', color: '#059669', label: 'Telephone' },
  recycling: { icon: '♻️', color: '#16a34a', label: 'Recycling' },
  recycling_glass: { icon: '🍾', color: '#15803d', label: 'Glass Recycling' },
  recycling_metal: { icon: '🥫', color: '#166534', label: 'Metal Recycling' },
  recycling_paper: { icon: '📄', color: '#22c55e', label: 'Paper Recycling' },
  waste_basket: { icon: '🗑️', color: '#6b7280', label: 'Waste Basket' },
};
// Categories shown in the layer list (edit freely; must match keys in FCLASS_STYLES).
// Every other POI category still draws on the map, it just isn't listed.
const MAIN_POI = [
  'hospital', 'pharmacy', 'school', 'college', 'bank', 'atm', 'restaurant',
  'cafe', 'hotel', 'police', 'temple', 'mosque', 'church', 'supermarket', 'park',
];

@Component({
  selector: 'app-geomind',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './geomind.html',
  styleUrls: ['./geomind.css'],
})
export class Geomind implements OnInit, AfterViewInit, OnDestroy {
  private gisService = inject(GisService);
  private cdr = inject(ChangeDetectorRef);
  tableFeatures: any[] = [];
  history = signal<HistoryItem[]>(this.loadHistory());
  stats = signal<QueryStat[]>(this.loadStats());

  // oldest -> newest, so the charts read left to right
  recent = computed(() => this.stats().slice(0, 10).reverse());
  maxMs = computed(() => Math.max(0, ...this.recent().map((s) => s.ms)));
  maxFeat = computed(() => Math.max(0, ...this.recent().map((s) => s.total ?? 0)));

  kpis = computed(() => {
    const all = this.stats();
    const times = all.filter((s) => s.status !== 'error').map((s) => s.ms);
    const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);
    const ok = all.filter((s) => s.status === 'ok');
    return {
      total: all.length,
      avgMs: times.length ? Math.round(sum(times) / times.length) : 0,
      fastest: times.length ? Math.min(...times) : 0,
      slowest: times.length ? Math.max(...times) : 0,
      totalFeatures: sum(all.map((s) => s.total ?? 0)),
      avgFeatures: ok.length ? Math.round(sum(ok.map((s) => s.total ?? 0)) / ok.length) : 0,
      successRate: all.length ? Math.round((ok.length / all.length) * 100) : 0,
    };
  });

  breakdown = computed(() => {
    const all = this.stats();
    const defs = [
      { key: 'ok', label: 'Results found', color: '#16a34a' },
      { key: 'empty', label: 'No match', color: '#f59e0b' },
      { key: 'unclear', label: 'Needs detail', color: '#3b82f6' },
      { key: 'error', label: 'Error', color: '#ef4444' },
    ];
    return defs.map((d) => {
      const n = all.filter((s) => s.status === d.key).length;
      return { ...d, n, pct: all.length ? (n / all.length) * 100 : 0 };
    });
  });
  showResultsCard = true;
  query = '';
  activeTab: 'Dashboard' | 'Map Explorer' | 'Results' = 'Map Explorer';
  hasResults = false;
  selectingLocation = false;
  apiOnline = signal(true);
  errorMessage = '';
  clarificationMessage = '';
  emptyMessage = '';
  truncationNotice = ''; // Displays when >100 results are capped

  // Reactive Signals
  loading = signal(false);
  totalFeatures = signal(0);
  queryTime = signal('0.00 s');
  analysisRadius = signal('Spatial');
  generatedSql = signal('');
  activeLegend = signal<SymbologyStyle[]>([]);

  favorites = [
    'Show me the schools in Kalamassery',
    'Restaurants within 1 km of Aster Medcity',
    'Buildings within 300 meters of a hospital',
    'Primary roads with bridges in Ernakulam',
  ];
  private map!: OlMap;
  private lastExtent?: Extent;
  private geoserverLayers: Record<string, BaseLayer> = {};

  private resultsSource = new VectorSource();
  private resultsLayer = new VectorLayer({
    source: this.resultsSource,
    zIndex: 10,
    style: (f) => this.styleFeature(f as Feature),
  });
  private bufferSource = new VectorSource();
  private bufferLayer = new VectorLayer({
    source: this.bufferSource,
    zIndex: 8,
    style: new Style({
      stroke: new Stroke({ color: '#2563eb', width: 1.5, lineDash: [6, 4] }),
      fill: new Fill({ color: 'rgba(37, 99, 235, 0.10)' }),
    }),
  });

  private refSource = new VectorSource();
  private refLayer = new VectorLayer({
    source: this.refSource,
    zIndex: 9,
    style: (f) => this.refStyle(f as Feature),
  });

  hasOverlay = false;
  showBuffer = true;
  showRefs = true;
  overlayNote = '';
  private poiStyleCache = new Map<string, Style>();

  private poiLayer = new VectorLayer({
    minZoom: zmin(LAYER_ZOOM.poi),                       // POIs appear when zoomed in past 12; raise if the map gets crowded
    zIndex: 5,
    source: new VectorSource({
      format: new GeoJSON(),
      strategy: bboxStrategy,          // loads only what is in the current view
      url: (extent) =>
        'http://localhost:8080/geoserver/ows?service=WFS&version=1.1.0&request=GetFeature' +
        '&typeName=gis:poi&outputFormat=application/json&srsName=EPSG:3857' +
        `&bbox=${extent.join(',')},EPSG:3857&maxFeatures=3000`,
    }),
    style: (f) => this.poiStyle(f as Feature),
  });

  private poiStyle(f: Feature): Style | undefined {
    const fclass = String(f.get('fclass') || '').toLowerCase().trim();
    if (fclass in this.poiCategoryVisible && !this.poiCategoryVisible[fclass]) return undefined;

    const sym = this.resolveSymbology(f.getProperties(), 'Point');
    let style = this.poiStyleCache.get(sym.label);
    if (!style) {
      style = new Style({
        image: new CircleStyle({
          radius: 12,
          fill: new Fill({ color: this.lighten(sym.color, 0.82) }),
          stroke: new Stroke({ color: this.lighten(sym.color, 0.35), width: 1.5 }),
        }),
        text: new Text({ text: sym.icon, font: '15px sans-serif', offsetY: 1 }),
      });
      this.poiStyleCache.set(sym.label, style);
    }
    return style;
  }

  private selectedSource = new VectorSource();
  private selectedLayer = new VectorLayer({
    source: this.selectedSource,
    zIndex: 20,
    style: new Style({
      image: new CircleStyle({
        radius: 9,
        fill: new Fill({ color: '#2F8F72' }),
        stroke: new Stroke({ color: '#ffffff', width: 3 }),
      }),
    }),
  });

  private popupEl = document.createElement('div');
  private popup = new Overlay({
    element: this.popupEl,
    positioning: 'bottom-center',
    offset: [0, -16],
    stopEvent: true,
  });
  currentZoom = signal(13);
  layersOpen = false;
  poiCatsOpen = true;
  layerItems = [
    { key: 'poi', label: 'Points of Interest', minZoom: LAYER_ZOOM.poi },
    { key: 'buildings', label: 'Buildings', minZoom: LAYER_ZOOM.buildings },
    { key: 'roads', label: 'Roads', minZoom: LAYER_ZOOM.roads },
  ];
  poiCategories = MAIN_POI.map((k) => ({ key: k, ...FCLASS_STYLES[k] }));
  poiCategoryVisible: Record<string, boolean> = Object.fromEntries(MAIN_POI.map((k) => [k, true]));
  layerVisibility: Record<string, boolean> = { poi: true, buildings: false, roads: true };
  selectedPoint: { lat: number; lon: number } | null = null;
  pointRadius = 1000;
  radii = [
    { m: 500, label: '500 m' },
    { m: 1000, label: '1 km' },
    { m: 2000, label: '2 km' },
    { m: 5000, label: '5 km' },
  ];
  quickCats = [
    { icon: '🏫', label: 'Schools', text: 'schools' },
    { icon: '🏥', label: 'Hospitals', text: 'hospitals' },
    { icon: '🍽️', label: 'Restaurants', text: 'restaurants' },
    { icon: '💊', label: 'Pharmacies', text: 'medical stores' },
    { icon: '🏧', label: 'ATMs', text: 'ATMs' },
    { icon: '🏨', label: 'Hotels', text: 'hotels' },
  ];
  ngOnInit(): void {
    this.checkSystemHealth();
  }

  ngAfterViewInit(): void {
    setTimeout(() => {
      if (document.getElementById('geomind-map')) {
        this.initMap();
      }
    }, 150);
  }

  ngOnDestroy(): void {
    this.map?.setTarget(undefined);
  }

  checkSystemHealth(): void {
    this.gisService.getHealth().subscribe({
      next: () => this.apiOnline.set(true),
      error: () => this.apiOnline.set(false),
    });
  }

  private initMap(): void {
    this.map?.setTarget(undefined);
    if (this.map) this.map.setTarget(undefined);

    const wmsUrl = 'http://localhost:8080/geoserver/wms';
    const wms = (layer: string, opacity: number, visibleFrom: number) =>
      new TileLayer({
        opacity,
        visible: false,
        minZoom: zmin(visibleFrom),
        source: new TileWMS({
          url: wmsUrl,
          params: { LAYERS: layer, FORMAT: 'image/png', TRANSPARENT: true, VERSION: '1.1.0' },
          serverType: 'geoserver',
        }),
      });

  this.geoserverLayers = {
    poi: this.poiLayer,
    buildings: wms('gis:buildings', 0.65, LAYER_ZOOM.buildings),
    roads: wms('gis:roads', 0.7, LAYER_ZOOM.roads),
  };
    Object.keys(this.geoserverLayers).forEach((k) =>
      this.geoserverLayers[k].setVisible(!!this.layerVisibility[k])
    );

    this.popupEl.className = 'ol-popup';
    this.popupEl.addEventListener('click', (ev) => {
      if ((ev.target as HTMLElement).classList.contains('ol-popup-close')) {
        this.popup.setPosition(undefined);
      }
    });

    this.map = new OlMap({
      target: 'geomind-map',
      layers: [
        new TileLayer({ source: new OSM() }),
        ...Object.values(this.geoserverLayers),
        this.bufferLayer,
        this.refLayer,
        this.resultsLayer,
        this.selectedLayer,
      ],
      overlays: [this.popup],
      controls: defaultControls({ zoom: false, rotate: false }), // keeps the OSM attribution
      view: new View({ center: fromLonLat([76.3125, 10.0261]), zoom: 13 }),
    });
    this.map.getView().on('change:resolution', () =>
      this.currentZoom.set(this.map.getView().getZoom() ?? 0)
    );

    if (this.lastExtent && !isEmpty(this.lastExtent)) {
      this.map.getView().fit(this.lastExtent, { padding: [30, 30, 30, 30], maxZoom: 17 });
    }

    this.map.on('singleclick', (e) => {
      if (this.selectingLocation) {
        const [lon, lat] = toLonLat(e.coordinate);
        this.selectedPoint = { lat: +lat.toFixed(6), lon: +lon.toFixed(6) };
        this.selectingLocation = false;
        this.selectedSource.clear();
        this.selectedSource.addFeature(new Feature(new Point(e.coordinate)));
        this.showPopup(e.coordinate, `<strong>Selected location</strong><div>${lat.toFixed(4)}, ${lon.toFixed(4)}</div>`);
        this.cdr.detectChanges();
        return;
      }
      const hit = this.map.forEachFeatureAtPixel(e.pixel, (f) => f as Feature, {
        layerFilter: (l) => l === this.resultsLayer || l === this.poiLayer|| l === this.refLayer,
      });
      if (hit) this.focusFeature(hit, e.coordinate);
      else this.popup.setPosition(undefined);
    });

    this.map.on('pointermove', (e) => {
      if (e.dragging) return;
      const overFeature = this.map.hasFeatureAtPixel(e.pixel, {
        layerFilter: (l) => l === this.resultsLayer || l === this.poiLayer || l === this.refLayer,
      });
      const target = this.map.getTargetElement() as HTMLElement | null;
      if (target) {
        target.style.cursor = this.selectingLocation ? 'crosshair' : overFeature ? 'pointer' : '';
      }
    });
  }
  // Toggle GeoServer layers on/off from UI
  toggleGeoServerLayer(layerKey: string): void {
    this.layerVisibility[layerKey] = !this.layerVisibility[layerKey];
    this.geoserverLayers[layerKey]?.setVisible(this.layerVisibility[layerKey]);
  }
  togglePoiCategory(key: string): void {
    this.poiCategoryVisible[key] = !this.poiCategoryVisible[key];
    this.poiLayer.changed();   // re-runs the style function
  }

  setAllPoi(on: boolean): void {
    MAIN_POI.forEach((k) => (this.poiCategoryVisible[k] = on));
    this.poiLayer.changed();
  }

  postgisStatus(): string { return this.apiOnline() ? 'Connected' : 'Offline'; }
  ollamaStatus(): string { return this.apiOnline() ? 'Ready' : 'Offline'; }

  switchTab(tab: 'Dashboard' | 'Map Explorer' | 'Results'): void {
    this.activeTab = tab;
    if (tab === 'Map Explorer') {
      setTimeout(() => {
        this.map?.updateSize();
        this.zoomToAllResults();
      }, 60);
    }
    this.cdr.detectChanges();
  }

  openFeature(f: any): void {
    this.switchTab('Map Explorer');
    setTimeout(() => this.zoomToFeature(f), 180);
  }

  private zoomBy(delta: number): void {
    const view = this.map?.getView();
    if (view) view.animate({ zoom: (view.getZoom() ?? 13) + delta, duration: 250 });
  }
  zoomIn(): void { this.zoomBy(1); }
  zoomOut(): void { this.zoomBy(-1); }

  zoomToAllResults(): void {
    if (this.lastExtent && !isEmpty(this.lastExtent)) {
      this.map?.getView().fit(this.lastExtent, { padding: [35, 35, 35, 35], maxZoom: 17, duration: 500 });
    }
  }

  analyzeQuery(): void {
    const trimmed = this.query.trim();
    if (!trimmed || this.loading()) return;

    // 👉 1. IMMEDIATE RESET (Clears old map features, table, and notices instantly)
    this.tableFeatures = [];

    if (this.resultsLayer) {
      this.resultsSource.clear();
    }

    this.activeLegend.set([]);
    this.hasResults = false;
    this.totalFeatures.set(0);
    this.queryTime.set('...');        // Resets the previous execution time immediately
    this.analysisRadius.set('');     // Resets the spatial intersect / buffer radius badge
    this.errorMessage = '';
    this.clarificationMessage = '';
    this.emptyMessage = '';
    this.truncationNotice = '';
    this.generatedSql.set('');
    this.lastExtent = undefined;

    // 👉 2. START LOADING STATE
    this.loading.set(true);
    this.showResultsCard = true;
    const startTime = performance.now();
    this.gisService
      .ask(trimmed, this.selectedPoint ?? undefined)
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (res: AskResponse & { notice?: string; total_available?: number;overlay?: any }) => {
          this.apiOnline.set(true);
          const duration = (performance.now() - startTime) / 1000;
          const ms = Math.round(duration * 1000);
          this.queryTime.set(duration < 1 ? `${(duration * 1000).toFixed(0)} ms` : `${duration.toFixed(2)} s`);
          this.generatedSql.set(res?.sql || '');

          if (res?.clarification) {
            this.clarificationMessage = res.clarification;
            this.addHistory(trimmed, 'unclear', null);
            this.recordStat(trimmed, ms, null, 'unclear');
            return;
          }

          const featuresList = res?.geojson?.features || [];
          const total = res?.total ?? featuresList.length;
          this.hasResults = total > 0;
          this.totalFeatures.set(total);
          this.analysisRadius.set(this.extractRadius(trimmed, res?.interpreted));

          // Populate the sidebar table data here
          this.tableFeatures = featuresList;

          if (res?.notice) {
            this.truncationNotice = res.notice;
          } else if (res?.total_available && res.total_available > featuresList.length) {
            this.truncationNotice = `Showing first ${featuresList.length} results (total matching features: ${res.total_available}).`;
          }

          if (total === 0) {
            const hint = res?.interpreted?.spatial?.length
              ? 'Try a larger buffer distance or relax one of the filters.'
              : 'Try different keywords, place names, or categories.';
            this.emptyMessage = `Nothing matched "${trimmed}". ${hint}`;
          }

          this.addHistory(trimmed, total > 0 ? 'ok' : 'empty', total);
          this.recordStat(trimmed, ms, total, total > 0 ? 'ok' : 'empty');
          this.renderGeoJson(res?.geojson);
          this.renderOverlay(res?.overlay);
        },
        error: (err) => {
          this.recordStat(trimmed, Math.round(performance.now() - startTime), null, 'error');
          this.apiOnline.set(false);
          this.queryTime.set('0.00 s');
          this.errorMessage = err?.error?.detail || err?.message || 'Cannot reach FastAPI backend.';
          this.tableFeatures = [];
          this.renderGeoJson(undefined);
        },
      });
  }
  private extractRadius(query: string, interpreted: any): string {
    if (interpreted?.spatial && interpreted.spatial.length > 0) {
      for (const cond of interpreted.spatial) {
        if (cond.distance_m) {
          const meters = cond.distance_m;
          return meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${meters} m`;
        }
        if (cond.operation === 'intersects') return 'Intersects';
      }
    }
    const match = query.match(/(\d+(\.\d+)?)\s*(m|meters|km|kilometers|mi|miles)/i);
    if (match) {
      const val = match[1];
      const unit = match[3].toLowerCase();
      if (unit.startsWith('m')) return `${val} m`;
      if (unit.startsWith('km')) return `${val} km`;
      if (unit.startsWith('mi')) return `${val} mi`;
    }
    return 'Spatial';
  }

  /**
   * Resolves symbology for POI (fclass), Buildings (type), Roads (fclass/bridge/tunnel), or Admin Boundaries
   */
  private resolveSymbology(props: Record<string, any> = {}, geomType = ''): SymbologyStyle {
    const fclass = String(props['fclass'] || '').toLowerCase().trim();
    const btype = String(props['type'] || '').toLowerCase().trim();

    if (fclass && FCLASS_STYLES[fclass]) {
      return FCLASS_STYLES[fclass];
    }
    if (btype && FCLASS_STYLES[btype]) {
      return FCLASS_STYLES[btype];
    }

    // Road symbology
    if (geomType.includes('Line')) {
      if (props['bridge'] === 'T') return { icon: '🌉', color: '#7c3aed', label: 'Bridge Road' };
      if (props['tunnel'] === 'T') return { icon: '🚇', color: '#334155', label: 'Tunnel Road' };
      if (fclass.includes('motorway') || fclass.includes('trunk')) return { icon: '🛣️', color: '#dc2626', label: 'Highway / Trunk' };
      if (fclass.includes('primary')) return { icon: '🛣️', color: '#ea580c', label: 'Primary Road' };
      if (fclass.includes('secondary')) return { icon: '🛣️', color: '#eab308', label: 'Secondary Road' };
      return { icon: '🛤️', color: '#475569', label: fclass ? `Road (${fclass})` : 'Road' };
    }

    // Polygon symbology (Buildings vs Admin Boundaries)
    if (geomType.includes('Polygon')) {
      if (btype) return { icon: '🏢', color: '#2F8F72', label: `Building (${btype})` };
      if (props['admin_level'] || (!btype && !fclass && props['name'])) {
        return { icon: '🗺️', color: '#2563eb', label: 'Admin Boundary' };
      }
      return { icon: '🏢', color: '#2F8F72', label: 'Building' };
    }

    // Fallback for unmapped POI fclass
    if (fclass) {
      return {
        icon: '📍',
        color: '#2F8F72',
        label: fclass.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
      };
    }

    return { icon: '📍', color: '#2F8F72', label: 'Feature' };
  }

  private renderGeoJson(geojson?: { type: string; features: any[] }): void {
    this.clearOverlay();
    this.resultsSource.clear();
    this.activeLegend.set([]);
    this.popup.setPosition(undefined);

    if (!geojson || !geojson.features?.length) {
      this.lastExtent = undefined;
      return;
    }

    this.tableFeatures = geojson.features;

    const features = new GeoJSON().readFeatures(geojson, {
      dataProjection: 'EPSG:4326',
      featureProjection: 'EPSG:3857',
    });
    this.resultsSource.addFeatures(features);

    const legendMap = new Map<string, SymbologyStyle>();
    features.forEach((f) => {
      const sym = this.resolveSymbology(f.getProperties(), f.getGeometry()?.getType() || '');
      legendMap.set(sym.label, sym);
    });
    this.activeLegend.set(Array.from(legendMap.values()).slice(0, 8));

    const extent = this.resultsSource.getExtent();
    if (extent && !isEmpty(extent)) {
      this.lastExtent = extent;
      this.map?.getView().fit(extent, { padding: [30, 30, 30, 30], maxZoom: 17, duration: 500 });
    }
  }

  toggleSelectOnMap(): void {
    this.selectingLocation = !this.selectingLocation;
  }

  // ---------------- History ----------------
  private loadHistory(): HistoryItem[] {
    try {
      const raw = localStorage.getItem(HISTORY_KEY);
      return raw ? (JSON.parse(raw) as HistoryItem[]) : [];
    } catch {
      return [];
    }
  }

  private saveHistory(items: HistoryItem[]): void {
    this.history.set(items);
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(items));
    } catch {}
  }

  private addHistory(query: string, status: HistoryItem['status'], total: number | null): void {
    const rest = this.history().filter((h) => h.query !== query);
    this.saveHistory([{ query, at: Date.now(), status, total }, ...rest].slice(0, HISTORY_MAX));
  }

  rerun(item: HistoryItem): void {
    this.query = item.query;
    this.analyzeQuery();
  }

  clearHistory(): void {
    this.saveHistory([]);
  }
  private styleFeature(feature: Feature): Style {
    const props = feature.getProperties();
    const geomType = feature.getGeometry()?.getType() || '';
    const sym = this.resolveSymbology(props, geomType);

    if (geomType.includes('Line')) {
      const special = props['bridge'] === 'T' || props['tunnel'] === 'T';
      return new Style({
        image: new CircleStyle({
          radius: 15,
          fill: new Fill({ color: this.lighten(sym.color, 0.78) }),
          stroke: new Stroke({ color: sym.color, width: 2 }),
        }),
        text: new Text({ text: sym.icon, font: '18px sans-serif', offsetY: 1 }),
      });
    }

    if (geomType.includes('Polygon')) {
      const isBoundary = !props['type'] && !props['fclass'];
      return new Style({
        stroke: new Stroke({
          color: isBoundary ? '#1d4ed8' : '#2d5a3f',
          width: isBoundary ? 2.5 : 2,
          lineDash: isBoundary ? [5, 5] : undefined,
        }),
        fill: new Fill({ color: this.withAlpha(sym.color, isBoundary ? 0.12 : 0.4) }),
      });
    }

    return new Style({
      image: new CircleStyle({
        radius: 13,
        fill: new Fill({ color: sym.color }),
        stroke: new Stroke({ color: '#ffffff', width: 2 }),
      }),
      text: new Text({ text: sym.icon, font: '13px sans-serif', offsetY: 1 }),
    });
  }

  private withAlpha(hex: string, alpha: number): string {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
  }
  // Mixes a hex color toward white. amount 0 = original color, 1 = white.
  private lighten(hex: string, amount: number): string {
    const n = parseInt(hex.slice(1), 16);
    const mix = (c: number) => Math.round(c + (255 - c) * amount);
    return `rgb(${mix((n >> 16) & 255)}, ${mix((n >> 8) & 255)}, ${mix(n & 255)})`;
  }

  private esc(v: unknown): string {
    return String(v).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!)
    );
  }

  private showPopup(coordinate: number[], html: string): void {
    this.popupEl.innerHTML = `<button type="button" class="ol-popup-close" aria-label="Close">&times;</button>${html}`;
    this.popup.setPosition(coordinate);
  }

  private focusFeature(f: Feature, clickCoord: number[]): void {
    const geom = f.getGeometry();
    if (!geom) return;
    const props = f.getProperties();
    const sym = this.resolveSymbology(props, geom.getType());
    const title = props['name'] || sym.label;

    const rows = Object.entries(props)
      .filter(([k, v]) => k !== 'geometry' && k !== 'geom' && v !== null && v !== '')
      .slice(0, 7)
      .map(([k, v]) => `<div><strong>${this.esc(k)}:</strong> ${this.esc(v)}</div>`)
      .join('');

    const isPoint = geom.getType() === 'Point';
    this.showPopup(
      isPoint ? (geom as Point).getCoordinates() : clickCoord,
      `<div style="font-weight:700;color:${sym.color};margin-bottom:4px;">${sym.icon} ${this.esc(title)}</div>${rows}`
    );

    const view = this.map.getView();
    if (isPoint) view.animate({ center: (geom as Point).getCoordinates(), zoom: 17, duration: 700 });
    else view.fit(geom.getExtent(), { padding: [50, 50, 50, 50], maxZoom: 17, duration: 700 });
  }

  zoomToFeature(feature: any): void {
    if (!feature?.geometry) return;
    const olFeature = new GeoJSON().readFeature(feature, {
      dataProjection: 'EPSG:4326',
      featureProjection: 'EPSG:3857',
    }) as Feature;
    const geom = olFeature.getGeometry();
    if (!geom) return;

    const view = this.map.getView();
    if (geom.getType() === 'Point') {
      view.animate({ center: (geom as Point).getCoordinates(), zoom: 17, duration: 700 });
    } else {
      view.fit(geom.getExtent(), { padding: [40, 40, 40, 40], maxZoom: 17, duration: 700 });
    }
  }
  closeResultsCard(): void {
    this.showResultsCard = false;
  }
  styleFor(f: any): SymbologyStyle {
    return this.resolveSymbology(f?.properties || {}, f?.geometry?.type || '');
  }

  fmt(ms: number): string {
    return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(2)} s`;
  }

  pct(v: number, max: number): number {
    return max > 0 ? Math.max((v / max) * 100, 2) : 0;   // 2% floor so zero-value bars stay visible
  }

  private loadStats(): QueryStat[] {
    try {
      const raw = localStorage.getItem(STATS_KEY);
      return raw ? (JSON.parse(raw) as QueryStat[]) : [];
    } catch {
      return [];
    }
  }

  private recordStat(query: string, ms: number, total: number | null, status: QueryStat['status']): void {
    const next = [{ query, at: Date.now(), ms, total, status }, ...this.stats()].slice(0, STATS_MAX);
    this.stats.set(next);
    try { localStorage.setItem(STATS_KEY, JSON.stringify(next)); } catch {}
  }

  clearStats(): void {
    this.stats.set([]);
    try { localStorage.removeItem(STATS_KEY); } catch {}
  }
  private refStyle(f: Feature): Style {
    const type = f.getGeometry()?.getType() || '';
    if (type === 'Point' || type === 'MultiPoint') {
      const sym = this.resolveSymbology(f.getProperties(), 'Point');
      return new Style({
        image: new CircleStyle({
          radius: 12,
          fill: new Fill({ color: this.lighten(sym.color, 0.82) }),
          stroke: new Stroke({ color: '#f59e0b', width: 2.5 }),   // orange ring = reference feature
        }),
        text: new Text({ text: sym.icon, font: '15px sans-serif', offsetY: 1 }),
      });
    }
    return new Style({
      stroke: new Stroke({ color: '#f59e0b', width: 2, lineDash: [6, 4] }),
      fill: new Fill({ color: 'rgba(245, 158, 11, 0.08)' }),
    });
  }

  private clearOverlay(): void {
    this.bufferSource.clear();
    this.refSource.clear();
    this.hasOverlay = false;
    this.overlayNote = '';
  }

  private renderOverlay(overlay?: any): void {
    if (!overlay) return;
    const fmt = new GeoJSON();
    const opts = { dataProjection: 'EPSG:4326', featureProjection: 'EPSG:3857' };

    if (overlay.buffer?.geometry) {
      this.bufferSource.addFeature(fmt.readFeature(overlay.buffer, opts) as Feature);
    }
    const refs = overlay.references?.features ?? [];
    if (refs.length) {
      this.refSource.addFeatures(fmt.readFeatures(overlay.references, opts) as Feature[]);
    }

    this.hasOverlay = refs.length > 0 || this.bufferSource.getFeatures().length > 0;
    this.bufferLayer.setVisible(this.showBuffer);
    this.refLayer.setVisible(this.showRefs);

    const d = overlay.distance_m;
    const radius = d >= 1000 ? `${+(d / 1000).toFixed(1)} km` : `${d} m`;
    const label = overlay.reference_label || 'reference';
    const who = overlay.around === 'reference' ? label : overlay.around === 'point' ? 'the selected location' : 'each result';
    this.overlayNote =
      `${radius} buffer around ${who}` +
      (refs.length ? ` · ${refs.length}${overlay.capped ? '+' : ''} ${label} shown with orange rings` : '');
    // zoom so the whole buffer is visible (extra right padding for the floating panel, bottom for the stats bar)
    const be = this.bufferSource.getExtent();
    if (be && !isEmpty(be)) {
      this.lastExtent = this.lastExtent ? extend([...this.lastExtent], be) : [...be];
      this.map?.getView().fit(this.lastExtent, { padding: [40, 380, 90, 40], maxZoom: 17, duration: 500 });
    }
  }

  toggleBuffer(): void {
    this.showBuffer = !this.showBuffer;
    this.bufferLayer.setVisible(this.showBuffer);
  }

  toggleRefs(): void {
    this.showRefs = !this.showRefs;
    this.refLayer.setVisible(this.showRefs);
  }

  // Used by the Clear button, so the map and overlay are wiped too
  clearAll(): void {
    this.query = '';
    this.selectingLocation = false;
    this.hasResults = false;
    this.tableFeatures = [];
    this.errorMessage = '';
    this.clarificationMessage = '';
    this.emptyMessage = '';
    this.truncationNotice = '';
    this.totalFeatures.set(0);
    this.queryTime.set('0.00 s');
    this.analysisRadius.set('Spatial');
    this.resultsSource.clear();
    this.selectedSource.clear();
    this.selectedPoint = null;
    this.clearOverlay();
    this.popup.setPosition(undefined);
    this.lastExtent = undefined;
  }
  searchHere(cat: { text: string }): void {
    const r = this.pointRadius >= 1000 ? `${this.pointRadius / 1000} km` : `${this.pointRadius} m`;
    this.query = `${cat.text} within ${r} of the selected location`;
    this.analyzeQuery();
  }

  clearPoint(): void {
    this.selectedPoint = null;
    this.selectedSource.clear();
    this.popup.setPosition(undefined);
  }
}