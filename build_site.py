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


def render_diagram(kind):
    diagrams = {
        "hero": """
        <div class="diagram-card hero-diagram" aria-hidden="true">
          <svg viewBox="0 0 420 300" role="img">
            <defs>
              <linearGradient id="heroPanel" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="rgba(255,252,247,0.98)"/>
                <stop offset="100%" stop-color="rgba(247,242,233,0.94)"/>
              </linearGradient>
            </defs>
            <rect x="12" y="12" width="396" height="276" rx="26" fill="url(#heroPanel)" stroke="rgba(219,207,194,0.92)"/>
            <rect x="38" y="52" width="102" height="40" rx="14" fill="rgba(243,248,246,0.96)" stroke="rgba(46,90,84,0.20)"/>
            <rect x="38" y="130" width="102" height="40" rx="14" fill="rgba(252,245,239,0.96)" stroke="rgba(155,73,44,0.18)"/>
            <rect x="38" y="208" width="102" height="40" rx="14" fill="rgba(247,243,232,0.96)" stroke="rgba(151,118,51,0.18)"/>
            <rect x="160" y="90" width="104" height="78" rx="18" fill="rgba(255,253,249,0.98)" stroke="rgba(23,20,18,0.10)"/>
            <rect x="286" y="40" width="98" height="40" rx="14" fill="rgba(255,253,249,0.96)" stroke="rgba(23,20,18,0.10)"/>
            <rect x="286" y="130" width="98" height="40" rx="14" fill="rgba(255,253,249,0.96)" stroke="rgba(23,20,18,0.10)"/>
            <rect x="286" y="220" width="98" height="40" rx="14" fill="rgba(255,253,249,0.96)" stroke="rgba(23,20,18,0.10)"/>
            <path d="M140 72 C155 72 150 115 160 120" fill="none" stroke="rgba(46,90,84,0.55)" stroke-width="2.2"/>
            <path d="M140 150 C155 150 150 130 160 129" fill="none" stroke="rgba(155,73,44,0.50)" stroke-width="2.2"/>
            <path d="M140 228 C155 228 150 145 160 140" fill="none" stroke="rgba(151,118,51,0.46)" stroke-width="2.2"/>
            <path d="M264 128 C276 128 274 60 286 60" fill="none" stroke="rgba(23,20,18,0.36)" stroke-width="2.2"/>
            <path d="M264 128 C276 128 274 150 286 150" fill="none" stroke="rgba(23,20,18,0.36)" stroke-width="2.2"/>
            <path d="M264 128 C276 128 274 240 286 240" fill="none" stroke="rgba(23,20,18,0.36)" stroke-width="2.2"/>
            <text x="59" y="77" class="diagram-label">notes</text>
            <text x="58" y="155" class="diagram-label">systems</text>
            <text x="59" y="233" class="diagram-label">signals</text>
            <text x="181" y="121" class="diagram-title">product</text>
            <text x="184" y="143" class="diagram-title">judgment</text>
            <text x="305" y="65" class="diagram-label">decisions</text>
            <text x="316" y="155" class="diagram-label">docs</text>
            <text x="316" y="245" class="diagram-label">shipping</text>
          </svg>
        </div>
        """,
        "case-studies": """
        <section class="diagram-band">
          <article class="diagram-card mini-diagram-card">
            <p class="meta">Orchestration</p>
            <svg viewBox="0 0 520 120" role="img" aria-label="Deterministic delivery diagram">
              <rect x="12" y="34" width="116" height="44" rx="16" class="tone-a"/>
              <rect x="202" y="34" width="116" height="44" rx="16" class="tone-b"/>
              <rect x="392" y="34" width="116" height="44" rx="16" class="tone-c"/>
              <path d="M128 56 H202" class="diagram-line"/>
              <path d="M318 56 H392" class="diagram-line"/>
              <text x="39" y="60" class="diagram-label">build specs</text>
              <text x="234" y="60" class="diagram-label">plan + test</text>
              <text x="425" y="60" class="diagram-label">ship region</text>
            </svg>
          </article>
          <article class="diagram-card mini-diagram-card">
            <p class="meta">Visibility</p>
            <svg viewBox="0 0 520 120" role="img" aria-label="Dependency and health diagram">
              <circle cx="82" cy="60" r="22" class="tone-a"/>
              <circle cx="196" cy="36" r="20" class="tone-b"/>
              <circle cx="196" cy="84" r="20" class="tone-b"/>
              <circle cx="326" cy="60" r="22" class="tone-c"/>
              <circle cx="442" cy="60" r="22" class="tone-d"/>
              <path d="M104 54 L176 40" class="diagram-line"/>
              <path d="M104 66 L176 80" class="diagram-line"/>
              <path d="M216 36 L304 56" class="diagram-line"/>
              <path d="M216 84 L304 64" class="diagram-line"/>
              <path d="M348 60 L420 60" class="diagram-line"/>
              <text x="55" y="65" class="diagram-label">service</text>
              <text x="178" y="41" class="diagram-label">skills</text>
              <text x="176" y="89" class="diagram-label">health</text>
              <text x="304" y="65" class="diagram-label">graph</text>
              <text x="420" y="65" class="diagram-label">owner</text>
            </svg>
          </article>
        </section>
        """,
        "how-i-use-ai-as-a-pm-with-a-real-workspace": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 140" role="img" aria-label="Workspace flow diagram">
            <rect x="18" y="44" width="120" height="46" rx="16" class="tone-a"/>
            <rect x="168" y="44" width="120" height="46" rx="16" class="tone-b"/>
            <rect x="318" y="44" width="120" height="46" rx="16" class="tone-c"/>
            <rect x="468" y="44" width="120" height="46" rx="16" class="tone-d"/>
            <rect x="618" y="44" width="84" height="46" rx="16" class="tone-e"/>
            <path d="M138 67 H168" class="diagram-line"/>
            <path d="M288 67 H318" class="diagram-line"/>
            <path d="M438 67 H468" class="diagram-line"/>
            <path d="M588 67 H618" class="diagram-line"/>
            <text x="46" y="71" class="diagram-label">notes</text>
            <text x="201" y="71" class="diagram-label">data</text>
            <text x="355" y="71" class="diagram-label">deck</text>
            <text x="489" y="71" class="diagram-label">follow-up</text>
            <text x="642" y="71" class="diagram-label">docs</text>
          </svg>
        </section>
        """,
        "feature-registries-are-about-operational-clarity": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 170" role="img" aria-label="Dependency clarity diagram">
            <circle cx="112" cy="86" r="24" class="tone-a"/>
            <circle cx="264" cy="52" r="22" class="tone-b"/>
            <circle cx="264" cy="120" r="22" class="tone-b"/>
            <circle cx="430" cy="86" r="26" class="tone-c"/>
            <circle cx="596" cy="86" r="24" class="tone-d"/>
            <path d="M136 78 L242 57" class="diagram-line"/>
            <path d="M136 94 L242 115" class="diagram-line"/>
            <path d="M286 52 L404 80" class="diagram-line"/>
            <path d="M286 120 L404 92" class="diagram-line"/>
            <path d="M456 86 L572 86" class="diagram-line"/>
            <text x="80" y="91" class="diagram-label">service</text>
            <text x="242" y="57" class="diagram-label">owners</text>
            <text x="244" y="125" class="diagram-label">health</text>
            <text x="396" y="91" class="diagram-label">dependencies</text>
            <text x="561" y="91" class="diagram-label">impact</text>
          </svg>
        </section>
        """,
        "developer-platforms-mostly-fail-on-friction": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 150" role="img" aria-label="Platform adoption flow diagram">
            <rect x="28" y="56" width="130" height="40" rx="16" class="tone-a"/>
            <rect x="202" y="56" width="130" height="40" rx="16" class="tone-b"/>
            <rect x="376" y="56" width="130" height="40" rx="16" class="tone-c"/>
            <rect x="550" y="56" width="130" height="40" rx="16" class="tone-d"/>
            <path d="M158 76 H202" class="diagram-line"/>
            <path d="M332 76 H376" class="diagram-line"/>
            <path d="M506 76 H550" class="diagram-line"/>
            <circle cx="180" cy="44" r="5" class="tone-e"/>
            <circle cx="354" cy="44" r="5" class="tone-e"/>
            <circle cx="528" cy="44" r="5" class="tone-e"/>
            <text x="66" y="80" class="diagram-label">setup</text>
            <text x="232" y="80" class="diagram-label">first run</text>
            <text x="419" y="80" class="diagram-label">repeatable</text>
            <text x="591" y="80" class="diagram-label">team use</text>
            <text x="163" y="37" class="diagram-label">friction</text>
            <text x="337" y="37" class="diagram-label">friction</text>
            <text x="511" y="37" class="diagram-label">friction</text>
          </svg>
        </section>
        """,
        "migration-readiness-is-a-product-problem": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 160" role="img" aria-label="Migration readiness diagram">
            <rect x="34" y="54" width="120" height="44" rx="16" class="tone-a"/>
            <rect x="198" y="54" width="120" height="44" rx="16" class="tone-b"/>
            <rect x="362" y="54" width="120" height="44" rx="16" class="tone-c"/>
            <rect x="526" y="54" width="120" height="44" rx="16" class="tone-d"/>
            <path d="M154 76 H198" class="diagram-line"/>
            <path d="M318 76 H362" class="diagram-line"/>
            <path d="M482 76 H526" class="diagram-line"/>
            <path d="M94 116 C182 136 498 136 586 116" class="diagram-line"/>
            <text x="66" y="79" class="diagram-label">dev loop</text>
            <text x="223" y="79" class="diagram-label">packaging</text>
            <text x="396" y="79" class="diagram-label">docs</text>
            <text x="558" y="79" class="diagram-label">cutover</text>
            <text x="282" y="132" class="diagram-label">confidence is built before migration starts</text>
          </svg>
        </section>
        """,
        "trustworthy-ai-products-need-recovery-paths": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 186" role="img" aria-label="AI recovery path diagram">
            <rect x="26" y="42" width="118" height="42" rx="16" class="tone-a"/>
            <rect x="194" y="42" width="118" height="42" rx="16" class="tone-b"/>
            <rect x="362" y="42" width="118" height="42" rx="16" class="tone-c"/>
            <rect x="530" y="42" width="118" height="42" rx="16" class="tone-d"/>
            <path d="M144 63 H194" class="diagram-line"/>
            <path d="M312 63 H362" class="diagram-line"/>
            <path d="M480 63 H530" class="diagram-line"/>
            <path d="M421 84 V122" class="diagram-line"/>
            <path d="M421 122 H290" class="diagram-line"/>
            <path d="M421 122 H552" class="diagram-line"/>
            <rect x="224" y="122" width="132" height="36" rx="14" class="tone-e"/>
            <rect x="486" y="122" width="132" height="36" rx="14" class="tone-e"/>
            <text x="63" y="67" class="diagram-label">request</text>
            <text x="232" y="67" class="diagram-label">model</text>
            <text x="384" y="67" class="diagram-label">check</text>
            <text x="563" y="67" class="diagram-label">answer</text>
            <text x="252" y="145" class="diagram-label">fallback</text>
            <text x="525" y="145" class="diagram-label">human review</text>
          </svg>
        </section>
        """,
    }
    return diagrams.get(kind, "")


def render_homepage(config, posts, projects, external_writing, case_studies, discovery_paths):
    current_note = find_post(posts, "how-i-use-ai-as-a-pm-with-a-real-workspace")
    showcase_html = ""
    if case_studies:
        featured_study = case_studies[0]
        study_outcomes = "".join(
            [f"<li>{html.escape(item)}</li>" for item in featured_study["outcome"][:2]]
        )
        note_card = ""
        if current_note:
            note_card = f"""
            <article class="showcase-card">
              <p class="meta">From the essays</p>
              <h3><a href="{relative_url('/', f'/blog/{current_note.slug}/')}">{html.escape(current_note.title)}</a></h3>
              <p>How I use a real workspace to turn notes, files, and raw material into shipping work.</p>
              <a class="spotlight-link" href="{relative_url('/', f'/blog/{current_note.slug}/')}">Read essay</a>
            </article>
            """
        article_card = ""
        if external_writing:
            article = external_writing[0]
            article_card = f"""
            <article class="showcase-card">
              <p class="meta">Published article</p>
              <h3><a href="{html.escape(article['url'])}" target="_blank" rel="noreferrer">{html.escape(article['title'])}</a></h3>
              <p>Patterns, migration shape, and practical design guidance from recent Functions work.</p>
              <a class="spotlight-link" href="{html.escape(article['url'])}" target="_blank" rel="noreferrer">Read article</a>
            </article>
            """
        showcase_html = f"""
        <section class="section showcase-section">
          <div class="section-head">
            <h2>Case study spotlight</h2>
            <a href="{relative_url('/', '/case-studies/')}">View case studies</a>
          </div>
          <div class="showcase-grid">
            <article class="showcase-card showcase-primary">
              <p class="meta">{html.escape(featured_study['period'])}</p>
              <h3><a href="{relative_url('/', '/case-studies/')}">{html.escape(featured_study['title'])}</a></h3>
              <p class="showcase-summary">{html.escape(featured_study['tagline'])}</p>
              <ul class="showcase-list">{study_outcomes}</ul>
            </article>
            <div class="showcase-stack">
              {note_card}
              {article_card}
            </div>
          </div>
        </section>
        """

    project_cards = []
    for project in projects:
        project_cards.append(
            f"""
            <article class="feature-card">
              <p class="meta">{html.escape(project['label'])}</p>
              <h3><a href="{html.escape(project['url'])}" target="_blank" rel="noreferrer">{html.escape(project['name'])}</a></h3>
              <p>{html.escape(project['summary'])}</p>
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
            "text": "Shape product across OCI Functions, CI/CD, and adjacent platform systems, with a focus on migration quality, friction, and recovery.",
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
              <h3>{html.escape(path["title"])}</h3>
              <p class="focus-summary">{html.escape(path["why"])}</p>
              <p class="focus-detail">{html.escape(item["text"])}</p>
              <div class="path-links">{''.join(links_html)}</div>
            </article>
            """
        )

    body = f"""
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">Case studies, essays, and tools</p>
        <h1>{html.escape(config["title"])}</h1>
        <p class="lead">{html.escape(config["tagline"])}</p>
        <div class="hero-links">
          <a class="button-link primary" href="{relative_url('/', '/case-studies/')}">Read case studies</a>
          <a class="button-link" href="{relative_url('/', '/blog/')}">Browse writing</a>
        </div>
      </div>
    </section>

    <section class="section work-section">
      <div class="section-head">
        <h2>Browse by area</h2>
        <p class="section-note">Three ways to move through the work.</p>
      </div>
      <div class="card-grid focus-grid">
        {''.join(focus_cards)}
      </div>
    </section>

    {showcase_html}

    <section class="section">
      <div class="section-head">
        <h2>Open source</h2>
        <a href="{html.escape(config['github_url'])}" target="_blank" rel="noreferrer">GitHub</a>
      </div>
      <div class="feature-grid">
        {''.join(project_cards[:3])}
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
        <h1>Essays on platform, AI, and operations</h1>
        <p>Short product essays on workflow quality, migration, recovery, and the systems behind adoption.</p>
      </div>
    </section>
    <section class="section">
      <div class="section-head">
        <h2>Start here</h2>
        <p class="section-note">Three essays to start with.</p>
      </div>
      <div class="feature-grid">
        {''.join(featured_cards)}
      </div>
    </section>
    <section class="section post-list">
      <div class="section-head">
        <h2>All writing</h2>
      </div>
      {''.join(cards)}
    </section>
    """
    return page_layout(
        config,
        "Writing",
        body,
        "/blog/",
        meta_description="Essays on platform quality, migration, AI workflow design, and small Python tools.",
    )


def render_case_studies_page(config, case_studies):
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
        <p class="eyebrow">Platform and AI work</p>
        <h1>Case studies</h1>
        <p>Three examples of product systems that improved delivery speed, operational clarity, and workflow quality.</p>
      </div>
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
        meta_description="Case studies spanning OCI Functions, CI/CD, and adjacent platform systems.",
    )


def render_post_page(config, post):
    post_diagram = render_diagram(post.slug)
    article = f"""
    <article class="post-page prose">
      <p class="meta">{html.escape(post.date)}</p>
      <h1>{html.escape(post.title)}</h1>
      <p class="post-summary">{html.escape(post.summary)}</p>
      {post_diagram}
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
    discovery_paths = load_json(CONTENT_DIR / "discovery_paths.json")
    external_writing = load_json(CONTENT_DIR / "external_writing.json")
    case_studies = load_json(CONTENT_DIR / "case_studies.json")
    posts = load_posts()

    ensure_clean_dist()
    shutil.copytree(STATIC_DIR, OUTPUT_DIR, dirs_exist_ok=True)
    write_text(OUTPUT_DIR / ".nojekyll", "")

    write_text(OUTPUT_DIR / "index.html", render_homepage(config, posts, projects, external_writing, case_studies, discovery_paths))
    write_text(OUTPUT_DIR / "blog" / "index.html", render_blog_index(config, posts))
    write_text(OUTPUT_DIR / "case-studies" / "index.html", render_case_studies_page(config, case_studies))
    write_text(OUTPUT_DIR / "404.html", render_not_found_page(config))

    for post in posts:
        write_text(OUTPUT_DIR / "blog" / post.slug / "index.html", render_post_page(config, post))

    write_support_files(config, posts)


if __name__ == "__main__":
    build()
