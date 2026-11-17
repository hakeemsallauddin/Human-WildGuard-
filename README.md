# WildGuard — Human-Wildlife Conflict Prediction System

> *Protecting wildlife and people through intelligent conflict prediction.*

WildGuard is a conservation technology platform that combines real-time animal detection, spatiotemporal machine learning, and interactive geospatial visualization to forecast human-wildlife conflict hotspots before they occur. It was developed as a final-year project and validated across two geographic regions: **Parks Canada** and **Chitwan National Park, Nepal**.

---

## The Problem

Human-wildlife conflicts are escalating in wildlife corridor regions worldwide — causing crop damage, livestock predation, property destruction, and threatening both human safety and wildlife conservation. Communities and park authorities currently respond *reactively* rather than *proactively*, lacking the predictive tools to anticipate and prevent conflicts before they happen.

---

## The Solution

WildGuard integrates four core ML/AI components into a unified, fully deployed web dashboard:

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Animal Detection | YOLOv8 (custom 7-class model) | Identify species from uploaded images with confidence scores, run live against the deployed backend |
| Risk Classification | Random Forest | Predict conflict risk (HIGH / MEDIUM / LOW + probability) for a given location, species, and month — real trained models for **both** Canada and Chitwan |
| Hotspot Mapping | DBSCAN + KMeans | Cluster historical incidents into spatial hotspots and risk zones |
| Conflict Forecasting | SARIMAX | Time-series forecast of monthly incident frequency up to 12 months ahead |

---

## Features

- **Animal Detection** — Upload a field photo, get real-time species identification from a custom-trained YOLOv8 model, auto-captured GPS location, and an instant risk assessment for that spot
- **Interactive Risk Map** — Color-coded heatmap of conflict zones with toggleable layers (RF Risk Heatmap, DBSCAN Hotspots, KMeans Zones, Live Reports), plus a live banner showing the most recent real detection
- **Risk Assessment Tool** — Select a real region, field unit/park, species, and month to get a genuine model-driven risk probability — backed by a real trained Random Forest classifier for **both** Canada (precomputed grid) and Chitwan (per-species probability grid, 12 distinguishable species)
- **Analytics Dashboard** — Species distribution charts, monthly trend lines, seasonal heatmaps, and SARIMAX forecast plots for both Canada and Chitwan
- **Live Reports Feed** — Real-time community sighting submissions pushed instantly via WebSocket, sortable/filterable, with an escalation workflow rangers can use to bump a report's risk level
- **Real-Time Notifications** — Every detection and every risk escalation creates a shared notification instantly visible to all logged-in users, with per-user read tracking and a live unread-count badge
- **Global Live Alerts** — A toast popup appears on *every* page, for *every* user, whenever a new detection or escalation happens anywhere in the system
- **User Authentication** — Register and sign in with JWT-backed sessions, personalized avatar initials, and a real profile page showing your own submission history
- **Fully Responsive** — Collapsible navigation and adaptive layouts across all pages, tested down to phone width

---

## Datasets

| Dataset | Source | Period | Records |
|---------|--------|--------|---------|
| Parks Canada Human-Wildlife Coexistence Database | [open.canada.ca](https://open.canada.ca/data/en/dataset/743a0b4a-9e33-4b12-981a-9f9fd3dd1680) | 2010–2023 | ~49,000 incidents |
| Chitwan National Park Conflict Data | Raw incident-level records (GPS/local grid coordinates) | 2015–2018 | ~4,000 incidents |
| Animal Detection Image Dataset | Roboflow (custom-annotated) | — | ~3,600 images, 7 species |

Both regional conflict datasets are used to train independent Random Forest classifiers, DBSCAN hotspot clusters, and SARIMAX forecasts — the two regions are **not** pooled into a single model, since their coordinate systems, feature sets, and data granularity differ significantly (Canada uses field-unit-level aggregation; Chitwan uses raw per-incident records converted from Nepal's local Nagarkot TM projection to standard lat/lon).

---

## Tech Stack

**Machine Learning**
- YOLOv8 (Ultralytics) — custom-trained 7-class animal detector (Bear, Elephant, Nilgai, Rhinoceros, Tiger, Wild-Boar, leopard)
- Random Forest Classifier — two independently trained models (Parks Canada, Chitwan), each exported to a real precomputed probability grid for fast lookup at request time
- DBSCAN — spatial clustering / hotspot detection, both regions
- KMeans — regional zone segmentation
- SARIMAX — time-series conflict forecasting, both regions

**Backend** — fully built and deployed
- FastAPI (Python)
- Turso (SQLite via `libsql-client`) — users, reports, notifications
- WebSockets — real-time detection and escalation broadcasts to every connected client
- bcrypt (password hashing) + python-jose (JWT sessions)
- pandas + pyproj — real-time risk lookups against the precomputed grids, including coordinate system conversion for Chitwan
- Deployed on Render (free tier)

**Frontend**
- HTML, CSS, JavaScript (vanilla)
- Plotly (interactive charts) and Leaflet (interactive maps)
- Shared `wg-notifications.js` (single WebSocket connection per page, live popups, notification badge) and `wg-responsive.css` (breakpoint handling) across all pages

---

## Repository Structure

```
WildGuard-HWC-Prediction-System/
├── README.md
├── notebooks/
│   ├── chitwan/
│   │   ├── DBSCAN_clustering.ipynb
│   │   ├── Random_forest_classification.ipynb
│   │   ├── Risk_Analysis_(Classification)_(dataset_cleaning).ipynb
│   │   └── Time_Series_Analysis.ipynb
│   ├── canada_parks/
│   │   ├── Random_Forest_Dataset_Preparation_(Parks_Canada).ipynb
│   │   ├── parks_canada_arima.ipynb
│   │   ├── parks_canada_dbscan.ipynb
│   │   └── parks_canada_rf_v2.ipynb
│   └── yolo/
│       └── wildguard_yolo_train_colab.ipynb   ← trains the 7-class detector
├── backend/
│   ├── main.py            ← FastAPI app, all routes, WebSocket
│   ├── database.py        ← Turso client + table setup
│   ├── auth.py             ← register/login/profile, JWT
│   ├── yolo.py              ← loads best.pt, runs detection
│   ├── risk.py               ← risk lookups for both regions
│   ├── ws_manager.py          ← WebSocket connection manager
│   ├── best.pt                 ← trained YOLOv8 weights
│   ├── requirements.txt
│   ├── .env                     ← Turso credentials, JWT secret (gitignored)
│   ├── data/                     ← precomputed CSVs risk.py reads at startup
│   │   ├── parks_canada_risk_grid.csv
│   │   ├── parks_canada_dbscan_hotspot_summary.csv
│   │   ├── chitwan_hotspot_summary.csv
│   │   ├── chitwan_risk_grid_by_species.csv
│   │   └── chitwan_species_peak_month.csv
│   └── uploads/                   ← saved report images, served at /uploads
└── frontend/
    ├── index.html                          ← entry point / dashboard
    ├── wg-responsive.css                   ← shared breakpoints, nav-drift fixes
    ├── wg-notifications.js                 ← shared WebSocket + notification badge
    ├── pages/                              ← app screens
    │   ├── wildguard_analytics_html_.html
    │   ├── wildguard_animal_detection.html
    │   ├── wildguard_live_reports.html
    │   ├── wildguard_login_html_.html
    │   ├── wildguard_notifications.html
    │   ├── wildguard_profile_html_.html
    │   ├── wildguard_risk_assessment_html_.html
    │   └── wildguard_risk_map_html.html
    ├── wildguard_field_protocol.html        ← legal pages live at root
    ├── wildguard_privacy_policy.html
    ├── wildguard_terms_of_service.html
    └── visualizations/                     ← static ML output charts
        ├── canada/
        │   ├── canada_viz3_dbscan_hotspot_map.html
        │   ├── canada_viz6_rf_risk_heatmap.html
        │   ├── canada_viz7_kmeans_zones.html
        │   ├── canada_viz_8_species_risk_heatmap.html
        │   └── canada_viz10_species_donut.html
        ├── chitwan/
        │   ├── chitwan_viz1_conflict_heatmap.html
        │   ├── chitwan_viz2_kmeans_zones_map.html
        │   ├── chitwan_viz3_dbscan_hotspot.html
        │   ├── chitwan_viz4_sarima_forecast.html
        │   ├── chitwan_viz5_species_donut.html
        │   ├── chitwan_viz6_monthly_trend.html
        │   └── chitwan_viz11_species_month_heatmap.html
        └── combined/
            ├── viz4_sarimax_forecast.html
            └── viz5_monthly_trend.html
```

---

## Team

| Member | Role |
|--------|------|
| Deepika | ML models — Random Forest, DBSCAN, KMeans, SARIMAX; dataset preparation; backend build and deployment; full-stack integration |
| Ina | Computer Vision — YOLOv8 training and species detection |
| Shikshya | Backend — Flask/FastAPI, database, API endpoints |
| Riya | Frontend — dashboard, detection, risk assessment, live reports pages |
| Prasamsha | Visualizations — Plotly charts, Folium maps, analytics dashboard |

---

## Running Locally

**Frontend:**
```bash
git clone https://github.com/Deepikahaha/WildGuard-HWC-Prediction-System.git
cd WildGuard-HWC-Prediction-System/frontend

# Serve with Python (required — direct file:// won't load iframes or fetch calls)
python -m http.server 8000
```
Then open `http://localhost:8000`.

**Backend** (only needed if working on backend/ML code — the deployed frontend already points at the live Render instance):
```bash
cd WildGuard-HWC-Prediction-System/backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
# Add TURSO_DATABASE_URL, TURSO_AUTH_TOKEN, JWT_SECRET to a .env file
uvicorn main:app --reload
```
Swagger docs available at `http://localhost:8000/docs` once running.

> **Note:** Open the frontend via `localhost`, not by double-clicking the HTML file. Browsers block iframe loading and fetch calls from `file://` paths.

---

## Status

- [x] Frontend complete (all 11 pages, fully responsive)
- [x] ML notebooks complete (Random Forest, DBSCAN, KMeans, SARIMAX) — both regions
- [x] YOLOv8 model trained and deployed (7 species)
- [x] Real per-species Random Forest risk grid — both Canada and Chitwan
- [x] Plotly visualizations complete (Canada + Chitwan)
- [x] Backend API complete and deployed (FastAPI on Render)
- [x] Backend–frontend integration complete
- [x] Real-time WebSocket updates (detections, escalations, notifications)
- [x] User authentication, sessions, and profile history
- [ ] Live camera trap integration (future)

---

## License

This project was developed for academic and conservation research purposes. Data sourced from Parks Canada is used under the [Open Government Licence – Canada](https://open.canada.ca/en/open-government-licence-canada).