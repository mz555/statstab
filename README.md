# #statstab archive

A small, static, searchable website for Mircea Zloteanu's **#statstab** posts.

It is designed for free hosting on **GitHub Pages**. A GitHub Actions workflow
refreshes the archive from Bluesky twice per hour and deploys the updated site.

## What it does

- reads `@mzloteanu.bsky.social` using Bluesky's public author-feed API;
- keeps only Mircea's own posts containing `#statstab`;
- extracts the `#statstab` sequence number;
- extracts all other hashtags as searchable/clickable topic tags;
- extracts the post year for year browsing;
- links each card back to the original Bluesky post;
- picks up outbound article/resource links from Bluesky facets/embeds;
- supports full-text search, year filters and tag filters;
- stores no passwords, API tokens, cookies or analytics.

## Deploy on GitHub Pages

1. Create a new GitHub repository, for example `statstab`.
2. Upload the **contents of this folder** to the repository root.
3. Commit/push them to the `main` branch.
4. On GitHub, open **Settings → Pages**.
5. Under **Build and deployment → Source**, choose **GitHub Actions**.
6. Open the **Actions** tab. The workflow named **Refresh #statstab and deploy**
   should run after the push.
7. When it finishes, GitHub will show the Pages URL.

For a repository called `statstab`, the usual URL is:

`https://YOUR-GITHUB-USERNAME.github.io/statstab/`

The updater also runs at minutes 17 and 47 of every hour. GitHub scheduled jobs are not
guaranteed to start at the exact minute, so a new #statstab can take a little
while to appear.

## Run locally

The site itself needs only a tiny local web server:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000`.

To refresh the data first:

```bash
python scripts/fetch_statstabs.py
python -m http.server 8000
```

No third-party Python packages are required.

## Change the Bluesky account or hashtag

Edit `.github/workflows/deploy.yml`:

```yaml
env:
  BSKY_HANDLE: mzloteanu.bsky.social
  STATSTAB_HASHTAG: statstab
  STATSTAB_START_DATE: "2024-01-01"
```

The same values can be supplied as environment variables when running the
fetcher manually.

## Site structure

```text
.
├── .github/workflows/deploy.yml
├── assets/
│   ├── app.js
│   ├── favicon.svg
│   └── styles.css
├── data/statstabs.json
├── scripts/fetch_statstabs.py
├── .nojekyll
├── index.html
└── README.md
```

`data/statstabs.json` contains a few seed entries so the design can be previewed
before the first live refresh. The first GitHub Actions deployment replaces that
file with the complete Bluesky-derived archive.

## Notes

Bluesky is used rather than X because public author-feed reads can be performed
without an API key. This makes the site practical to keep entirely static and
free to host.

If you later want Mastodon as a fallback source, the fetcher can be extended
without changing the front end.
