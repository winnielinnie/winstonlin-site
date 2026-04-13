import html
import json
import posixpath
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
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


def format_rss_date(date_text):
    dt = datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def page_layout(config, title, body, current_path="/", meta_description=None, og_type="website"):
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

    meta_description_text = meta_description or config.get("meta_description", config["tagline"])
    meta_description_escaped = html.escape(meta_description_text)
    canonical = absolute_url(config, current_path)
    title_text = html.escape(config["name"]) if title == config["name"] else f"{html.escape(title)} | {html.escape(config['name'])}"
    canonical_tag = f'\n  <link rel="canonical" href="{html.escape(canonical)}">' if canonical else ""
    favicon_tag = f'\n  <link rel="icon" type="image/svg+xml" href="{static_url(current_path, "favicon.svg")}">'
    footer_links = []
    if config.get("github_url"):
        footer_links.append(f'<a href="{html.escape(config["github_url"])}" target="_blank" rel="noreferrer">GitHub</a>')
    if config.get("linkedin_url"):
        footer_links.append(f'<a href="{html.escape(config["linkedin_url"])}" target="_blank" rel="noreferrer">LinkedIn</a>')
    if config.get("oracle_blogs_url"):
        footer_links.append(f'<a href="{html.escape(config["oracle_blogs_url"])}" target="_blank" rel="noreferrer">Oracle Blogs</a>')
    footer_links.append(f'<a href="mailto:{html.escape(config["email"])}">Email</a>')
    og_tags = ""
    if canonical:
        og_tags = f"""
  <meta property="og:title" content="{title_text}">
  <meta property="og:description" content="{meta_description_escaped}">
  <meta property="og:type" content="{html.escape(og_type)}">
  <meta property="og:url" content="{html.escape(canonical)}">
  <meta name="twitter:card" content="summary">
""".rstrip()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title_text}</title>
  <meta name="description" content="{meta_description_escaped}">{canonical_tag}{favicon_tag}
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600;6..72,700&display=swap" rel="stylesheet">
  <link rel="alternate" type="application/rss+xml" title="{html.escape(config['name'])} RSS" href="{static_url(current_path, 'feed.xml')}">
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
    <footer class="site-footer">
      <div class="compact-links">{''.join(footer_links)}</div>
    </footer>
  </div>
</body>
</html>
"""


def render_homepage(config, posts, projects, external_writing, case_studies, proof_points, discovery_paths):
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
            <article class="external-card">
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

    proof_cards = []
    for item in proof_points:
        proof_cards.append(
            f"""
            <article class="proof-card">
              <p class="proof-label">{html.escape(item["label"])}</p>
              <p>{html.escape(item["text"])}</p>
            </article>
            """
        )

    path_cards = []
    for path in discovery_paths:
        links_html = []
        for link in path["links"]:
            links_html.append(
                f'<a href="{relative_url("/", link["url"])}">{html.escape(link["label"])}</a>'
            )
        path_cards.append(
            f"""
            <article class="path-card">
              <p class="meta">{html.escape(path["who"])}</p>
              <h3>{html.escape(path["title"])}</h3>
              <p>{html.escape(path["why"])}</p>
              <div class="path-links">{''.join(links_html)}</div>
            </article>
            """
        )

    current_note = find_post(posts, "how-i-use-ai-as-a-pm-with-a-real-workspace")
    current_note_html = ""
    if current_note:
        current_note_html = f"""
        <section class="spotlight-band">
          <article class="spotlight-card">
            <div class="spotlight-main">
              <p class="eyebrow">Featured note</p>
              <h2><a href="{relative_url('/', f'/blog/{current_note.slug}/')}">{html.escape(current_note.title)}</a></h2>
              <p class="spotlight-summary">How I turn notes and files into a working PM system.</p>
            </div>
            <div class="spotlight-footer">
              <p class="spotlight-meta">Real workspace • PM workflow</p>
              <a class="spotlight-link" href="{relative_url('/', f'/blog/{current_note.slug}/')}">Read note</a>
            </div>
          </article>
        </section>
        """

    featured_work_cards = []
    featured_work_cards.append(
        f"""
        <article class="feature-card">
          <p class="meta">Platform note</p>
          <h3><a href="{relative_url('/', '/blog/developer-platforms-mostly-fail-on-friction/')}">Developer Platforms Mostly Fail On Friction</a></h3>
          <p>Why adoption is usually won or lost in the first hour.</p>
        </article>
        """
    )
    if case_studies:
        study = case_studies[0]
        featured_work_cards.append(
            f"""
            <article class="feature-card">
              <p class="meta">Case study</p>
              <h3><a href="{relative_url('/', '/case-studies/')}">{html.escape(study['title'])}</a></h3>
              <p>Regional delivery from about 3 months to 30 days.</p>
            </article>
            """
        )
    if external_writing:
        article = external_writing[0]
        featured_work_cards.append(
            f"""
            <article class="feature-card">
              <p class="meta">Oracle blog</p>
              <h3><a href="{html.escape(article['url'])}" target="_blank" rel="noreferrer">{html.escape(article['title'])}</a></h3>
              <p>Patterns, migration shape, and practical design guidance for Functions.</p>
            </article>
            """
        )

    practice_items = [
        {
            "label": "AI-PM workspace",
            "title": "Turn raw material into decisions and artifacts",
            "text": "Turn notes, spreadsheets, screenshots, and drafts into decks, follow-up, and publishable work.",
            "url": relative_url('/', '/blog/how-i-use-ai-as-a-pm-with-a-real-workspace/'),
            "link_label": "Read note",
        },
        {
            "label": "Platform product",
            "title": "Work at the layer where adoption is won or lost",
            "text": "Shape product across OCI Functions, Kubernetes, and CI/CD, with a focus on migration quality, friction, and recovery.",
            "url": relative_url('/', '/case-studies/'),
            "link_label": "View work",
        },
        {
            "label": "Business strategy",
            "title": "Apply the same lens to operating models",
            "text": "Apply product thinking to growth, service design, and operating systems.",
            "url": relative_url('/', '/blog/growth-breaks-in-the-operating-model/'),
            "link_label": "Read note",
        },
    ]
    focus_cards = []
    for path, item in zip(discovery_paths, practice_items):
        links_html = [f'<a href="{item["url"]}">{html.escape(item["link_label"])}</a>']
        seen_urls = {item["url"]}
        for link in path["links"]:
            link_url = relative_url("/", link["url"])
            if link_url in seen_urls:
                continue
            links_html.append(f'<a href="{link_url}">{html.escape(link["label"])}</a>')
            break
        focus_cards.append(
            f"""
            <article class="focus-card">
              <p class="meta">{html.escape(path["who"])}</p>
              <h3>{html.escape(path["title"])}</h3>
              <p class="focus-summary">{html.escape(path["why"])}</p>
              <p class="focus-detail">{html.escape(item["text"])}</p>
              <div class="path-links">{''.join(links_html)}</div>
            </article>
            """
        )

    body = f"""
    <section class="hero">
      <h1>{html.escape(config["title"])}</h1>
      <p class="hero-kickerline">Product leadership where workflow quality, migration, and operating leverage matter.</p>
      <div class="hero-links">
        <a class="button-link primary" href="{relative_url('/', '/case-studies/')}">Read case studies</a>
        <a class="button-link" href="{relative_url('/', '/blog/')}">Browse writing</a>
      </div>
    </section>

    <section class="proof-grid">
      {''.join(proof_cards)}
    </section>

    <section class="section work-section">
      <div class="section-head">
        <h2>What I work on</h2>
      </div>
      <div class="card-grid focus-grid">
        {''.join(focus_cards)}
      </div>
    </section>

    {current_note_html}

    <section class="section">
      <div class="section-head">
        <h2>Selected work</h2>
        <a href="{relative_url('/', '/blog/')}">More writing</a>
      </div>
      <div class="feature-grid">
        {''.join(featured_work_cards)}
      </div>
    </section>
    """
    return page_layout(config, config["name"], body, "/", meta_description=config["tagline"])


def render_blog_index(config, posts):
    featured_posts = []
    featured_slugs = config.get("home_featured_post_slugs", [])[:3]
    for slug in featured_slugs:
        post = find_post(posts, slug)
        if post:
            featured_posts.append(post)
    if not featured_posts:
        featured_posts = posts[:3]

    featured_cards = []
    featured_keys = {post.slug for post in featured_posts}
    for post in featured_posts:
        featured_cards.append(
            f"""
            <article class="feature-card">
              <p class="meta">{html.escape(post.date)}</p>
              <h3><a href="{relative_url('/blog/', f'/blog/{post.slug}/')}">{html.escape(post.title)}</a></h3>
              <p>{html.escape(post.summary)}</p>
            </article>
            """
        )

    cards = []
    for post in posts:
        if post.slug in featured_keys:
            continue
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
    <section class="section page-intro">
      <div class="panel prose page-intro-panel">
        <p class="eyebrow">Writing</p>
        <h1>Notes on AI, platforms, and tools</h1>
        <p>Short, specific, useful.</p>
      </div>
    </section>
    <section class="section">
      <div class="section-head">
        <h2>Start with</h2>
      </div>
      <div class="feature-grid">
        {''.join(featured_cards)}
      </div>
    </section>
    <section class="section post-list">
      <div class="section-head">
        <h2>All notes</h2>
      </div>
      {''.join(cards)}
    </section>
    """
    return page_layout(
        config,
        "Writing",
        body,
        "/blog/",
        meta_description="Notes on developer platforms, migration, AI workflow design, and small Python tools.",
    )


def render_case_studies_page(config, case_studies):
    summary_cards = [
        {"label": "Delivery", "text": "Regional delivery from about 3 months to 30 days."},
        {"label": "Operations", "text": "Root-cause analysis cut by about 60%."},
        {"label": "AI workflows", "text": "AI-assisted setup and triage with better recovery."},
    ]
    summary_html = []
    for item in summary_cards:
        summary_html.append(
            f"""
            <article class="proof-card">
              <p class="proof-label">{html.escape(item['label'])}</p>
              <p>{html.escape(item['text'])}</p>
            </article>
            """
        )

    cards = []
    for study in case_studies:
        what_i_did = "".join([f"<li>{html.escape(item)}</li>" for item in study["what_i_did"]])
        why_it_was_hard = "".join([f"<li>{html.escape(item)}</li>" for item in study["why_it_was_hard"]])
        outcome = "".join([f"<li>{html.escape(item)}</li>" for item in study["outcome"]])
        cards.append(
            f"""
            <article class="timeline-item">
              <div class="study-head">
                <p class="meta">{html.escape(study['period'])}</p>
                <h2>{html.escape(study['title'])}</h2>
                <p class="post-summary">{html.escape(study['tagline'])}</p>
              </div>
              <section class="study-problem">
                <p class="meta">Problem</p>
                <p>{html.escape(study['problem'])}</p>
              </section>
              <div class="study-grid">
                <section class="study-section">
                  <p class="meta">What I did</p>
                  <ul>{what_i_did}</ul>
                </section>
                <section class="study-section">
                  <p class="meta">Why it was hard</p>
                  <ul>{why_it_was_hard}</ul>
                </section>
                <section class="study-section">
                  <p class="meta">Outcome</p>
                  <ul>{outcome}</ul>
                </section>
              </div>
            </article>
            """
        )

    body = f"""
    <section class="section page-intro">
      <div class="panel prose page-intro-panel">
        <p class="eyebrow">Case studies</p>
        <h1>Selected product work</h1>
        <p>Short enough to scan. Specific enough to matter.</p>
      </div>
    </section>
    <section class="proof-grid case-proof-grid">
      {''.join(summary_html)}
    </section>
    <section class="section timeline">
      {''.join(cards)}
    </section>
    """
    return page_layout(
        config,
        "Case Studies",
        body,
        "/case-studies/",
        meta_description="Selected product case studies spanning OCI Functions, Kubernetes, and CI/CD platform work.",
    )


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
    return page_layout(
        config,
        post.title,
        article,
        f"/blog/{post.slug}/",
        meta_description=post.summary,
        og_type="article",
    )


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
    feed_items = []
    for post in posts[:20]:
        post_url = absolute_url(config, f"/blog/{post.slug}/")
        feed_items.append(
            f"""  <item>
    <title>{html.escape(post.title)}</title>
    <link>{html.escape(post_url)}</link>
    <guid>{html.escape(post_url)}</guid>
    <pubDate>{html.escape(format_rss_date(post.date))}</pubDate>
    <description>{html.escape(post.summary)}</description>
  </item>"""
        )
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>{html.escape(config["name"])}</title>
  <link>{html.escape(site_url + "/")}</link>
  <description>{html.escape(config.get("meta_description", config["tagline"]))}</description>
{chr(10).join(feed_items)}
</channel>
</rss>
"""
    write_text(OUTPUT_DIR / "feed.xml", feed)


def render_not_found_page(config):
    body = """
    <section class="section prose">
      <p class="eyebrow">Not found</p>
      <h1>This page wandered off</h1>
      <p>The link may be old, or I may have moved something while cleaning up the site.</p>
      <p><a href="../">Back home</a></p>
    </section>
    """
    return page_layout(
        config,
        "Not Found",
        body,
        "/404/",
        meta_description="Winston Lin portfolio page not found.",
    )


def build():
    config = load_json(ROOT / "site_config.json")
    projects = load_json(CONTENT_DIR / "projects.json")
    proof_points = load_json(CONTENT_DIR / "proof_points.json")
    discovery_paths = load_json(CONTENT_DIR / "discovery_paths.json")
    external_writing = load_json(CONTENT_DIR / "external_writing.json")
    case_studies = load_json(CONTENT_DIR / "case_studies.json")
    posts = load_posts()

    ensure_clean_dist()
    shutil.copytree(STATIC_DIR, OUTPUT_DIR, dirs_exist_ok=True)
    write_text(OUTPUT_DIR / ".nojekyll", "")

    write_text(OUTPUT_DIR / "index.html", render_homepage(config, posts, projects, external_writing, case_studies, proof_points, discovery_paths))
    write_text(OUTPUT_DIR / "blog" / "index.html", render_blog_index(config, posts))
    write_text(OUTPUT_DIR / "case-studies" / "index.html", render_case_studies_page(config, case_studies))
    write_text(OUTPUT_DIR / "404.html", render_not_found_page(config))

    for post in posts:
        write_text(OUTPUT_DIR / "blog" / post.slug / "index.html", render_post_page(config, post))

    write_support_files(config, posts)


if __name__ == "__main__":
    build()
