import html
import json
import posixpath
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"
POSTS_DIR = CONTENT_DIR / "posts"
STATIC_DIR = ROOT / "static"
DIST_DIR = ROOT / "dist"
OUTPUT_DIR = ROOT / "docs"


@dataclass
class Post:
    title: str
    date: str
    slug: str
    summary: str
    body_markdown: str


def load_json(path):
    return json.loads(Path(path).read_text())


def parse_frontmatter(text):
    if not text.startswith("---\n"):
        raise ValueError("Missing frontmatter")
    _, remainder = text.split("---\n", 1)
    frontmatter_text, body = remainder.split("\n---\n", 1)
    frontmatter = {}
    for line in frontmatter_text.splitlines():
        if not line.strip():
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip()
    return frontmatter, body.strip()


def load_posts():
    posts = []
    for path in sorted(POSTS_DIR.glob("*.md")):
        frontmatter, body = parse_frontmatter(path.read_text())
        posts.append(
            Post(
                title=frontmatter["title"],
                date=frontmatter["date"],
                slug=frontmatter["slug"],
                summary=frontmatter["summary"],
                body_markdown=body,
            )
        )
    return list(sorted(posts, key=lambda post: post.date, reverse=True))


def find_post(posts, slug):
    for post in posts:
        if post.slug == slug:
            return post
    return None


def inline_markup(text):
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def markdown_to_html(markdown_text):
    lines = markdown_text.splitlines()
    parts = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    paragraph = []

    def flush_paragraph():
        if paragraph:
            parts.append(f"<p>{inline_markup(' '.join(paragraph))}</p>")
            paragraph.clear()

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            close_list()
            continue

        if stripped.startswith("## "):
            flush_paragraph()
            close_list()
            parts.append(f"<h2>{inline_markup(stripped[3:])}</h2>")
            continue

        if stripped.startswith("# "):
            flush_paragraph()
            close_list()
            parts.append(f"<h1>{inline_markup(stripped[2:])}</h1>")
            continue

        if stripped.startswith("- "):
            flush_paragraph()
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{inline_markup(stripped[2:])}</li>")
            continue

        paragraph.append(stripped)

    flush_paragraph()
    close_list()
    return "\n".join(parts)


def normalize_path(path):
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/" and not path.endswith("/"):
        path = f"{path}/"
    return path


def relative_url(current_path, target_path):
    current_path = normalize_path(current_path)
    target_path = normalize_path(target_path)

    current_dir = current_path.lstrip("/")
    target_dir = target_path.lstrip("/")

    if current_dir == "":
        base = "."
    else:
        base = current_dir

    rel = posixpath.relpath(target_dir or ".", start=base)
    if rel == ".":
        return "./"
    if not rel.endswith("/"):
        rel = f"{rel}/"
    return rel


def static_url(current_path, asset_name):
    return f"{relative_url(current_path, '/')}{asset_name}"


def absolute_url(config, path):
    site_url = config.get("site_url", "").rstrip("/")
    if not site_url:
        return ""
    path = normalize_path(path)
    if path == "/":
        return f"{site_url}/"
    return f"{site_url}{path}"


def page_layout(config, title, body, current_path="/"):
    nav_items = [('Home', '/'), ('Case Studies', '/case-studies/'), ('Writing', '/blog/')]
    if config.get("github_url"):
        nav_items.append(('GitHub', config["github_url"]))
    if config.get("linkedin_url"):
        nav_items.append(('LinkedIn', config["linkedin_url"]))
    nav_html = []
    for label, url in nav_items:
        external = url.startswith("http")
        target = ' target="_blank" rel="noreferrer"' if external else ""
        is_active = url == current_path or (url != "/" and current_path.startswith(url))
        active = ' class="active"' if is_active else ""
        href = url if external else relative_url(current_path, url)
        nav_html.append(f'<a href="{href}"{target}{active}>{html.escape(label)}</a>')

    meta_description = html.escape(config.get("meta_description", config["tagline"]))
    canonical = absolute_url(config, current_path)
    title_text = html.escape(config["name"]) if title == config["name"] else f"{html.escape(title)} | {html.escape(config['name'])}"
    canonical_tag = f'\n  <link rel="canonical" href="{html.escape(canonical)}">' if canonical else ""
    og_tags = ""
    if canonical:
        og_tags = f"""
  <meta property="og:title" content="{title_text}">
  <meta property="og:description" content="{meta_description}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{html.escape(canonical)}">
  <meta name="twitter:card" content="summary">
""".rstrip()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title_text}</title>
  <meta name="description" content="{meta_description}">{canonical_tag}
  <link rel="stylesheet" href="{static_url(current_path, 'styles.css')}">{og_tags}
</head>
<body>
  <div class="page-shell">
    <header class="site-header">
      <div>
        <p class="site-kicker">{html.escape(config["location"])}</p>
        <a href="{relative_url(current_path, '/')}" class="site-name">{html.escape(config["name"])}</a>
      </div>
      <nav>{"".join(nav_html)}</nav>
    </header>
    <main>
      {body}
    </main>
  </div>
</body>
</html>
"""


def render_homepage(config, posts, projects, external_writing, case_studies):
    latest_posts = []
    featured_posts = []
    for slug in config.get("home_featured_post_slugs", []):
        post = find_post(posts, slug)
        if post:
            featured_posts.append(post)
    if not featured_posts:
        featured_posts = posts[:3]

    for post in featured_posts:
        latest_posts.append(
            f"""
            <article class="post-card">
              <p class="meta">{html.escape(post.date)}</p>
              <h3><a href="{relative_url('/', f'/blog/{post.slug}/')}">{html.escape(post.title)}</a></h3>
              <p>{html.escape(post.summary)}</p>
            </article>
            """
        )

    project_cards = []
    for project in projects:
        link_start = f'<a href="{project["url"]}" target="_blank" rel="noreferrer">' if project["url"] else "<div>"
        link_end = "</a>" if project["url"] else "</div>"
        project_cards.append(
            f"""
            {link_start}
              <article class="project-card">
                <h3>{html.escape(project["name"])}</h3>
                <p>{html.escape(project["summary"])}</p>
              </article>
            {link_end}
            """
        )

    external_cards = []
    for item in external_writing:
        external_cards.append(
            f"""
            <article class="post-card">
              <p class="meta">{html.escape(item['date'])} • {html.escape(item['publication'])}</p>
              <h3><a href="{html.escape(item['url'])}" target="_blank" rel="noreferrer">{html.escape(item['title'])}</a></h3>
            </article>
            """
        )

    case_study_cards = []
    for study in case_studies[:3]:
        case_study_cards.append(
            f"""
            <article class="post-card">
              <p class="meta">{html.escape(study['period'])}</p>
              <h3><a href="{relative_url('/', '/case-studies/')}">{html.escape(study['title'])}</a></h3>
              <p>{html.escape(study['tagline'])}</p>
            </article>
            """
        )

    focus_items = "".join([f"<li>{html.escape(item)}</li>" for item in config["focus_areas"]])
    experience_items = "".join([f"<li>{html.escape(item)}</li>" for item in config["experience_highlights"]])
    intro_html = "".join([f"<p>{html.escape(paragraph)}</p>" for paragraph in config["intro_paragraphs"]])
    elsewhere_html = []
    if config.get("oracle_blogs_url"):
        elsewhere_html.append(f'<p><a href="{html.escape(config["oracle_blogs_url"])}" target="_blank" rel="noreferrer">Oracle Blogs</a></p>')
    if config.get("github_url"):
        elsewhere_html.append(f'<p><a href="{html.escape(config["github_url"])}" target="_blank" rel="noreferrer">GitHub</a></p>')
    if config.get("linkedin_url"):
        elsewhere_html.append(f'<p><a href="{html.escape(config["linkedin_url"])}" target="_blank" rel="noreferrer">LinkedIn</a></p>')
    elsewhere_html.append(f'<p><a href="mailto:{html.escape(config["email"])}">{html.escape(config["email"])}</a></p>')

    body = f"""
    <section class="hero">
      <p class="eyebrow">Product leader • developer platforms • Python tools</p>
      <h1>{html.escape(config["title"])}</h1>
      <p class="lead">{html.escape(config["tagline"])}</p>
    </section>

    <section class="two-column intro-grid">
      <div class="panel prose">
        {intro_html}
      </div>
      <div class="panel">
        <h2>What I keep working on</h2>
        <ul>{focus_items}</ul>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Case studies</h2>
        <a href="{relative_url('/', '/case-studies/')}">See all</a>
      </div>
      <div class="card-grid">
        {''.join(case_study_cards)}
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Writing</h2>
        <a href="{relative_url('/', '/blog/')}">See all posts</a>
      </div>
      <div class="card-grid">
        {''.join(latest_posts)}
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Selected projects</h2>
        <a href="{html.escape(config["github_url"])}" target="_blank" rel="noreferrer">GitHub</a>
      </div>
      <div class="card-grid">
        {''.join(project_cards)}
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Published elsewhere</h2>
        <a href="{html.escape(config["oracle_blogs_url"])}" target="_blank" rel="noreferrer">Oracle author page</a>
      </div>
      <div class="card-grid">
        {''.join(external_cards)}
      </div>
    </section>

    <section class="two-column">
      <div class="panel">
        <h2>Background</h2>
        <ul>{experience_items}</ul>
      </div>
      <div class="panel">
        <h2>Elsewhere</h2>
        {''.join(elsewhere_html)}
      </div>
    </section>
    """
    return page_layout(config, config["name"], body, "/")


def render_blog_index(config, posts):
    cards = []
    for post in posts:
        cards.append(
            f"""
            <article class="post-list-item">
              <p class="meta">{html.escape(post.date)}</p>
              <h2><a href="{relative_url('/blog/', f'/blog/{post.slug}/')}">{html.escape(post.title)}</a></h2>
              <p>{html.escape(post.summary)}</p>
            </article>
            """
        )
    body = f"""
    <section class="section prose">
      <p class="eyebrow">Writing</p>
      <h1>Notes on platform work, migration, and small tools</h1>
      <p>I am trying to keep these fairly direct. Less “content,” more notes that might actually help another builder think something through.</p>
    </section>
    <section class="section post-list">
      {''.join(cards)}
    </section>
    """
    return page_layout(config, "Writing", body, "/blog/")


def render_case_studies_page(config, case_studies):
    cards = []
    for study in case_studies:
        what_i_did = "".join([f"<li>{html.escape(item)}</li>" for item in study["what_i_did"]])
        why_it_was_hard = "".join([f"<li>{html.escape(item)}</li>" for item in study["why_it_was_hard"]])
        outcome = "".join([f"<li>{html.escape(item)}</li>" for item in study["outcome"]])
        cards.append(
            f"""
            <article class="timeline-item">
              <p class="meta">{html.escape(study['period'])}</p>
              <h2>{html.escape(study['title'])}</h2>
              <p class="post-summary">{html.escape(study['tagline'])}</p>
              <p><strong>Problem:</strong> {html.escape(study['problem'])}</p>
              <h3>What I did</h3>
              <ul>{what_i_did}</ul>
              <h3>Why it was hard</h3>
              <ul>{why_it_was_hard}</ul>
              <h3>Outcome</h3>
              <ul>{outcome}</ul>
            </article>
            """
        )

    body = f"""
    <section class="section prose">
      <p class="eyebrow">Case studies</p>
      <h1>Product work with more detail than a resume bullet</h1>
      <p>These are intentionally sanitized, but still specific enough to show how I think about scope, tradeoffs, and what actually made the work difficult.</p>
    </section>
    <section class="section timeline">
      {''.join(cards)}
    </section>
    """
    return page_layout(config, "Case Studies", body, "/case-studies/")


def render_post_page(config, post):
    article = f"""
    <article class="post-page prose">
      <p class="meta">{html.escape(post.date)}</p>
      <h1>{html.escape(post.title)}</h1>
      <p class="post-summary">{html.escape(post.summary)}</p>
      {markdown_to_html(post.body_markdown)}
      <p class="back-link"><a href="{relative_url(f'/blog/{post.slug}/', '/blog/')}">Back to writing</a></p>
    </article>
    """
    return page_layout(config, post.title, article, f"/blog/{post.slug}/")


def ensure_clean_dist():
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "blog").mkdir(parents=True, exist_ok=True)


def write_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content)


def write_support_files(config, posts):
    site_url = config.get("site_url", "").rstrip("/")
    if not site_url:
        return

    urls = ["/", "/blog/", "/case-studies/"] + [f"/blog/{post.slug}/" for post in posts]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path in urls:
        sitemap.append("  <url>")
        sitemap.append(f"    <loc>{html.escape(absolute_url(config, path))}</loc>")
        sitemap.append("  </url>")
    sitemap.append("</urlset>")
    write_text(OUTPUT_DIR / "sitemap.xml", "\n".join(sitemap))
    write_text(OUTPUT_DIR / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {site_url}/sitemap.xml\n")


def build():
    config = load_json(ROOT / "site_config.json")
    projects = load_json(CONTENT_DIR / "projects.json")
    external_writing = load_json(CONTENT_DIR / "external_writing.json")
    case_studies = load_json(CONTENT_DIR / "case_studies.json")
    posts = load_posts()

    ensure_clean_dist()
    shutil.copy(STATIC_DIR / "styles.css", OUTPUT_DIR / "styles.css")
    write_text(OUTPUT_DIR / ".nojekyll", "")

    write_text(OUTPUT_DIR / "index.html", render_homepage(config, posts, projects, external_writing, case_studies))
    write_text(OUTPUT_DIR / "blog" / "index.html", render_blog_index(config, posts))
    write_text(OUTPUT_DIR / "case-studies" / "index.html", render_case_studies_page(config, case_studies))

    for post in posts:
        write_text(OUTPUT_DIR / "blog" / post.slug / "index.html", render_post_page(config, post))

    write_support_files(config, posts)


if __name__ == "__main__":
    build()
