# Running on Windows — from a zipped folder to a live demo

These steps assume a normal Windows 10/11 laptop with no dev tools
pre-installed. Follow them in order.

## 1. Unzip the project

Right-click `sih-ambulance-router.zip` → **Extract All…** → choose a short
path like `C:\sih-ambulance-router` (avoid deeply nested folders / OneDrive
sync paths, which can cause file-lock issues with `node_modules`).

## 2. Install prerequisites

Install these in order, accepting defaults unless noted:

1. **Python 3.11+** — https://www.python.org/downloads/windows/
   During install, **check "Add python.exe to PATH"**.
2. **Node.js 20 LTS** — https://nodejs.org/en/download
3. **Git** (optional, only if you'll `git clone` instead of unzipping) — https://git-scm.com/download/win
4. **Docker Desktop** (optional — only needed for the full docker-compose stack with OSRM/Mosquitto) — https://www.docker.com/products/docker-desktop/
   Enable WSL2 backend when prompted.

Verify installs by opening **PowerShell** and running:
```powershell
python --version
node --version
npm --version
```

## 3. Backend setup (PowerShell)

```powershell
cd C:\sih-ambulance-router\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If `torch` fails to install (large download / slow network), install the
CPU-only build directly first, then retry:
```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

Start the backend:
```powershell
uvicorn app.main:app --reload --port 8000
```
Leave this window open. Visit http://localhost:8000/health — you should
see `{"status":"ok",...}`.

## 4. Frontend setup (new PowerShell window)

```powershell
cd C:\sih-ambulance-router\frontend
npm install
npm run dev
```
Leave this window open too. Open **http://localhost:5173** in your
browser — this is the jury-demo UI (Chaos Mode map, Algorithm Arena,
Profiler dashboards, Explainability Log).

## 5. Run the smoke test (optional, third PowerShell window)

```powershell
cd C:\sih-ambulance-router
..\backend\venv\Scripts\Activate.ps1   # or: backend\venv\Scripts\Activate.ps1 from repo root
pip install httpx
python smoke_test.py --base-url http://localhost:8000
```
You should see 7 green `OK` steps ending in "✅ Full loop smoke test passed".

## 6. (Optional) Full stack with Docker Desktop

Only needed if you want live OSRM/Mosquitto containers instead of the
automatic fallbacks. With Docker Desktop running:
```powershell
cd C:\sih-ambulance-router
docker compose up --build
```
Open http://localhost:5173. First build can take 5–10 minutes (downloading
base images and the OSRM/Node/Python layers).

### One-time OSRM dataset prep (only if you want real road-network routing via OSRM)

```powershell
# Download a .osm.pbf extract for your city from https://download.geofabrik.de/
# then, with Docker Desktop running:
docker run -t -v "%cd%/backend/data/osrm:/data" osrm/osrm-backend osrm-extract -p /opt/car.lua /data/southern-zone-260903.osm.pbf
docker run -t -v "%cd%/backend/data/osrm:/data" osrm/osrm-backend osrm-partition /data/southern-zone-260903.osrm
docker run -t -v "%cd%/backend/data/osrm:/data" osrm/osrm-backend osrm-customize /data/southern-zone-260903.osrm
```
Then update `docker-compose.yml`'s `osrm` service command to point at
`southern-zone-260903.osrm` and re-run `docker compose up --build`. Until you do this,
the router automatically uses haversine-distance estimates instead — the
rest of the system works identically either way.

## 7. Enabling the optional GenAI Copilot (Section 4.1)

```powershell
$env:GROQ_API_KEY = "your-groq-api-key-here"
```
Set this **before** starting `uvicorn` (step 3) in that same PowerShell
window, then restart the backend. Get a free key at https://console.groq.com.

## Troubleshooting

- **"python is not recognized"** — Python wasn't added to PATH; re-run the
  installer and check that box, or use the `py` launcher instead of `python`.
- **Port already in use (8000 or 5173)** — another process is bound to it;
  stop it or change the port (`--port 8001` for uvicorn; edit
  `vite.config.js`'s `server.port` for the frontend).
- **`pip install -r requirements.txt` is slow/times out on `torch`** — see
  the CPU-only install command in step 3.
- **Frontend shows "disconnected" in the header** — the backend isn't
  running or is on a different port than the Vite proxy expects
  (`frontend/vite.config.js` assumes `http://localhost:8000`).
