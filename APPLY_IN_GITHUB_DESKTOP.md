# How to apply this patch safely with GitHub Desktop

1. Open GitHub Desktop and select `clocked-smart-service-desk`.
2. Click **Fetch origin** first and confirm there are no changes you haven't saved. If you have local changes, commit or stash them before continuing.
3. Choose **Branch > New Branch**, type `fix/qa-h1-h9`, and base it on `main`. Select **Create Branch**.
4. Extract this ZIP to a separate folder on Windows.
5. In GitHub Desktop, choose **Repository > Show in Explorer**. This opens the **repository** directory.
6. From the extracted patch folder, copy **only** `app.py`, `public/static/app.js`, `public/static/styles.css`, and the new `tests/test_qa_regressions.py` into their exact matching paths in the repository. Do not replace the original `data/` directory. Also copy `QA_FIX_REPORT.md` and `APPLY_IN_GITHUB_DESKTOP.md` if you want the notes in GitHub.
7. Review changes in GitHub Desktop, confirm `.env` and API keys are not included, and commit with message `Address QA high severity routing and session defects`.
8. Click **Publish branch** (or **Push origin**). Open a **draft Pull Request** from `fix/qa-h1-h9` into `main`.
9. On Vercel, review the preview deployment for the branch. Perform local unit tests and QA reruns, including real Clocked calls. Do not merge until they pass.
10. After reviewing and approving the PR, merge it. Vercel will then deploy the updated `main` version.

**Note:** If your GitHub repository has changed since the package was prepared, inspect the diff and reconcile changes before copying. This patch is based on the source from 2026-11-04.
