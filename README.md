# Simple Task Tracker API

Django REST API for the Simple Task Tracker frontend. See [DOCKER.md](DOCKER.md) for details on the database layout, uploads and permissions.

## Run with Docker Compose

```bash
cp .env.example .env          # then set POSTGRES_PASSWORD
docker compose up --build -d
docker compose exec web python manage.py seed_demo    # optional demo accounts and work
```

| Service | URL | Purpose |
| --- | --- | --- |
| `web` | http://localhost:8001 | Django API (migrations run on start) |
| `mailpit` | http://localhost:8025 | Development inbox: every email the API sends |
| `db` | localhost:5434 | PostgreSQL |
| `redis` | internal | Rate-limit counters for the code endpoints |

Start the frontend (`../STT-frontend/simple-task-tracker`) with `npm run dev`. Links in emails point at `FRONTEND_URL` (default http://localhost:3000).

## Email codes

All codes are sent by **email only**. Each code is 6 digits, stored only as a hash, expires after 10 minutes, and stops working after 5 wrong guesses or once a newer code is sent. A new code can be requested every 45 seconds. Code emails are limited to 5 per hour per IP address and per email address (`CODE_SEND_RATE`). Emails are sent on a background thread after the database commits; delivery failures are logged in the `web` container and never shown to the user.

With `SMTP_HOST=mailpit` (the default) nothing leaves your machine. To use a real mail server, set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS` and `DEFAULT_FROM_EMAIL` in `.env` and run `docker compose up -d`.

| Endpoint (under `/api/auth/`) | Body | Result |
| --- | --- | --- |
| `register/` | `email, full_name, phone_no, password, password_confirm` | Creates an **unverified** account and emails a verification code |
| `verify-email/` | `email, code` | Verifies the account and sends a welcome email |
| `resend-code/` | `email, purpose` (`email_verify` or `password_reset`) | Sends a new code if the account can use one |
| `password/forgot/` | `email` | Emails a reset code if the account exists |
| `password/verify-code/` | `email, code` | Returns `reset_token`, valid for 15 minutes and usable once |
| `password/reset/` | `reset_token, password, confirm_password` | Sets the password, ends every session and sends a "password changed" email |

`resend-code/` and `password/forgot/` return the same response whether or not the email belongs to an account. Passwords must have 8+ characters, an uppercase and a lowercase letter, a number and a special character; registration, reset and the in-app password change all enforce this.

Signing in to an unverified account returns HTTP 403 with `"code": "email_not_verified"` and emails a fresh code. Accounts that existed before email verification was added, accounts made with `createsuperuser`, and demo accounts count as verified.

## Test the flows by hand

**Email verification**

1. Open the frontend at `/register` and create an account with any address (Mailpit accepts everything).
2. You land on **Verify your email**. Open http://localhost:8025, open "Verify your email for Task Tracker" and copy the code.
3. Enter or paste the code. You'll see **Email verified**, and a "Welcome to Task Tracker" email arrives in Mailpit.
4. Sign in. Before step 3, signing in sends you back to the code screen and emails a new code.

**Password reset**

1. On `/login`, choose **Forgot password?** and enter an account's email, for example `hubert@demo.tasktracker.test` after running `seed_demo`.
2. **Check your inbox** shows the masked address. Open the "Your Task Tracker password reset code" email in Mailpit.
3. Choose **Enter reset code**, enter the code, then set a new password. The button stays disabled until every rule is met and both fields match.
4. **Password reset successful** appears and a "password was changed" email arrives. Any browser still signed in to that account is signed out on its next request.
5. To check that addresses aren't revealed, request a code for an address that has no account: the response is identical and no email is sent.

**From the command line**

```bash
curl -s -X POST localhost:8001/api/auth/password/forgot/ -H 'Content-Type: application/json' -d '{"email":"hubert@demo.tasktracker.test"}'
curl -s localhost:8025/api/v1/messages | python3 -m json.tool | grep -m1 Snippet
```

If you hit the rate limit while testing, clear the counters with `docker compose exec redis redis-cli FLUSHDB`.

## Tests

```bash
docker compose exec web python manage.py test     # backend (uses a separate test database)
```

The frontend browser tests (`npm run test:e2e` in the frontend) also need this stack running, because they read codes from Mailpit.
