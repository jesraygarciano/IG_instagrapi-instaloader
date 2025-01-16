#!/usr/bin/env python3
"""
main.py

- Reads "item_accounts_rows.csv" from data/target_usernames to get IG usernames.
- For each username, randomly pick Instagrapi or Instaloader:
  - Fetch user info: name (full_name), bio, avatar (profile pic), #followers, #followings
  - Fetch up to N posts: caption, date, views (if available), likes, comments
- Combine the results into a single JSON file in data/results/instagram_users.json
- Maintains 2FA login for both libraries, storing sessions to avoid repeated logins.
"""

import os
import sys
import time
import random
import csv
import json
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

# Optional (requests for fallback)
import requests

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
    Fetch user profile info + up to `max_posts` details using Instagrapi.
    """
    result = {
        "username": username,
        "source_library": "instagrapi",
        "user_info": {},
        "posts": [],
    }

    # 1) user info
    user_data = cl.user_info_by_username(username)
    result["user_info"] = {
        "full_name": user_data.full_name,
        "bio": user_data.biography,
        "profile_pic_url": user_data.profile_pic_url,
        "follower_count": user_data.follower_count,
        "following_count": user_data.following_count,
    }

    # 2) fetch up to max_posts from the user feed
    user_id = user_data.pk
    medias = cl.user_medias(user_id, max_posts)  # quick fetch
    for m in medias:
        # For posts that are *videos*, instagrapi has .view_count
        view_count = None
        if m.media_type == 2:  # video
            # instagrapi calls it m.video_view_count in many versions
            view_count = getattr(m, "video_view_count", None)

        # For a carousel, you might gather subitems, etc.
        # For a single post (photo or video), we have .taken_at, .comment_count, etc.
        post_entry = {
            "description": m.caption_text,
            "date_of_publication": str(m.taken_at),
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
    Note: Instaloader can get post likes, comments, but
    'view count' is only for videos, and is not always guaranteed accessible.
    """
    result = {
        "username": username,
        "source_library": "instaloader",
        "user_info": {},
        "posts": [],
    }

    profile = Profile.from_username(L.context, username)
    result["user_info"] = {
        "full_name": profile.full_name,
        "bio": profile.biography,
        "profile_pic_url": profile.profile_pic_url,
        "follower_count": profile.followers,
        "following_count": profile.followees,
    }

    count = 0
    for post in profile.get_posts():
        if count >= max_posts:
            break
        # post is an instance of `Post`
        # Instaloader doesn't always supply 'view_count' for normal feed posts,
        # but we can do post.video_view_count if it's a video:
        view_count = getattr(post, "video_view_count", None)
        post_entry = {
            "description": post.caption,
            "date_of_publication": str(post.date_local),
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


def main():
    # 0) Load CSV from data/target_usernames/item_accounts_rows.csv
    csv_path = Path("data/target_usernames/item_accounts_rows.csv")
    if not csv_path.exists():
        print(f"[ERROR] CSV file not found: {csv_path}")
        sys.exit(1)

    # We'll parse the 'name' column as the IG handle
    # item_accounts_rows.csv has a header:
    #   id,app_id,name,app_unique_id,created_at,updated_at,display_name,...
    # We'll store them in a list of usernames
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

    # 1) Initialize sessions (both Instagrapi & Instaloader)
    cl = init_instagrapi_session("data/ig_settings.json")
    L = init_instaloader_session("data/sessions")

    # We'll store results in a list of dict
    all_results = []

    # 2) For each username, pick library
    for username in target_usernames:
        random_delay()  # reduce block risk

        pick = random.choice(["instagrapi", "instaloader"])
        print(f"\n===== Processing {username} via {pick} =====")

        try:
            if pick == "instagrapi":
                user_data = fetch_user_info_instagrapi(cl, username, max_posts=3)
            else:
                user_data = fetch_user_info_instaloader(L, username, max_posts=3)
        except Exception as e:
            print(f"[ERROR] Failed to fetch data for {username}: {e}")
            # We can store a partial or skip
            continue

        # Append to all_results
        all_results.append(user_data)

        # Possibly add another random delay
        random_delay()

    # 3) Save to JSON inside data/results
    results_dir = Path("data/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    out_json = results_dir / "instagram_users.json"

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n[INFO] Results saved to: {out_json}")
    print("Done. Exiting.")


if __name__ == "__main__":
    main()
