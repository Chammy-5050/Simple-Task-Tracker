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

## Application tables and authentication

The STT migration creates `roles`, `users`, `projects`, and `tasks`. Authentication uses `STT.Users`, with email as the login identifier and `user_id` as the JWT user identifier. Django admin is enabled at `/admin/` and uses sessions; the API uses JWTs. Django's supporting tables remain in use. Accounts in the old `auth_user` table are not automatically transferred into `users`.

To create the team administrator, run `docker compose run --rm web python manage.py createsuperuser` and enter an email, full name, phone number, and password. Sign in through the frontend login page to see all projects and tasks. User creation/management is not exposed in the frontend, API, or Django admin. Members register themselves through public registration, which grants no administrative privileges.

`STT/serializers.py` includes the serializers required by all API views. Login accepts `email` and `password`. Registration accepts `email`, `full_name`, `phone_no`, `password`, and `password_confirm`; passwords are write-only and preserve whitespace. Public registration never accepts role or superuser privileges. Project and task serializers keep ownership, identifiers, and timestamps read-only.

## Uploaded pictures

Django uses its default `FileSystemStorage`, with `MEDIA_ROOT` set to `/app/media` in Docker and `MEDIA_URL` set to `/media/`. The existing `./taskTracker:/app` bind mount keeps uploads on your computer under `taskTracker/media/`, so recreating a container does not remove them. These files are excluded from Git and Docker builds. The database stores the relative file path, not the image bytes.

Profile and project pictures use `ImageField` with Pillow. Users set their own profile pictures through the authenticated endpoint below; public registration does not accept a profile picture. Replaced profile pictures are removed after the database transaction commits.

With `DEBUG=True`, Django serves uploaded files publicly under `/media/`. Production hosting must serve media separately or use a storage backend such as object storage; the development media route does not run with `DEBUG=False`.

## Creating projects

`POST /api/projects/` requires an access token in `Authorization: Bearer <access_token>`. Supply `project_name` and optional `description` as JSON. The service assigns ownership from the signed-in user and returns HTTP 201 with the serialized project. A duplicate project name returns a field validation error. The model currently requires project names to be unique across all users.

`ProjectSerializer` accepts `project_name` and optional `description`, with `user_id`, `project_id`, and timestamps read-only. The endpoint never accepts ownership from the client. Picture uploads are not part of this endpoint.

## Updating your profile picture

`GET /api/users/me/` retrieves the signed-in user's profile. `PATCH /api/users/me/` accepts either JSON profile fields (`full_name`, `email`, `phone_no`) or a multipart `profile_picture` upload. The endpoint always selects the authenticated user; request-supplied user IDs or privilege fields cannot change another account. A valid upload returns HTTP 200 with `user_id` and the picture's absolute URL. Invalid images and empty patches return validation errors.

`POST /api/users/me/password/` requires the current password, a new `password`, and matching `password_confirm`. The frontend signs out after a successful password change.

## Frontend user management

The superuser is the team administrator and uses the regular frontend workspace, with access to all projects and tasks. User-management API routes are removed and the old `/admin/users` frontend URL redirects to the workspace. Ordinary members remain limited to projects they own. Django admin registers projects and tasks only, without user or group management.

Tasks support optional `due_date` and authenticated updates at `PATCH /api/projects/<project_id>/tasks/<task_id>/`. Project ownership is checked before every task operation. `POST /api/auth/refresh/` exchanges a valid refresh token for a new access token.

## Database schemas

Migration `STT.0006_separate_django_tables` separates PostgreSQL tables:

- `public`: `users`, `roles`, `projects`, `tasks`.
- `django_internal`: Django permissions, groups, sessions, admin history, content types, and migration history.

The backend connection searches `public,django_internal`, so Django can still resolve its supporting tables. Keep this search path when changing database settings. The migration moves existing tables and their data; it does not recreate the database or remove accounts. It also runs on a new database through the normal `docker compose up` migration command.

Refresh DBeaver's Schemas tree after applying migrations. Application tables appear under `public` without individual table filters. The internal schema remains visible to database accounts that can access it; this is organization, not a permission boundary.

Rollback with `docker compose exec web python manage.py migrate STT 0005_tasks_due_date`. This returns the supporting tables to `public` and leaves the empty schema in place. Future framework migrations that introduce additional tables should include a follow-up schema move; existing table alterations resolve through the search path.

Local database backups belong in the Git-ignored `.backups/` directory and must not be committed.
