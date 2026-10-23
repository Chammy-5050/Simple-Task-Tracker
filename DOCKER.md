# Local development with Docker

Start Docker Desktop, then run these commands from this directory.

The Compose file, Dockerfile, and `.env` stay at the repository root. Django's `manage.py`, `requirements.txt`, and `.dockerignore` live in `taskTracker/`. Compose uses that folder as the build context and mounts it at `/app`, so commands inside the container still run beside `manage.py`.

If `.env` does not exist, copy `.env.template` to `.env` and enter your database credentials. Docker Compose reads this file automatically and passes its database settings to Django without overriding them.

```powershell
docker compose -f docker-compose.yaml up --build -d
docker compose -f docker-compose.yaml logs -f web
```

Open http://localhost:8001/. Port 8000 is already used by another local Docker app, so this project exposes Django on port 8001. Django's initial welcome page appears until application URLs are added. Database migrations run before the development server starts. Source code is mounted into the container for automatic reloads.

With your current `.env`, the application connects to database `smalltask` as user `tasktracker` at `db:5433`. PostgreSQL listens on `POSTGRES_PORT` inside Docker. The Compose mapping exposes it on `localhost:5434` for connections from your computer.

```powershell
docker compose -f docker-compose.yaml exec web python manage.py createsuperuser
docker compose -f docker-compose.yaml exec web python manage.py makemigrations
docker compose -f docker-compose.yaml exec web python manage.py migrate
docker compose -f docker-compose.yaml down
```

The database volume persists after `down`. Adding `-v` deletes its data. Database credentials initialize a new volume only; editing `.env` does not update credentials in an existing database. This starts a separate PostgreSQL database and does not import an existing database.

This configuration uses Django's development server and the project's development settings. Deployment requires production settings and a production application server.
