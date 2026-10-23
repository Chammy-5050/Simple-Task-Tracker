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

To create the first administrator, run `docker compose run --rm web python manage.py createsuperuser --skip-checks` and enter an email, full name, phone number, and password. The `--skip-checks` option permits this command while your colleague's serializers are still missing. Once those files are ready and the server is running, sign in at http://localhost:8000/admin/ to create and manage additional administrators. Admin accounts need both `is_staff` and `is_superuser`; ordinary public registration grants neither. A selected role controls the user's `is_superuser` flag, so use an administrator role that grants superuser access or leave the role empty when creating a superuser.

The serializer implementation is owned by your colleague. `LoginSerializer` must supply `email` and `password`. `RegisterSerializer` must supply `email`, `full_name`, `phone_no`, `password`, and `password_confirm`; passwords must be write-only and must not trim whitespace. Public registration never accepts role or superuser privileges. `ProjectSerializer` represents the existing `Projects` fields. Until these serializers exist, URL loading and normal server startup will fail.

## Uploaded pictures

Django uses its default `FileSystemStorage`, with `MEDIA_ROOT` set to `/app/media` in Docker and `MEDIA_URL` set to `/media/`. The existing `./taskTracker:/app` bind mount keeps uploads on your computer under `taskTracker/media/`, so recreating a container does not remove them. These files are excluded from Git and Docker builds. The database stores the relative file path, not the image bytes.

Profile and project pictures use `ImageField` with Pillow. A user profile picture is optional during registration: your colleague should add `profile_picture = serializers.ImageField(required=False)` to `RegisterSerializer`. Send a picture and registration fields as `multipart/form-data`. The service validates the image, saves it through Django storage, and the response includes its URL. Existing users' pictures can also be edited in Django admin. Replaced profile pictures are removed after the database transaction commits.

With `DEBUG=True`, Django serves uploaded files publicly under `/media/`. Production hosting must serve media separately or use a storage backend such as object storage; the development media route does not run with `DEBUG=False`.
