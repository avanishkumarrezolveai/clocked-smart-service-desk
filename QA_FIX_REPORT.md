# Clocked Smart Service Desk: QA remediation candidate

This is a **review patch**, not a production release or a completed live QA certification. It preserves the existing visual language and synthetic data. It was compared against the repository versions of `app.py`, `public/static/app.js`, and `public/static/styles.css` on 2026-11-04.

## Implemented changes

| QA finding | Change | Current evidence |
| --- | --- | --- |
| H1 escalation changes incident to request | A shared incident detector is used for initial routing and knowledge escalation; phrases such as *won't*, *no longer*, *jam* are recognised. | Offline smoke: laptop, VPN, printer maintain INC. |
| H2 valid questions out of scope | Explicit service requests or agent requests are not rejected solely because `it_support` probability is low. | Offline checks: new laptop routes REQ001 and vague agent request asks for clarification. |
| H3 wrong Outlook offering | Vague `Create a ticket about Outlook` now asks whether there is a failure or a new service request. | Offline smoke: clarify_intent. |
| H4 fictitious application mapped to wrong offering | Rejects unsupported multiword named application targets and asks for clarification. | Offline smoke: Zorblax has no offering assigned. This is a heuristic, not an entity registry. |
| H5 asset selection dead end | Adds `I don't know the model`, supports typed unknown answer and continuation without an asset. | Offline smoke: asset_choice progresses to missing_field. |
| H6 unrelated KB articles | Respects `answers_question: false` from Clocked rerank; adds topical screen/battery checks. | Offline smoke: laptop screen no longer shows KB010. Live source relevance must be checked. |
| H7 disappearing composer | Adds CSS grid min-height fix and scoped scrolling. | CSS updated. **Browser viewport verification required.** |
| H8 Clocked HTTP 429 | Live Clocked failures return 503 instead of silently producing local answers; a per-process semaphore caps concurrent outbound calls. | Static checks only. Full multi-instance load testing needed; this is not a distributed rate limiter. |
| H9 incorrect catalog offering | Strong phrase and synonym matching is preserved; shortlists are recorded in LOCAL trace; unknown matches ask a question rather than inventing IDs. | 37 of 41 noninteractive expected offering cases matched in offline smoke; remaining scenarios include ambiguous and catalogue-coverage cases. Live API testing required. |

Additional: signed state tokens prevent forged unverified ticket confirmations; malformed JSON/state returns a 400; explicit security headers and JSON error responses were added. The Inspector now displays local shortlist decisions and one-decimal timings, and is hidden from keyboard navigation on small screens. Application corrections are handled for common device and software names.

## Known limitations and pending items

* **Do not merge yet.** Flask and clocked-sdk could not be installed in the test environment (package download unavailable). Python compilation, JavaScript syntax validation, synthetic data validation, and direct service logic smoke checks passed. The Flask HTTP regression suite is provided but **not yet executed**.
* No live Clocked calls were made during this remediation. Clocked rate limiting, dynamic reranking, grounding semantics, and API response variations need live verification on a protected preview deployment.
* Catalog category and subcategory names remain synthetic and repetitive. This needs content improvement, not just code changes.
* Session tokens are signed. On Vercel, configure `SESSION_SIGNING_KEY` to a long secret (or rely on the configured Clocked API key derived signing key). Do not commit secrets.
* A true distributed rate limiter / abuse control needs durable shared infrastructure. The local semaphore only limits requests within one Python instance. Protect Clocked credits before a public judge demo.
* A stateless server cannot guarantee globally idempotent simulated actions across concurrent instances or token replays; a shared store is needed for strong replay protection.
* A true full-browser visual audit, microcopy pass, cross-browser voice test and formal WCAG contrast audit are still pending.
* No code has been written to GitHub because the connector returned 403 when attempting to create a branch. The patch must be applied by the repository owner using GitHub Desktop.

## Run checks locally

From the repository root on Windows, with Python installed:

```powershell
py -m pip install -r requirements.txt
py scripts/validate_data.py
py -m unittest discover -s tests -v
```

Then run the app, test on a Vercel preview deployment, and rerun Claude's attached QA matrix. **All high severity findings must be independently rechecked before declaring judge readiness.**
