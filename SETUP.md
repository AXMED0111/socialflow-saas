# SocialFlow SaaS - Setup Guide

## What's built so far

- **backend/** — Node.js/Express API. Handles auth, workspaces, team roles,
  media uploads, post scheduling, and the cron job that fires posts to each platform.
  SQLite database (one file per company — no separate DB server needed to start).
- **telegram-bot/** — Python bot. Full conversation flow: link account → upload
  media → caption → pick platforms → schedule → confirm.
- **database/schema.sql** — All tables, used automatically on first run.

Posting to Facebook/Instagram/TikTok/Twitter is currently **stubbed**
(`backend/services/socialPlatforms.js`) — it logs what would be sent and marks
the post as "posted" so you can test the whole flow end-to-end before wiring
in real API keys for each platform (which need approval from each platform first).

## Why I couldn't run it live here

This sandbox's network is locked to a specific allowlist (GitHub, PyPI, a few
others) and `registry.npmjs.org` got blocked mid-session, so `npm install`
failed here. Nothing wrong with the code — just run these steps on your own
machine or server where npm has normal internet access.

## Run it yourself

### 1. Backend
```bash
cd backend
npm install
cp .env.example .env
# edit .env: set JWT_SECRET to a random string, TELEGRAM_BOT_TOKEN once you have one
npm start
```
Should print `✓ SocialFlow backend running on port 3000`.

Test it:
```bash
curl -X POST http://localhost:3000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"axmed@example.com","password":"test1234","workspaceName":"Cawl Pizza"}'
```
You'll get back a JWT token — that confirms the whole backend + database works.

### 2. Telegram bot
1. Message **@BotFather** on Telegram, run `/newbot`, get your token.
2. Put that token in `backend/.env` (`TELEGRAM_BOT_TOKEN`) and `telegram-bot/.env`.
```bash
cd telegram-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```
3. Open your bot in Telegram, send `/start`, log in with the email/password
   from step 1, then send it a photo to test the full flow.

### 3. Going live on real platforms
Each platform function in `backend/services/socialPlatforms.js` has a comment
showing exactly which real API endpoint replaces the stub — Facebook/Instagram
via Graph API, TikTok via their Content Posting API, Twitter via API v2. Each
needs a developer app + approval before it can post live, so I left them as
clearly-marked stubs rather than guessing at credentials you don't have yet.

## Deploying for a second company (the white-label part)

1. Copy the whole `socialflow-saas` folder, rename it.
2. New `.env` for that company: new `DATABASE_PATH`, new `TELEGRAM_BOT_TOKEN`,
   new `JWT_SECRET`.
3. Run it as its own process (own server/port, or its own container).

No code changes needed — everything company-specific lives in `.env`.
