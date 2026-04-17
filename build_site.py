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


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


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
    nav_items = [('Home', '/'), ('About', '/about/'), ('Case Studies', '/case-studies/'), ('Writing', '/blog/')]
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

    body_class = "page-home"
    if current_path.startswith("/blog/") and current_path != "/blog/":
        body_class = "page-post"
    elif current_path == "/blog/":
        body_class = "page-writing"
    elif current_path == "/case-studies/":
        body_class = "page-case-studies"
    elif current_path == "/about/":
        body_class = "page-about"

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
<body class="{body_class}">
  <div class="page-shell">
    <header class="site-header">
      <div class="site-brand">
        <p class="site-kicker">{html.escape(config["location"])}</p>
        <div class="site-brand-row">
          <figure class="site-portrait">
            <img src="{static_url(current_path, 'winston-headshot.jpg')}" alt="Portrait of Winston">
          </figure>
          <a href="{relative_url(current_path, '/')}" class="site-name">{html.escape(config["name"])}</a>
        </div>
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
  <script>
    document.addEventListener("DOMContentLoaded", function () {{
      const tabs = Array.from(document.querySelectorAll("[data-showcase-target]"));
      const panels = Array.from(document.querySelectorAll("[data-showcase-panel]"));
      if (!tabs.length || !panels.length) return;

      function setActive(key) {{
        tabs.forEach((tab) => {{
          const active = tab.dataset.showcaseTarget === key;
          tab.classList.toggle("active", active);
          tab.setAttribute("aria-pressed", active ? "true" : "false");
        }});
        panels.forEach((panel) => {{
          const active = panel.dataset.showcasePanel === key;
          panel.classList.toggle("active", active);
          panel.hidden = !active;
        }});
      }}

      tabs.forEach((tab) => {{
        tab.addEventListener("click", function () {{
          setActive(tab.dataset.showcaseTarget);
        }});
      }});
    }});
  </script>
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
        <div class="diagram-band">
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
        </div>
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
        "growth-breaks-in-the-operating-model": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 172" role="img" aria-label="Operating model diagram">
            <rect x="26" y="50" width="124" height="42" rx="16" class="tone-a"/>
            <rect x="190" y="50" width="124" height="42" rx="16" class="tone-b"/>
            <rect x="354" y="50" width="124" height="42" rx="16" class="tone-c"/>
            <rect x="518" y="50" width="124" height="42" rx="16" class="tone-d"/>
            <path d="M150 71 H190" class="diagram-line"/>
            <path d="M314 71 H354" class="diagram-line"/>
            <path d="M478 71 H518" class="diagram-line"/>
            <path d="M354 92 V122" class="diagram-line"/>
            <path d="M354 122 H246" class="diagram-line"/>
            <path d="M354 122 H462" class="diagram-line"/>
            <text x="58" y="75" class="diagram-label">demand</text>
            <text x="224" y="75" class="diagram-label">handoffs</text>
            <text x="394" y="75" class="diagram-label">service</text>
            <text x="550" y="75" class="diagram-label">margin</text>
            <text x="282" y="141" class="diagram-label">operating model decides what scales cleanly</text>
          </svg>
        </section>
        """,
        "why-i-still-like-small-python-tools": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 154" role="img" aria-label="Small Python tools diagram">
            <rect x="42" y="52" width="136" height="40" rx="16" class="tone-a"/>
            <rect x="222" y="52" width="136" height="40" rx="16" class="tone-b"/>
            <rect x="402" y="52" width="136" height="40" rx="16" class="tone-c"/>
            <rect x="582" y="52" width="96" height="40" rx="16" class="tone-e"/>
            <path d="M178 72 H222" class="diagram-line"/>
            <path d="M358 72 H402" class="diagram-line"/>
            <path d="M538 72 H582" class="diagram-line"/>
            <text x="72" y="76" class="diagram-label">rough task</text>
            <text x="261" y="76" class="diagram-label">script</text>
            <text x="437" y="76" class="diagram-label">clean output</text>
            <text x="604" y="76" class="diagram-label">less drag</text>
          </svg>
        </section>
        """,
        "fun-projects-are-how-i-test-workflow-ideas": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 170" role="img" aria-label="Fun projects workflow diagram">
            <rect x="36" y="50" width="124" height="42" rx="16" class="tone-a"/>
            <rect x="204" y="50" width="124" height="42" rx="16" class="tone-b"/>
            <rect x="372" y="50" width="124" height="42" rx="16" class="tone-c"/>
            <rect x="540" y="50" width="144" height="42" rx="16" class="tone-d"/>
            <path d="M160 71 H204" class="diagram-line"/>
            <path d="M328 71 H372" class="diagram-line"/>
            <path d="M496 71 H540" class="diagram-line"/>
            <path d="M436 92 V124" class="diagram-line"/>
            <path d="M436 124 H274" class="diagram-line"/>
            <path d="M436 124 H602" class="diagram-line"/>
            <text x="70" y="75" class="diagram-label">friction</text>
            <text x="236" y="75" class="diagram-label">small tool</text>
            <text x="396" y="75" class="diagram-label">real use</text>
            <text x="574" y="75" class="diagram-label">taste check</text>
            <text x="294" y="144" class="diagram-label">good experiments earn reuse</text>
          </svg>
        </section>
        """,
        "one-page-tools-beat-premature-decks": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 164" role="img" aria-label="One-page workflow diagram">
            <rect x="28" y="56" width="118" height="40" rx="16" class="tone-a"/>
            <rect x="186" y="56" width="128" height="40" rx="16" class="tone-b"/>
            <rect x="354" y="56" width="128" height="40" rx="16" class="tone-c"/>
            <rect x="522" y="56" width="134" height="40" rx="16" class="tone-d"/>
            <path d="M146 76 H186" class="diagram-line"/>
            <path d="M314 76 H354" class="diagram-line"/>
            <path d="M482 76 H522" class="diagram-line"/>
            <text x="61" y="80" class="diagram-label">notes</text>
            <text x="223" y="80" class="diagram-label">one pager</text>
            <text x="388" y="80" class="diagram-label">decision</text>
            <text x="568" y="80" class="diagram-label">slides later</text>
            <text x="222" y="132" class="diagram-label">structure first, presentation second</text>
          </svg>
        </section>
        """,
        "public-surfaces-should-route-not-recite": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 170" role="img" aria-label="Public surfaces routing diagram">
            <rect x="38" y="50" width="120" height="42" rx="16" class="tone-a"/>
            <rect x="204" y="50" width="132" height="42" rx="16" class="tone-b"/>
            <rect x="382" y="50" width="132" height="42" rx="16" class="tone-c"/>
            <rect x="560" y="50" width="122" height="42" rx="16" class="tone-d"/>
            <path d="M158 71 H204" class="diagram-line"/>
            <path d="M336 71 H382" class="diagram-line"/>
            <path d="M514 71 H560" class="diagram-line"/>
            <path d="M270 92 V124" class="diagram-line"/>
            <path d="M270 124 H622" class="diagram-line"/>
            <text x="70" y="75" class="diagram-label">profile</text>
            <text x="238" y="75" class="diagram-label">site</text>
            <text x="418" y="75" class="diagram-label">repo</text>
            <text x="587" y="75" class="diagram-label">deeper proof</text>
            <text x="352" y="144" class="diagram-label">good surfaces route to the next useful depth</text>
          </svg>
        </section>
        """,
        "public-repos-need-a-short-path-to-first-useful-success": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 168" role="img" aria-label="Repository onboarding diagram">
            <rect x="32" y="52" width="116" height="40" rx="16" class="tone-a"/>
            <rect x="192" y="52" width="132" height="40" rx="16" class="tone-b"/>
            <rect x="368" y="52" width="132" height="40" rx="16" class="tone-c"/>
            <rect x="544" y="52" width="144" height="40" rx="16" class="tone-d"/>
            <path d="M148 72 H192" class="diagram-line"/>
            <path d="M324 72 H368" class="diagram-line"/>
            <path d="M500 72 H544" class="diagram-line"/>
            <text x="67" y="76" class="diagram-label">repo</text>
            <text x="225" y="76" class="diagram-label">example</text>
            <text x="405" y="76" class="diagram-label">run it</text>
            <text x="576" y="76" class="diagram-label">useful output</text>
            <text x="212" y="132" class="diagram-label">good repos shorten the distance to proof</text>
          </svg>
        </section>
        """,
        "examples-are-the-interface-for-small-tools": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 178" role="img" aria-label="Examples as interface diagram">
            <rect x="54" y="54" width="138" height="40" rx="16" class="tone-a"/>
            <rect x="290" y="54" width="138" height="40" rx="16" class="tone-b"/>
            <rect x="526" y="54" width="138" height="40" rx="16" class="tone-c"/>
            <path d="M192 74 H290" class="diagram-line"/>
            <path d="M428 74 H526" class="diagram-line"/>
            <text x="96" y="78" class="diagram-label">input</text>
            <text x="333" y="78" class="diagram-label">command</text>
            <text x="572" y="78" class="diagram-label">output</text>
            <text x="194" y="140" class="diagram-label">good examples turn curiosity into proof quickly</text>
          </svg>
        </section>
        """,
        "incident-timelines-need-a-stable-shape": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 176" role="img" aria-label="Incident timeline diagram">
            <rect x="40" y="54" width="130" height="42" rx="16" class="tone-a"/>
            <rect x="212" y="54" width="130" height="42" rx="16" class="tone-b"/>
            <rect x="384" y="54" width="130" height="42" rx="16" class="tone-c"/>
            <rect x="556" y="54" width="124" height="42" rx="16" class="tone-d"/>
            <path d="M170 75 H212" class="diagram-line"/>
            <path d="M342 75 H384" class="diagram-line"/>
            <path d="M514 75 H556" class="diagram-line"/>
            <path d="M276 96 V126" class="diagram-line"/>
            <path d="M276 126 H618" class="diagram-line"/>
            <circle cx="170" cy="75" r="6" class="tone-e"/>
            <circle cx="342" cy="75" r="6" class="tone-e"/>
            <circle cx="514" cy="75" r="6" class="tone-e"/>
            <text x="71" y="79" class="diagram-label">signal</text>
            <text x="247" y="79" class="diagram-label">handoff</text>
            <text x="416" y="79" class="diagram-label">diagnosis</text>
            <text x="584" y="79" class="diagram-label">mitigation</text>
            <text x="388" y="145" class="diagram-label">stable sequence makes the review easier to trust</text>
          </svg>
        </section>
        """,
    }
    return diagrams.get(kind, "")


def render_homepage(config, posts, projects, case_studies):
    showcase_note_slug = config.get("home_showcase_note_slug", "how-i-use-ai-as-a-pm-with-a-real-workspace")
    current_note = find_post(posts, showcase_note_slug) or find_post(posts, "how-i-use-ai-as-a-pm-with-a-real-workspace")
    showcase_html = ""
    bio_strip = ""
    if config.get("home_bio_strip"):
        bio_strip = f"""
        <div class="bio-strip">
          <p>{html.escape(config["home_bio_strip"])}</p>
        </div>
        """
    if case_studies:
        featured_study = next(
            (study for study in case_studies if study["slug"] == "oci-functions-product-direction"),
            case_studies[0],
        )
        delivery_study = next(
            (study for study in case_studies if study["slug"] == "service-installer"),
            case_studies[1] if len(case_studies) > 1 else None,
        )
        showcase_items = []
        if current_note:
            showcase_items.append(
                {
                    "key": "workspace",
                    "label": "AI Workflow",
                    "meta": "Writing",
                    "title": current_note.title,
                    "summary": current_note.summary,
                    "href": relative_url('/', f'/blog/{current_note.slug}/'),
                    "cta": "Read note",
                    "tone": "showcase-tone-workspace",
                }
            )
        showcase_items.append(
            {
                "key": "functions",
                "label": "Functions",
                "meta": featured_study["period"],
                "title": "OCI Functions Product Direction",
                "summary": "Simpler onboarding, stronger trust, and clearer async execution.",
                "href": f"{relative_url('/', '/case-studies/')}#{featured_study['slug']}",
                "cta": "Read case study",
                "tone": "showcase-tone-functions",
            }
        )
        if delivery_study:
            showcase_items.append(
                {
                    "key": "delivery",
                    "label": "Delivery",
                    "meta": delivery_study["period"],
                    "title": "Regional Delivery Orchestration",
                    "summary": "Making regional rollout planning, sequencing, and rollback far more deterministic.",
                    "href": f"{relative_url('/', '/case-studies/')}#{delivery_study['slug']}",
                    "cta": "See delivery work",
                    "tone": "showcase-tone-delivery",
                }
            )
        showcase_tabs = []
        showcase_panels = []
        for index, item in enumerate(showcase_items[:3]):
            active_attr = "true" if index == 0 else "false"
            active_class = " active" if index == 0 else ""
            hidden_attr = "" if index == 0 else ' hidden'
            showcase_tabs.append(
                f"""
                <button class="showcase-tab{active_class}" type="button" data-showcase-target="{html.escape(item['key'])}" aria-pressed="{active_attr}">
                  <span>{html.escape(item['label'])}</span>
                </button>
                """
            )
            showcase_panels.append(
                f"""
                <article class="showcase-card {html.escape(item['tone'])}{active_class}" data-showcase-panel="{html.escape(item['key'])}"{hidden_attr}>
                  <div class="showcase-panel-copy">
                    <p class="meta">{html.escape(item['meta'])}</p>
                    <h3><a href="{html.escape(item['href'])}">{html.escape(item['title'])}</a></h3>
                    <p class="showcase-summary">{html.escape(item['summary'])}</p>
                  </div>
                  <a class="spotlight-link" href="{html.escape(item['href'])}">{html.escape(item['cta'])}</a>
                </article>
                """
            )
        showcase_html = f"""
        <section class="section showcase-section section-frame section-frame-spotlight">
          <div class="section-head showcase-head">
            <h2>Featured work</h2>
          </div>
          <div class="showcase-tabs" role="tablist" aria-label="Featured work">
            {''.join(showcase_tabs)}
          </div>
          <div class="showcase-panels">
            {''.join(showcase_panels)}
          </div>
        </section>
        """

    selected_projects = [project for project in projects if project["name"] != "winstonlin-site"][:8]

    project_cards = []
    for project in selected_projects:
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
            "meta": "Longer read",
            "title": "Case studies",
            "text": "Deeper work on product decisions, migration, recovery, and platform strategy.",
            "url": relative_url('/', '/case-studies/'),
            "link_label": "Open case studies",
        },
        {
            "meta": "Shorter notes",
            "title": "Writing",
            "text": "Short notes on workflow quality, migration, AI as a working tool, and operating models.",
            "url": relative_url('/', '/blog/'),
            "link_label": "Browse writing",
        },
        {
            "meta": "Practical",
            "title": "Practical tools",
            "text": "Small utilities and workflow helpers drawn from real platform, docs, and AI-assisted operating work.",
            "url": html.escape(config['github_url']),
            "link_label": "View GitHub",
        },
    ]
    focus_cards = []
    for item in practice_items:
        focus_cards.append(
            f"""
            <article class="focus-card">
              <p class="meta">{html.escape(item["meta"])}</p>
              <h3>{html.escape(item["title"])}</h3>
              <p class="focus-detail">{html.escape(item["text"])}</p>
              <div class="path-links"><a href="{item['url']}">{html.escape(item["link_label"])}</a></div>
            </article>
            """
        )

    body = f"""
    <section class="hero">
      <p class="eyebrow">Work and Writing</p>
      <h1>{html.escape(config["title"])}</h1>
      <p class="lead">{html.escape(config["tagline"])}</p>
      <div class="hero-links">
        <a class="button-link primary" href="{relative_url('/', '/case-studies/')}">Read case studies</a>
        <a class="button-link" href="{relative_url('/', '/blog/')}">Browse writing</a>
      </div>
      {bio_strip}
    </section>

    {showcase_html}

    <section class="section work-section section-frame section-frame-explore">
      <div class="section-head section-head-stack">
        <h2>Browse by format</h2>
        <p class="section-note">Case studies go deeper, writing is faster to scan, and repositories show the hands-on side of how I work.</p>
      </div>
      <div class="card-grid focus-grid">
        {''.join(focus_cards)}
      </div>
    </section>

    <section class="section section-frame section-frame-open-source">
      <div class="section-head section-head-stack">
        <h2>Selected repositories</h2>
        <p class="section-note">Practical tools shaped by workflow pain, docs work, and platform operations.</p>
        <a href="{html.escape(config['github_url'])}" target="_blank" rel="noreferrer">GitHub</a>
      </div>
      <div class="feature-grid">
        {''.join(project_cards)}
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

    oracle_blog_links = config.get("oracle_blog_links", [])[:3]
    oracle_blog_items = []
    for item in oracle_blog_links:
        title = html.escape(item["title"])
        url = html.escape(item["url"])
        meta = html.escape(item.get("meta", "Oracle Blogs"))
        oracle_blog_items.append(
            f"""
            <article class="feature-card oracle-blog-card">
              <p class="meta">{meta}</p>
              <h3><a href="{url}" target="_blank" rel="noreferrer">{title}</a></h3>
            </article>
            """
        )

    oracle_blogs_section = ""
    if oracle_blog_items:
        oracle_author_url = html.escape(config.get("oracle_blogs_url", "https://blogs.oracle.com/"))
        oracle_blogs_section = f"""
        <section class="section oracle-blogs-section">
          <div class="section-head section-head-stack oracle-blogs-head">
            <h2>Oracle writing</h2>
            <p class="section-note oracle-blogs-note">Selected Oracle posts and <a class="oracle-blogs-link" href="{oracle_author_url}" target="_blank" rel="noreferrer">author profile</a>.</p>
          </div>
          <div class="feature-grid oracle-blogs-grid">
            {''.join(oracle_blog_items)}
          </div>
        </section>
        """

    body = f"""
    <section class="page-hero page-hero-writing">
      <div class="page-hero-copy">
        <p class="eyebrow">Writing</p>
        <h1>Writing on platform, AI, and operations</h1>
        <p class="lead">Short notes on platform judgment, migration, AI workflows, and the systems behind adoption.</p>
      </div>
    </section>
    <section class="section">
      <div class="section-head section-head-stack">
        <h2>Featured writing</h2>
      </div>
      <div class="feature-grid">
        {''.join(featured_cards)}
      </div>
    </section>
    {oracle_blogs_section}
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
        meta_description="Writing on platform quality, migration, AI workflow design, and small Python tools.",
    )


def render_case_studies_page(config, case_studies):
    grouped = {}
    for study in case_studies:
        grouped.setdefault(study["period"], []).append(study)

    jump_links = []
    group_sections = []
    for period, studies in grouped.items():
        group_id = slugify(period)
        cards = []
        for study in studies:
            focus = html.escape(study["what_i_did"][0])
            constraint = html.escape(study["why_it_was_hard"][0])
            result = html.escape(study["outcome"][0])
            cards.append(
                f"""
                <article class="timeline-item" id="{html.escape(study['slug'])}">
                  <div class="study-head">
                    <p class="meta">{html.escape(study['period'])}</p>
                    <h2>{html.escape(study['title'])}</h2>
                    <p class="post-summary">{html.escape(study['tagline'])}</p>
                  </div>
                  <p class="study-problem-copy">{html.escape(study['problem'])}</p>
                  <div class="study-signal-grid">
                    <section class="study-signal">
                      <p class="meta">Focus</p>
                      <p>{focus}</p>
                    </section>
                    <section class="study-signal">
                      <p class="meta">Constraint</p>
                      <p>{constraint}</p>
                    </section>
                    <section class="study-signal">
                      <p class="meta">Result</p>
                      <p>{result}</p>
                    </section>
                  </div>
                </article>
                """
            )
        jump_links.append(
            f"""
            <a class="jump-area-link" href="#{html.escape(group_id)}">{html.escape(period)}</a>
            """
        )
        group_sections.append(
            f"""
            <section class="case-group" id="{html.escape(group_id)}">
              <div class="section-head section-head-stack case-group-head">
                <h2>{html.escape(period)}</h2>
              </div>
              <div class="timeline">
                {''.join(cards)}
              </div>
            </section>
            """
        )

    body = f"""
    <section class="page-hero page-hero-case">
      <div class="page-hero-copy">
        <p class="eyebrow">Product, platform, and delivery</p>
        <h1>Case studies</h1>
        <p class="lead">A small set of projects across product direction, platform quality, and delivery.</p>
      </div>
    </section>
    <section class="section jump-section" id="case-jumps">
      <div class="section-head section-head-stack">
        <h2>Jump by area</h2>
        <p class="section-note">Quick ways into the main areas of work.</p>
      </div>
      <div class="jump-scroller">
        {''.join(jump_links)}
      </div>
    </section>
    <section class="section case-study-groups">
      {''.join(group_sections)}
    </section>
    """
    return page_layout(
        config,
        "Case Studies",
        body,
        "/case-studies/",
        meta_description="Case studies spanning OCI Functions, CI/CD, and adjacent platform systems.",
    )


def render_about_page(config):
    about = config.get("about", {})
    intro = "".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in about.get("intro", []))
    background_paragraphs = "".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in about.get("background", []))
    personal_paragraphs = "".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in about.get("personal", []))

    body = f"""
    <section class="page-hero page-hero-about">
      <div class="page-hero-copy">
        <p class="eyebrow">About</p>
        <h1>A little about me.</h1>
        <p class="lead">A bit more on my background and how I like to work:</p>
      </div>
    </section>
    <section class="section about-layout">
      <div class="about-main-column">
        <div class="about-intro prose">
          {intro}
        </div>
        <div class="about-story-grid">
          <section class="about-copy-block prose">
            <p class="eyebrow">Background</p>
            <h2>Where I come from.</h2>
            {background_paragraphs}
          </section>
          <figure class="about-photo-card about-photo-card-side">
            <div class="about-photo">
              <img src="{static_url('/about/', 'winston-trail-clean.png')}" alt="Winston standing on a mountain trail">
            </div>
          </figure>
        </div>
        <div class="about-story-copy about-story-copy-standalone">
          <section class="about-copy-block prose">
            <p class="eyebrow">Outside of work</p>
            <h2>A few things I spend time on outside the day job.</h2>
            {personal_paragraphs}
          </section>
        </div>
      </div>
    </section>
    """
    return page_layout(
        config,
        "About",
        body,
        "/about/",
        meta_description="About Winston Lin: product leadership across AI workflows, developer platforms, business systems, and broader operating interests.",
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

    urls = ["/", "/about/", "/blog/", "/case-studies/"] + [f"/blog/{post.slug}/" for post in posts]
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
    case_studies = load_json(CONTENT_DIR / "case_studies.json")
    posts = load_posts()

    ensure_clean_dist()
    shutil.copytree(STATIC_DIR, OUTPUT_DIR, dirs_exist_ok=True)
    write_text(OUTPUT_DIR / ".nojekyll", "")

    write_text(OUTPUT_DIR / "index.html", render_homepage(config, posts, projects, case_studies))
    write_text(OUTPUT_DIR / "about" / "index.html", render_about_page(config))
    write_text(OUTPUT_DIR / "blog" / "index.html", render_blog_index(config, posts))
    write_text(OUTPUT_DIR / "case-studies" / "index.html", render_case_studies_page(config, case_studies))
    write_text(OUTPUT_DIR / "404.html", render_not_found_page(config))

    for post in posts:
        write_text(OUTPUT_DIR / "blog" / post.slug / "index.html", render_post_page(config, post))

    write_support_files(config, posts)


if __name__ == "__main__":
    build()
