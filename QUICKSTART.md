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
