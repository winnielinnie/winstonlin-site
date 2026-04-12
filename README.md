# winstonlin-site

Personal site for Winston Lin: writing, case studies, and a small set of public technical projects.

This repo is intentionally simple:
- content lives in Markdown
- a small Python script builds the static site
- `docs/` holds the generated output so the site can be served easily with GitHub Pages

## Local run

```bash
python3 scripts/local_preview.py
```

That rebuilds the site and serves it locally at `http://127.0.0.1:8892`.

## Adding a post

```bash
python3 scripts/new_post.py "Working title"
```

That creates a dated Markdown file under `content/posts/`.

## Notes

- No framework on purpose
- No external Python dependencies
- Built for easy iteration and readable structure
