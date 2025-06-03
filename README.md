# 🌿 NDVI Change Detector

This Streamlit app compares two Sentinel-2 images over a user-defined AOI, computes NDVI change, and outputs a shapefile of significant differences.

## 🚀 Features
- Draw AOI or upload GeoJSON
- Select two dates for NDVI comparison
- Visualize and download NDVI change polygons

## 🔗 Powered by:
- Sentinel Hub (Copernicus Data Space)
- Streamlit + Folium + GeoPandas

## 📦 Install locally

```bash
pip install -r requirements.txt
streamlit run app.py
