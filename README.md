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
- Postgres: localhost:5432 (`scotive` / `scotive`) — empty database, no migrations yet
- Redis: localhost:6379
- Sidekiq: same file

Rebuild after Gemfile changes: `docker compose up --build`. Stop: `docker compose down`.

### Production

```bash
cp backend/.env.prod.example backend/.env.prod
# fill SECRET_KEY_BASE, DEVISE_JWT_SECRET_KEY, DB password, integration keys
docker compose -f docker-compose.prod.yml up --build -d
```

- API: host port 3000
- Postgres / Redis: not published (compose network only)
- `RUN_DB_PREPARE` is still `false` (no table creation)

Logs: `docker compose -f docker-compose.prod.yml logs -f api`
Stop: `docker compose -f docker-compose.prod.yml down`

Set `POSTGRES_PASSWORD` in the shell or a root `.env` next to the prod compose file so it matches `DATABASE_URL` in `backend/.env.prod`.

Turn `FORCE_SSL=true` in `.env.prod` only when TLS terminates in front of the API.

## Auth (JSON)

- `POST /api/auth/sign_up` `{ "user": { "email", "password", "password_confirmation", "first_name", "last_name" }, "organization_name": "Acme" }`
- `POST /api/auth/sign_in` `{ "user": { "email", "password" } }`
- `DELETE /api/auth/sign_out` `Authorization: Bearer <token>`

Host Ruby (optional, RVM): `rvm use 3.3.10@scotive` then `cd backend && bundle exec rails s -p 3000` against compose Postgres/Redis.

Interactor pattern: from `backend/` run `bash ../interactor_setup.sh` when you start domain jobs.

Rulebook prompt: `backend/prompts/rulebook_reeval.txt`
