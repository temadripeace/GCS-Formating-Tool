import streamlit as st
import pyodbc
import pandas as pd
import geopandas as gpd
import os
from shapely import wkt
from shapely.geometry import Point, Polygon, MultiPolygon, MultiPoint
from io import BytesIO


col1, col2, col3 = st.columns([1, 3, 1])  # Left, Center, Right columns
with col2:
    st.image("Sucafina Logo.jpg", width=500)

st.markdown("<h3 style='text-align: center;'>Geographic Coordinate Formatting Tool - 6DP</h3>", unsafe_allow_html=True)

# ------------------ App Description ------------------
st.markdown(
    """
    <div style="text-align: justify; font-size: 16px;">
        This tool formats plot coordinates to <b>six decimal places</b> in compliance with <b>EUDR requirements</b>.
        It supports importing files in <b>CSV</b>, <b>Excel</b>, or <b>GeoJSON</b> format.
        <br><br>
        <b>Required column names:</b>
        <ul>
            <li><b>Longitude/Latitude</b>: <code>long</code>, <code>lat</code>, <code>longitude</code>, <code>latitude</code>, <code>plot_longitude</code>, <code>plot_latitude</code></li>
            <li><b>WKT format</b>: <code>gps_point</code>, <code>gps_polygon</code>, <code>plot_gps_point</code>, <code>plot_gps_polygon</code>, <code>plot_wkt</code>, <code>WKT</code>, <code>geometry</code></li>
        </ul>
    </div>
    """,
    unsafe_allow_html=True
)

# ------------------------------------- Streamlit Page Setup ---------------------------------------------
st.set_page_config(page_title="File Viewer", layout="centered")

st.markdown("<h3 style='text-align: left;'>📂 Upload Geospatial Data</h3>", unsafe_allow_html=True)

# ------------------ -----------Coordinate Processing Functions ------------------------------------------
def format_coord(value):
    try:
        s = str(value)
        if '.' in s:
            integer, decimal = s.split('.')
            if len(decimal) > 6:
                # Round to 6 decimals
                return f"{round(float(s), 6):.6f}"
            elif len(decimal) < 6:
                # Pad zeros so length before adding 1 is 5 decimals
                zeros_needed = 5 - len(decimal)
                padding = '0' * zeros_needed
                new_decimal = decimal + padding + '1'  # Add 1 as the 6th decimal digit
                return f"{integer}.{new_decimal}"
            else:
                return f"{float(s):.6f}"
        else:
            # No decimal, add 000001
            return f"{s}.000001"
    except Exception:
        return value

def apply_n_times(func, value, n):
    for _ in range(n):
        value = func(value)
    return value

def process_coords(coords):
    return [(float(format_coord(lon_col)), float(format_coord(lat_col))) for lon_col, lat_col in coords]

def process_polygon(polygon):
    exterior = process_coords(polygon.exterior.coords)
    interiors = [process_coords(ring.coords) for ring in polygon.interiors]
    return Polygon(exterior, interiors)

def process_point(point):
    x = float(format_coord(point.x))
    y = float(format_coord(point.y))
    return Point(x, y)

def process_wkt(wkt_string):
    try:
        geom = wkt.loads(wkt_string)
        if isinstance(geom, Polygon):
            return process_polygon(geom).wkt
        elif isinstance(geom, MultiPolygon):
            return MultiPolygon([process_polygon(p) for p in geom.geoms]).wkt
        elif isinstance(geom, Point):
            return process_point(geom).wkt
        elif isinstance(geom, MultiPoint):
            return MultiPoint([process_point(p) for p in geom.geoms]).wkt
        else:
            return wkt_string
    except:
        return wkt_string





# ----------------------------------------Convert to GeoDataFrame ----------------------------------------
def convert_to_geodf(df):
    wkt_columns = [col for col in df.columns if col.lower() in [
        "gps_point", "gps_polygon", "plot_gps_point", "plot_gps_polygon", "plot_wkt", "wkt", "geometry"
    ]]
    
    # Try WKT columns one by one
    for wkt_col in wkt_columns:
        try:
            # Attempt to parse WKT only where values are non-null/non-empty
            parsed = df[wkt_col].apply(lambda x: wkt.loads(str(x)) if pd.notnull(x) and str(x).strip() != '' else None)
            # Check if at least one valid geometry parsed
            if parsed.notnull().any():
                df[wkt_col] = parsed
                return gpd.GeoDataFrame(df, geometry=wkt_col, crs="EPSG:4326")
        except Exception as e:
            # Log or show warning but keep trying other columns
            st.warning(f"⚠ Could not parse WKT column '{wkt_col}': {e}")
            continue

    # If no WKT columns succeeded, try lat/lon columns
    lon_candidates = [col for col in df.columns if "lon" in col.lower()]
    lat_candidates = [col for col in df.columns if "lat" in col.lower()]
    if lon_candidates and lat_candidates:
        lon_col = lon_candidates[0]
        lat_col = lat_candidates[0]
        try:
            geometry = gpd.points_from_xy(df[lon_col], df[lat_col])
            return gpd.GeoDataFrame(df.copy(), geometry=geometry, crs="EPSG:4326")
        except Exception as e:
            st.warning(f"⚠ Could not create geometry from lat/lon: {e}")

    st.warning("⚠ No valid geometry found (WKT or Lat/Lon). GeoJSON/KML export may not work.")
    return df



# ------------------ ---------------------File Processing -------------------------------------------------
uploaded_file = st.file_uploader(
    "Upload CSV, Excel, or GeoJSON",
    type=["csv", "xlsx", "xls", "geojson", "json"]
)

if uploaded_file:
    ext = os.path.splitext(uploaded_file.name)[1].lower()

    try:
        # Step 1: Load as plain DataFrame
        if ext == ".csv":
            Data = pd.read_csv(uploaded_file)
        elif ext in [".xlsx", ".xls"]:
            Data = pd.read_excel(uploaded_file)
        elif ext in [".geojson", ".json", ".kml"]:
            gdf_temp = gpd.read_file(uploaded_file, driver="KML" if ext == ".kml" else None)
            Data = pd.DataFrame(gdf_temp)  # Temporarily drop geometry to process as text
            if "geometry" in Data.columns:
                Data["geometry"] = Data["geometry"].apply(lambda g: g.wkt if g is not None else None)
        else:
            st.error("❌ Unsupported file format")
            st.stop()

        # Step 2: Format lat/lon columns
        lat_lon_cols = ['plot_longitude', 'plot_latitude', 'longitute', 'latitute', 'log', 'lat']
        for col in lat_lon_cols:
            if col in Data.columns:
                Data[col] = Data[col].apply(lambda x: format_coord(x) if pd.notnull(x) else x)
                # Convert back to float
                try:
                    Data[col] = Data[col].astype(float)
                except:
                    pass

        # Step 3: Format WKT columns
        wkt_cols = ['plot_gps_point', 'plot_gps_polygon', 'gps_point', 'gps_polygon', 'plot_wkt', 'WKT','wkt', 'geometry', 'Geometry', 'GEOMETRY' ]
        for col in wkt_cols:
            if col in Data.columns:
                Data[col] = Data[col].apply(lambda x: apply_n_times(process_wkt, x, 2) if pd.notnull(x) else x)

        # Step 4: Convert to GeoDataFrame
        Data = convert_to_geodf(Data)

        # Step 5: Display processed data
        st.markdown("<h3 style='text-align: left;'>Processed Data Table</h3>", unsafe_allow_html=True)
        st.dataframe(Data)





        # ------------------ ---------------------------------Download Section -------------------------------------
        st.markdown("<h3 style='text-align: left;'> 🡇 Download Processed Data</h3>", unsafe_allow_html=True)
        format_choice = st.selectbox(
            "Select file format to download:",
            ["CSV", "EXCEL", "GeoJSON", "KML"]
        )

        file_name = f"processed_data.{format_choice.lower()}"
        file_data = None
        mime_type = ""

        if format_choice == "CSV":
            file_data = Data.to_csv(index=False).encode("utf-8")
            mime_type = "text/csv"

        elif format_choice == "EXCEL":
            try:
                buffer = BytesIO()
                Data.to_excel(buffer, index=False, engine="openpyxl")
                buffer.seek(0)
                file_data = buffer
                mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                file_name = "processed_data.xlsx"
            except ImportError:
                st.error("❌ Excel export requires `openpyxl`. Install it: `pip install openpyxl`")

        elif format_choice == "GeoJSON":
            if isinstance(Data, gpd.GeoDataFrame):
                file_data = Data.to_json().encode("utf-8")
                mime_type = "application/geo+json"
            else:
                st.error("❌ Data is not a GeoDataFrame. Cannot export as GeoJSON.")

        elif format_choice == "KML":
            if isinstance(Data, gpd.GeoDataFrame):
                kml_buffer = BytesIO()
                Data.to_file(kml_buffer, driver="KML")
                kml_buffer.seek(0)
                file_data = kml_buffer
                mime_type = "application/vnd.google-earth.kml+xml"
            else:
                st.error("❌ Data is not a GeoDataFrame. Cannot export as KML.")

        # Step 6: Download button
        if file_data:
            st.download_button(
                label=f"⬇ Download {format_choice}",
                data=file_data,
                file_name=file_name,
                mime=mime_type
            )

    except Exception as e:
        st.error(f"Error loading file: {e}")

