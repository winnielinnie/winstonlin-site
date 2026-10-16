# winstonlin-site

Personal site for Winston Lin: writing, case studies, and a small set of public technical projects.

The site uses plain HTML and CSS generated with Python. No package installation or framework is required. GitHub Pages publishes `docs/` from the `main` branch.

## Content and design

- `site_config.json`: biography, contact links, and metadata.
- `content/case_studies.json`: work summaries, individual stories, contribution scope, and public sources.
- `content/posts/`: essays in Markdown.
- `content/external_writing.json`: published articles elsewhere.
- `content/projects.json` and `content/project_spotlights.json`: open-source builds.
- `static/styles.css`: responsive layout, type, and colors.
- `build_site.py`: shared page templates and generation of pages, RSS, and the sitemap.

The homepage features three work stories and a short writing collection. Every original story anchor, essay, and project URL remains available. Case studies also have their own pages.

The build copies an explicit list of public assets. Add new assets to that list rather than copying an entire working directory. Use sanitized descriptions for professional work, distinguish product contribution from engineering implementation, and preserve qualifications on outcomes.

## Local run

```bash
python3 scripts/local_preview.py
```

That rebuilds the site and serves it locally at `http://127.0.0.1:8892`.

To rebuild without starting the server:

```bash
python3 -B build_site.py
```

After changing content, rebuild and commit the corresponding `docs/` changes with the source changes. Pushing to `main` triggers GitHub Pages. Before publishing, check desktop and mobile layouts, follow navigation and story links, and verify any new public evidence.

## Adding a post

```bash
python3 scripts/new_post.py "Working title"
```

That creates a dated Markdown file under `content/posts/`.

## Notes

- No framework on purpose
- No external Python dependencies
- Built for easy iteration and readable structure
