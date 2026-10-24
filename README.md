# Community Bookmarks

A searchable, community-curated directory of tools, Apple documentation, blogs, podcasts, conferences and user groups for people who manage Apple devices.

It is the website version of The Apple Community Bookmarks, now also including [The Definitive MacAdmins resource directory](https://github.com/maccy10/definitivemacadmins), and works the same way as the [MacAdmins community calendar](https://github.com/macadminsdotorg/macadmins-calendar).

The original `Apple_Community_Bookmarks.html` stays in this repository so existing links keep working. The site's `/bookmarks.html` is the up-to-date version, rebuilt on every change.

## Suggest a resource

Use the [submission form](../../issues/new?template=resource-submission.yml). No git needed. A maintainer reviews it, and once approved it's added automatically. Pull requests are welcome too; see [CONTRIBUTING.md](CONTRIBUTING.md).

## What the site offers

- Search across names, descriptions and domains, with `/` or ⌘K to jump to the search field
- Categories and subcategories, plus filters for GitHub projects and Apple pages
- `/bookmarks.html`: the whole directory as a browser bookmarks file, rebuilt on every change
- `/resources.json`: every resource and category, for scripts and other sites
- Light and dark mode, following the system setting

## How it's built

| Part | Where |
| --- | --- |
| Data, one YAML file per category | `data/resources/` |
| Category names, icons, colours and subcategories | `data/categories.yaml` |
| Page templates (Hugo) | `layouts/` |
| Theme | `assets/css/main.css` |
| Search and filters | `assets/js/app.js` |
| Submit and About pages | `content/` |
| Checks and helper scripts (Python) | `scripts/` |
| Submission form, workflows | `.github/` |

The site is plain [Hugo](https://gohugo.io) with no theme dependency, no Node.js and no build tools beyond the Hugo binary.

### Run it locally

```sh
brew install hugo
hugo server            # http://localhost:1313
```

Before opening a pull request:

```sh
pip3 install pyyaml
python3 scripts/validate.py --fix
```

### Automation

| Workflow | When | What it does |
| --- | --- | --- |
| `validate.yml` | Every pull request | Checks the data and that the site builds |
| `submission.yml` | `approved` label on a submission issue | Adds the resource, fills in missing details and opens a pull request |
| `enrich-test.yml` | Manually | Shows what the automatic fill-in would produce for some URLs, without changing anything |
| `deploy.yml` | Every push to `main` | Builds the site and publishes it to GitHub Pages |
| `linkcheck.yml` | Mondays | Opens or updates one issue listing broken links |
| Dependabot | Monthly | Keeps the GitHub Actions versions current |

### One-time setup

1. Settings > Pages > Source: **GitHub Actions**.
2. Settings > Actions > General > Workflow permissions: allow GitHub Actions to **create and approve pull requests**.
3. Create the labels `resource-submission`, `resource-update`, `approved` and `broken-links` (GitHub skips form labels that don't exist).
4. If the repository moves, update `params.repo` in `hugo.toml`.
5. For a custom domain, add it under Settings > Pages and point a CNAME record at `<owner>.github.io`.

### Automatic fill-in

When a submission is approved, `scripts/enrich.py` fills in fields the submitter left empty. GitHub projects get their About text, topics (as keywords), licence and archived status from the GitHub API. Other sites get their title and own description. On top of that, a summary and keywords are written with [GitHub Models](https://github.blog/ai-and-ml/llms/solving-the-inference-problem-for-open-source-ai-projects-with-github-models/), using the repository's built-in token; there is no API key to manage. Set `MODEL` in `submission.yml` to change the model, or leave it empty to skip the AI step. Everything filled in is listed in the pull request so a maintainer can check it.

Pull requests opened by `submission.yml` use the default token, so GitHub doesn't run `validate.yml` on them. The validation result is written into the pull request description instead. To get the normal checks, use a GitHub App token in `submission.yml`.
