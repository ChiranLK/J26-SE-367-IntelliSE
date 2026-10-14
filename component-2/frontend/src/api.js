// All calls to the FastAPI backend (api.py) go through this file.
export const API = "http://localhost:8000";

async function request(path, options) {
  let res;
  try {
    res = await fetch(API + path, options);
  } catch {
    throw new Error("Cannot reach the backend. Start it with: uvicorn api:app --port 8000");
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail);
  return data;
}

export const getJson = (path) => request(path);

export const postJson = (path, body) =>
  request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

// PlantUML sends the picture as SVG text; an <img> can show it like this
export const svgSrc = (svg) => "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);