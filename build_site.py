import html
import json
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


def page_layout(config, title, body, current_path="/"):
    nav_items = [('Home', '/'), ('Writing', '/blog/')]
    if config.get("github_url"):
        nav_items.append(('GitHub', config["github_url"]))
    if config.get("linkedin_url"):
        nav_items.append(('LinkedIn', config["linkedin_url"]))
    nav_html = []
    for label, url in nav_items:
        external = url.startswith("http")
        target = ' target="_blank" rel="noreferrer"' if external else ""
        active = ' class="active"' if url == current_path else ""
        nav_html.append(f'<a href="{url}"{target}{active}>{html.escape(label)}</a>')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)} | {html.escape(config["name"])}</title>
  <link rel="stylesheet" href="/styles.css">
</head>
<body>
  <div class="page-shell">
    <header class="site-header">
      <div>
        <p class="site-kicker">{html.escape(config["location"])}</p>
        <a href="/" class="site-name">{html.escape(config["name"])}</a>
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


def render_homepage(config, posts, projects):
    latest_posts = []
    for post in posts[:3]:
        latest_posts.append(
            f"""
            <article class="post-card">
              <p class="meta">{html.escape(post.date)}</p>
              <h3><a href="/blog/{html.escape(post.slug)}/">{html.escape(post.title)}</a></h3>
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

    focus_items = "".join([f"<li>{html.escape(item)}</li>" for item in config["focus_areas"]])
    now_items = "".join([f"<li>{html.escape(item)}</li>" for item in config["now_items"]])
    experience_items = "".join([f"<li>{html.escape(item)}</li>" for item in config["experience_highlights"]])
    intro_html = "".join([f"<p>{html.escape(paragraph)}</p>" for paragraph in config["intro_paragraphs"]])
    elsewhere_html = []
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
        <h2>What I work on</h2>
        <ul>{focus_items}</ul>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>Writing</h2>
        <a href="/blog/">See all posts</a>
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

    <section class="two-column">
      <div class="panel">
        <h2>Background</h2>
        <ul>{experience_items}</ul>
      </div>
      <div class="panel">
        <h2>Now</h2>
        <ul>{now_items}</ul>
      </div>
    </section>

    <section class="two-column">
      <div class="panel">
        <h2>Elsewhere</h2>
        {''.join(elsewhere_html)}
      </div>
      <div class="panel prose">
        <h2>What I want this to become</h2>
        <p>A quiet home for work that tends to get lost otherwise: product notes, migration ideas, small Python tools, and a few stronger points of view than I can usually fit into slides.</p>
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
              <h2><a href="/blog/{html.escape(post.slug)}/">{html.escape(post.title)}</a></h2>
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


def render_post_page(config, post):
    article = f"""
    <article class="post-page prose">
      <p class="meta">{html.escape(post.date)}</p>
      <h1>{html.escape(post.title)}</h1>
      <p class="post-summary">{html.escape(post.summary)}</p>
      {markdown_to_html(post.body_markdown)}
      <p class="back-link"><a href="/blog/">Back to writing</a></p>
    </article>
    """
    return page_layout(config, post.title, article)


def ensure_clean_dist():
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "blog").mkdir(parents=True, exist_ok=True)


def write_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content)


def build():
    config = load_json(ROOT / "site_config.json")
    projects = load_json(CONTENT_DIR / "projects.json")
    posts = load_posts()

    ensure_clean_dist()
    shutil.copy(STATIC_DIR / "styles.css", OUTPUT_DIR / "styles.css")
    write_text(OUTPUT_DIR / ".nojekyll", "")

    write_text(OUTPUT_DIR / "index.html", render_homepage(config, posts, projects))
    write_text(OUTPUT_DIR / "blog" / "index.html", render_blog_index(config, posts))

    for post in posts:
        write_text(OUTPUT_DIR / "blog" / post.slug / "index.html", render_post_page(config, post))


if __name__ == "__main__":
    build()
