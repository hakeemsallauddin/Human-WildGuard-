import pandas as pd
import numpy as np

# Load existing datasets
_canada_grid = pd.read_csv("data/parks_canada_risk_grid.csv")
_canada_hot = pd.read_csv("data/parks_canada_dbscan_hotspot_summary.csv")
_chitwan_hot = pd.read_csv("data/chitwan_hotspot_summary.csv")
_chitwan_peak = (
    pd.read_csv("data/chitwan_species_peak_month.csv")
    .set_index("PROBLEM_ANIMAL")["Peak_Month"]
)

try:
    _chitwan_grid = pd.read_csv("data/chitwan_risk_grid_by_species.csv")
    _chitwan_grid["Species"] = _chitwan_grid["Species"].str.strip().str.title()
except FileNotFoundError:
    _chitwan_grid = None

_PRIORITY_TO_RISK = {"CRITICAL": "HIGH", "ACTIVE": "MEDIUM"}


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def _inside_grid(lat, lon, grid, lat_col, lon_col):
    return (
        grid[lat_col].min() <= lat <= grid[lat_col].max()
        and grid[lon_col].min() <= lon <= grid[lon_col].max()
    )


def _unavailable_result():
    return {
        "region": "unsupported",
        "risk_level": "NOT_AVAILABLE",
        "high_risk_prob": None,
        "nearest_hotspot": None,
        "hotspot_species": None,
        "hotspot_distance_km": None,
        "hotspot_priority": None,
        "hotspot_peak_month": None,
        "hotspot_incident_count": None,
        "is_peak_season": False,
        "message": "No supported risk dataset covers these coordinates."
    }


def predict_risk(lat: float, lon: float, species: str = None, month: int = None):

    # Reject invalid coordinates
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return _unavailable_result()

    if not np.isfinite(lat) or not np.isfinite(lon):
        return _unavailable_result()

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return _unavailable_result()

    # Select a region only when its dataset actually covers the coordinates
    if _inside_grid(lat, lon, _canada_grid, "Latitude", "Longitude"):
        result = _canada_risk(lat, lon)

    elif (
        _chitwan_grid is not None
        and _inside_grid(lat, lon, _chitwan_grid, "Latitude", "Longitude")
    ):
        result = _chitwan_risk(lat, lon, species)

    else:
        return _unavailable_result()

    result["is_peak_season"] = (
        month is not None
        and result["hotspot_peak_month"] is not None
        and month == result["hotspot_peak_month"]
    )

    return result


def _canada_risk(lat, lon):
    d_grid = _haversine_km(
        lat, lon, _canada_grid.Latitude, _canada_grid.Longitude
    )
    cell = _canada_grid.iloc[d_grid.idxmin()]

    d_hot = _haversine_km(
        lat, lon, _canada_hot.Center_Lat, _canada_hot.Center_Lon
    )
    hot = _canada_hot.iloc[d_hot.idxmin()]

    return {
        "region": "canada",
        "risk_level": cell.Risk_Level,
        "high_risk_prob": round(float(cell.High_Risk_Prob), 3),
        "nearest_hotspot": hot.Primary_Park,
        "hotspot_species": hot.Primary_Species,
        "hotspot_distance_km": round(float(d_hot.min()), 1),
        "hotspot_priority": hot.Priority,
        "hotspot_peak_month": int(hot.Peak_Month),
        "hotspot_incident_count": int(hot.Incident_Count),
    }


def _chitwan_risk(lat, lon, species=None):
    d_hot = _haversine_km(
        lat, lon, _chitwan_hot.Center_Lat, _chitwan_hot.Center_Lon
    )
    hot = _chitwan_hot.iloc[d_hot.idxmin()]

    lookup_species = (species or hot.Primary_Animal).strip().title()
    peak_month = _chitwan_peak.get(
        lookup_species, _chitwan_peak.get(hot.Primary_Animal)
    )

    if _chitwan_grid is not None:
        subset = _chitwan_grid[_chitwan_grid.Species == lookup_species]

        if subset.empty:
            subset = _chitwan_grid[_chitwan_grid.Species == "Unspecified"]

        if subset.empty:
            return _unavailable_result()

        d_grid = _haversine_km(
            lat, lon, subset.Latitude, subset.Longitude
        )
        cell = subset.iloc[d_grid.values.argmin()]
        risk_level = cell.Risk_Level
        high_risk_prob = round(float(cell.High_Risk_Prob), 3)

    else:
        risk_level = _PRIORITY_TO_RISK.get(
            hot.Priority_Level, "MEDIUM"
        )
        high_risk_prob = None

    return {
        "region": "chitwan",
        "risk_level": risk_level,
        "high_risk_prob": high_risk_prob,
        "nearest_hotspot": f"Cluster {hot.DBSCAN_Cluster} ({hot.CONFLICT_TYPE})",
        "hotspot_species": hot.Primary_Animal,
        "hotspot_distance_km": round(float(d_hot.min()), 1),
        "hotspot_priority": hot.Priority_Level,
        "hotspot_peak_month": int(peak_month) if pd.notna(peak_month) else None,
        "hotspot_incident_count": int(hot.Incident_Count),
    }
