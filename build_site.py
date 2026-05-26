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


def sentence_count(text):
    matches = re.findall(r"[.!?](?:['\"])?(?=\s|$)", text)
    return len(matches) or 1


def parse_markdown_blocks(markdown_text):
    blocks = []
    current = []

    def flush_block():
        nonlocal current
        if not current:
            return
        stripped_lines = [line.strip() for line in current if line.strip()]
        if not stripped_lines:
            current = []
            return

        first = stripped_lines[0]
        if first.startswith("## "):
            blocks.append({"type": "h2", "text": first[3:]})
        elif first.startswith("# "):
            blocks.append({"type": "h1", "text": first[2:]})
        elif all(line.startswith("- ") for line in stripped_lines):
            blocks.append({"type": "list", "items": [line[2:] for line in stripped_lines]})
        else:
            blocks.append({"type": "paragraph", "text": " ".join(stripped_lines)})
        current = []

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            flush_block()
            continue
        current.append(line)

    flush_block()
    return blocks


def merge_paragraph_blocks(blocks):
    merged = []
    paragraph_buffer = []
    buffered_sentences = 0
    buffered_chars = 0

    def flush_paragraph_buffer():
        nonlocal paragraph_buffer, buffered_sentences, buffered_chars
        if paragraph_buffer:
            merged.append({"type": "paragraph", "text": " ".join(paragraph_buffer)})
            paragraph_buffer = []
            buffered_sentences = 0
            buffered_chars = 0

    for block in blocks:
        if block["type"] != "paragraph":
            flush_paragraph_buffer()
            merged.append(block)
            continue

        text = block["text"]
        text_sentences = sentence_count(text)
        text_chars = len(text)

        if not paragraph_buffer:
            paragraph_buffer = [text]
            buffered_sentences = text_sentences
            buffered_chars = text_chars
            continue

        should_merge = buffered_sentences < 3 and buffered_chars < 320
        if text_chars > 260 and buffered_chars > 180:
            should_merge = False

        if should_merge:
            paragraph_buffer.append(text)
            buffered_sentences += text_sentences
            buffered_chars += 1 + text_chars
        else:
            flush_paragraph_buffer()
            paragraph_buffer = [text]
            buffered_sentences = text_sentences
            buffered_chars = text_chars

    flush_paragraph_buffer()
    return merged


def markdown_to_html(markdown_text):
    parts = []
    blocks = merge_paragraph_blocks(parse_markdown_blocks(markdown_text))

    for block in blocks:
        if block["type"] == "paragraph":
            parts.append(f"<p>{inline_markup(block['text'])}</p>")
        elif block["type"] == "h2":
            parts.append(f"<h2>{inline_markup(block['text'])}</h2>")
        elif block["type"] == "h1":
            parts.append(f"<h1>{inline_markup(block['text'])}</h1>")
        elif block["type"] == "list":
            parts.append("<ul>")
            for item in block["items"]:
                parts.append(f"<li>{inline_markup(item)}</li>")
            parts.append("</ul>")

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
    if path != "/" and not path.endswith("/") and "." not in posixpath.basename(path):
        path = f"{path}/"
    return path


def relative_url(current_path, target_path):
    fragment = ""
    if "#" in target_path:
        target_path, target_fragment = target_path.split("#", 1)
        fragment = f"#{target_fragment}"

    current_path = normalize_path(current_path)
    target_path = normalize_path(target_path)

    current_dir = current_path.lstrip("/")
    target_dir = target_path.lstrip("/")

    if "." in posixpath.basename(current_dir):
        current_dir = posixpath.dirname(current_dir)

    if current_dir == "":
        base = "."
    else:
        base = current_dir

    rel = posixpath.relpath(target_dir or ".", start=base)
    if rel == ".":
        return f"./{fragment}" if fragment else "./"
    if not rel.endswith("/"):
        rel = f"{rel}/"
    return f"{rel}{fragment}"


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


def render_external_writing_cards(current_path, external_writing, limit=3):
    cards = []
    for item in external_writing[:limit]:
        cards.append(render_context_feature_card(current_path, item, card_class="external-card", default_cta="Read post"))
    return cards


def render_context_feature_card(current_path, item, card_class="feature-card", default_cta="Read more"):
    href = item["url"]
    external = href.startswith("http")
    target = ' target="_blank" rel="noreferrer"' if external else ""
    if not external:
        href = relative_url(current_path, href)

    meta = item.get("meta", "").strip()
    if not meta:
        meta_bits = [item.get("publication", "").strip(), item.get("date", "").strip()]
        meta = " · ".join(bit for bit in meta_bits if bit)

    title = item.get("short_title") or item["title"]
    summary = item.get("summary", "").strip()
    summary_html = f"<p>{html.escape(summary)}</p>" if summary else ""
    cta = item.get("cta", default_cta)
    return f"""
    <article class="{card_class}">
      <p class="meta">{html.escape(meta)}</p>
      <h3><a href="{html.escape(href)}"{target}>{html.escape(title)}</a></h3>
      {summary_html}
      <div class="card-links">
        <a href="{html.escape(href)}"{target}>{html.escape(cta)}</a>
      </div>
    </article>
    """


def find_project_track(repo_tracks, project_name):
    for track in repo_tracks:
        if project_name in track.get("projects", []):
            return track
    return None


def render_track_links(current_path, links, limit=3):
    rendered = []
    for link in links[:limit]:
        href = link["url"]
        external = href.startswith("http")
        target = ' target="_blank" rel="noreferrer"' if external else ""
        if not external:
            href = relative_url(current_path, href)
        rendered.append(f'<a href="{html.escape(href)}"{target}>{html.escape(link["label"])}</a>')
    return rendered


def page_layout(config, title, body, current_path="/", meta_description=None, og_type="website"):
    nav_items = [('Home', '/'), ('Projects', '/projects/'), ('About', '/about/'), ('Case Studies', '/case-studies/'), ('Writing', '/blog/')]
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
    elif current_path.startswith("/projects/"):
        body_class = "page-projects"
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
</body>
</html>
"""


def render_diagram(kind, current_path):
    diagrams = {
        "how-i-use-ai-as-a-pm-with-a-real-workspace": {
            "asset": "diagrams/workspace-loop.svg",
            "alt": "Diagram showing source material feeding one shared workspace and then several reusable outputs.",
            "heading": "What the workflow actually looks like",
        },
        "dependencies-need-owners-before-they-need-slides": {
            "asset": "diagrams/dependency-board.svg",
            "alt": "Diagram showing a dependency board with owner, status, and downstream impact visible in one view.",
            "heading": "The failure mode is usually in the middle",
        },
        "incident-timelines-need-a-stable-shape": {
            "asset": "diagrams/incident-timeline.svg",
            "alt": "Diagram showing a stable incident timeline with owner, event, and impact progression.",
            "heading": "What I want from the timeline first",
        },
        "small-repo-batches-should-teach-a-pattern": {
            "asset": "diagrams/repo-batch-map.svg",
            "alt": "Diagram showing a repo batch moving from a clear pattern statement to examples, boundaries, and related tools.",
            "heading": "What I want the batch to do",
        },
        "fun-projects-get-stronger-when-they-leave-a-reusable-artifact": {
            "asset": "diagrams/reusable-artifact.svg",
            "alt": "Diagram showing a small project becoming more reusable when it leaves behind a clear output, handoff, and rerun path.",
            "heading": "The artifact is what makes the project reusable",
        },
        "repeated-work-should-become-a-check": {
            "asset": "diagrams/repeated-work-check.svg",
            "alt": "Diagram showing repeated work becoming a small rerunnable check instead of relying on reminder loops and memory.",
            "heading": "A good check replaces memory with a rerun",
        },
        "github-should-prove-and-the-site-should-route": {
            "asset": "diagrams/site-routing-map.svg",
            "alt": "Diagram showing GitHub as the proof layer and the personal site as the routing layer for writing, projects, and case studies.",
            "heading": "The site should route the next move",
        },
        "github-profiles-should-choose-the-first-click": {
            "asset": "diagrams/profile-first-click.svg",
            "alt": "Diagram showing a GitHub profile routing different readers toward projects, case studies, or a short note depending on the first useful click.",
            "heading": "The first click should match the intent",
        },
        "good-small-repos-should-show-the-second-move": {
            "asset": "diagrams/second-move-map.svg",
            "alt": "Diagram showing a small repo moving from first proof to the artifact, handoff, or rerun path that makes it reusable.",
            "heading": "What I want to know after the demo",
        },
        "project-pages-should-explain-the-batch": {
            "asset": "diagrams/project-batch-map.svg",
            "alt": "Diagram showing a stronger projects page grouping repos into a named batch with a standard, a related note, and clearer next clicks.",
            "heading": "A projects page should answer what the batch is proving",
        },
        "repo-tracks-should-recommend-a-first-example": {
            "asset": "diagrams/first-example-map.svg",
            "alt": "Diagram showing each repo track pointing to one best first example before branching into the wider batch.",
            "heading": "One good example should carry the track first",
        },
        "anchor-repos-should-carry-the-batch": {
            "asset": "diagrams/anchor-repo-map.svg",
            "alt": "Diagram showing a projects page routing into anchor repos that then carry the README, example, and output proof for the wider repo batch.",
            "heading": "The anchor repo should carry the proof",
        },
        "decision-logs-should-keep-the-revisit-date-visible": {
            "asset": "diagrams/decision-revisit-loop.svg",
            "alt": "Diagram showing a decision log staying useful when owner, assumption, and revisit date keep feeding the next review instead of sinking into archive.",
            "heading": "The revisit date keeps the log alive",
        },
        "starter-patterns-should-leave-one-stable-handoff-artifact": {
            "asset": "diagrams/handoff-artifact-map.svg",
            "alt": "Diagram showing noisy inbound file events being condensed into one stable manifest artifact that downstream systems can consume.",
            "heading": "One artifact should carry the handoff",
        },
        "alerting-starter-patterns-should-normalize-before-they-notify": {
            "asset": "diagrams/alert-normalization-flow.svg",
            "alt": "Diagram showing noisy alerts being normalized into one readable message before they reach chat or an on-call reader.",
            "heading": "Normalize the message before it reaches a person",
        },
    }
    diagram = diagrams.get(kind)
    if not diagram:
        return "", None

    diagram_html = f"""
    <figure class="post-diagram">
      <img src="{static_url(current_path, diagram['asset'])}" alt="{html.escape(diagram['alt'])}">
    </figure>
    """
    return diagram_html, diagram["heading"]


def render_post_nav(post, posts, nav_class="post-nav-top"):
    current_index = next((index for index, item in enumerate(posts) if item.slug == post.slug), 0)
    newer_post = posts[current_index - 1] if current_index > 0 else None
    older_post = posts[current_index + 1] if current_index + 1 < len(posts) else None
    current_path = f"/blog/{post.slug}/"

    links = [
        f'<a href="{relative_url(current_path, "/blog/")}">Back to all writing</a>',
    ]
    if newer_post:
        links.append(
            f'<a href="{relative_url(current_path, f"/blog/{newer_post.slug}/")}">Previous note</a>'
        )
    if older_post:
        links.append(
            f'<a href="{relative_url(current_path, f"/blog/{older_post.slug}/")}">Next note</a>'
        )

    return f'<nav class="post-nav {nav_class}" aria-label="Writing navigation">{"".join(links)}</nav>'


def render_project_card(project, current_path, extra_links=None, card_class="feature-card"):
    card_links = []
    site_path = project.get("site_path")
    title_href = html.escape(project["url"])
    title_target = ' target="_blank" rel="noreferrer"'
    if site_path:
        card_links.append(f'<a href="{relative_url(current_path, site_path)}">Site guide</a>')
        title_href = relative_url(current_path, site_path)
        title_target = ""

    if extra_links:
        for link in extra_links:
            href = link["url"]
            external = href.startswith("http")
            target = ' target="_blank" rel="noreferrer"' if external else ""
            if not external:
                href = relative_url(current_path, href)
            card_links.append(f'<a href="{html.escape(href)}"{target}>{html.escape(link["label"])}</a>')

    card_links.append(f'<a href="{html.escape(project["url"])}" target="_blank" rel="noreferrer">GitHub</a>')
    link_row = f'<div class="card-links">{"".join(card_links)}</div>'

    return f"""
    <article class="{html.escape(card_class)}">
      <p class="meta">{html.escape(project['label'])}</p>
      <h3><a href="{title_href}"{title_target}>{html.escape(project['name'])}</a></h3>
      <p>{html.escape(project['summary'])}</p>
      {link_row}
    </article>
    """


def render_homepage(config, posts, projects, case_studies, discovery_paths, proof_points, repo_tracks, external_writing):
    showcase_note_config = config.get("home_showcase_note", {})
    showcase_note_slug = showcase_note_config.get(
        "slug",
        config.get("home_showcase_note_slug", "how-i-use-ai-as-a-pm-with-a-real-workspace"),
    )
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
        showcase_items = []
        if current_note:
            showcase_items.append(
                {
                    "label": showcase_note_config.get("label", "Writing"),
                    "meta": showcase_note_config.get("meta", "Writing"),
                    "title": current_note.title,
                    "summary": showcase_note_config.get("summary", current_note.summary),
                    "href": relative_url('/', f'/blog/{current_note.slug}/'),
                    "cta": showcase_note_config.get("cta", "Read note"),
                    "tone": "showcase-tone-workspace",
                    "external": False,
                }
            )
        showcase_items.append(
            {
                "label": "Case study",
                "meta": featured_study["period"],
                "title": featured_study["title"],
                "summary": featured_study["home_summary"],
                "href": f"{relative_url('/', '/case-studies/')}#{featured_study['slug']}",
                "cta": "Read case study",
                "tone": "showcase-tone-functions",
                "external": False,
            }
        )
        external_item = external_writing[0] if external_writing else None
        if external_item:
            showcase_items.append(
                {
                    "label": "Published elsewhere",
                    "meta": external_item.get("publication", "Oracle Blogs"),
                    "title": external_item.get("short_title") or external_item["title"],
                    "summary": external_item.get("summary", external_item["title"]),
                    "href": external_item["url"],
                    "cta": "Read Oracle post",
                    "tone": "showcase-tone-oracle",
                    "external": True,
                }
            )
        else:
            showcase_items.append(
                {
                    "label": "Oracle writing",
                    "meta": "Oracle Blogs",
                    "title": "Author profile and selected posts",
                    "summary": "Public writing on OCI Functions patterns, recovery, and async execution.",
                    "href": config.get("oracle_blogs_url", "https://blogs.oracle.com/"),
                    "cta": "Open Oracle profile",
                    "tone": "showcase-tone-oracle",
                    "external": True,
                }
            )

        showcase_cards = []
        for item in showcase_items[:3]:
            target = ' target="_blank" rel="noreferrer"' if item["external"] else ""
            showcase_cards.append(
                f"""
                <article class="showcase-card {html.escape(item['tone'])}">
                  <div class="showcase-panel-copy">
                    <p class="meta">{html.escape(item['label'])} · {html.escape(item['meta'])}</p>
                    <h3><a href="{html.escape(item['href'])}"{target}>{html.escape(item['title'])}</a></h3>
                    <p class="showcase-summary">{html.escape(item['summary'])}</p>
                  </div>
                  <a class="spotlight-link" href="{html.escape(item['href'])}"{target}>{html.escape(item['cta'])}</a>
                </article>
                """
            )
        showcase_html = f"""
        <section class="section showcase-section section-frame section-frame-spotlight">
          <div class="section-head section-head-stack showcase-head">
            <h2>Start here</h2>
            <p class="section-note">Three fast routes into the work.</p>
          </div>
          <div class="showcase-grid">
            {''.join(showcase_cards)}
          </div>
        </section>
        """

    proof_html = ""
    if proof_points:
        proof_cards = []
        for point in proof_points[:3]:
            route_html = ""
            route = point.get("route")
            if route:
                route_href = route["url"]
                route_external = route_href.startswith("http")
                route_target = ' target="_blank" rel="noreferrer"' if route_external else ""
                if not route_external:
                    route_href = relative_url('/', route_href)
                route_label = html.escape(route.get("label", "Evidence"))
                route_html = f"""
                  <a class="proof-compact-link" href="{html.escape(route_href)}"{route_target}>{route_label}</a>
                """
            proof_cards.append(
                f"""
                <article class="proof-item">
                  <p class="proof-compact-value">
                    <span>{html.escape(point['value'])}</span>
                    <strong>{html.escape(point['label'])}</strong>
                  </p>
                  <p>{html.escape(point['text'])}</p>
                  {route_html}
                </article>
                """
            )
        proof_html = f"""
        <section class="section section-frame section-frame-explore">
          <div class="section-head section-head-stack">
            <h2>Selected outcomes</h2>
            <p class="section-note">A compact reference to the measurable parts of the case studies.</p>
          </div>
          <div class="proof-list">
            {''.join(proof_cards)}
          </div>
        </section>
        """

    discovery_html = ""
    if discovery_paths:
        path_cards = []
        for path in discovery_paths[:4]:
            link_items = []
            for link in path.get("links", [])[:3]:
                href = link["url"]
                external = href.startswith("http")
                target = ' target="_blank" rel="noreferrer"' if external else ""
                if not external:
                    href = relative_url('/', href)
                link_items.append(f'<a href="{html.escape(href)}"{target}>{html.escape(link["label"])}</a>')
            starter_html = ""
            starter = path.get("starter")
            if starter:
                starter_href = starter["url"]
                starter_external = starter_href.startswith("http")
                starter_target = ' target="_blank" rel="noreferrer"' if starter_external else ""
                if not starter_external:
                    starter_href = relative_url('/', starter_href)
                starter_route = starter.get("route", "Recommended first move")
                starter_html = f"""
                  <div class="path-starter">
                    <div class="path-route-row">
                      <span class="track-route-label">First move</span>
                      <span class="path-route-pill">{html.escape(starter_route)}</span>
                    </div>
                    <p>
                      Start with <a href="{html.escape(starter_href)}"{starter_target}>{html.escape(starter['label'])}</a>.
                      {html.escape(starter['reason'])}
                    </p>
                  </div>
                """
            links_label = path.get("links_label", "Then go deeper")
            path_cards.append(
                f"""
                <article class="path-card">
                  <p class="meta">{html.escape(path['who'])}</p>
                  <h3>{html.escape(path['title'])}</h3>
                  <p>{html.escape(path['why'])}</p>
                  {starter_html}
                  <p class="path-links-label">{html.escape(links_label)}</p>
                  <div class="path-links">
                    {''.join(link_items)}
                  </div>
                </article>
                """
            )
        discovery_html = f"""
        <section class="section section-frame section-frame-explore">
          <div class="section-head section-head-stack">
            <h2>Ways into the work</h2>
            <p class="section-note">Choose the first click by what you care about.</p>
          </div>
          <div class="card-grid path-grid">
            {''.join(path_cards)}
          </div>
        </section>
        """

    project_lookup = {project["name"]: project for project in projects}
    repo_tracks_html = ""
    if repo_tracks:
        anchor_cards = []
        for track in repo_tracks[:3]:
            starter_project = project_lookup.get(track.get("starter_project", ""))
            if not starter_project:
                continue

            track_id = slugify(track["title"])
            starter_reason = track.get("starter_reason", "").strip()
            proof_card = dict(starter_project)
            proof_card["label"] = f"Proof repo · {track['title']}"
            if starter_reason:
                proof_card["summary"] = starter_reason

            context_feature = track.get("context_feature")
            context_card = ""
            if context_feature:
                context_card = render_context_feature_card(
                    "/",
                    {
                        **context_feature,
                        "meta": context_feature.get("meta", f"Context note · {track['title']}"),
                    },
                    card_class="feature-card feature-card-context",
                    default_cta="Read context",
                )

            proof_links = [
                {"label": "Track guide", "url": f"/projects/#{track_id}"},
                {"label": "Projects page", "url": "/projects/"},
            ]
            related_links = render_track_links("/", track.get("links", []))
            anchor_cards.append(
                f"""
                <article class="project-track-home-card">
                  <div class="project-track-home-head">
                    <p class="meta">Repo track</p>
                    <h3>{html.escape(track['title'])}</h3>
                    <p>{html.escape(track['summary'])}</p>
                  </div>
                  <div class="project-track-intro-grid project-track-home-pair">
                    {render_project_card(proof_card, "/", extra_links=proof_links, card_class="feature-card feature-card-proof")}
                    {context_card}
                  </div>
                  <div class="path-links project-track-links">
                    {''.join(related_links)}
                  </div>
                </article>
                """
            )

        if anchor_cards:
            repo_tracks_html = f"""
            <section class="section section-frame section-frame-open-source section-frame-project-tracks">
              <div class="section-head section-head-stack">
                <h2>One repo per track</h2>
                <p class="section-note">One proof repo, one context route, and the rest on the <a href="{relative_url('/', '/projects/')}">projects page</a>.</p>
              </div>
              <div class="project-track-home-grid">
                {''.join(anchor_cards)}
              </div>
            </section>
            """

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
    {proof_html}
    {discovery_html}

    {repo_tracks_html}
    """
    return page_layout(
        config,
        config["name"],
        body,
        "/",
        meta_description=config.get("meta_description", config["tagline"]),
    )


def render_blog_index(config, posts, external_writing):
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

    oracle_blog_items = render_external_writing_cards("/blog/", external_writing)

    oracle_blogs_section = ""
    if oracle_blog_items:
        oracle_author_url = html.escape(config.get("oracle_blogs_url", "https://blogs.oracle.com/"))
        oracle_blogs_section = f"""
        <section class="section section-frame section-frame-spotlight oracle-blogs-section">
          <div class="section-head section-head-stack oracle-blogs-head">
            <h2>Published elsewhere</h2>
            <p class="section-note oracle-blogs-note">Selected Oracle posts plus my <a class="oracle-blogs-link" href="{oracle_author_url}" target="_blank" rel="noreferrer">author profile</a>.</p>
          </div>
          <div class="external-grid oracle-blogs-grid">
            {''.join(oracle_blog_items)}
          </div>
        </section>
        """

    body = f"""
    <section class="page-hero page-hero-writing">
      <div class="page-hero-copy">
        <p class="eyebrow">Writing</p>
        <h1>Writing on product, platform, and AI work</h1>
        <p class="lead">Short notes on AI workflows, platform work, incidents, small tools, and the day-to-day details that usually decide how the work goes.</p>
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
        meta_description="Writing on AI workflows, platform work, incidents, small tools, and the operating details around them.",
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
                      <p class="meta">What I did</p>
                      {focus}
                    </section>
                    <section class="study-signal">
                      <p class="meta">What made it hard</p>
                      {constraint}
                    </section>
                    <section class="study-signal">
                      <p class="meta">What changed</p>
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
        <p class="lead">A small set of product and platform projects, with the constraints and outcomes called out directly.</p>
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
        <h1>About me.</h1>
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
        </div>
        <div class="about-story-copy about-story-copy-standalone">
          <section class="about-copy-block prose">
            <p class="eyebrow">Personal</p>
            <h2>Away from the desk.</h2>
            {personal_paragraphs}
          </section>
        </div>
      </div>
      <figure class="about-photo-card about-photo-card-side">
        <div class="about-photo">
          <img src="{static_url('/about/', 'winston-trail-clean.png')}" alt="Winston standing on a mountain trail">
        </div>
      </figure>
    </section>
    """
    return page_layout(
        config,
        "About",
        body,
        "/about/",
        meta_description="About Winston Lin: background, work, and interests across cloud products, developer tools, AI workflows, and small businesses.",
    )


def render_projects_page(config, projects, repo_tracks, posts, external_writing):
    project_lookup = {project["name"]: project for project in projects}
    jump_links = []
    track_sections = []
    track_map_rows = []

    for track in repo_tracks:
        track_id = slugify(track["title"])
        jump_links.append(f'<a class="jump-area-link" href="#{html.escape(track_id)}">{html.escape(track["title"])}</a>')

        starter_project_name = track.get("starter_project")
        starter_reason = track.get("starter_reason", "")
        starter_project = project_lookup.get(starter_project_name) if starter_project_name else None
        context_feature = track.get("context_feature")
        context_title = context_feature.get("title", "Context note") if context_feature else "Context note"

        if starter_project:
            starter_name = starter_project["name"]
        else:
            starter_name = track.get("starter_project", "First repo")
        track_map_rows.append(
            "\n".join(
                [
                    "            <tr>",
                    f"              <th scope=\"row\">{html.escape(track['title'])}</th>",
                    f"              <td>{html.escape(starter_name)}</td>",
                    f"              <td>{html.escape(context_title)}</td>",
                    "            </tr>",
                ]
            )
        )

        project_cards = []
        for name in track.get("projects", []):
            if name == starter_project_name:
                continue
            project = project_lookup.get(name)
            if not project:
                continue
            project_cards.append(render_project_card(project, "/projects/"))

        related_links = render_track_links("/projects/", track.get("links", []))

        starter_html = ""
        if starter_project:
            if starter_project.get("site_path"):
                starter_link = f'<a href="{relative_url("/projects/", starter_project["site_path"])}">{html.escape(starter_project["name"])}</a>'
            else:
                starter_link = f'<a href="{html.escape(starter_project["url"])}" target="_blank" rel="noreferrer">{html.escape(starter_project["name"])}</a>'
            starter_html = f"""
            <p class="section-note project-track-pattern">
              One proof and one context link is enough to start this track cleanly.
            </p>
            <p class="section-note project-track-starter">
              Start with {starter_link}
              if you want the clearest first example in this track. {html.escape(starter_reason)}
            </p>
            """

        intro_cards = []
        if starter_project:
            starter_card = dict(starter_project)
            starter_card["label"] = f"Starter repo · {track['title']}"
            intro_cards.append(render_project_card(starter_card, "/projects/", card_class="feature-card feature-card-proof"))
        if context_feature:
            intro_cards.append(
                render_context_feature_card(
                    "/projects/",
                    {
                        **context_feature,
                        "meta": context_feature.get("meta", f"Track context · {track['title']}"),
                    },
                    card_class="feature-card feature-card-context",
                    default_cta="Read context",
                )
            )

        intro_html = ""
        if intro_cards:
            intro_html = f"""
            <div class="project-track-intro-grid">
              {''.join(intro_cards)}
            </div>
            """

        repo_grid_html = ""
        if project_cards:
            repo_grid_html = f"""
            <div class="project-track-rest">
              <p class="project-track-subhead">More repos in this track</p>
              <div class="feature-grid repo-grid">
                {''.join(project_cards)}
              </div>
            </div>
            """

        track_sections.append(
            f"""
            <section class="section section-frame section-frame-explore project-track-section" id="{html.escape(track_id)}">
              <div class="section-head section-head-stack">
                <h2>{html.escape(track['title'])}</h2>
                <p class="section-note">{html.escape(track['summary'])}</p>
                {starter_html}
              </div>
              {intro_html}
              {repo_grid_html}
              <div class="path-links project-track-links">
                {''.join(related_links)}
              </div>
            </section>
            """
        )

    all_project_cards = []
    for project in projects:
        if project["name"] == "winstonlin-site":
            continue
        all_project_cards.append(render_project_card(project, "/projects/"))

    track_map_rows_html = "\n".join(track_map_rows)
    project_map = f"""
    <section class="section section-frame section-frame-explore project-map-section">
      <div class="section-head section-head-stack">
        <h2>How the repo tracks fit together</h2>
        <p class="section-note">The useful split here is between checks, reusable artifacts, and starter patterns with a clean handoff boundary.</p>
      </div>
      <div class="track-map-table-wrap">
        <table class="track-map-table">
          <thead>
            <tr>
              <th scope="col">Track</th>
              <th scope="col">Start with</th>
              <th scope="col">Then read</th>
            </tr>
          </thead>
          <tbody>
{track_map_rows_html}
          </tbody>
        </table>
      </div>
    </section>
    """

    latest_posts = []
    project_featured_slugs = config.get(
        "projects_featured_post_slugs",
        [
            "repeated-work-should-become-a-check",
            "fun-projects-get-stronger-when-they-leave-a-reusable-artifact",
            "starter-repos-should-stop-at-the-right-boundary",
        ],
    )
    for slug in project_featured_slugs[:3]:
        post = find_post(posts, slug)
        if post:
            latest_posts.append(
                f"""
                <article class="feature-card">
                  <p class="meta">{html.escape(post.date)}</p>
                  <h3><a href="{relative_url('/projects/', f'/blog/{post.slug}/')}">{html.escape(post.title)}</a></h3>
                  <p>{html.escape(post.summary)}</p>
                </article>
                """
            )

    external_writing_section = ""
    supplemental_external = external_writing[1:] if len(external_writing) > 1 else []
    external_cards = render_external_writing_cards("/projects/", supplemental_external)
    if external_cards:
        author_href = html.escape(config.get("oracle_blogs_url", "https://blogs.oracle.com/"))
        external_writing_section = f"""
        <section class="section section-frame section-frame-spotlight">
          <div class="section-head section-head-stack">
            <h2>More Oracle context around the starter work</h2>
            <p class="section-note">A couple of additional Oracle posts that expand the OCI Functions side of the same starter-pattern preferences. <a class="oracle-blogs-link" href="{author_href}" target="_blank" rel="noreferrer">Author profile</a>.</p>
          </div>
          <div class="external-grid">
            {''.join(external_cards)}
          </div>
        </section>
        """

    body = f"""
    <section class="page-hero page-hero-projects">
      <div class="page-hero-copy">
        <p class="eyebrow">Projects</p>
        <h1>Small tools, starter patterns, and reusable workflow artifacts.</h1>
        <p class="lead">This is the cleanest route through the public repo work: grouped by the kind of repeated problem each batch is trying to make more visible, more reusable, or easier to rerun.</p>
      </div>
    </section>
    <section class="section jump-section">
      <div class="section-head section-head-stack">
        <h2>Jump by project track</h2>
        <p class="section-note">A short path if you care more about checks, planning artifacts, or OCI Functions starter patterns.</p>
      </div>
      <div class="jump-scroller">
        {''.join(jump_links)}
      </div>
    </section>
    {project_map}
    {''.join(track_sections)}
    {external_writing_section}
    <section class="section section-frame section-frame-spotlight">
      <div class="section-head section-head-stack">
        <h2>Notes behind the repos</h2>
        <p class="section-note">Short writing that explains the standard behind the public repo work, not just the repo inventory.</p>
      </div>
      <div class="feature-grid">
        {''.join(latest_posts)}
      </div>
    </section>
    <section class="section section-frame section-frame-open-source">
      <div class="section-head section-head-stack">
        <h2>All repositories</h2>
        <p class="section-note">The full public set currently called out on the site.</p>
        <a href="{html.escape(config['github_url'])}" target="_blank" rel="noreferrer">GitHub profile</a>
      </div>
      <div class="feature-grid repo-grid">
        {''.join(all_project_cards)}
      </div>
    </section>
    """
    return page_layout(
        config,
        "Projects",
        body,
        "/projects/",
        meta_description="Grouped public projects, workflow tools, and OCI Functions starter patterns from Winston Lin.",
    )


def render_post_page(config, post, posts):
    current_path = f"/blog/{post.slug}/"
    post_diagram, diagram_heading = render_diagram(post.slug, current_path)
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
    </article>
    """
    return page_layout(
        config,
        post.title,
        article,
        current_path,
        meta_description=post.summary,
        og_type="article",
    )


def render_project_spotlight_page(config, spotlight, projects, repo_tracks):
    project_lookup = {project["name"]: project for project in projects}
    project = project_lookup.get(spotlight["project"])
    if not project:
        raise KeyError(f"Missing project metadata for spotlight: {spotlight['project']}")

    current_path = project.get("site_path", f"/projects/{project['name']}/")
    track = find_project_track(repo_tracks, project["name"])

    proof_cards = []
    for point in spotlight.get("proof_points", [])[:3]:
        proof_cards.append(
            f"""
            <article class="proof-card">
              <p class="proof-label">{html.escape(point['label'])}</p>
              <p>{html.escape(point['text'])}</p>
            </article>
            """
        )

    track_links = []
    track_context_card = render_project_card(project, current_path)
    if track:
        track_id = slugify(track["title"])
        track_links = [f'<a href="{relative_url(current_path, f"/projects/#{track_id}")}">Open full track</a>']
        track_links.extend(render_track_links(current_path, track.get("links", []), limit=2))
        track_context_card = f"""
        <article class="feature-card">
          <p class="meta">Project track</p>
          <h3><a href="{relative_url(current_path, f'/projects/#{track_id}')}">{html.escape(track['title'])}</a></h3>
          <p>This repo sits inside the {html.escape(track['title'].lower())} batch, where the shared standard is {html.escape(track['summary'].lower())}</p>
          <div class="card-links">
            {''.join(track_links)}
          </div>
        </article>
        """

    context_feature_card = track_context_card
    if track and track.get("context_feature"):
        context_feature_card = render_context_feature_card(current_path, track["context_feature"], default_cta="Read context")

    body = f"""
    <section class="page-hero page-hero-projects">
      <div class="page-hero-copy">
        <p class="eyebrow">{html.escape(spotlight['eyebrow'])}</p>
        <h1>{html.escape(spotlight['headline'])}</h1>
        <p class="lead">{html.escape(spotlight['lead'])}</p>
        <div class="hero-links">
          <a class="button-link primary" href="{html.escape(project['url'])}" target="_blank" rel="noreferrer">Open GitHub repo</a>
          <a class="button-link" href="{relative_url(current_path, '/projects/')}">Back to projects</a>
        </div>
      </div>
    </section>
    <section class="section section-frame section-frame-explore">
      <div class="section-head section-head-stack">
        <h2>Why this repo carries the track</h2>
        <p class="section-note">A short site-side guide before the proof layer on GitHub.</p>
      </div>
      <div class="proof-grid project-proof-grid">
        {''.join(proof_cards)}
      </div>
    </section>
    <section class="section section-frame section-frame-spotlight">
      <div class="section-head section-head-stack">
        <h2>{html.escape(spotlight['artifact_heading'])}</h2>
        <p class="section-note">{html.escape(project['name'])} as a first useful success, not only a demo.</p>
      </div>
      <div class="project-spotlight-layout">
        <div class="project-spotlight-copy">
          <p>{html.escape(spotlight['artifact_text'])}</p>
          <p>{html.escape(spotlight['next_text'])}</p>
        </div>
        <div class="project-code-card">
          <p class="meta">Quick run</p>
          <pre><code>{html.escape(spotlight['sample_command'])}</code></pre>
          <p class="meta">Sample output shape</p>
          <pre><code>{html.escape(spotlight['sample_output'])}</code></pre>
        </div>
      </div>
    </section>
    <section class="section section-frame section-frame-open-source">
      <div class="section-head section-head-stack">
        <h2>{html.escape(spotlight['next_heading'])}</h2>
        <p class="section-note">{html.escape(project['summary'])}</p>
      </div>
      <div class="project-next-grid">
        <article class="feature-card">
          <p>{html.escape(spotlight['next_text'])}</p>
          <div class="card-links">
            {''.join(track_links)}
          </div>
        </article>
        {context_feature_card}
      </div>
    </section>
    """
    return page_layout(
        config,
        project["name"],
        body,
        current_path,
        meta_description=spotlight["lead"],
    )


def ensure_clean_dist():
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "blog").mkdir(parents=True, exist_ok=True)


def write_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content)


def write_support_files(config, posts, project_spotlights):
    site_url = config.get("site_url", "").rstrip("/")
    if not site_url:
        return

    spotlight_urls = []
    for spotlight in project_spotlights:
        project_name = spotlight.get("project")
        if project_name:
            spotlight_urls.append(f"/projects/{project_name}/")

    urls = ["/", "/about/", "/blog/", "/case-studies/", "/projects/"] + spotlight_urls + [f"/blog/{post.slug}/" for post in posts]
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
      <p><a href="./">Back home</a></p>
    </section>
    """
    return page_layout(
        config,
        "Not Found",
        body,
        "/404.html",
        meta_description="Winston Lin portfolio page not found.",
    )


def build():
    config = load_json(ROOT / "site_config.json")
    projects = load_json(CONTENT_DIR / "projects.json")
    project_spotlights = load_json(CONTENT_DIR / "project_spotlights.json")
    repo_tracks = load_json(CONTENT_DIR / "repo_tracks.json")
    external_writing = load_json(CONTENT_DIR / "external_writing.json")
    case_studies = load_json(CONTENT_DIR / "case_studies.json")
    discovery_paths = load_json(CONTENT_DIR / "discovery_paths.json")
    proof_points = load_json(CONTENT_DIR / "proof_points.json")
    posts = load_posts()

    ensure_clean_dist()
    shutil.copytree(STATIC_DIR, OUTPUT_DIR, dirs_exist_ok=True)
    write_text(OUTPUT_DIR / ".nojekyll", "")

    write_text(OUTPUT_DIR / "index.html", render_homepage(config, posts, projects, case_studies, discovery_paths, proof_points, repo_tracks, external_writing))
    write_text(OUTPUT_DIR / "about" / "index.html", render_about_page(config))
    write_text(OUTPUT_DIR / "blog" / "index.html", render_blog_index(config, posts, external_writing))
    write_text(OUTPUT_DIR / "case-studies" / "index.html", render_case_studies_page(config, case_studies))
    write_text(OUTPUT_DIR / "projects" / "index.html", render_projects_page(config, projects, repo_tracks, posts, external_writing))
    write_text(OUTPUT_DIR / "404.html", render_not_found_page(config))

    for spotlight in project_spotlights:
        project_name = spotlight.get("project")
        if not project_name:
            continue
        write_text(OUTPUT_DIR / "projects" / project_name / "index.html", render_project_spotlight_page(config, spotlight, projects, repo_tracks))

    for post in posts:
        write_text(OUTPUT_DIR / "blog" / post.slug / "index.html", render_post_page(config, post, posts))

    write_support_files(config, posts, project_spotlights)


if __name__ == "__main__":
    build()
