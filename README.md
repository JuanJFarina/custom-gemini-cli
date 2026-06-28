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
