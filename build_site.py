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


def insert_after_section(article_html, heading_text, snippet):
    if not snippet:
        return article_html

    heading_html = f"<h2>{inline_markup(heading_text)}</h2>"
    heading_index = article_html.find(heading_html)
    if heading_index == -1:
        return article_html

    section_start = heading_index + len(heading_html)
    next_heading_index = article_html.find("<h2>", section_start)
    insert_at = next_heading_index if next_heading_index != -1 else len(article_html)
    return f"{article_html[:insert_at]}\n{snippet}\n{article_html[insert_at:]}"


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
        "how-i-use-ai-as-a-pm-with-a-real-workspace": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 246" role="img" aria-label="Workspace diagram showing source material moving through one shared AI workspace into multiple outputs">
            <text x="28" y="28" class="diagram-kicker">WORKSPACE VIEW</text>
            <text x="28" y="54" class="diagram-title">The leverage comes from keeping the artifacts in one loop.</text>
            <rect x="28" y="74" width="126" height="28" rx="14" class="tone-d"/>
            <rect x="164" y="74" width="142" height="28" rx="14" class="tone-a"/>
            <rect x="316" y="74" width="162" height="28" rx="14" class="tone-b"/>
            <text x="91" y="92" class="diagram-chip-text" text-anchor="middle">same sources</text>
            <text x="235" y="92" class="diagram-chip-text" text-anchor="middle">same thread</text>
            <text x="397" y="92" class="diagram-chip-text" text-anchor="middle">same working state</text>

            <rect x="38" y="124" width="162" height="86" rx="18" class="tone-a"/>
            <rect x="38" y="124" width="162" height="10" class="diagram-bar-green"/>
            <text x="54" y="151" class="diagram-label">Source material</text>
            <text x="54" y="171" class="diagram-body">customer notes</text>
            <text x="54" y="187" class="diagram-body">usage data</text>
            <text x="54" y="203" class="diagram-body">draft decks and docs</text>

            <rect x="254" y="112" width="208" height="106" rx="18" class="tone-d"/>
            <rect x="254" y="112" width="208" height="10" class="diagram-bar-navy"/>
            <text x="270" y="139" class="diagram-label">Shared workspace</text>
            <text x="270" y="159" class="diagram-body">inspect the source</text>
            <text x="270" y="175" class="diagram-body">restructure the story</text>
            <text x="270" y="191" class="diagram-body">convert across formats</text>
            <text x="270" y="207" class="diagram-body">keep the context attached</text>

            <rect x="516" y="118" width="166" height="42" rx="15" class="tone-b"/>
            <rect x="516" y="118" width="166" height="8" class="diagram-bar-blue"/>
            <text x="532" y="143" class="diagram-label">Presentation</text>
            <text x="532" y="158" class="diagram-note">editable deck</text>

            <rect x="516" y="168" width="166" height="42" rx="15" class="tone-c"/>
            <rect x="516" y="168" width="166" height="8" class="diagram-bar-rust"/>
            <text x="532" y="193" class="diagram-label">Follow-through</text>
            <text x="532" y="208" class="diagram-note">recap, doc, outline</text>

            <path d="M200 166 H254" class="diagram-line-strong"/>
            <path d="M462 144 H516" class="diagram-line"/>
            <path d="M462 189 H516" class="diagram-line"/>
            <circle cx="227" cy="166" r="4.5" class="diagram-dot"/>
            <circle cx="489" cy="144" r="4.5" class="diagram-dot-soft"/>
            <circle cx="489" cy="189" r="4.5" class="diagram-dot-soft"/>
          </svg>
        </section>
        """,
        "what-working-with-codex-taught-me-about-ai-work": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 256" role="img" aria-label="AI work diagram showing files, tools, review points, and outputs inside one working loop">
            <text x="28" y="28" class="diagram-kicker">REAL AI LOOP</text>
            <text x="28" y="54" class="diagram-title">Useful AI work looks more like a teammate loop than a chat box.</text>

            <rect x="28" y="74" width="112" height="28" rx="14" class="tone-d"/>
            <rect x="150" y="74" width="124" height="28" rx="14" class="tone-a"/>
            <rect x="284" y="74" width="120" height="28" rx="14" class="tone-b"/>
            <rect x="414" y="74" width="132" height="28" rx="14" class="tone-c"/>
            <text x="84" y="92" class="diagram-chip-text" text-anchor="middle">files</text>
            <text x="212" y="92" class="diagram-chip-text" text-anchor="middle">tool use</text>
            <text x="344" y="92" class="diagram-chip-text" text-anchor="middle">review</text>
            <text x="480" y="92" class="diagram-chip-text" text-anchor="middle">rebuild</text>

            <rect x="40" y="124" width="176" height="84" rx="18" class="tone-a"/>
            <rect x="40" y="124" width="176" height="10" class="diagram-bar-rust"/>
            <text x="56" y="151" class="diagram-label">Winston</text>
            <text x="56" y="171" class="diagram-body">frame the task</text>
            <text x="56" y="187" class="diagram-body">steer the tradeoff</text>
            <text x="56" y="203" class="diagram-body">review the result</text>

            <rect x="272" y="110" width="208" height="98" rx="18" class="tone-d"/>
            <rect x="272" y="110" width="208" height="10" class="diagram-bar-navy"/>
            <text x="288" y="137" class="diagram-label">Workspace + Codex</text>
            <text x="288" y="157" class="diagram-body">inspect the repo and source files</text>
            <text x="288" y="173" class="diagram-body">make the change and rebuild</text>
            <text x="288" y="189" class="diagram-body">show what happened</text>

            <rect x="538" y="122" width="144" height="42" rx="15" class="tone-b"/>
            <rect x="538" y="122" width="144" height="8" class="diagram-bar-blue"/>
            <text x="554" y="147" class="diagram-label">Proof</text>
            <text x="554" y="162" class="diagram-note">files, diff, artifact</text>

            <rect x="538" y="172" width="144" height="42" rx="15" class="tone-c"/>
            <rect x="538" y="172" width="144" height="8" class="diagram-bar-green"/>
            <text x="554" y="197" class="diagram-label">Output</text>
            <text x="554" y="212" class="diagram-note">site, doc, deck, tool</text>

            <path d="M216 166 H272" class="diagram-line-strong"/>
            <path d="M480 143 H538" class="diagram-line"/>
            <path d="M480 193 H538" class="diagram-line"/>
            <path d="M376 208 V232 H128 V208" class="diagram-line-soft"/>
            <text x="252" y="247" class="diagram-note" text-anchor="middle">the loop stays grounded because the work can be checked</text>
            <circle cx="244" cy="166" r="4.5" class="diagram-dot"/>
            <circle cx="509" cy="143" r="4.5" class="diagram-dot-soft"/>
            <circle cx="509" cy="193" r="4.5" class="diagram-dot-soft"/>
          </svg>
        </section>
        """,
        "public-repos-need-a-short-path-to-first-useful-success": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 250" role="img" aria-label="Repository onboarding diagram showing a realistic input, an exact command, and a useful output">
            <text x="28" y="28" class="diagram-kicker">FIRST USEFUL SUCCESS</text>
            <text x="28" y="54" class="diagram-title">A public repo should get someone from curiosity to proof quickly.</text>

            <rect x="28" y="74" width="118" height="28" rx="14" class="tone-d"/>
            <rect x="156" y="74" width="126" height="28" rx="14" class="tone-a"/>
            <rect x="292" y="74" width="148" height="28" rx="14" class="tone-b"/>
            <text x="87" y="92" class="diagram-chip-text" text-anchor="middle">problem</text>
            <text x="219" y="92" class="diagram-chip-text" text-anchor="middle">exact run</text>
            <text x="366" y="92" class="diagram-chip-text" text-anchor="middle">believable output</text>

            <rect x="38" y="122" width="188" height="92" rx="18" class="tone-a"/>
            <rect x="38" y="122" width="188" height="10" class="diagram-bar-green"/>
            <text x="54" y="149" class="diagram-label">Sample input</text>
            <text x="54" y="170" class="diagram-code">release_notes.md</text>
            <text x="54" y="188" class="diagram-code">- region us-phoenix-1</text>
            <text x="54" y="204" class="diagram-code">- status deprecated</text>

            <rect x="266" y="122" width="188" height="92" rx="18" class="tone-d"/>
            <rect x="266" y="122" width="188" height="10" class="diagram-bar-navy"/>
            <text x="282" y="149" class="diagram-label">Exact command</text>
            <text x="282" y="170" class="diagram-code">$ repo-tool scan release_notes.md</text>
            <text x="282" y="188" class="diagram-code">--format summary</text>
            <text x="282" y="204" class="diagram-code">--output findings.txt</text>

            <rect x="494" y="122" width="188" height="92" rx="18" class="tone-b"/>
            <rect x="494" y="122" width="188" height="10" class="diagram-bar-rust"/>
            <text x="510" y="149" class="diagram-label">Useful output</text>
            <text x="510" y="170" class="diagram-code">1 deprecated region found</text>
            <text x="510" y="188" class="diagram-code">next step: update rollout doc</text>
            <text x="510" y="204" class="diagram-code">see example/output.txt</text>

            <path d="M226 168 H266" class="diagram-line-strong"/>
            <path d="M454 168 H494" class="diagram-line-strong"/>
            <circle cx="246" cy="168" r="4.5" class="diagram-dot"/>
            <circle cx="474" cy="168" r="4.5" class="diagram-dot"/>
          </svg>
        </section>
        """,
        "dependencies-need-owners-before-they-need-slides": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 262" role="img" aria-label="Dependency board diagram showing that planning becomes useful when owner, risk, and downstream impact are visible together">
            <text x="28" y="28" class="diagram-kicker">DEPENDENCY BOARD</text>
            <text x="28" y="54" class="diagram-title">The useful plan is the one that makes missing ownership and blocked work visible.</text>

            <rect x="28" y="74" width="122" height="28" rx="14" class="tone-d"/>
            <rect x="160" y="74" width="118" height="28" rx="14" class="tone-a"/>
            <rect x="288" y="74" width="136" height="28" rx="14" class="tone-b"/>
            <text x="89" y="92" class="diagram-chip-text" text-anchor="middle">owners</text>
            <text x="219" y="92" class="diagram-chip-text" text-anchor="middle">lateness</text>
            <text x="356" y="92" class="diagram-chip-text" text-anchor="middle">downstream risk</text>

            <rect x="36" y="122" width="204" height="110" rx="18" class="tone-a"/>
            <rect x="36" y="122" width="204" height="10" class="diagram-bar-green"/>
            <text x="52" y="149" class="diagram-label">Needs owner</text>
            <rect x="52" y="163" width="172" height="26" rx="13" class="tone-d"/>
            <rect x="52" y="196" width="172" height="26" rx="13" class="tone-d"/>
            <text x="66" y="180" class="diagram-note">IAM policy review</text>
            <text x="66" y="213" class="diagram-note">region allowlist check</text>
            <text x="168" y="180" class="diagram-chip-text">none</text>
            <text x="168" y="213" class="diagram-chip-text">none</text>

            <rect x="258" y="122" width="204" height="110" rx="18" class="tone-b"/>
            <rect x="258" y="122" width="204" height="10" class="diagram-bar-rust"/>
            <text x="274" y="149" class="diagram-label">Late or at risk</text>
            <rect x="274" y="163" width="172" height="26" rx="13" class="tone-d"/>
            <rect x="274" y="196" width="172" height="26" rx="13" class="tone-d"/>
            <text x="288" y="180" class="diagram-note">customer cutover date slipped</text>
            <text x="288" y="213" class="diagram-note">observability validation open</text>
            <text x="392" y="180" class="diagram-chip-text">+5d</text>
            <text x="392" y="213" class="diagram-chip-text">open</text>

            <rect x="480" y="122" width="204" height="110" rx="18" class="tone-c"/>
            <rect x="480" y="122" width="204" height="10" class="diagram-bar-blue"/>
            <text x="496" y="149" class="diagram-label">Downstream impact</text>
            <rect x="496" y="163" width="172" height="26" rx="13" class="tone-d"/>
            <rect x="496" y="196" width="172" height="26" rx="13" class="tone-d"/>
            <text x="510" y="180" class="diagram-note">launch review cannot lock scope</text>
            <text x="510" y="213" class="diagram-note">field enablement stays blocked</text>
            <text x="612" y="180" class="diagram-chip-text">milestone</text>
            <text x="616" y="213" class="diagram-chip-text">training</text>
          </svg>
        </section>
        """,
        "incident-timelines-need-a-stable-shape": """
        <section class="post-diagram">
          <svg viewBox="0 0 720 252" role="img" aria-label="Incident timeline diagram with a stable sequence from signal to mitigation and a customer impact band underneath">
            <text x="28" y="28" class="diagram-kicker">TIMELINE SHAPE</text>
            <text x="28" y="54" class="diagram-title">The timeline gets better once sequence, handoff, and impact sit in one consistent frame.</text>

            <line x1="70" y1="142" x2="650" y2="142" class="diagram-divider"/>
            <circle cx="112" cy="142" r="7" class="diagram-dot"/>
            <circle cx="272" cy="142" r="7" class="diagram-dot"/>
            <circle cx="434" cy="142" r="7" class="diagram-dot"/>
            <circle cx="596" cy="142" r="7" class="diagram-dot"/>

            <rect x="56" y="84" width="114" height="44" rx="16" class="tone-a"/>
            <rect x="216" y="84" width="114" height="44" rx="16" class="tone-b"/>
            <rect x="378" y="84" width="114" height="44" rx="16" class="tone-c"/>
            <rect x="540" y="84" width="114" height="44" rx="16" class="tone-d"/>
            <text x="72" y="102" class="diagram-small">08:12</text>
            <text x="232" y="102" class="diagram-small">08:29</text>
            <text x="394" y="102" class="diagram-small">09:04</text>
            <text x="556" y="102" class="diagram-small">09:22</text>
            <text x="72" y="119" class="diagram-label">signal</text>
            <text x="232" y="119" class="diagram-label">handoff</text>
            <text x="394" y="119" class="diagram-label">diagnosis</text>
            <text x="556" y="119" class="diagram-label">mitigation</text>

            <line x1="112" y1="128" x2="112" y2="178" class="diagram-line"/>
            <line x1="272" y1="128" x2="272" y2="178" class="diagram-line"/>
            <line x1="434" y1="128" x2="434" y2="178" class="diagram-line"/>
            <line x1="596" y1="128" x2="596" y2="178" class="diagram-line"/>

            <rect x="70" y="188" width="530" height="24" rx="12" class="tone-e"/>
            <rect x="70" y="188" width="176" height="24" rx="12" class="diagram-bar-rust"/>
            <rect x="246" y="188" width="206" height="24" rx="12" class="diagram-bar-blue"/>
            <rect x="452" y="188" width="148" height="24" rx="12" class="diagram-bar-green"/>
            <text x="88" y="204" class="diagram-chip-text">impact rising</text>
            <text x="296" y="204" class="diagram-chip-text">customer pain steady</text>
            <text x="489" y="204" class="diagram-chip-text">recovery visible</text>
          </svg>
        </section>
        """,
    }
    diagram_positions = {
        "how-i-use-ai-as-a-pm-with-a-real-workspace": "Why I prefer a workspace over one-off prompting",
        "what-working-with-codex-taught-me-about-ai-work": "Good AI work still depends on structure",
        "public-repos-need-a-short-path-to-first-useful-success": "Examples usually beat adjectives",
        "dependencies-need-owners-before-they-need-slides": "What I want a planning artifact to do",
        "incident-timelines-need-a-stable-shape": "Why a small formatter is often enough",
    }
    return diagrams.get(kind, ""), diagram_positions.get(kind)


def render_post_nav(post, posts, nav_class="post-nav-top"):
    current_index = next((index for index, item in enumerate(posts) if item.slug == post.slug), 0)
    newer_post = posts[current_index - 1] if current_index > 0 else None
    older_post = posts[current_index + 1] if current_index + 1 < len(posts) else None
    current_path = f"/blog/{post.slug}/"

    links = [
        '<span class="post-nav-label">Writing</span>',
        f'<a href="{relative_url(current_path, "/blog/")}">All writing</a>',
    ]
    if newer_post:
        links.append(
            f'<a href="{relative_url(current_path, f"/blog/{newer_post.slug}/")}">Newer note</a>'
        )
    if older_post:
        links.append(
            f'<a href="{relative_url(current_path, f"/blog/{older_post.slug}/")}">Older note</a>'
        )

    return f'<nav class="post-nav {nav_class}" aria-label="Writing navigation">{"".join(links)}</nav>'


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
                "label": "Product Direction",
                "meta": featured_study["period"],
                "title": "OCI Functions Product Direction",
                "summary": "Product direction around onboarding, trust, and async execution.",
                "href": f"{relative_url('/', '/case-studies/')}#{featured_study['slug']}",
                "cta": "Read case study",
                "tone": "showcase-tone-functions",
            }
        )
        if delivery_study:
            showcase_items.append(
                {
                    "key": "delivery",
                    "label": "Delivery Systems",
                    "meta": delivery_study["period"],
                    "title": "Regional Delivery Orchestration",
                    "summary": "Regional rollout planning, sequencing, and rollback across teams and dependencies.",
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
            <h2>Start here</h2>
          </div>
          <div class="showcase-tabs" role="tablist" aria-label="Start here">
            {''.join(showcase_tabs)}
          </div>
          <div class="showcase-panels">
            {''.join(showcase_panels)}
          </div>
        </section>
        """

    selected_projects = [project for project in projects if project["name"] != "winstonlin-site"][:6]

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
            "meta": "Deep dive",
            "title": "Case studies",
            "text": "Product direction, rollout planning, recovery, and platform decisions in context.",
            "url": relative_url('/', '/case-studies/'),
            "link_label": "Open case studies",
        },
        {
            "meta": "Short notes",
            "title": "Writing",
            "text": "Short notes on AI workflows, platform quality, tooling, and operating judgment.",
            "url": relative_url('/', '/blog/'),
            "link_label": "Browse writing",
        },
        {
            "meta": "Hands-on",
            "title": "Tools",
            "text": "Small tools for incidents, workflow automation, and platform operations.",
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
      <div class="hero-layout">
        <div class="hero-copy">
          <p class="eyebrow">Work and Writing</p>
          <h1>{html.escape(config["title"])}</h1>
          <p class="lead">{html.escape(config["tagline"])}</p>
          <div class="hero-links">
            <a class="button-link primary" href="{relative_url('/', '/case-studies/')}">Read case studies</a>
            <a class="button-link" href="{relative_url('/', '/blog/')}">Browse writing</a>
          </div>
        </div>
      </div>
      {bio_strip}
    </section>

    {showcase_html}

    <section class="section work-section section-frame section-frame-explore">
      <div class="section-head section-head-stack">
        <h2>Quick paths</h2>
        <p class="section-note">Case studies show product and operational work in context, writing is faster to scan, and repositories show the hands-on side.</p>
      </div>
      <div class="card-grid focus-grid">
        {''.join(focus_cards)}
      </div>
    </section>

    <section class="section section-frame section-frame-open-source">
      <div class="section-head section-head-stack">
        <h2>Selected repositories</h2>
        <p class="section-note">Tools from incidents, workflow automation, and platform operations.</p>
        <a href="{html.escape(config['github_url'])}" target="_blank" rel="noreferrer">GitHub</a>
      </div>
      <div class="feature-grid">
        {''.join(project_cards)}
      </div>
    </section>
    """
    return page_layout(
        config,
        config["name"],
        body,
        "/",
        meta_description=config.get("meta_description", config["tagline"]),
    )


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
        <h1>Writing on product, systems, and AI work</h1>
        <p class="lead">Short notes on AI workflows, platform judgment, docs, migration, and the small operating details that shape execution.</p>
      </div>
    </section>
    <section class="section">
      <h2 class="section-title">Featured writing</h2>
      <div class="feature-grid">
        {''.join(featured_cards)}
      </div>
    </section>
    {oracle_blogs_section}
    <section class="section post-list">
      <h2 class="section-title">All writing</h2>
      {''.join(cards)}
    </section>
    """
    return page_layout(
        config,
        "Writing",
        body,
        "/blog/",
        meta_description="Writing on product judgment, AI workflows, migration, docs, and small Python tools.",
    )


def render_case_studies_page(config, case_studies):
    def render_signal_list(items):
        return f"<ul>{''.join(f'<li>{html.escape(item)}</li>' for item in items)}</ul>"

    grouped = {}
    for study in case_studies:
        grouped.setdefault(study["period"], []).append(study)

    jump_links = []
    group_sections = []
    for period, studies in grouped.items():
        group_id = slugify(period)
        cards = []
        for study in studies:
            focus = render_signal_list(study["what_i_did"])
            constraint = render_signal_list(study["why_it_was_hard"])
            result = render_signal_list(study["outcome"])
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
                      {focus}
                    </section>
                    <section class="study-signal">
                      <p class="meta">Constraint</p>
                      {constraint}
                    </section>
                    <section class="study-signal">
                      <p class="meta">Result</p>
                      {result}
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
              <h2 class="section-title case-group-title">{html.escape(period)}</h2>
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
        <p class="lead">A small set of product and platform projects, with the operational constraints and outcomes called out directly.</p>
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
        meta_description="About Winston Lin: background, work, and interests across cloud products, developer tools, AI workflows, and small businesses.",
    )


def render_post_page(config, post, posts):
    post_diagram, diagram_heading = render_diagram(post.slug)
    article_body = markdown_to_html(post.body_markdown)
    if post_diagram and diagram_heading:
        article_body = insert_after_section(article_body, diagram_heading, post_diagram)

    article = f"""
    <article class="post-page prose">
      <p class="meta">{html.escape(post.date)}</p>
      <h1>{html.escape(post.title)}</h1>
      <p class="post-summary">{html.escape(post.summary)}</p>
      {render_post_nav(post, posts, "post-nav-top")}
      {article_body}
      {render_post_nav(post, posts, "post-nav-bottom")}
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
        write_text(OUTPUT_DIR / "blog" / post.slug / "index.html", render_post_page(config, post, posts))

    write_support_files(config, posts)


if __name__ == "__main__":
    build()
