# arXiv Paper Finder

A small Python project that fetches newly submitted papers from the official arXiv API,
scores them against a configurable research profile, prints a ranked digest, and can send
that digest through the Gmail API. A GitHub Actions workflow can run it every morning.

The ranking is deliberately simple and explainable. Semantic ranking, LLM summaries,
HTML email, and persistent seen-paper storage are not implemented yet.

## Project structure

```text
.
├── .github/workflows/daily-digest.yml  # Manual and daily GitHub Actions run
├── arxiv_digest/
│   ├── __main__.py       # Fetch/rank/print/send command
│   ├── arxiv_client.py   # Official API query and Atom parsing
│   ├── config.py         # YAML loading and validation
│   ├── digest.py         # Reusable plain-text digest rendering
│   ├── gmail_auth.py     # One-time local OAuth consent helper
│   ├── gmail_sender.py   # Gmail API message delivery
│   ├── models.py         # Core paper/ranking data models
│   └── ranking.py        # Keyword relevance scoring
├── tests/
├── profile.yaml          # Research and email profile
├── requirements.txt
└── .gitignore
```

## Local setup

Python 3.10 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Edit `profile.yaml` to choose the categories, lookback window, keyword weights, output
limit, sender, and recipient. To print a digest without sending email:

```bash
python -m arxiv_digest --config profile.yaml
```

## Authorize Gmail and send a real test

The application requests only the `gmail.send` OAuth scope. It never needs your Gmail
password.

1. Open the [Google Cloud Console](https://console.cloud.google.com/), create or select a
   project, and enable the Gmail API.
2. In Google Auth Platform, configure the consent screen. For a personal Gmail account,
   select an External audience and add `peter.mosk123@gmail.com` as a test user.
3. Create an OAuth client with application type **Desktop app**. Download it into this
   folder as `credentials.json`.
4. Run the one-time browser authorization:

   ```bash
   python -m arxiv_digest.gmail_auth --client-secrets credentials.json
   ```

   This creates `token.json` for local sending and `.env.github` for importing three
   separate GitHub Secrets. Both files are private, ignored by Git, and written with
   owner-only permissions.
5. Send the current digest to the address in `profile.yaml`:

   ```bash
   python -m arxiv_digest --config profile.yaml --send-email
   ```

Google expires authorizations, including refresh tokens, after seven days while an
External OAuth app using Gmail scopes remains in **Testing**. Before relying on the daily
job, change its publishing status to **In production**. A personal, unverified app may
still show Google's warning during consent; only authorize the Cloud project you created.

The OAuth setup follows Google's current
[Gmail Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)
and messages are sent with the documented
[`users.messages.send` flow](https://developers.google.com/workspace/gmail/api/guides/sending).

## GitHub Actions

The workflow runs every day at 08:15 in `Asia/Singapore` and can also be started manually.
Scheduled workflows only run after this project has been committed and pushed to the
repository's default branch.

From an authenticated GitHub CLI in the repository, import the generated secrets without
printing their values:

```bash
gh secret set -f .env.github
```

After pushing the workflow, test it from the repository's **Actions** tab or run:

```bash
gh workflow run daily-digest.yml
```

The workflow has read-only repository permissions. Its Gmail client ID, client secret,
and refresh token come only from encrypted GitHub Secrets. Do not commit
`credentials.json`, `token.json`, or `.env.github`; after importing `.env.github`, you can
delete that duplicate local secrets file.

Until seen-paper storage is added, repeated runs inside the configured lookback window can
send some of the same papers again.

## Ranking behavior

The program makes one combined category query, sorts it by submission date, removes
duplicate arXiv IDs, keeps papers published inside `lookback_hours`, and ranks up to
`max_papers`. Title occurrences are multiplied by `title_multiplier`; abstract occurrences
use the configured keyword weight directly. Negative keyword weights are subtracted.

arXiv publishes on a weekday announcement cycle, so a strict 48-hour window can be empty
on weekends or holidays. Increase `lookback_hours` temporarily for a larger test set. If a
category is especially busy, increase `fetch_limit` so the API page covers the full window.

The client follows the [arXiv API manual](https://info.arxiv.org/help/api/user-manual.html)
and its [API terms of use](https://info.arxiv.org/help/api/tou.html).

## Tests

```bash
python -m unittest discover -s tests
```
