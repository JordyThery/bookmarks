#!/usr/bin/env python3
"""Fill in missing details for a resource: description, keywords, platforms, cost.

Sources, in order:
  1. GitHub API, for github.com repositories: About text, topics, licence, archived.
  2. The page itself: title, the site's own description, readable text.
  3. Optionally an AI summary through GitHub Models (needs `models: read` and GITHUB_TOKEN).

Only empty fields are filled; anything a submitter or maintainer wrote is kept.

    # Fill one entry in a data file (used by .github/workflows/submission.yml)
    python scripts/enrich.py --file data/resources/tools.yaml --url https://github.com/org/tool

    # Try it on some URLs without changing anything (used by enrich-test.yml)
    python scripts/enrich.py --dry-run https://example.com https://github.com/org/tool

Environment: GITHUB_TOKEN (GitHub API and GitHub Models), MODEL (GitHub Models model id,
for example openai/gpt-4o; leave empty to skip the AI step).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from resources_io import dump_resources, load_yaml, normalize_url
from validate import COSTS, DESCRIPTION_MAX, KEYWORDS_MAX, PLATFORMS, WORKS_WITH

MODELS_URL = "https://models.github.ai/inference/chat/completions"
USER_AGENT = "CommunityBookmarks/1.0 (+https://github.com/cbookmarks/bookmarks)"
TEXT_LIMIT = 6000
GENERIC = {"mac", "macos", "apple", "macadmin", "macadmins", "mac admin", "mac admins", "tool", "tools",
           "website", "admin", "sysadmin", "it", "osx", "macosx", "swift", "bash", "zsh", "python", "shell"}
OPEN_LICENCES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "GPL-2.0", "GPL-3.0", "LGPL-2.1",
                 "LGPL-3.0", "MPL-2.0", "ISC", "Unlicense", "AGPL-3.0", "0BSD", "CC0-1.0", "EPL-2.0"}

STYLE = f"""You write entries for Community Bookmarks, a directory for people who manage Apple devices (Mac admins).
Return only a JSON object with these keys:
- "description": one sentence, at most {DESCRIPTION_MAX} characters, saying concretely what it is or does.
  Start with a verb or noun phrase, never "This site". No marketing words (best, powerful, seamless), no dates,
  version numbers, "latest" or "next event". Only claims supported by the material given.
- "keywords": 3 to 6 lowercase search terms an admin would type, especially ones not in the name:
  acronyms (abm, ade, ddm, apns, mdm), related products (installomator, jamf pro), the problem it solves.
  No generic words like mac, apple, tool, website, admin.
- "platforms": subset of {sorted(PLATFORMS)}, only if clear; otherwise [].
- "works_with": subset of {sorted(WORKS_WITH)}, only if the material says it's built for that tool; otherwise [].
- "cost": one of {sorted(COSTS)} only if clear for software; otherwise "". Empty for docs, blogs, podcasts, communities.
Example: {{"description": "Scans a Mac for installed apps, matches them to Installomator labels and updates the outdated ones.",
"keywords": ["installomator", "patching", "app updates", "swiftdialog"], "platforms": ["macOS"], "works_with": [], "cost": "open-source"}}"""


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.meta, self.parts, self._skip, self._in_title = "", {}, [], 0, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "svg", "nav", "footer"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key in ("description", "og:description", "og:title", "twitter:description") and a.get("content"):
                self.meta[key] = a["content"].strip()

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "nav", "footer") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip and data.strip():
            self.parts.append(data.strip())


def http(url: str, headers: dict | None = None, data: bytes | None = None, timeout: int = 25) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(2_000_000)
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return 0, b""


def github_info(url: str, token: str | None) -> dict | None:
    m = re.match(r"https?://(?:www\.)?github\.com/([^/]+)/([^/#?]+)", url)
    if not m or m.group(1) in ("orgs", "apps", "sponsors"):
        return None
    owner, repo = m.group(1), m.group(2).removesuffix(".git")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    status, body = http(f"https://api.github.com/repos/{owner}/{repo}", headers)
    if status != 200:
        return None
    info = json.loads(body)
    readme_status, readme = http(f"https://api.github.com/repos/{owner}/{repo}/readme",
                                 {**headers, "Accept": "application/vnd.github.raw+json"})
    return {
        "about": (info.get("description") or "").strip(),
        "topics": info.get("topics") or [],
        "licence": (info.get("license") or {}).get("spdx_id"),
        "archived": bool(info.get("archived")),
        "text": readme.decode("utf-8", "replace")[:TEXT_LIMIT] if readme_status == 200 else "",
    }


def page_info(url: str) -> dict:
    status, body = http(url, {"Accept": "text/html,application/xhtml+xml"})
    if status != 200 or not body:
        return {"status": status}
    p = _Text()
    try:
        p.feed(body.decode("utf-8", "replace"))
    except Exception:
        pass
    return {
        "status": status,
        "title": " ".join(p.title.split()),
        "site_description": p.meta.get("description") or p.meta.get("og:description") or p.meta.get("twitter:description", ""),
        "text": " ".join(" ".join(p.parts).split())[:TEXT_LIMIT],
    }


def ai_summary(entry: dict, material: dict, token: str, model: str) -> dict | None:
    body = json.dumps({
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": STYLE},
            {"role": "user", "content": json.dumps({"name": entry.get("name"), "url": entry["url"],
                                                    "category": entry.get("category"), **material})},
        ],
    }).encode()
    status, resp = http(MODELS_URL, {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                     "Accept": "application/json"}, data=body, timeout=60)
    if status != 200:
        print(f"  GitHub Models answered HTTP {status}", file=sys.stderr)
        return None
    try:
        text = json.loads(resp)["choices"][0]["message"]["content"]
        return json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    except Exception:
        return None


def clean(result: dict) -> dict:
    """Keep only values that pass the same rules as validate.py."""
    out = {}
    desc = " ".join(str(result.get("description") or "").split())
    if 0 < len(desc) <= DESCRIPTION_MAX:
        out["description"] = desc
    kws = [str(k).strip().lower() for k in result.get("keywords") or [] if str(k).strip()]
    kws = [k for k in dict.fromkeys(kws) if len(k) <= 40 and k not in GENERIC][:min(6, KEYWORDS_MAX)]
    if kws:
        out["keywords"] = kws
    for key, allowed in (("platforms", PLATFORMS), ("works_with", WORKS_WITH)):
        vals = [v for v in result.get(key) or [] if v in allowed]
        if vals:
            out[key] = vals
    if result.get("cost") in COSTS:
        out["cost"] = result["cost"]
    return out


def enrich(entry: dict, token: str | None, model: str | None) -> tuple[dict, list[str]]:
    """Return (fields to fill, report lines). Never overwrites fields that already have a value."""
    found: dict = {}
    report: list[str] = []
    gh = github_info(entry["url"], token)
    if gh:
        if gh["about"] and len(gh["about"]) <= DESCRIPTION_MAX:
            found["description"] = gh["about"]
        topics = [t.replace("-", " ") for t in gh["topics"]][:6]
        if topics:
            found["keywords"] = topics
        if gh["licence"] in OPEN_LICENCES:
            found["cost"] = "open-source"
        if gh["archived"]:
            found["archived"] = True
            report.append("the GitHub repository is archived")
        material = {"github_about": gh["about"], "github_topics": gh["topics"], "readme": gh["text"]}
        source = "GitHub"
    else:
        page = page_info(entry["url"])
        if page["status"] != 200:
            report.append(f"page could not be read (HTTP {page['status'] or 'error'})")
            material = {}
        else:
            material = {k: page[k] for k in ("title", "site_description", "text")}
        source = "the page"

    if model and token and material:
        ai = ai_summary(entry, material, token, model)
        if ai:
            ai = clean(ai)
            # The AI summary wins over GitHub's About text; GitHub topics are kept as keywords when present.
            if "keywords" in found and "keywords" in ai:
                ai["keywords"] = list(dict.fromkeys(found["keywords"] + ai["keywords"]))[:6]
            found.update(ai)
            source += f" + {model}"
        else:
            report.append("AI summary failed; used basic details only")
    if not found.get("description") and material.get("site_description"):
        desc = " ".join(material["site_description"].split())
        if len(desc) <= DESCRIPTION_MAX:
            found["description"] = desc

    fill = {k: v for k, v in clean(found).items() if not entry.get(k)}
    if found.get("archived") and not entry.get("archived"):
        fill["archived"] = True
    if fill:
        report.insert(0, f"filled {', '.join(fill)} from {source}")
    else:
        report.insert(0, "nothing to fill")
    return fill, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", type=Path, help="data file that contains the entry")
    ap.add_argument("--url", help="url of the entry to fill in")
    ap.add_argument("--dry-run", nargs="+", metavar="URL", help="show what would be filled for these URLs")
    args = ap.parse_args()
    token, model = os.environ.get("GITHUB_TOKEN"), os.environ.get("MODEL") or None
    summary = os.environ.get("GITHUB_STEP_SUMMARY")

    if args.dry_run:
        lines = [f"## Enrichment test ({model or 'no AI'})", ""]
        for url in args.dry_run:
            fill, report = enrich({"url": url, "name": ""}, token, model)
            lines += [f"### {url}", "", "```yaml", dump_resources([{"name": "(name)", "url": url, **fill}]).strip(),
                      "```", "", *[f"- {r}" for r in report], ""]
        out = "\n".join(lines)
        print(out)
        if summary:
            Path(summary).write_text(out, encoding="utf-8")
        return 0

    if not (args.file and args.url):
        ap.error("use --file and --url, or --dry-run")
    entries = load_yaml(args.file) or []
    target = next((e for e in entries if normalize_url(e["url"]) == normalize_url(args.url)), None)
    if not target:
        print(f"No entry with url {args.url} in {args.file}", file=sys.stderr)
        return 1
    fill, report = enrich(target, token, model)
    target.update(fill)
    args.file.write_text(dump_resources(entries), encoding="utf-8")
    print("\n".join(f"- {r}" for r in report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
