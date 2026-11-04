# Deploy the Clocked Smart Service Desk to Vercel

Vercel supports Python Flask projects directly. This project exports a Flask application as `app` in the root `app.py`. Its web assets live in `public/static/`, following Vercel's recommended public asset convention. You do not need to rewrite the Python backend or add a `vercel.json` for a standard Flask deployment.

## Publish to GitHub

1. Create a GitHub repository and commit the files **inside** this directory. Retain `app.py`, `requirements.txt`, `public/`, `templates/`, `data/`, and `docs/`.
2. Keep the actual `CLOCKED_API_KEY` out of GitHub and out of project files. Do not upload `.env` or customer records.

## Deploy on Vercel

1. Sign in to https://vercel.com/ and select **Add New → Project**.
2. Import the GitHub repository. The detected framework should be Flask/Python. Keep the **Root Directory** at the repository root. No custom build or output settings should normally be needed.
3. In **Project Settings → Environment Variables**, add `CLOCKED_API_KEY` with the real key as its private value, for the Production environment. You can initially omit it to preview the clearly labeled local demo mode.
4. Deploy the project. If you add or change the key after initial deployment, trigger a new deployment so it takes effect.
5. Visit the assigned `vercel.app` site. Check `/api/health` and `/api/status`, then run the judge journeys described in `README.md`.
6. Confirm the **Decision inspector** records an actual **REAL API** response after sending a question. **LOCAL** denotes the demo fallback, and **API ERROR** denotes a failed live call; neither is proof of working live integration.

## Limitations and safeguards

* Vercel's free **Hobby** plan is intended for personal, noncommercial use, with resource limits. Check that the planned competition use meets its terms. For commercial/customer use you may need a paid plan.
* Python execution uses Vercel Functions. A new function instance might have cold start latency, and invocation/runtime limits apply. Validate all real Clocked calls within the available request duration.
* This project reads synthetic catalog data from packaged CSV/Markdown files. It does not require a durable writable file system. Conversation state stays in the user's browser; synthetic tickets and chats are not persisted or sent to real systems.
* Clocked API credits and charges, if any, are separate from Vercel hosting.

## Official references

* https://vercel.com/docs/frameworks/backend/flask
* https://vercel.com/docs/plans/hobby
* https://vercel.com/docs/environment-variables
