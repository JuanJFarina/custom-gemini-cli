# Custom Gemini CLI

Minimal CLI for sending one-shot prompts to Gemini with Google Search grounding enabled.

## Setup

Create a `.env` file or set the environment variables directly:

```powershell
Copy-Item .env.example .env
```

Then edit `.env`:

```env
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Install the CLI in editable mode:

```powershell
python -m pip install -e .
```

On Windows, if `gemini` is not found after installation, add your Python user scripts directory to `PATH`:

```powershell
$env:Path += ";$env:APPDATA\Python\Python313\Scripts"
```

## Usage

```powershell
gemini "what is the current trend in AI ?"
```

Use another model:

```powershell
gemini --model gemini-2.5-pro "summarize today's AI news"
```

Show grounding source URLs when Gemini returns them:

```powershell
gemini --show-sources "what is the current trend in AI ?"
```

## Notes

- This uses the official Gemini API through `google-genai`.
- Google Search grounding is enabled for every request.
- The command reads `GEMINI_API_KEY` and `GEMINI_MODEL` from the environment, a `.env` file in the current directory, or a `.env` file in this project directory.

## Telegram bot

This project also includes a small FastAPI Telegram webhook app. It reuses the Gemini request code, but stores Telegram conversations separately in SQLite so the CLI behavior remains unchanged.

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run locally:

```powershell
uvicorn custom_gemini_bot.app:app --reload
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthcheck
```

Required environment variables:

```env
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_ALLOWED_USER_ID=123456789
TELEGRAM_WEBHOOK_SECRET=your_random_webhook_secret_here
SQLITE_PATH=data/bot_conversations.sqlite3
```

Create the bot with Telegram's `@BotFather`, then register the Render webhook:

```powershell
Invoke-RestMethod `
  -Uri "https://api.telegram.org/bot$env:TELEGRAM_BOT_TOKEN/setWebhook" `
  -Method Post `
  -Body @{
    url = "https://your-render-service.onrender.com/telegram/webhook"
    secret_token = $env:TELEGRAM_WEBHOOK_SECRET
  }
```

Render Web Service settings:

```text
Build command: python -m pip install -r requirements.txt
Start command: uvicorn custom_gemini_bot.app:app --host 0.0.0.0 --port $PORT
Health check path: /healthcheck
```

For durable SQLite storage on Render, attach a persistent disk and set `SQLITE_PATH` to a path inside that mounted disk. Without a persistent disk, SQLite is still useful for quick testing, but the database can be lost when the instance restarts or redeploys.
