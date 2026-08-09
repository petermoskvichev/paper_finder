# arXiv Paper Finder

A small Python application that finds newly published arXiv papers matching a personal
research profile and sends a daily email digest.

It queries configurable arXiv category groups, removes duplicate cross-lists, and ranks
papers using a combination of:

- semantic similarity to natural-language research themes; and
- exact aliases such as `trustworthy ML`, with optional negative keywords.

Semantic ranking runs locally with Sentence Transformers—paper text is not sent to an LLM.
The default profile scans the previous 24 hours and emails at most five papers. If none are
found, no email is sent.

## Setup and local use

Python 3.10 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Edit `profile.yaml` to configure categories, research themes, ranking weights, email
addresses, the lookback window, and the paper limit. Then print a digest locally:

```bash
python -m arxiv_digest --config profile.yaml
```

The first run downloads the embedding model; subsequent runs use the local cache. For a
larger test window:

```bash
python -m arxiv_digest --lookback-hours 168
```

## Gmail setup

1. Enable the Gmail API in the [Google Cloud Console](https://console.cloud.google.com/).
2. Configure the OAuth consent screen and add your Gmail account as a test user.
3. Create a **Desktop app** OAuth client and save its download as `credentials.json`.
4. Authorize the application:

   ```bash
   python -m arxiv_digest.gmail_auth --client-secrets credentials.json
   ```

5. Send a test digest:

   ```bash
   python -m arxiv_digest --send-email
   ```

Authorization creates `token.json` for local use and `.env.github` for GitHub Secrets.
These files are ignored by Git and must never be committed. The application requests only
the `gmail.send` permission. For a reliable daily job, change the OAuth app from
**Testing** to **In production** so its refresh token does not expire after seven days.

## Daily GitHub Action

The workflow in `.github/workflows/daily-digest.yml` runs every day at 08:15 Singapore
time. Import the generated secrets and push the repository:

```bash
gh secret set -f .env.github
git push
```

You can test the workflow from GitHub's **Actions** tab or with:

```bash
gh workflow run daily-digest.yml
```

The workflow uses encrypted Gmail secrets, a CPU-only inference runtime, and a cached
embedding model. Scheduled execution begins only after the workflow is on the default
branch.

## Project layout

```text
arxiv_digest/                    Application modules
tests/                           Unit tests
profile.yaml                     Research and email configuration
.github/workflows/daily-digest.yml
requirements.txt
```

Run the tests with:

```bash
python -m unittest discover -s tests
```

Persistent tracking of previously seen arXiv IDs and LLM summaries are not implemented
yet.
