BetweenUs

A real anonymous peer-support MVP: anonymous sessions, SQLite-backed thoughts and relate counts, lightweight matching, private two-person chat, and report/block actions.

Run locally

```powershell
python server.py
```

Then open `http://127.0.0.1:4173`. Open a second private/incognito browser window to test a live match and chat with another anonymous session.

Deploy

The included `Dockerfile` can deploy to any Docker host; `render.yaml` also supplies a Render Blueprint with a persistent disk for the SQLite database. Set `PORT` if your platform supplies one.

Before a public launch, use managed Postgres instead of SQLite, add rate limiting, trusted moderation review queues, encrypted backups, terms/privacy pages, age-gating where required, and a crisis-safety flow. This MVP intentionally does not claim to be therapy or emergency care.
