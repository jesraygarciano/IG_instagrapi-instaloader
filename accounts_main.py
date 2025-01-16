#!/usr/bin/env python3
"""
accounts_main.py

- Reads "item_accounts_rows.csv" from data/target_usernames to get IG usernames.
- For each username, randomly pick Instagrapi or Instaloader:
  - Fetch user info: name (full_name), bio, avatar (profile pic), #followers, #followings
  - Fetch up to N posts: caption, date, views (if available), likes, comments
- After each user's data is scraped, the script immediately saves partial results to data/results/instagram_users.json
  => So if the script stops, you'll still have the data for previously-scraped users.
- Maintains 2FA login for both libraries, storing sessions to avoid repeated logins.
- Fix: Convert any non-serializable fields (like 'HttpUrl') to string.
- Fix #2: Use `.replace(...)` on Windows to overwrite the file.
"""

import os
import sys
import time
import random
import csv
import json
import uuid  # for a unique temp file name
from pathlib import Path
from typing import Optional, List, Dict

from dotenv import load_dotenv

# Instagrapi
from instagrapi import Client as IGClient
from instagrapi.exceptions import LoginRequired, TwoFactorRequired

# Instaloader
import instaloader
from instaloader import Instaloader, Profile, Post
from instaloader.exceptions import TwoFactorAuthRequiredException

############################
# 1) Environment / Config
############################
load_dotenv()

IG_USERNAME = os.getenv("IG_USERNAME", "")
IG_PASSWORD = os.getenv("IG_PASSWORD", "")

PROXIES_RAW = os.getenv("PROXIES", "")
PROXY_LIST: List[str] = [p.strip() for p in PROXIES_RAW.split(",") if p.strip()]


def get_random_proxy() -> Optional[str]:
    """Return a random proxy from the list, or None if empty."""
    return random.choice(PROXY_LIST) if PROXY_LIST else None


############################
# 2) Instagrapi Helpers
############################
def init_instagrapi_session(session_path: str = "data/ig_settings.json") -> IGClient:
    """
    Create an Instagrapi client, optionally loading from session file if it exists.
    Handle 2FA if required. Store session to avoid re-login.
    """
    cl = IGClient()

    # Optionally set proxy:
    # p = get_random_proxy()
    # if p: cl.set_proxy(p)

    if Path(session_path).exists():
        try:
            cl.load_settings(session_path)
            cl.get_timeline_feed()  # check if logged in
        except LoginRequired:
            pass
        except Exception as e:
            print(f"[Instagrapi] Warning while loading session: {e}")

    if not cl.user_id:
        print(f"[Instagrapi] Logging in with {IG_USERNAME}...")
        try:
            cl.login(IG_USERNAME, IG_PASSWORD)
            print("[Instagrapi] Login successful (no 2FA?).")
            cl.dump_settings(session_path)
        except TwoFactorRequired:
            print("[Instagrapi] 2FA required. Check your authenticator or SMS.")
            code = input("Enter 2FA code: ").strip()
            cl.login(IG_USERNAME, IG_PASSWORD, verification_code=code)
            print("[Instagrapi] 2FA login successful.")
            cl.dump_settings(session_path)

    return cl


def fetch_user_info_instagrapi(cl: IGClient, username: str, max_posts=3) -> Dict:
    """
    Fetch user profile info + up to `max_posts` details using Instagrapi,
    converting all non-serializable fields (like HttpUrl) to string.
    """
    result = {
        "username": username,
        "source_library": "instagrapi",
        "user_info": {},
        "posts": [],
    }

    # Attempt the user info request
    user_data = cl.user_info_by_username(username)

    # Convert the profile_pic_url to a string if it's an HttpUrl
    pic_url_str = str(user_data.profile_pic_url) if user_data.profile_pic_url else None

    result["user_info"] = {
        "full_name": user_data.full_name,
        "bio": user_data.biography,
        "profile_pic_url": pic_url_str,
        "follower_count": user_data.follower_count,
        "following_count": user_data.following_count,
    }

    # For user posts
    user_id = user_data.pk
    medias = cl.user_medias(user_id, max_posts)
    for m in medias:
        view_count = None
        if m.media_type == 2:  # video
            view_count = getattr(m, "video_view_count", None)

        # date_of_publication => cast to str
        date_str = m.taken_at.isoformat() if m.taken_at else None

        post_entry = {
            "description": m.caption_text,
            "date_of_publication": date_str,
            "view_count": view_count,
            "like_count": m.like_count,
            "comment_count": m.comment_count,
        }
        result["posts"].append(post_entry)

    return result


############################
# 3) Instaloader Helpers
############################
def init_instaloader_session(session_dir: str = "data/sessions") -> Instaloader:
    """
    Create an Instaloader instance, load session if exists, handle 2FA if needed,
    and store session.
    """
    L = Instaloader()
    session_file = Path(session_dir) / f"{IG_USERNAME}.session"
    session_file.parent.mkdir(parents=True, exist_ok=True)

    # Optionally set proxy:
    # p = get_random_proxy()
    # if p:
    #     L.context.request.proxies = {"http": p, "https": p}

    if session_file.exists():
        try:
            L.load_session_from_file(IG_USERNAME, str(session_file))
            print("[Instaloader] Session loaded from file.")
        except Exception as e:
            print(f"[Instaloader] Could not load session: {e}")

    if not L.test_login():
        print(f"[Instaloader] Logging in with {IG_USERNAME}...")
        try:
            L.login(IG_USERNAME, IG_PASSWORD)
            L.save_session_to_file(str(session_file))
            print("[Instaloader] Session saved.")
        except TwoFactorAuthRequiredException:
            print("[Instaloader] 2FA required. Check your phone or authenticator.")
            code = input("Enter Instaloader 2FA code: ").strip()
            L.two_factor_login(code)
            L.save_session_to_file(str(session_file))
            print("[Instaloader] 2FA login successful, session saved.")

    return L


def fetch_user_info_instaloader(L: Instaloader, username: str, max_posts=3) -> Dict:
    """
    Fetch user profile + up to N posts via Instaloader.
    Convert any non-serializable fields to strings before returning.
    """
    result = {
        "username": username,
        "source_library": "instaloader",
        "user_info": {},
        "posts": [],
    }

    profile = Profile.from_username(L.context, username)

    pic_url_str = str(profile.profile_pic_url) if profile.profile_pic_url else None

    result["user_info"] = {
        "full_name": profile.full_name,
        "bio": profile.biography,
        "profile_pic_url": pic_url_str,
        "follower_count": profile.followers,
        "following_count": profile.followees,
    }

    count = 0
    for post in profile.get_posts():
        if count >= max_posts:
            break
        view_count = getattr(post, "video_view_count", None)
        date_str = post.date_local.isoformat() if post.date_local else None

        post_entry = {
            "description": post.caption,
            "date_of_publication": date_str,
            "view_count": view_count,
            "like_count": post.likes,
            "comment_count": post.comments,
        }
        result["posts"].append(post_entry)
        count += 1

    return result


############################
# 4) Combined Logic
############################
def random_delay(min_sec=3, max_sec=7):
    delay = random.uniform(min_sec, max_sec)
    print(f"[Delay] Sleeping for {delay:.1f} seconds...")
    time.sleep(delay)


def save_results_atomic(results_list: List[Dict], out_file: Path):
    """
    Write the results to a temp file then use `.replace(...)`,
    which on Windows will overwrite the existing file safely.
    """
    out_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = out_file.parent / f".tmp_{uuid.uuid4().hex}.json"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(results_list, f, indent=2, ensure_ascii=False)
    # Use 'replace()' instead of 'rename()' to avoid FileExistsError on Windows:
    temp_file.replace(out_file)


def main():
    # 0) Load CSV from data/target_usernames/item_accounts_rows.csv
    csv_path = Path("data/target_usernames/item_accounts_rows.csv")
    if not csv_path.exists():
        print(f"[ERROR] CSV file not found: {csv_path}")
        sys.exit(1)

    target_usernames = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ig_name = row.get("name")
            if ig_name:
                target_usernames.append(ig_name.strip())

    if not target_usernames:
        print("[WARN] No IG usernames found in CSV.")
        sys.exit(0)

    # 1) Initialize sessions
    cl = init_instagrapi_session("data/ig_settings.json")
    L = init_instaloader_session("data/sessions")

    # We'll store results in a list
    all_results: List[Dict] = []

    # The final file
    results_dir = Path("data/results")
    out_json = results_dir / "instagram_users.json"

    # 2) Process each username
    for username in target_usernames:
        random_delay()

        pick = random.choice(["instagrapi", "instaloader"])
        print(f"\n===== Processing {username} via {pick} =====")

        try:
            if pick == "instagrapi":
                user_data = fetch_user_info_instagrapi(cl, username, max_posts=3)
            else:
                user_data = fetch_user_info_instaloader(L, username, max_posts=3)
        except Exception as e:
            print(f"[ERROR] Failed to fetch data for {username}: {e}")
            continue

        all_results.append(user_data)

        # **Immediately** save partial results
        save_results_atomic(all_results, out_json)
        print(f"[INFO] Intermediate results saved ({len(all_results)} total so far).")

        random_delay()

    print(f"\n[INFO] Final results saved to: {out_json}")
    print("All tasks done. Exiting.")


if __name__ == "__main__":
    main()
