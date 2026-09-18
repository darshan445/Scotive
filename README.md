# Scotive

Chase layer on QBO/Xero + Gmail/Outlook. Frontend is Next.js. API is Rails 8 (API-only).

## Docker — development vs production

Two compose files at the repo root. One Dockerfile with two targets (`development` / `production`).

| | Development | Production |
|---|---|---|
| Compose | `docker-compose.yml` | `docker-compose.prod.yml` |
| Env | `backend/.env` | `backend/.env.prod` |
| Image | `target: development` | `target: production` |
| Source | bind-mount `./backend` | baked into the image |
| Postgres / Redis ports | published (`5432`, `6379`) | internal only |
| Project name | `scotive-dev` | `scotive-prod` |

Do not run both stacks at once — they both want host port **3000**.

### Development

```bash
cp backend/.env.example backend/.env   # once; fill secrets
docker compose up --build
```

- API: http://localhost:3000/api/health
- Frontend: `cd frontend && npm run dev` → http://localhost:3001 (`NEXT_PUBLIC_BACKEND_URL=http://localhost:3000`)
- Postgres: localhost:5432 (`scotive` / `scotive`)
- Redis: localhost:6379
- Sidekiq: same compose file

After schema changes: `docker compose exec api bin/rails db:migrate`

Rebuild after Gemfile changes: `docker compose up --build`. Stop: `docker compose down`.

### Production

```bash
cp backend/.env.prod.example backend/.env.prod
# fill SECRET_KEY_BASE, DEVISE_JWT_SECRET_KEY, DB password, integration keys
docker compose -f docker-compose.prod.yml up --build -d
```

- API: host port 3000
- Postgres / Redis: not published (compose network only)

Logs: `docker compose -f docker-compose.prod.yml logs -f api`
Stop: `docker compose -f docker-compose.prod.yml down`

Set `POSTGRES_PASSWORD` in the shell or a root `.env` next to the prod compose file so it matches `DATABASE_URL` in `backend/.env.prod`.

Turn `FORCE_SSL=true` in `.env.prod` only when TLS terminates in front of the API.

## Auth (`/api/v1`)

Envelope: `{ "data": ... }` or `{ "errors": [{ "status", "code", "detail" }] }`. JWT in `Authorization: Bearer`.

| Method | Path | Body |
|---|---|---|
| POST | `/api/v1/auth/sign-up` | `{ email, password, name?, timezone? }` |
| POST | `/api/v1/auth/sign-in` | `{ email, password }` |
| GET | `/api/v1/auth/me` | Bearer |
| DELETE | `/api/v1/auth/sign-out` | Bearer |
| POST | `/api/v1/auth/forgot-password` | `{ email }` |
| POST | `/api/v1/auth/reset-password` | `{ token, password }` |

Host Ruby (optional, RVM): `rvm use 3.3.10@scotive` then `cd backend && bundle exec rails s -p 3000` against compose Postgres/Redis.

Interactors: `bin/rails generate interactor Auth::DoSomething` from `backend/`. Pattern is already installed.

Rulebook prompt: `backend/prompts/rulebook_reeval.txt`
