# GitHub and Render launch guide

## What this project is

An interactive, responsive Flask website with 200 synthetic demo users, 200 demo assets, 215 service desk offerings, 200 categories, 260 subcategories, 430 catalog mappings and 10 knowledge documents. All records and ticket or live chat actions are fictional. The website can run without a Clocked key, but **its local fallback is NOT an API demonstration**.

## Local test

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python scripts/validate_data.py
python app.py
```

Visit `http://127.0.0.1:5000`. The status should say **Local demo**, with the inspector explaining that no Clocked call occurred.

## GitHub

1. Create an empty GitHub repository, for example `clocked-smart-service-desk`.
2. Upload **the contents of this folder**, not the outer ZIP itself. Keep the `data/`, `static/`, `templates/` and `scripts/` folders intact.
3. Do not upload a real API key, `.env` or private company/customer data. The `.gitignore` helps protect these files.

## Render

1. At `https://dashboard.render.com`, choose **New > Web Service**, connect GitHub, and select your repository.
2. Set language to Python, instance type to **Free** and use these commands (or the included `render.yaml` blueprint):
   * Build: `pip install -r requirements.txt && python scripts/validate_data.py`
   * Start: `gunicorn app:app --workers 2 --bind 0.0.0.0:$PORT --timeout 90`
3. In **Environment**, add `CLOCKED_API_KEY` with your actual Clocked key, or leave it unset if you want to preview local fallback only. Do not paste the key into chat or the GitHub repository.
4. Deploy. A generated `onrender.com` URL will be accessible to judges, no GitHub login required.
5. Open the **Decision inspector** and run a question. Verify the event label says **REAL API** and that it includes a genuine Clocked result. If it says **LOCAL** or **API ERROR**, no live decision was verified for that event.

Important: Render Free services sleep after inactivity and do not retain writable files across restarts. Ticket and live chat results are simulated and not saved in a production system. The Clocked API may have its own credit usage and cost. Monitor usage through the official service dashboards.

## Judge demonstration

1. Ask: `How do I reset my password?`. Show the knowledge document and resolve without a ticket.
2. Ask: `My Dell computer isn't working` as DEMO001. Clarify laptop vs desktop and then the specific assigned device.
3. Ask: `I need Microsoft Visio installed`. Follow the required request fields; inspect the catalog and then create a **simulated** ticket.
4. Ask: `My laptop will not turn on` and escalate to a **simulated** live chat.
5. Open the inspector to show the difference between retrieval, live Clocked reranking, grounding, and local guardrails.

For the real API demonstration, perform these steps only after adding the secret key and confirming the responses. Never claim a live API decision was made solely because an API key is configured.
