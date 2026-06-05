# Quickstart

Run the backend agent and the frontend locally.

## Prerequisites
- Python ≥ 3.11
- Node.js ≥ 18
- A Gemini API key

## Backend

### First-time setup
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -e .
cp .env.example .env            # then set GOOGLE_API_KEY
```

### Configure API keys
Edit `backend/.env`. `GOOGLE_API_KEY` is required; the three security sources
are optional — leave a key unset and that source is simply skipped.

#### 1. `GOOGLE_API_KEY` — Gemini (required)
1. Open https://aistudio.google.com/apikey
2. Sign in with your Google account → **Create API key**.
3. Copy the key into `GOOGLE_API_KEY` in `backend/.env`.

#### 2. `VIRUSTOTAL_API_KEY` — 70+ engine URL reputation (optional)
1. Register at https://www.virustotal.com/gui/join-us and verify your email.
2. Sign in, click your avatar (top-right) → **API Key**.
3. Copy the key into `VIRUSTOTAL_API_KEY`.
   - Free tier: 4 requests/min, 500/day — enough for a demo.

#### 3. `SAFE_BROWSING_API_KEY` — Google malware/phishing blacklist (optional)
1. Go to https://console.cloud.google.com and create (or pick) a project.
2. **APIs & Services → Library**, search **Safe Browsing API**, click **Enable**.
3. **APIs & Services → Credentials → Create credentials → API key**.
4. Copy the key into `SAFE_BROWSING_API_KEY`.
   - If you get HTTP 403, the API is not enabled on the selected project — recheck step 2.

#### 4. `URLHAUS_AUTH_KEY` — abuse.ch malware-URL blacklist (optional)
1. Create an account at https://auth.abuse.ch and sign in.
2. Open your **Profile** page → find the **Auth-Key** field.
3. Copy the full key into `URLHAUS_AUTH_KEY`.
   - A `403 unknown_auth_key` means the key is wrong — copy it again, in full.

### Run
```bash
cd backend
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
cd ..
adk web                         # UI at http://localhost:8000
```

## Frontend

### First-time setup
```bash
cd frontend
npm install
```

### Run
```bash
cd frontend
npm run dev                     # http://localhost:5173
```
