import os
import json
import time
import requests

DEFAULT_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
GH_TOKEN = os.getenv("GH_TOKEN")

REPOS_FILE = "repos.json"
STATE_FILE = "state.json"

headers = {"Accept": "application/vnd.github.v3+json"}
if GH_TOKEN:
    headers["Authorization"] = f"Bearer {GH_TOKEN}"

GLOBAL_IGNORED_KEYWORDS = [
    "merge branch",
    "merge pull request"
]

def format_size(bytes_size):
    if not bytes_size:
        return "0 B"
    size = float(bytes_size)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

def is_bot(user_obj, fallback_name=""):
    if user_obj and user_obj.get("type") == "Bot":
        return True
    
    login = (user_obj.get("login") if user_obj else "") or ""
    if "[bot]" in login.lower() or "[bot]" in fallback_name.lower():
        return True

    known_bots = ["dependabot", "renovate", "github-actions", "snyk-bot", "greenkeeper"]
    if any(bot in login.lower() or bot in fallback_name.lower() for bot in known_bots):
        return True

    return False

def has_ignored_keyword(text, custom_keywords=None):
    if not text:
        return False
    
    first_line = text.strip().split("\n")[0].lower()
    active_keywords = set(k.lower() for k in GLOBAL_IGNORED_KEYWORDS)
    if custom_keywords:
        active_keywords.update(k.lower() for k in custom_keywords)

    return any(keyword in first_line for keyword in active_keywords)

def format_mentions(mention_data):
    if not mention_data:
        return None
    
    if isinstance(mention_data, (str, int)):
        mention_data = [mention_data]

    formatted_list = []
    for item in mention_data:
        m_str = str(item).strip()
        if not m_str:
            continue
        if m_str.isdigit():
            formatted_list.append(f"<@&{m_str}>")
        else:
            formatted_list.append(m_str)

    return " ".join(formatted_list) if formatted_list else None

def get_target_webhook(item):
    secret_name = item.get("webhook_secret")
    base_url = None

    if secret_name and os.getenv(secret_name):
        base_url = os.getenv(secret_name)
    else:
        base_url = DEFAULT_WEBHOOK_URL

    if not base_url:
        return None

    thread_id = item.get("thread_id")
    if thread_id:
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}thread_id={str(thread_id).strip()}"

    return base_url

def send_discord(webhook_url, title, url, description, color, fields, repo_name, branch=None, content=None, components=None):
    if not webhook_url:
        print(f"[{repo_name}] Webhook tidak valid atau belum diatur di Secrets.")
        return

    footer_text = f"Repository: {repo_name}"
    if branch:
        footer_text += f" | Branch: {branch}"

    payload = {
        "username": "GitHub Sentinel",
        "embeds": [{
            "title": title,
            "url": url,
            "description": description[:1000] if description else "Tidak ada deskripsi rilis/commit.",
            "color": color,
            "fields": fields,
            "footer": {"text": footer_text}
        }]
    }

    if content:
        payload["content"] = content

    if components:
        payload["components"] = components

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code not in (200, 204):
            print(f"[{repo_name}] Discord API error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[{repo_name}] Gagal mengirim webhook Discord: {e}")

def load_json(filepath, default_value):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return default_value
    return default_value

def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def check_commits(repo, branch, state, webhook_url, ignored_keywords=None):
    params = {"per_page": 1}
    if branch:
        params["sha"] = branch

    url = f"https://api.github.com/repos/{repo}/commits"
    res = requests.get(url, headers=headers, params=params, timeout=10)
    if res.status_code != 200 or not res.json():
        return

    commit = res.json()[0]
    sha = commit["sha"]

    if state.get("last_commit") is None:
        state["last_commit"] = sha
        return

    if sha != state["last_commit"]:
        author_user = commit.get("author")
        author_name = commit["commit"]["author"]["name"]
        commit_msg = commit["commit"]["message"]

        if is_bot(author_user, fallback_name=author_name):
            print(f"[{repo}] Mengabaikan commit bot: {author_name}")
        elif has_ignored_keyword(commit_msg, ignored_keywords):
            print(f"[{repo}] Mengabaikan commit terfilter kata kunci: {commit_msg.splitlines()[0]}")
        else:
            branch_label = f"[{branch}] " if branch else ""
            send_discord(
                webhook_url=webhook_url,
                title=f"🔨 Commit Baru di {repo} {branch_label}",
                url=commit["html_url"],
                description=commit_msg,
                color=0x5865F2,
                fields=[
                    {"name": "Author", "value": author_name, "inline": True},
                    {"name": "Branch", "value": f"`{branch or 'default'}`", "inline": True},
                    {"name": "Hash", "value": f"`{sha[:7]}`", "inline": True}
                ],
                repo_name=repo,
                branch=branch
            )
        state["last_commit"] = sha

def check_releases(repo, state, webhook_url, mention_data=None, ignore_prerelease=False, mention_on_prerelease=False, allowed_extensions=None):
    url = f"https://api.github.com/repos/{repo}/releases?per_page=1"
    res = requests.get(url, headers=headers, timeout=10)
    if res.status_code != 200 or not res.json():
        return

    release = res.json()[0]
    rel_id = release["id"]

    if state.get("last_release_id") is None:
        state["last_release_id"] = rel_id
        return

    if rel_id != state["last_release_id"]:
        publisher = release.get("author")
        publisher_name = publisher["login"] if publisher else "Unknown"
        is_prerelease = release.get("prerelease", False)

        if is_bot(publisher, fallback_name=publisher_name):
            print(f"[{repo}] Mengabaikan release dari bot: {publisher_name}")
        elif is_prerelease and ignore_prerelease:
            print(f"[{repo}] Mengabaikan pre-release: {release.get('tag_name')}")
        else:
            tag_name = release.get("tag_name", "Release")
            name = release.get("name") or tag_name

            if is_prerelease:
                embed_title = f"🧪 Pre-Release Baru: {name}"
                embed_color = 0xFEE75C
                status_label = "⚠️ PRE-RELEASE"
            else:
                embed_title = f"🚀 Release Stabil Baru: {name}"
                embed_color = 0x57F287
                status_label = "✅ STABLE RELEASE"

            parsed_mentions = format_mentions(mention_data)
            mention_content = None
            should_mention = parsed_mentions and (not is_prerelease or mention_on_prerelease)
            if should_mention:
                mention_content = f"📢 {parsed_mentions} Versi baru telah dirilis untuk **{repo}**!"

            fields = [
                {"name": "Tag / Versi", "value": f"`{tag_name}`", "inline": True},
                {"name": "Tipe Rilis", "value": status_label, "inline": True},
                {"name": "Publisher", "value": publisher_name, "inline": True}
            ]

            assets = release.get("assets", [])
            if allowed_extensions:
                valid_exts = tuple(
                    ext.lower() if ext.startswith(".") else f".{ext.lower()}"
                    for ext in allowed_extensions
                )
                filtered_assets = [
                    a for a in assets 
                    if a.get("name", "").lower().endswith(valid_exts)
                ]
            else:
                filtered_assets = assets

            buttons = []
            for asset in filtered_assets[:4]:
                file_name = asset.get("name")
                download_url = asset.get("browser_download_url")
                file_size = format_size(asset.get("size", 0))

                short_name = (file_name[:22] + "...") if len(file_name) > 25 else file_name
                label = f"{short_name} ({file_size})"

                buttons.append({
                    "type": 2,
                    "style": 5,
                    "label": label[:80],
                    "url": download_url,
                    "emoji": {"name": "📦"}
                })

            buttons.append({
                "type": 2,
                "style": 5,
                "label": "View Changelog",
                "url": release["html_url"],
                "emoji": {"name": "📜"}
            })

            components = [{"type": 1, "components": buttons}]

            send_discord(
                webhook_url=webhook_url,
                title=embed_title,
                url=release["html_url"],
                description=release.get("body", ""),
                color=embed_color,
                fields=fields,
                repo_name=repo,
                content=mention_content,
                components=components
            )

        state["last_release_id"] = rel_id

def check_pull_requests(repo, branch, state, webhook_url, ignored_keywords=None):
    params = {"state": "all", "sort": "created", "direction": "desc", "per_page": 1}
    if branch:
        params["base"] = branch

    url = f"https://api.github.com/repos/{repo}/pulls"
    res = requests.get(url, headers=headers, params=params, timeout=10)
    if res.status_code != 200 or not res.json():
        return

    pr = res.json()[0]
    pr_number = pr["number"]

    if state.get("last_pr_number") is None:
        state["last_pr_number"] = pr_number
        return

    if pr_number != state["last_pr_number"]:
        pr_user = pr.get("user")
        creator_name = pr_user["login"] if pr_user else "Unknown"
        pr_title = pr.get("title", "")

        if is_bot(pr_user, fallback_name=creator_name):
            print(f"[{repo}] Mengabaikan PR bot: {creator_name}")
        elif has_ignored_keyword(pr_title, ignored_keywords):
            print(f"[{repo}] Mengabaikan PR terfilter: {pr_title}")
        else:
            send_discord(
                webhook_url=webhook_url,
                title=f"🔀 PR Baru: #{pr_number} - {pr_title}",
                url=pr["html_url"],
                description=pr.get("body", ""),
                color=0xEB459E,
                fields=[
                    {"name": "Pembuat", "value": creator_name, "inline": True},
                    {"name": "Target Branch", "value": f"`{pr['base']['ref']}`", "inline": True},
                    {"name": "Status", "value": pr["state"].upper(), "inline": True}
                ],
                repo_name=repo,
                branch=branch
            )
        state["last_pr_number"] = pr_number

def main():
    target_items = load_json(REPOS_FILE, [])
    if not target_items:
        print("File repos.json kosong atau tidak ditemukan.")
        return

    all_states = load_json(STATE_FILE, {})

    for item in target_items:
        if isinstance(item, str):
            repo = item
            branch = None
            ignored_keywords = []
            target_webhook = DEFAULT_WEBHOOK_URL
            release_mention = None
            ignore_prerelease = False
            mention_on_prerelease = False
            asset_extensions = None
        else:
            repo = item.get("repo")
            branch = item.get("branch")
            ignored_keywords = item.get("ignored_keywords", [])
            target_webhook = get_target_webhook(item)
            release_mention = item.get("release_mention")
            ignore_prerelease = item.get("ignore_prerelease", False)
            mention_on_prerelease = item.get("mention_on_prerelease", False)
            asset_extensions = item.get("asset_extensions")

        if not repo:
            continue

        state_key = f"{repo}#{branch}" if branch else repo
        print(f"Memeriksa {state_key}...")

        if state_key not in all_states:
            all_states[state_key] = {
                "last_commit": None,
                "last_release_id": None,
                "last_pr_number": None
            }

        target_state = all_states[state_key]

        try:
            check_commits(repo, branch, target_state, webhook_url=target_webhook, ignored_keywords=ignored_keywords)
            check_releases(
                repo=repo,
                state=target_state,
                webhook_url=target_webhook,
                mention_data=release_mention,
                ignore_prerelease=ignore_prerelease,
                mention_on_prerelease=mention_on_prerelease,
                allowed_extensions=asset_extensions
            )
            check_pull_requests(repo, branch, target_state, webhook_url=target_webhook, ignored_keywords=ignored_keywords)
        except Exception as err:
            print(f"Error pada {state_key}: {err}")

        time.sleep(1)

    save_json(STATE_FILE, all_states)
    print("Selesai memperbarui status.")

if __name__ == "__main__":
    main()
