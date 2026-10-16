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
ASSET_VERSION = '20261016-editorial'
ARROW = '<svg class="arrow" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 19 19 5M5 5h14v14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
DOWN = '<svg class="arrow" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 4v16m-6-6 6 6 6-6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
NEXT = '<svg class="flow-arrow" viewBox="0 0 64 20" fill="none" aria-hidden="true"><path d="M1 10h60m-7-7 7 7-7 7" stroke="currentColor" stroke-width="1.2"/></svg>'


def esc(value):
    return html.escape(str(value), quote=True)


def href(current, target):
    if target.startswith(('https://', 'http://', 'mailto:', '#')):
        return target
    return relative_url(current, target)


def link(current, target, label, css='text-link', arrow=True):
    return f'<a class="{esc(css)}" href="{esc(href(current, target))}">{esc(label)}{ARROW if arrow else ""}</a>'


def paragraphs(items):
    return ''.join(f'<p>{esc(item)}</p>' for item in items)


def flow_diagram(items):
    return '<div class="workflow" aria-label="' + esc(' then '.join(items)) + '">' + NEXT.join(f'<span>{esc(item)}</span>' for item in items) + '</div>'


def page_layout(config, title, body, current_path='/', meta_description=None, og_type='website'):
    page_title = f'{title} | Winston Lin' if title != config['name'] else 'Winston Lin — Product leader'
    description = meta_description or config['meta_description']
    canonical = absolute_url(config,current_path)
    nav=[]
    for label,path in [('Work','/case-studies/'),('Writing','/blog/'),('About','/about/')]:
        active = current_path.startswith(path) or (label=='Work' and current_path.startswith('/projects/'))
        current_attr = ' aria-current="page"' if active else ''
        nav.append(f'<a href="{href(current_path,path)}"{current_attr}>{label}</a>')
    structured=json.dumps({'@context':'https://schema.org','@type':'Person','name':'Winston Lin','url':config['site_url']+'/', 'jobTitle':'Principal Product Manager','worksFor':{'@type':'Organization','name':'Oracle'},'sameAs':[config['linkedin_url'],config['github_url']]},ensure_ascii=False).replace('<','\\u003c')
    return f'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(page_title)}</title><meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}"><link rel="icon" href="{static_url(current_path,'favicon.svg')}" type="image/svg+xml">
<meta property="og:title" content="{esc(page_title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:type" content="{og_type}"><meta property="og:url" content="{esc(canonical)}"><meta property="og:image" content="{config['site_url']}/winston-headshot.jpg"><meta name="twitter:card" content="summary">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;550;600;650;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{static_url(current_path,'styles.css')}?v={ASSET_VERSION}">
<link rel="alternate" type="application/rss+xml" title="Winston Lin — Writing" href="{static_url(current_path,'feed.xml')}">
<script type="application/ld+json">{structured}</script>
</head><body>
<a class="skip-link" href="#main">Skip to content</a>
<div class="site-shell">
<header class="site-header"><a class="wordmark" href="{href(current_path,'/')}">Winston Lin<span>.</span></a><nav aria-label="Main navigation">{''.join(nav)}{link(current_path,'#contact','Get in touch','contact-link')}</nav></header>
<main id="main">{body}</main>
<footer id="contact" class="site-footer"><div><p class="footer-invitation">Have a problem worth working on?</p>{link(current_path,'mailto:'+config['email'],config['email'],'email-link')}</div><div class="footer-right"><div class="social-links">{link(current_path,config['linkedin_url'],'LinkedIn')}{link(current_path,config['github_url'],'GitHub')}</div><small>© {datetime.now().year} Winston Lin</small></div></footer>
</div></body></html>'''


def section_heading(title, current='/', target=None, label=None):
    return f'<div class="section-heading"><h2>{esc(title)}</h2>{link(current,target,label) if target else ""}</div>'


def work_row(study, number, current='/', featured=False):
    target=f'/case-studies/{study["slug"]}/'
    flow=flow_diagram(study['flow']) if study.get('flow') else ''
    return f'''<article class="work-row{' featured' if featured else ''}" id="{esc(study['slug'])}">
<span class="work-number">{number:02}</span><div class="work-title"><p class="meta">{esc(study['period'])}</p><h3>{link(current,target,study['title'],'title-link',False)}</h3>{link(current,target,'Read the story')}</div>
<div class="work-description"><p>{esc(study.get('home_summary',study['tagline']))}</p>{flow}<p class="work-focus">{esc(study.get('focus',study.get('role','Product judgment · Customer workflows')))}</p></div></article>'''


def collection_row(current,title,meta,target):
    return f'<a class="collection-row" href="{esc(href(current,target))}"><span><span class="collection-title">{esc(title)}</span><span class="collection-meta">{esc(meta)}</span></span>{ARROW}</a>'


def render_homepage(config,posts,studies,external):
    body=f'''<section class="hero" aria-labelledby="hero-title"><div class="hero-copy"><h1 id="hero-title">Making complex products<br class="desktop-break"> easier to use.</h1><p>{esc(config['tagline'])}</p><div class="hero-actions"><a href="#selected-work" class="button">Explore my work{DOWN}</a>{link('/','/about/','More about me')}</div></div><figure class="portrait"><img src="winston-headshot.jpg" alt="Winston Lin" width="350" height="432" fetchpriority="high"><figcaption>San Francisco, CA</figcaption></figure></section>
<div class="experience-strip"><p><span>Currently</span>Principal Product Manager, Oracle</p><p><span>Previously</span>Sitetracker · Cisco</p></div>
<section class="home-work" id="selected-work">{section_heading('Selected work','/','/case-studies/','View all work')}{''.join(work_row(x,i+1,featured=True) for i,x in enumerate(studies[:3]))}</section>
<section class="home-writing">{section_heading('Writing & small builds','/','/blog/','Browse the collection')}
{collection_row('/','Trustworthy AI needs a recovery path','Essay · AI & product','/blog/trustworthy-ai-products-need-recovery-paths/')}
{collection_row('/','Long-running Functions and Response Destinations','Oracle publication · Serverless','https://blogs.oracle.com/cloud-infrastructure/longrunning-functions-and-response-destinations')}
{collection_row('/','One-page canvas','Open-source project · Planning','/projects/one-page-canvas/')}
</section><section class="home-about"><h2>A little about me</h2><div><p class="about-statement">I like finding the useful path through a complicated problem.</p><p>My work spans cloud products, enterprise software, and practical advice for growing businesses. I’m based in San Francisco.</p>{link('/','/about/','More about me')}</div></section>'''
    return page_layout(config,config['name'],body)


def page_intro(title,summary):
    return f'<header class="page-intro"><h1>{esc(title)}</h1><p>{esc(summary)}</p></header>'


def render_work_index(config,studies):
    current='/case-studies/'
    # Old group fragments remain valid, along with every original story slug.
    aliases=''.join(f'<span id="{s}" class="fragment-alias"></span>' for s in ['case-jumps','advisory','oci-functions','oke-oci-kubernetes-engine','oci-dev-platform','sitetracker'])
    body=page_intro('Selected work.','Product decisions, the constraints behind them, and what happened next.')
    body+=aliases+'<section class="work-list" aria-label="Case studies">'+''.join(work_row(s,i+1,current) for i,s in enumerate(studies))+'</section>'
    body+=f'<div class="section-end">{link(current,"/projects/","Explore my small builds")}</div>'
    return page_layout(config,'Work',body,current)


def render_case_detail(config,study,studies):
    current=f'/case-studies/{study["slug"]}/'
    sources=''
    if study.get('sources'):
        sources='<section class="case-sources"><h2>See the work</h2>'+''.join(link(current,s['url'],s['label']) for s in study['sources'])+'</section>'
    body=f'''<div class="back-link">{link(current,'/case-studies/','All work',arrow=False)}</div>
<article class="reading-page case-page"><header class="reading-header"><h1>{esc(study['title'])}</h1><p class="reading-deck">{esc(study['tagline'])}</p><div class="article-meta"><span>{esc(study['period'])}</span><span>{esc(study.get('role','Product contribution'))}</span></div></header>
{flow_diagram(study['flow']) if study.get('flow') else ''}
<div class="prose"><section><h2>The problem</h2><p>{esc(study['problem'])}</p></section><section><h2>My contribution</h2>{paragraphs(study['what_i_did'])}</section><section><h2>The decisions</h2>{paragraphs(study['why_it_was_hard'])}</section><section><h2>Where it landed</h2>{paragraphs(study['outcome'])}</section>{sources}</div></article>'''
    others=[s for s in studies[:3] if s['slug']!=study['slug']]
    body+='<section class="read-next">'+section_heading('More work')+''.join(collection_row(current,s['title'],s['period'],f'/case-studies/{s["slug"]}/') for s in others[:2])+'</section>'
    return page_layout(config,study['title'],body,current,study['tagline'],'article')


def render_blog_index(config,posts,external):
    current='/blog/'
    chosen=['trustworthy-ai-products-need-recovery-paths','support-boundaries-are-product-strategy','how-i-use-ai-as-a-pm-with-a-real-workspace','what-building-internal-platforms-taught-me']
    selected=[p for slug in chosen for p in posts if p.slug==slug]
    body=page_intro('Notes from the work.','Writing on product decisions, developer experience, and the practical side of AI.')
    body+='<section class="collection-section">'+section_heading('Published at Oracle')+''.join(collection_row(current,x['title'],f'{x["publication"]} · {x["date"]}',x['url']) for x in external)+'</section>'
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
    body=page_intro('Small tools, real uses.','Open-source experiments in planning, developer workflows, and serverless patterns.')
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
    body=page_intro('A little about me.','Product leader, builder, and a curious person outside the day job.')
    body+=f'<div class="about-layout"><div class="prose"><section>{paragraphs(about["intro"])}</section><section><h2>Outside the day job</h2>{paragraphs(about["advisory"])}</section><section><h2>Where I come from</h2>{paragraphs(about["background"])}</section><section><h2>Away from the desk</h2>{paragraphs(about["personal"])}</section></div><figure class="about-portrait"><img src="{static_url(current,"winston-trail-clean.png")}" alt="Winston on a mountain trail" width="400" height="533" loading="lazy"><figcaption>Outside, whenever I can.</figcaption></figure></div>'
    body+='<section class="experience-list">'+section_heading('The path so far')
    for dates,company,role in [('2022–Present','Oracle Cloud Infrastructure','Principal Product Manager, OCI Functions; earlier work in developer platforms and Kubernetes.'),('2021–2022','Sitetracker','Enterprise software implementations and customer workflows.'),('2019–2021','Cisco','Engineering program management for enterprise networking.')]:
        body+=f'<div class="experience-row"><span>{dates}</span><div><h3>{company}</h3><p>{role}</p></div></div>'
    body+='</section>'
    return page_layout(config,'About',body,current)


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
    posts=load_posts()
    if OUTPUT_DIR.exists(): shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir()
    # Only copy declared public assets, never arbitrary untracked files.
    assets=['styles.css','favicon.svg','winston-headshot.jpg','winston-trail-clean.png','winston-trail.png']
    for asset in assets: shutil.copy2(STATIC_DIR/asset,OUTPUT_DIR/asset)
    if (STATIC_DIR/'diagrams').exists(): shutil.copytree(STATIC_DIR/'diagrams',OUTPUT_DIR/'diagrams')
    pages={'/':render_homepage(config,posts,studies,external),'/case-studies/':render_work_index(config,studies),'/blog/':render_blog_index(config,posts,external),'/projects/':render_projects_page(config,projects,tracks),'/about/':render_about_page(config)}
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
