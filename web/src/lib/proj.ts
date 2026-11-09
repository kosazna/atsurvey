import proj4 from "proj4";

export const EGSA87 =
  "+proj=tmerc +lat_0=0 +lon_0=24 +k=0.9996 +x_0=500000 +y_0=0 +ellps=GRS80 +towgs84=-199.87,74.79,246.62,0,0,0,0 +units=m +no_defs";

proj4.defs("EPSG:2100", EGSA87);

const toWgs = proj4("EPSG:2100", "WGS84");

/** EGSA87 (E, N) → [lon, lat] */
export function egsaToLngLat(x: number, y: number): [number, number] {
  const [lon, lat] = toWgs.forward([x, y]);
  return [lon, lat];
}

/** [lon, lat] → EGSA87 (E, N) */
export function lngLatToEgsa(lon: number, lat: number): [number, number] {
  const [x, y] = toWgs.inverse([lon, lat]);
  return [x, y];
}
