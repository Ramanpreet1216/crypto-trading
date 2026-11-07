import os
import sys
import base64
import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "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")
REPO_OWNER = "Ramanpreet1216"
REPO_NAME = "crypto-trading"
BRANCH = "main"

BASE_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

IGNORE_FILES = {
    ".env",
    "sync_github.py",
}

IGNORE_DIRS = {
    ".git",
    "__pycache__",
    ".idea",
    ".vscode",
    ".agents",
    ".gemini"
}

def sync():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"[*] Starting GitHub sync from {root_dir} to {REPO_OWNER}/{REPO_NAME}:{BRANCH}...")

    # 1. Get latest commit SHA on main
    ref_res = requests.get(f"{BASE_URL}/git/ref/heads/{BRANCH}", headers=HEADERS)
    if ref_res.status_code != 200:
        print(f"[!] Failed to get branch ref: {ref_res.status_code} {ref_res.text}")
        return False
    latest_commit_sha = ref_res.json()["object"]["sha"]
    print(f"[*] Current commit SHA: {latest_commit_sha}")

    # 2. Get tree SHA of the latest commit
    commit_res = requests.get(f"{BASE_URL}/git/commits/{latest_commit_sha}", headers=HEADERS)
    if commit_res.status_code != 200:
        print(f"[!] Failed to get commit: {commit_res.status_code} {commit_res.text}")
        return False
    base_tree_sha = commit_res.json()["tree"]["sha"]

    # 3. Create blobs for all eligible files
    tree_items = []
    total_files = 0

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Exclude ignored directories
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]

        for filename in filenames:
            if filename in IGNORE_FILES:
                continue
            if filename.endswith(".pyc"):
                continue

            filepath = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(filepath, root_dir).replace("\\", "/")

            try:
                with open(filepath, "rb") as f:
                    content_bytes = f.read()

                # Upload blob
                blob_payload = {
                    "content": base64.b64encode(content_bytes).decode("utf-8"),
                    "encoding": "base64"
                }
                blob_res = requests.post(f"{BASE_URL}/git/blobs", headers=HEADERS, json=blob_payload)
                if blob_res.status_code != 201:
                    print(f"[!] Failed to upload blob for {rel_path}: {blob_res.text}")
                    continue

                blob_sha = blob_res.json()["sha"]
                tree_items.append({
                    "path": rel_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha
                })
                total_files += 1
                print(f"  [+] Synced: {rel_path}")
            except Exception as e:
                print(f"[!] Error processing {rel_path}: {e}")

    print(f"[*] Uploaded {total_files} blobs. Creating new tree...")

    # 4. Create new tree
    tree_payload = {
        "base_tree": base_tree_sha,
        "tree": tree_items
    }
    tree_res = requests.post(f"{BASE_URL}/git/trees", headers=HEADERS, json=tree_payload)
    if tree_res.status_code != 201:
        print(f"[!] Failed to create tree: {tree_res.status_code} {tree_res.text}")
        return False
    new_tree_sha = tree_res.json()["sha"]

    # 5. Create new commit
    commit_payload = {
        "message": "Implement Turtle System 2 with 1:2 R:R, 2-slot cap, cleared paper history, DRY_RUN paper-only mode",
        "tree": new_tree_sha,
        "parents": [latest_commit_sha]
    }
    new_commit_res = requests.post(f"{BASE_URL}/git/commits", headers=HEADERS, json=commit_payload)
    if new_commit_res.status_code != 201:
        print(f"[!] Failed to create commit: {new_commit_res.status_code} {new_commit_res.text}")
        return False
    new_commit_sha = new_commit_res.json()["sha"]
    print(f"[*] Created commit: {new_commit_sha}")

    # 6. Update branch ref
    update_ref_res = requests.patch(
        f"{BASE_URL}/git/refs/heads/{BRANCH}",
        headers=HEADERS,
        json={"sha": new_commit_sha, "force": True}
    )
    if update_ref_res.status_code != 200:
        print(f"[!] Failed to update ref: {update_ref_res.status_code} {update_ref_res.text}")
        return False

    print(f"[SUCCESS] Branch '{BRANCH}' updated to {new_commit_sha}! Render will now auto-deploy!")
    return True

if __name__ == "__main__":
    sync()
