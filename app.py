import streamlit as st
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape, mapping
import geopandas as gpd
from sentinelhub import SHConfig, BBox, CRS, SentinelHubRequest, DataCollection, MimeType, bbox_to_dimensions, SentinelHubDownloadClient
import numpy as np
import tempfile
import os
import json
import rasterio
from rasterio.features import shapes
from zipfile import ZipFile

# Sentinel Hub Auth
config = SHConfig()
config.sh_client_id = st.secrets["CLIENT_ID"]
config.sh_client_secret = st.secrets["CLIENT_SECRET"]

st.title("🌿 Sentinel-2 NDVI Change Detector")

# Upload or draw AOI
st.subheader("1️⃣ Define Area of Interest (AOI)")
aoi_geojson = None

aoi_file = st.file_uploader("Upload AOI (GeoJSON)", type=["geojson"])

if aoi_file:
    aoi_geojson = json.load(aoi_file)
else:
    st.write("Or draw your AOI on the map below ⬇️")

    m = folium.Map(location=[0, 0], zoom_start=2)
    draw = folium.plugins.Draw(export=True)
    draw.add_to(m)

    output = st_folium(m, width=700, height=500)
    if output.get("last_active_drawing"):
        aoi_geojson = output["last_active_drawing"]

if aoi_geojson:
    geom = shape(aoi_geojson["geometry"])
    aoi_gdf = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
    bounds = geom.bounds
    bbox = BBox(bbox=[bounds[0], bounds[1], bounds[2], bounds[3]], crs=CRS.WGS84)

    st.success("AOI loaded!")

    # Dates
    st.subheader("2️⃣ Select Dates")
    date1 = st.date_input("Start Date")
    date2 = st.date_input("End Date")

    resolution = 10  # meters
    size = bbox_to_dimensions(bbox, resolution=resolution)

    # NDVI evalscript
    evalscript = """
    //VERSION=3
    function setup() {
      return {
        input: ["B04", "B08"],
        output: {
          bands: 1,
          sampleType: "FLOAT32"
        }
      };
    }

    function evaluatePixel(sample) {
      let ndvi = index(sample.B08, sample.B04);
      return [ndvi];
    }
    """

    def get_ndvi(date):
        request = SentinelHubRequest(
            evalscript=evalscript,
            input_data=[SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L2A,
                time_interval=(str(date), str(date))
            )],
            responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
            bbox=bbox,
            size=size,
            config=config
        )
        return request.get_data()[0]

    if st.button("🛰️ Compute NDVI Difference"):
        with st.spinner("Downloading Sentinel data..."):
            ndvi1 = get_ndvi(date1)
            ndvi2 = get_ndvi(date2)
            diff = ndvi2 - ndvi1

            # Save diff to temporary raster
            with tempfile.TemporaryDirectory() as tmpdir:
                diff_path = os.path.join(tmpdir, "ndvi_diff.tif")
                meta = {
                    "driver": "GTiff",
                    "dtype": rasterio.float32,
                    "count": 1,
                    "height": diff.shape[0],
                    "width": diff.shape[1],
                    "transform": rasterio.transform.from_bounds(*bbox, diff.shape[1], diff.shape[0]),
                    "crs": "EPSG:4326"
                }
                with rasterio.open(diff_path, "w", **meta) as dst:
                    dst.write(diff, 1)

                st.subheader("3️⃣ NDVI Difference Map")
                st.image((diff - np.min(diff)) / (np.max(diff) - np.min(diff)), caption="Normalized NDVI Difference")

                # Threshold
                threshold = st.slider("NDVI change threshold", 0.0, 1.0, 0.2)

                # Binary change
                binary = (np.abs(diff) > threshold).astype(np.uint8)

                # Extract polygons
                shapes_gen = shapes(binary, mask=binary.astype(bool), transform=meta["transform"])
                geoms = [shape(geom) for geom, val in shapes_gen if val == 1]
                gdf = gpd.GeoDataFrame(geometry=geoms, crs="EPSG:4326")

                st.success(f"Detected {len(gdf)} change areas.")

                # Download options
                geojson_bytes = gdf.to_json().encode("utf-8")
                st.download_button("📥 Download GeoJSON", geojson_bytes, "ndvi_change.geojson", "application/geo+json")

                with tempfile.TemporaryDirectory() as zdir:
                    shp_path = os.path.join(zdir, "ndvi_change.shp")
                    gdf.to_file(shp_path)
                    zip_path = os.path.join(zdir, "ndvi_change.zip")
                    with ZipFile(zip_path, "w") as zf:
                        for ext in [".shp", ".shx", ".dbf", ".cpg", ".prj"]:
                            part = shp_path.replace(".shp", ext)
                            if os.path.exists(part):
                                zf.write(part, arcname=os.path.basename(part))
                    with open(zip_path, "rb") as f:
                        st.download_button("📥 Download Shapefile (ZIP)", f.read(), "ndvi_change.zip", "application/zip")
