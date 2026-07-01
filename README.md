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

## Development

This repository includes a devcontainer for a ready-to-use Linux Python environment. In Cursor or VS Code, reopen the project in the container to install the package with development tooling and set up pre-commit hooks.

For local development without the container, install the dev extra and hooks:

```powershell
python -m pip install -e ".[dev]"
pre-commit install
```

Run the full hook suite before committing:

```powershell
pre-commit run --all-files
```

## Usage

```powershell
gemini "what is the current trend in AI ?"
```

Use another model:

```powershell
gemini --model gemini-2.5-pro "summarize today's AI news"
```

## Expense updates

The assistant can update Juan's Google Sheets expense tracker when Google Sheets credentials are configured. This works from both the CLI and Telegram bot because both entry points use the same assistant engine.

The first supported tool is for non-credit payments only. It updates the category cell for a given day/month by appending to the existing formula:

```text
=100 -> =100+200 for a normal expense
=100 -> =100-200 for a refund
```

Required Google Sheets environment variables:

```env
EXPENSES_SPREADSHEET_ID=your_expenses_spreadsheet_id_here
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=base64_encoded_service_account_json_here
```

To enable writes:

1. Enable the Google Sheets API in a Google Cloud project.
2. Create a service account and download its JSON credential.
3. Share the expenses spreadsheet with the service account `client_email` as Editor.
4. Base64-encode the JSON credential and set it as `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`.

PowerShell helper:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("service-account.json"))
```

The tool only writes to the confirmed category columns:

```text
B:I -> alquileres, servicios_esenciales, servicios_no_esenciales, hogar, transporte, salidas, shopping, otros
```

Columns for totals, moving averages, and past markers are never written by the tool.

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
uvicorn harle_api.app:app --reload
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
EXPENSES_SPREADSHEET_ID=your_expenses_spreadsheet_id_here
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=base64_encoded_service_account_json_here
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
Start command: uvicorn harle_api.app:app --host 0.0.0.0 --port $PORT
Health check path: /healthcheck
```

For durable SQLite storage on Render, attach a persistent disk and set `SQLITE_PATH` to a path inside that mounted disk. Without a persistent disk, SQLite is still useful for quick testing, but the database can be lost when the instance restarts or redeploys.

On Vercel, SQLite is only suitable for quick testing because the filesystem is ephemeral. The app automatically stores SQLite under `/tmp` when it detects Vercel, so a relative `SQLITE_PATH` such as `data/bot_conversations.sqlite3` becomes `/tmp/bot_conversations.sqlite3`.
