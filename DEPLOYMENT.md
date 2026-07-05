# Streamlit Community Cloud Deployment

## 1. Push the project to GitHub

Confirm that these files are in the repository root:

- `app.py`
- `requirements.txt`
- `research_agent.py`
- `research_ui.py`
- `ai_report.py`
- `integrated_decision.py`
- `scoring.py`
- `assessment_rules.py`
- `scenario_analysis.py`

Do not commit:

- `.env`
- `.streamlit/secrets.toml`
- `.venv/`
- `.cache/`

## 2. Deploy

1. Sign in to Streamlit Community Cloud with GitHub.
2. Click **Create app**.
3. Select the repository and branch.
4. Set the entrypoint to `app.py`.
5. Open **Advanced settings**.
6. Choose a Python version matching local development when possible.
7. Paste the secrets below into the Secrets field:

```toml
OPENAI_API_KEY = "sk-your-real-key"
OPENAI_RESEARCH_MODEL = "gpt-4.1-mini"
OPENAI_REPORT_MODEL = "gpt-4.1-mini"
```

8. Click **Deploy**.

## 3. Smoke test after deployment

Run this sequence:

1. Open the default chest X-ray case.
2. Confirm the four Taiwan research tasks can load from cache or run one at a time.
3. Run the hospital assessment with default values.
4. Confirm the integrated decision appears.
5. Generate the complete management report.
6. Download Markdown and JSON outputs.

## 4. Important deployment note about cache

The local `.cache/` directory is intentionally excluded from Git. On a fresh cloud deployment, Taiwan research tasks may need to run again. Community Cloud storage should not be treated as a permanent database.

For a public demo, either:

- run the four tasks once after deployment, or
- later add a reviewed demo snapshot stored as a non-secret JSON fixture.

## 5. Common failures

### Missing API key

Check the app's Secrets settings and confirm `OPENAI_API_KEY` is present.

### ModuleNotFoundError

Confirm the missing package is listed in `requirements.txt`, then reboot the app.

### Rate limit

Wait before rerunning. Run Taiwan research one task at a time and use the existing cache whenever possible.

### Research results disappear after reboot

The current cache is local runtime storage. Add a durable database or reviewed demo snapshot in a future version if persistent results are required.
