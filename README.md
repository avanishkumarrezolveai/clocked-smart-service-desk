# Clocked Smart Service Desk

A premium, responsive IT service desk prototype that demonstrates how a decision engine can help users find knowledge, clarify ambiguous assets, and prepare the right support request. All data and all ticket or chat actions are **synthetic**.

## What is included

- A Flask web interface with accessible chat, example prompts, optional browser speech recognition, and a separate **Decision inspector**.
- 200 synthetic users, 200 assets, 200 service request offerings, 15 incident offerings, 200 categories, 260 subcategories, 430 allowed catalog mappings, 10 knowledge articles, and 46 test cases.
- A guided Dell example that asks laptop versus desktop, then the exact owned device when necessary.
- Knowledge assistance, request classification, asset matching, required fields, final review, and **simulated** ticket and live chat confirmation.
- A real Clocked SDK integration pathway. Where available, the inspector shows actual SDK results. It labels local fallback rules separately.
- Vercel deployment instructions, an optional Render deployment blueprint, and a validation script.

## Run locally

Use Python 3.11 or newer.

```bash
python -m venv .venv
# macOS or Linux:
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python scripts/validate_data.py
python app.py
```

Open `http://127.0.0.1:5000`. Without a `CLOCKED_API_KEY`, this is a local demonstration, **not** evidence of live Clocked API integration.

## Deploy through GitHub and Vercel (recommended)

See [VERCEL_DEPLOYMENT.md](VERCEL_DEPLOYMENT.md) for the Vercel steps. Vercel supports the existing Python Flask app with static files in `public/static/`. Vercel Hobby is free for eligible personal, noncommercial use within plan limits.

## Alternative: GitHub and Render

See [DEPLOYMENT.md](DEPLOYMENT.md) for the Render steps. Upload the **contents** of this project folder to a GitHub repository, connect that repository as a Python web service on Render, choose its free instance if offered, and enter `CLOCKED_API_KEY` only in Render's private Environment settings. Never commit a secret or send one through chat.

The included `render.yaml` supplies build and start commands. Render Free has service limits and can sleep when idle. Clocked API credits and billing, if applicable, are separate.

## Judging walkthrough

1. `How do I reset my password?` → sourced synthetic knowledge answer, with an option to resolve.
2. `My Dell computer isn't working` as `DEMO001` → ask which kind of device, then identify the specific assigned asset.
3. `I need Microsoft Visio installed` → choose valid service request offering, gather required details, review, then create a **simulated** ticket.
4. `My laptop won't turn on and I need to speak to an agent` → clarify the issue and demonstrate **simulated** chat handoff.
5. Open the Decision inspector to distinguish **REAL API** events from **LOCAL** decisions and **API ERROR** events. An API key being configured does not prove a live call succeeded.

## Important limitations

This repository has no real employee records, live ITSM ticket creation, or real support agent handoff. Live SDK operations could not be verified without your own Clocked API key. Run the full test journeys with the actual key before submitting to judges. Application conversations are held in the browser state and simulated records are not persisted.

Project documentation lives in `docs/`, and synthetic data lives under `data/`.
