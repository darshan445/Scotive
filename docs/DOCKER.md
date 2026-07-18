# Docker — Scotive API (FastAPI + MongoDB)
#
# Frontend stays on Vercel. This stack is backend-only.
#
# ## Development (hot reload)
#   cp backend/.env.example backend/.env
#   # set secrets; MONGO_URL is overridden by compose to mongodb://mongo:27017
#   docker compose up --build
#   curl http://localhost:8000/api/health
#
# ## Production (single Uvicorn worker)
#   cp backend/.env.example backend/.env.production
#   # set FRONTEND_URL, GMAIL_REDIRECT_URI, secrets for api.scotive.com
#   docker compose -f docker-compose.prod.yml up -d --build
#
# Production image CMD uses: uvicorn ... --workers 1
# That guarantees startup recovery + background loops run once per boot.
# Do not scale `api` replicas above 1 until you move jobs to a real worker queue.
#
# Images: python:3.11-slim-bookworm · mongo:7.0 · uvicorn 0.25 · fastapi 0.110
