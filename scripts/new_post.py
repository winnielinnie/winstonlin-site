import argparse
import re
from datetime import date
from pathlib import Path


def slugify(value):
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def main():
    parser = argparse.ArgumentParser(description="Create a new dated blog post.")
    parser.add_argument("title")
    args = parser.parse_args()

    today = date.today().isoformat()
    slug = slugify(args.title)
    post_path = Path(__file__).resolve().parents[1] / "content" / "posts" / f"{today}-{slug}.md"

    template = f"""---
title: {args.title}
date: {today}
slug: {slug}
summary: Add summary here.
---

Start writing.
"""

    post_path.write_text(template)
    print(post_path)


if __name__ == "__main__":
    main()
