import html
import json
import posixpath
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"
POSTS_DIR = CONTENT_DIR / "posts"
STATIC_DIR = ROOT / "static"
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


# Templates share one small visual system. Content stays in JSON and Markdown.
ASSET_VERSION = '20261021-public'
HEADSHOT_ASSET = 'winston-headshot-editorial.jpg'
TRAIL_ASSET = 'winston-trail-editorial.jpg'
WATERFRONT_ASSET = 'winston-waterfront-editorial.jpg'
BALCONY_ASSET = 'winston-balcony-editorial.jpg'
ARROW = '<svg class="arrow" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 19 19 5M5 5h14v14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
DOWN = '<svg class="arrow" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 4v16m-6-6 6 6 6-6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
NEXT = '<svg class="flow-arrow" viewBox="0 0 64 20" fill="none" aria-hidden="true"><path d="M1 10h60m-7-7 7 7-7 7" stroke="currentColor" stroke-width="1.2"/></svg>'


def motif(kind, css='motif'):
    shapes = {
        'code': '<rect x="10" y="14" width="60" height="48" rx="3"/><path d="M10 25h60M29 36l-8 8 8 8m22-16 8 8-8 8M44 33l-8 22"/><circle cx="17" cy="20" r="1"/><circle cx="23" cy="20" r="1"/>',
        'diagnosis': '<circle cx="35" cy="33" r="19"/><path d="m49 47 17 17M23 34h7l5-9 7 16 5-7"/>',
        'platform': '<path d="m40 10 29 16-29 16L11 26zM11 39l29 16 29-16M11 52l29 16 29-16"/>',
        'path': '<path d="M16 16h30a15 15 0 0 1 0 30H32a12 12 0 0 0 0 24h32M56 62l8 8-8 8"/><circle cx="16" cy="16" r="5"/>',
        'write': '<path d="M18 12h35l10 10v46H18zM53 12v13h10M28 36h25M28 46h25M28 56h17"/>',
        'people': '<circle cx="29" cy="28" r="10"/><path d="M10 63v-9a19 19 0 0 1 38 0v9M50 20a10 10 0 0 1 0 20m6 7a16 16 0 0 1 13 16"/>',
        'photo': '<path d="M12 22h14l5-8h18l5 8h14v43H12z"/><circle cx="40" cy="43" r="14"/><circle cx="59" cy="29" r="2"/>',
    }
    return f'<svg class="{css}" viewBox="0 0 80 80" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{shapes.get(kind, shapes["platform"])}</svg>'


def study_motif(study):
    return {'oci-functions-product-direction':'code', 'ai-assisted-functions-workflows':'diagnosis', 'service-installer':'platform', 'oci-functions-migration-and-docs':'path', 'feature-registry':'diagnosis', 'oci-functions-product-boundaries':'path', 'sitetracker-enterprise-delivery':'people', 'startup-small-business-advisory':'people'}.get(study['slug'],'platform')


def work_art(kind):
    # Editorial illustrations of the product themes, not product screenshots.
    art = {
        'code': '''<rect width="400" height="200" fill="#b4482f"/>
<rect x="83" y="34" width="234" height="132" rx="4" fill="#f2e7d2"/>
<path d="M83 60h234" stroke="#b4482f" stroke-width="2"/>
<g fill="#b4482f"><circle cx="97" cy="47" r="3"/><circle cx="108" cy="47" r="3"/><circle cx="119" cy="47" r="3"/></g>
<g fill="none" stroke="#843329" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"><path d="m161 86-24 25 24 25m78-50 24 25-24 25m-32-58-14 66"/></g>''',
        'diagnosis': '''<rect width="400" height="200" fill="#244d40"/>
<path d="m70 142 76-34 89 37 94-78" fill="none" stroke="#a9c9b0" stroke-width="2"/>
<rect x="55" y="127" width="30" height="30" rx="3" fill="#d6bd78"/><circle cx="329" cy="67" r="15" fill="#a8c5db"/>
<circle cx="180" cy="83" r="53" fill="#e9ead3"/><circle cx="180" cy="83" r="39" fill="#365f50"/>
<path d="M149 85h15l10-19 13 36 12-23h13" fill="none" stroke="#e9ead3" stroke-width="3" stroke-linejoin="round"/>
<path d="m218 121 43 43" stroke="#e9ead3" stroke-width="21" stroke-linecap="round"/><path d="m230 133 31 31" stroke="#d6bd78" stroke-width="11" stroke-linecap="round"/>''',
        'platform': '''<rect width="400" height="200" fill="#3a5570"/>
<path d="m200 88 96 50-96 50-96-50z" fill="#8eb1b9"/><path d="m200 54 96 50-96 50-96-50z" fill="#a7b7c6"/>
<path d="m200 20 96 50-96 50-96-50z" fill="#f0d7a0"/>
<path d="m200 39 60 31-60 31-60-31z" fill="none" stroke="#9d7449" stroke-width="1.5"/>
<path d="m184 69 12 11 23-22" fill="none" stroke="#3a5570" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>''',
    }
    return f'<svg class="work-art" viewBox="0 0 400 200" fill="none" aria-hidden="true">{art.get(kind,art["platform"])}</svg>'


def photo_link(current, slug, css='', loading='lazy', sizes='(max-width:700px) 50vw, 320px'):
    photo=next(p for p in load_json(CONTENT_DIR/'photographs.json') if p['slug']==slug)
    small=static_url(current,'photography/'+photo['thumbnail'])+'?v='+ASSET_VERSION
    large=static_url(current,'photography/'+photo['asset'])+'?v='+ASSET_VERSION
    return f'<figure class="editorial-photo {css}"><a href="{href(current,"/photography/#"+slug)}" aria-label="View {esc(photo["title"])} in the photo gallery"><img src="{small}" srcset="{small} {photo["thumbnail_width"]}w, {large} {photo["width"]}w" sizes="{esc(sizes)}" alt="{esc(photo["alt"])}" width="{photo["width"]}" height="{photo["height"]}" loading="{loading}" decoding="async"></a></figure>'


def esc(value):
    return html.escape(str(value), quote=True)


def href(current, target):
    if target.startswith(('https://', 'http://', 'mailto:', '#')):
        return target
    return relative_url(current, target)


def link(current, target, label, css='text-link', arrow=False):
    return f'<a class="{esc(css)}" href="{esc(href(current, target))}">{esc(label)}{ARROW if arrow else ""}</a>'


def paragraphs(items):
    return ''.join(f'<p>{esc(item)}</p>' for item in items)


def flow_diagram(items):
    return '<div class="workflow" aria-label="' + esc(' then '.join(items)) + '">' + NEXT.join(f'<span>{esc(item)}</span>' for item in items) + '</div>'


def page_layout(config, title, body, current_path='/', meta_description=None, og_type='website'):
    page_title = f'{title} | Winston Lin' if title != config['name'] else 'Winston Lin — Product manager'
    description = meta_description or config['meta_description']
    canonical = absolute_url(config,current_path)
    nav=[]
    for label,path in [('Work','/case-studies/'),('Writing','/blog/'),('About','/about/'),('Photos','/photography/')]:
        active = current_path.startswith(path) or (label=='Work' and current_path.startswith('/projects/'))
        current_attr = ' aria-current="page"' if active else ''
        nav.append(f'<a href="{href(current_path,path)}"{current_attr}>{label}</a>')
    structured=json.dumps({'@context':'https://schema.org','@type':'Person','name':'Winston Lin','url':config['site_url']+'/', 'jobTitle':'Principal Product Manager','worksFor':{'@type':'Organization','name':'Oracle'},'sameAs':[config['linkedin_url'],config['github_url']]},ensure_ascii=False).replace('<','\\u003c')
    page_class='page-home' if current_path=='/' else 'page-'+current_path.strip('/').split('/')[0]
    return f'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(page_title)}</title><meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}"><link rel="icon" href="{static_url(current_path,'favicon.svg')}" type="image/svg+xml">
<meta property="og:title" content="{esc(page_title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:type" content="{og_type}"><meta property="og:url" content="{esc(canonical)}"><meta property="og:image" content="{config['site_url']}/{HEADSHOT_ASSET}"><meta name="twitter:card" content="summary">
<link rel="stylesheet" href="{static_url(current_path,'styles.css')}?v={ASSET_VERSION}">
<script src="{static_url(current_path,'gallery.js')}?v={ASSET_VERSION}" defer></script>
<link rel="alternate" type="application/rss+xml" title="Winston Lin — Writing" href="{static_url(current_path,'feed.xml')}">
<script type="application/ld+json">{structured}</script>
</head><body class="{page_class}">
<a class="skip-link" href="#main">Skip to content</a>
<div class="site-shell">
<header class="site-header"><a class="wordmark" href="{href(current_path,'/')}" aria-label="Winston Lin home">WL<span>.</span></a><nav aria-label="Main navigation">{''.join(nav)}</nav></header>
<main id="main">{body}</main>
<footer id="contact" class="site-footer"><div class="footer-invitation">{link(current_path,'mailto:'+config['email'],'Let’s talk.','footer-contact',True)}</div><div class="footer-details">{link(current_path,'mailto:'+config['email'],config['email'],'email-link')}<div class="social-links">{link(current_path,config['linkedin_url'],'LinkedIn',arrow=True)}{link(current_path,config['github_url'],'GitHub',arrow=True)}</div><small>© {datetime.now().year} Winston Lin</small></div></footer>
</div></body></html>'''


def section_heading(title, current='/', target=None, label=None):
    return f'<div class="section-heading"><h2>{esc(title)}</h2>{link(current,target,label) if target else ""}</div>'


def work_row(study, number, current='/', featured=False):
    target=f'/case-studies/{study["slug"]}/'
    if featured:
        return f'''<article class="work-feature" id="{esc(study['slug'])}"><a class="feature-art" href="{href(current,target)}" aria-label="Read {esc(study['title'])}">{work_art(study_motif(study))}</a><div class="feature-copy"><p class="meta">{esc(study['period'])}</p><h3>{link(current,target,study['title'],'title-link')}</h3><p class="feature-summary">{esc(study.get('home_summary',study['tagline']))}</p><p class="work-focus">{esc(study.get('public_status',study.get('role','Product work')))}</p>{link(current,target,'Read the case study',arrow=True)}</div></article>'''
    return f'''<article class="work-row{' featured' if featured else ''}" id="{esc(study['slug'])}">
<div class="work-mark" aria-hidden="true"><span>{number:02}</span>{motif(study_motif(study))}</div><div class="work-title"><p class="meta">{esc(study['period'])}</p><h3>{link(current,target,study['title'],'title-link',False)}</h3></div>
<div class="work-description"><p>{esc(study.get('home_summary',study['tagline']))}</p><p class="work-focus">{esc(study.get('public_status',study.get('role','Product work')))}</p>{link(current,target,'Read the case study',arrow=True)}</div></article>'''


def collection_row(current,title,meta,target):
    return f'<a class="collection-row" href="{esc(href(current,target))}"><span><span class="collection-title">{esc(title)}</span><span class="collection-meta">{esc(meta)}</span></span>{ARROW}</a>'


def render_homepage(config,posts,studies,external):
    selected_essay=next(p for p in posts if p.slug=='support-boundaries-are-product-strategy')
    body=f'''<section class="hero" aria-labelledby="hero-title"><div class="hero-copy"><h1 id="hero-title">Winston Lin<span>.</span></h1><p class="hero-intro">I’m a Principal Product Manager at Oracle, based in San Francisco. I work on developer tools and AI-assisted workflows.</p><div class="hero-actions"><a class="text-link" href="#selected-work">Selected work{DOWN}</a>{link('/','/about/','More about me',arrow=True)}</div><p class="hero-previous">Previously at Sitetracker and Cisco.</p></div><figure class="hero-photo"><img src="{static_url('/',HEADSHOT_ASSET)}" alt="Portrait of Winston Lin" width="1254" height="1254" fetchpriority="high"></figure></section>
<section class="home-work" id="selected-work">{section_heading('Selected work','/','/case-studies/','All work')}<div class="featured-work">{''.join(work_row(x,i+1,featured=True) for i,x in enumerate(studies[:3]))}</div></section>
<section class="home-writing"><div class="writing-intro">{motif('write')}<h2>Writing</h2>{link('/','/blog/','All writing',arrow=True)}</div><div class="writing-selection">{collection_row('/','Introducing code-only deployment','Oracle · September 2026','https://blogs.oracle.com/cloud-infrastructure/oci-functions-code-only-deployment')}{collection_row('/','AI skills for deployment and troubleshooting','Oracle · July 2026','https://blogs.oracle.com/cloud-infrastructure/oci-functions-ai-serverless-deployment-skills')}{collection_row('/',selected_essay.title,'Essay',f'/blog/{selected_essay.slug}/')}</div></section>
<section class="home-about"><div class="home-about-copy"><h2>Outside work</h2><p>I grew up between Taipei and Orange County. These days I spend my free time hiking, playing basketball or volleyball, and taking photos.</p>{link('/','/photography/','A few photos',arrow=True)}</div><div class="home-photos">{photo_link('/','coastal-bay','personal-wide',sizes='(max-width:700px) 65vw, (max-width:1312px) 65vw, 767px')}{photo_link('/','wood-and-glass','personal-tall',sizes='(max-width:700px) 35vw, (max-width:1312px) 35vw, 409px')}</div></section>'''
    return page_layout(config,config['name'],body)


def page_intro(title,summary):
    kind={'Work':'platform','Writing':'write','Projects':'code','About':'people','Photos':'photo'}.get(title)
    return f'<header class="page-intro"><div><h1>{esc(title)}</h1><p>{esc(summary)}</p></div>{motif(kind,"intro-motif") if kind else ""}</header>'


def render_work_index(config,studies):
    current='/case-studies/'
    # Old group fragments remain valid, along with every original story slug.
    aliases=''.join(f'<span id="{s}" class="fragment-alias"></span>' for s in ['case-jumps','advisory','oci-functions','oke-oci-kubernetes-engine','oci-dev-platform','sitetracker'])
    body=page_intro('Work','A selection of product work and advisory projects.')
    body+=aliases+'<section class="work-list" aria-label="Case studies">'+''.join(work_row(s,i+1,current) for i,s in enumerate(studies))+'</section>'
    body+=f'<aside class="builds-callout">{motif("code")}<div><h2>Small builds</h2><p>Tools for planning and developer workflows.</p></div>{link(current,"/projects/","Explore the projects",arrow=True)}</aside>'
    return page_layout(config,'Work',body,current)


def render_case_detail(config,study,studies):
    current=f'/case-studies/{study["slug"]}/'
    sources=''
    if study.get('sources'):
        sources='<section class="case-sources"><h2>See the work</h2>'+''.join(link(current,s['url'],s['label']) for s in study['sources'])+'</section>'
    body=f'''<div class="back-link">{link(current,'/case-studies/','All work',arrow=False)}</div>
<article class="reading-page case-page"><header class="reading-header"><div class="case-heading-icon">{motif(study_motif(study))}</div><h1>{esc(study['title'])}</h1><p class="reading-deck">{esc(study['tagline'])}</p><div class="article-meta"><span>{esc(study['period'])}</span><span>{esc(study.get('role','Product contribution'))}</span></div></header>
<div class="case-body"><nav class="case-contents" aria-label="Case study sections"><a href="#problem">01 <span>The problem</span></a><a href="#contribution">02 <span>My contribution</span></a><a href="#decisions">03 <span>The decisions</span></a><a href="#outcome">04 <span>Where it landed</span></a></nav><div class="prose"><section id="problem"><h2>The problem</h2><p>{esc(study['problem'])}</p></section><section id="contribution"><h2>My contribution</h2>{paragraphs(study['what_i_did'])}</section><section id="decisions"><h2>The decisions</h2>{paragraphs(study['why_it_was_hard'])}</section><section id="outcome"><h2>Where it landed</h2>{paragraphs(study['outcome'])}</section>{sources}</div></div></article>'''
    others=[s for s in studies[:3] if s['slug']!=study['slug']]
    body+='<section class="read-next">'+section_heading('More work')+''.join(collection_row(current,s['title'],s['period'],f'/case-studies/{s["slug"]}/') for s in others[:2])+'</section>'
    return page_layout(config,study['title'],body,current,study['tagline'],'article')


def render_blog_index(config,posts,external):
    current='/blog/'
    chosen=['trustworthy-ai-products-need-recovery-paths','support-boundaries-are-product-strategy','how-i-use-ai-as-a-pm-with-a-real-workspace','what-building-internal-platforms-taught-me']
    selected=[p for slug in chosen for p in posts if p.slug==slug]
    body=page_intro('Writing','Launch articles and notes on product work.')
    body+='<section class="collection-section published-writing">'+section_heading('Published at Oracle')+''.join(collection_row(current,x['title'],f'{x["publication"]} · {x["date"]}',x['url']) for x in external)+'</section>'
    body+='<section class="collection-section">'+section_heading('Selected essays')+''.join(collection_row(current,p.title,f'{p.date} · {max(1,round(len(p.body_markdown.split())/220))} min read',f'/blog/{p.slug}/') for p in selected)+'</section>'
    archive=[p for p in posts if p not in selected]
    body+='<details class="archive"><summary>All other essays <span>'+str(len(archive))+'</span></summary><div>'+''.join(collection_row(current,p.title,p.date,f'/blog/{p.slug}/') for p in archive)+'</div></details>'
    body+='<div class="section-end">'+link(current,'/projects/','Browse small builds')+'</div>'
    return page_layout(config,'Writing',body,current)


def render_post_page(config,post,posts):
    current=f'/blog/{post.slug}/'
    # Body-level H1s become H2s so each document has one clear primary heading.
    article=markdown_to_html(post.body_markdown).replace('<h1>','<h2>').replace('</h1>','</h2>')
    body=f'''<div class="back-link">{link(current,'/blog/','All writing',arrow=False)}</div><article class="reading-page"><header class="reading-header"><h1>{esc(post.title)}</h1><p class="reading-deck">{esc(post.summary)}</p><div class="article-meta"><time datetime="{esc(post.date)}">{esc(post.date)}</time><span>{max(1,round(len(post.body_markdown.split())/220))} min read</span></div></header><div class="prose">{article}</div></article>'''
    index=posts.index(post)
    next_post=posts[(index+1)%len(posts)]
    body+='<section class="read-next">'+section_heading('Keep reading')+collection_row(current,next_post.title,next_post.summary,f'/blog/{next_post.slug}/')+'</section>'
    return page_layout(config,post.title,body,current,post.summary,'article')


def render_projects_page(config,projects,tracks):
    current='/projects/'
    body=page_intro('Projects','Small tools for planning and developer workflows.')
    by={p['name']:p for p in projects}
    used=set()
    for track in tracks:
        # Keep track anchors from existing incoming links.
        names=[n for n in track.get('projects',[]) if isinstance(n,str) and n in by]
        if not names:
            names=[p['name'] for p in projects if (p['label']=='Functions pattern') == ('Functions' in track['title']) and p['name'] not in used and p['name']!='winstonlin-site']
        names=[n for n in names if n not in used]
        if not names: continue
        used.update(names)
        rows=''.join(collection_row(current,n,by[n]['summary'],by[n].get('site_path',by[n]['url'])) for n in names)
        body+=f'<section class="collection-section" id="{slugify(track["title"])}">{section_heading(track["title"])}{rows}</section>'
    remaining=[p for p in projects if p['name'] not in used]
    if remaining:
        body+='<section class="collection-section">'+section_heading('More on GitHub')+''.join(collection_row(current,p['name'],p['summary'],p.get('site_path',p['url'])) for p in remaining)+'</section>'
    return page_layout(config,'Small builds',body,current)


def render_project_detail(config,project,spotlight):
    current=f'/projects/{project["name"]}/'
    body=f'<div class="back-link">{link(current,"/projects/","All small builds",arrow=False)}</div><article class="reading-page"><header class="reading-header"><h1>{esc(project["name"])}</h1><p class="reading-deck">{esc(project["summary"])}</p><div class="article-meta"><span>{esc(project["label"])}</span>{link(current,project["url"],"View on GitHub")}</div></header><div class="prose">'
    if spotlight:
        body+=f'<h2>What it does</h2><p>{esc(spotlight["artifact_text"])}</p><h2>Try it locally</h2><pre><code>{esc(spotlight["sample_command"])}</code></pre><h2>Example output</h2><pre><code>{esc(spotlight["sample_output"])}</code></pre><h2>Where it helps</h2><p>{esc(spotlight["next_text"])}</p>'
    body+='</div></article>'
    return page_layout(config,project['name'],body,current,project['summary'])


def render_about_page(config):
    current='/about/'
    about=config['about']
    body=page_intro('About','A product manager in San Francisco, by way of Taipei and Orange County.')
    body+=f'<div class="about-layout"><div class="prose"><section>{paragraphs(about["intro"])}</section><section><h2>Beyond Oracle</h2>{paragraphs(about["advisory"])}</section><section><h2>Before all that</h2>{paragraphs(about["background"])}</section></div><div class="about-photos"><figure><img src="{static_url(current,WATERFRONT_ASSET)}" alt="Winston sitting beside the water" width="1122" height="1402"></figure><figure><img src="{static_url(current,BALCONY_ASSET)}" alt="Winston on a balcony beside a waterfall" width="1122" height="1402" loading="lazy"></figure></div></div>'
    body+='<section class="experience-list">'+section_heading('Experience')
    for dates,company,role in [('2022–Present','Oracle Cloud Infrastructure','Principal Product Manager, OCI Functions; earlier work in developer platforms and Kubernetes.'),('2021–2022','Sitetracker','Enterprise software implementations and customer workflows.'),('2019–2021','Cisco','Engineering program management for enterprise networking.')]:
        body+=f'<div class="experience-row"><span>{dates}</span><div><h3>{company}</h3><p>{role}</p></div></div>'
    body+='</section>'
    body+=f'<section class="about-personal"><div><h2>Away from the desk</h2><div class="prose">{paragraphs(about["personal"])}</div>{link(current,"/photography/","A few photos",arrow=True)}</div><div class="about-personal-photos">{photo_link(current,"giant-leaves")}{photo_link(current,"goldfish")}</div></section>'
    return page_layout(config,'About',body,current)


def render_photography(config, photographs):
    current='/photography/'
    body=page_intro('Photos','A few things that caught my eye.')
    body+='<div class="photo-grid">'
    rows=[photographs[:1]] if photographs else []
    remaining=photographs[1:]
    while remaining:
        count=3 if len(remaining)==3 else min(2,len(remaining))
        rows.append(remaining[:count])
        remaining=remaining[count:]
    for row in rows:
        body+='<div class="photo-row">'
        total_ratio=sum(photo['width']/photo['height'] for photo in row)
        for photo in row:
            ratio=photo['width']/photo['height']
            fraction=ratio/total_ratio
            source=static_url(current,'photography/'+photo.get('asset',photo['slug']+'.jpg'))+'?v='+ASSET_VERSION
            preview=static_url(current,'photography/'+photo['thumbnail'])+'?v='+ASSET_VERSION if photo.get('thumbnail') else source
            desktop_width=round((960-24*(len(row)-1))*fraction)
            sizes=f'(max-width: 700px) min(520px, calc(100vw - 40px)), (max-width: 1000px) {round(fraction*100)}vw, {desktop_width}px'
            responsive=f' srcset="{preview} {photo["thumbnail_width"]}w, {source} {photo["width"]}w" sizes="{sizes}"' if photo.get('thumbnail') else ''
            body+=f'''<figure class="photo-item" style="--photo-ratio:{ratio:.8f}" id="{esc(photo['slug'])}"><a href="{source}" data-photo aria-label="Enlarge {esc(photo['title'])}"><img src="{preview}"{responsive} alt="{esc(photo['alt'])}" width="{photo['width']}" height="{photo['height']}" loading="lazy" decoding="async"></a></figure>'''
        body+='</div>'
    body+='</div>'
    body+='''<dialog class="photo-viewer" aria-labelledby="viewer-title"><div class="viewer-header"><p id="viewer-title">Photographs</p><button type="button" data-close autofocus>Close ×</button></div><div class="viewer-image"><img alt="Selected photograph"></div><div class="viewer-footer"><div class="viewer-actions"><button type="button" data-previous aria-label="Previous photograph">←</button><span class="viewer-count" aria-live="polite"></span><button type="button" data-next aria-label="Next photograph">→</button></div></div></dialog>'''
    body+=f'<div class="section-end">{link(current,"/about/","Back to About")}</div>'
    return page_layout(config,'Photos',body,current,'A few photographs by Winston Lin, from walks and trips.')


def write_text(path,content):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(content.rstrip()+'\n' if content else '')


def build():
    config=load_json(ROOT/'site_config.json')
    studies=load_json(CONTENT_DIR/'case_studies.json')
    projects=load_json(CONTENT_DIR/'projects.json')
    spotlights=load_json(CONTENT_DIR/'project_spotlights.json')
    tracks=load_json(CONTENT_DIR/'repo_tracks.json')
    external=load_json(CONTENT_DIR/'external_writing.json')
    photographs=load_json(CONTENT_DIR/'photographs.json')
    posts=load_posts()
    if OUTPUT_DIR.exists(): shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir()
    # Only copy declared public assets, never arbitrary untracked files.
    assets=['styles.css','gallery.js','favicon.svg','winston-headshot.jpg','winston-headshot-retouched.jpg',HEADSHOT_ASSET,TRAIL_ASSET,WATERFRONT_ASSET,BALCONY_ASSET,'winston-trail-clean.png','winston-trail.png']
    for asset in assets: shutil.copy2(STATIC_DIR/asset,OUTPUT_DIR/asset)
    (OUTPUT_DIR/'photography').mkdir()
    for photo in photographs:
        filename=photo.get('asset',photo['slug']+'.jpg')
        shutil.copy2(STATIC_DIR/'photography'/filename,OUTPUT_DIR/'photography'/filename)
        if photo.get('thumbnail'):
            shutil.copy2(STATIC_DIR/'photography'/photo['thumbnail'],OUTPUT_DIR/'photography'/photo['thumbnail'])
    if (STATIC_DIR/'diagrams').exists(): shutil.copytree(STATIC_DIR/'diagrams',OUTPUT_DIR/'diagrams')
    pages={'/':render_homepage(config,posts,studies,external),'/case-studies/':render_work_index(config,studies),'/blog/':render_blog_index(config,posts,external),'/projects/':render_projects_page(config,projects,tracks),'/about/':render_about_page(config),'/photography/':render_photography(config,photographs)}
    for study in studies: pages[f'/case-studies/{study["slug"]}/']=render_case_detail(config,study,studies)
    for post in posts: pages[f'/blog/{post.slug}/']=render_post_page(config,post,posts)
    spot_by={x['project']:x for x in spotlights}
    for project in projects:
        if project.get('site_path'): pages[project['site_path']]=render_project_detail(config,project,spot_by.get(project['name']))
    for path,content in pages.items(): write_text(OUTPUT_DIR/path.strip('/')/'index.html',content)
    # Rooted homepage link also works when GitHub serves this file for an arbitrarily nested URL.
    not_found=page_intro('That page isn’t here.','The address may have changed. You can find the current work and writing from the homepage.')+link('/404.html',config['site_url']+'/','Back to the homepage','button')
    not_found_html=page_layout(config,'Page not found',not_found,'/404.html')
    # A missing URL can be arbitrarily deep; every non-fragment URL must be rooted.
    not_found_html=re.sub(r'(href|src)="([^"]+)"', lambda m: f'{m[1]}="{m[2] if m[2].startswith("#") else urljoin(config["site_url"]+"/",m[2])}"', not_found_html)
    write_text(OUTPUT_DIR/'404.html',not_found_html)
    write_text(OUTPUT_DIR/'.nojekyll','')
    sitemap='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f'<url><loc>{esc(absolute_url(config,p))}</loc></url>' for p in pages)+'</urlset>'
    write_text(OUTPUT_DIR/'sitemap.xml',sitemap)
    write_text(OUTPUT_DIR/'robots.txt',f'User-agent: *\nAllow: /\nSitemap: {config["site_url"]}/sitemap.xml')
    items=''.join(f'<item><title>{esc(p.title)}</title><link>{esc(absolute_url(config,f"/blog/{p.slug}/"))}</link><guid>{esc(absolute_url(config,f"/blog/{p.slug}/"))}</guid><pubDate>{format_rss_date(p.date)}</pubDate><description>{esc(p.summary)}</description></item>' for p in posts[:20])
    write_text(OUTPUT_DIR/'feed.xml',f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Winston Lin</title><link>{esc(config["site_url"])}/</link><description>{esc(config["meta_description"])}</description>{items}</channel></rss>')
    print(f'Built {len(pages)+1} pages for {config["site_url"]}')


if __name__=='__main__':
    build()
