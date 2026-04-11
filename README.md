# winstonlin-site

Personal site and writing home for Winston Lin.

This repo is intentionally simple:
- content lives in Markdown
- a small Python script builds the static site
- `docs/` holds the generated output so the site can be served easily with GitHub Pages

## Local run

```bash
python3 build_site.py
python3 serve_site.py
```

## Adding a post

```bash
python3 scripts/new_post.py "Working title"
```

That creates a dated Markdown file under `content/posts/`.

## Notes

- No framework on purpose
- No external Python dependencies
- Built for easy iteration, not maximal abstraction
