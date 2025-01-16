#!/usr/bin/env python3
"""
media_main.py

Script to handle “media data” requests in two patterns:
  1) Retrieve all posts from a user (via user_id or username).
  2) Retrieve a single post’s info if we have its shortcode (like 'CqzmmWjy95o').

We read from "items_rows.csv" in "data/media_data/",
which can contain either:
  - A row with "link" containing https://www.instagram.com/p/<shortcode>/
    => single-post approach
  - Or a row with a "username" or "owner_id" => multi-post approach
      (some CSV may have a JSON 'data' column containing owner info, etc.)

After scraping, partial results are immediately saved to `data/results/instagram_media.json`,
so we don’t lose progress if the script is interrupted.

Like main.py, we handle 2FA in both Instagrapi & Instaloader,
and we store sessions in `data/sessions`.
"""

import os
import sys
import time
import random
import csv
import json
import uuid
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
# 2) Instagrapi: Login & Helpers
############################
def init_instagrapi_session(session_path: str = "data/ig_settings.json") -> IGClient:
    """
    Create an Instagrapi client, optionally loading from a session file if it exists.
    Handle 2FA if required. Store session to avoid re-login.
    """
    cl = IGClient()

    # Optionally set a random proxy
    # p = get_random_proxy()
    # if p:
    #     cl.set_proxy(p)

    # Attempt to load existing session
    if Path(session_path).exists():
        try:
            cl.load_settings(session_path)
            cl.get_timeline_feed()  # check if logged in
        except LoginRequired:
            pass
        except Exception as exc:
            print(f"[Instagrapi] Warning while loading session: {exc}")

    # If not logged in, do a fresh login
    if not cl.user_id:
        print(f"[Instagrapi] Logging in with {IG_USERNAME}...")
        try:
            cl.login(IG_USERNAME, IG_PASSWORD)
            print("[Instagrapi] Login successful (no 2FA?).")
            cl.dump_settings(session_path)
        except TwoFactorRequired:
            print("[Instagrapi] 2FA required.")
            code = input("Enter 2FA code: ").strip()
            cl.login(IG_USERNAME, IG_PASSWORD, verification_code=code)
            print("[Instagrapi] 2FA login successful.")
            cl.dump_settings(session_path)

    return cl

###########################
# Instagrapi: Pattern #1 - user all posts
###########################
def fetch_user_all_posts_instagrapi(cl: IGClient, username_or_id: str, limit=5) -> Dict:
    """
    If you have a username or user ID, fetch the user's profile info & up to 'limit' posts.
    For demonstration, we accept either "username" or numeric ID as a string.
    We'll try to detect which is which.
    """
    result = {
        "mode": "user_all_posts",
        "library": "instagrapi",
        "user_info": {},
        "posts": [],
    }

    # Distinguish numeric ID from username:
    # If purely digits, assume user_id. Otherwise treat as username
    if username_or_id.isdigit():
        user_id = int(username_or_id)
    else:
        # treat as username => get user_id
        user_id = cl.user_id_from_username(username_or_id)

    user_info = cl.user_info(user_id)
    result["user_info"] = {
        "username": user_info.username,
        "full_name": user_info.full_name,
        "bio": user_info.biography,
        "profile_pic_url": str(user_info.profile_pic_url),
        "follower_count": user_info.follower_count,
        "following_count": user_info.following_count,
    }

    # fetch up to 'limit' recent posts
    medias = cl.user_medias(user_id, amount=limit)
    for m in medias:
        # single post data
        # If video:
        view_count = getattr(m, "video_view_count", None) if m.media_type == 2 else None
        post_entry = {
            "id": m.pk,
            "shortcode": m.code,
            "description": m.caption_text,
            "date_of_publication": m.taken_at.isoformat() if m.taken_at else None,
            "view_count": view_count,
            "like_count": m.like_count,
            "comment_count": m.comment_count,
        }
        result["posts"].append(post_entry)

    return result

###########################
# Instagrapi: Pattern #2 - single post by shortcode
###########################
def fetch_single_post_instagrapi(cl: IGClient, shortcode: str) -> Dict:
    """
    If we have a single post's shortcode (like "CqzmmWjy95o"),
    we can directly fetch that media info, which sometimes includes the 'play count'.
    """
    result = {
        "mode": "single_post",
        "library": "instagrapi",
        "post": {},
    }

    media_pk = cl.media_pk_from_code(shortcode)
    media = cl.media_info(media_pk)
    # For single post => gather details
    result["post"] = {
        "id": media.pk,
        "shortcode": media.code,
        "description": media.caption_text,
        "date_of_publication": media.taken_at.isoformat() if media.taken_at else None,
        "view_count": getattr(media, "video_view_count", None) if media.media_type == 2 else None,
        "like_count": media.like_count,
        "comment_count": media.comment_count,
        # Some versions can have "play_count" if you see that in media dict, e.g.:
        "play_count": getattr(media, "play_count", None),  # optional
    }
    return result

############################
# 3) Instaloader equivalents
############################
def init_instaloader_session(session_dir: str = "data/sessions") -> Instaloader:
    L = Instaloader()
    session_file = Path(session_dir) / f"{IG_USERNAME}.session"
    session_file.parent.mkdir(parents=True, exist_ok=True)

    # p = get_random_proxy()
    # if p:
    #     L.context.request.proxies = {"http": p, "https": p}

    if session_file.exists():
        try:
            L.load_session_from_file(IG_USERNAME, str(session_file))
            print("[Instaloader] Session loaded from file.")
        except Exception as exc:
            print(f"[Instaloader] Could not load session: {exc}")

    if not L.test_login():
        print(f"[Instaloader] Logging in with {IG_USERNAME}...")
        try:
            L.login(IG_USERNAME, IG_PASSWORD)
            L.save_session_to_file(str(session_file))
            print("[Instaloader] Session saved.")
        except TwoFactorAuthRequiredException:
            print("[Instaloader] 2FA required.")
            code = input("Enter Instaloader 2FA code: ").strip()
            L.two_factor_login(code)
            L.save_session_to_file(str(session_file))
            print("[Instaloader] 2FA login successful, session saved.")

    return L

def fetch_user_all_posts_instaloader(L: Instaloader, username_or_id: str, limit=5) -> Dict:
    """
    Instaloader does not natively handle numeric user_id easily; typically we use username.
    If you do have user_id, you'd need a special approach. We'll assume 'username'.
    """
    result = {
        "mode": "user_all_posts",
        "library": "instaloader",
        "user_info": {},
        "posts": [],
    }

    # We'll treat it as a username here
    profile = Profile.from_username(L.context, username_or_id)

    result["user_info"] = {
        "username": profile.username,
        "full_name": profile.full_name,
        "bio": profile.biography,
        "profile_pic_url": str(profile.profile_pic_url),
        "follower_count": profile.followers,
        "following_count": profile.followees,
    }

    count = 0
    for post in profile.get_posts():
        if count >= limit:
            break
        # single post
        view_count = getattr(post, "video_view_count", None) if post.is_video else None
        post_entry = {
            "id": post.mediaid,
            "shortcode": post.shortcode,
            "description": post.caption,
            "date_of_publication": post.date_local.isoformat() if post.date_local else None,
            "view_count": view_count,
            "like_count": post.likes,
            "comment_count": post.comments,
        }
        result["posts"].append(post_entry)
        count += 1

    return result

def fetch_single_post_instaloader(L: Instaloader, shortcode: str) -> Dict:
    """
    Instaloader does not have a direct “fetch by shortcode” method in the public API,
    but we can do:
        Post.from_shortcode(L.context, shortcode)
    Then gather details.
    """
    result = {
        "mode": "single_post",
        "library": "instaloader",
        "post": {},
    }

    post = Post.from_shortcode(L.context, shortcode)

    result["post"] = {
        "id": post.mediaid,
        "shortcode": post.shortcode,
        "description": post.caption,
        "date_of_publication": post.date_local.isoformat() if post.date_local else None,
        "view_count": post.video_view_count if post.is_video else None,
        "like_count": post.likes,
        "comment_count": post.comments,
        # Instaloader typically returns only .video_view_count for videos,
        # no separate play_count. 
    }
    return result


############################
# 4) Utility: random delay & atomic save
############################
def random_delay(min_sec=3, max_sec=7):
    delay = random.uniform(min_sec, max_sec)
    print(f"[Delay] Sleeping for {delay:.1f} seconds...")
    time.sleep(delay)

def save_results_atomic(results_list: List[Dict], out_file: Path):
    out_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = out_file.parent / f".tmp_{uuid.uuid4().hex}.json"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(results_list, f, indent=2, ensure_ascii=False)
    temp_file.replace(out_file)


############################
# 5) MAIN SCRIPT LOGIC
############################
def main():
    """
    We read data/media_data/items_rows.csv.

    Each row might have:
      - a column 'link' => https://www.instagram.com/p/<shortcode>/ => single post
      - or we might have a column 'owner_id' or 'username' => fetch user’s multiple posts.

    We'll store results in data/results/instagram_media.json, partial-saving after each row.
    """
    csv_path = Path("data/media_data/items_rows.csv")
    if not csv_path.exists():
        print(f"[ERROR] CSV not found: {csv_path}")
        sys.exit(1)

    # parse CSV
    media_requests = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # e.g. row['link'] or row['data'] or row['some_user_id'] ...
            # We'll store a dict describing how we want to handle it
            link = row.get("link") or ""
            # if link is of the form https://www.instagram.com/p/xxxxxx/
            # parse out the shortcode if present
            if "/p/" in link:
                # single post approach
                # we can do a simple parse:
                # link ends with /p/<shortcode>/ or /? blah
                parts = link.split("/p/")
                if len(parts) > 1:
                    remainder = parts[1]
                    # remainder might be 'CqzmmWjy95o/' or 'CqzmmWjy95o/?some=stuff'
                    short = remainder.split("/")[0]
                    media_requests.append({
                        "type": "single_post",
                        "shortcode": short,
                        "original_link": link,
                        "row_data": row
                    })
                else:
                    # fallback
                    pass
            else:
                # assume we do the "user all posts" approach
                # maybe there's a 'app_unique_id' or 'app_id' or 'display_name' or user_name
                # In your CSV snippet, it might have 'item_account_id', 'app_unique_id', etc.
                # We'll guess there's a 'app_unique_id' or 'name' that is the user handle or ID.
                user_str = row.get("app_unique_id") or row.get("name") or ""
                if user_str:
                    media_requests.append({
                        "type": "user_all",
                        "user_id_or_name": user_str,
                        "row_data": row
                    })
                else:
                    print(f"[WARN] No handle/shortcode found in row, skipping: {row}")

    if not media_requests:
        print("[WARN] No media requests found in CSV.")
        sys.exit(0)

    # initialize sessions
    cl = init_instagrapi_session("data/ig_settings.json")
    L = init_instaloader_session("data/sessions")

    out_path = Path("data/results/instagram_media.json")
    all_results = []

    for req in media_requests:
        random_delay()

        # randomly pick library
        library_pick = random.choice(["instagrapi", "instaloader"])
        print(f"\n=== Processing {req} with {library_pick} ===")

        try:
            if library_pick == "instagrapi":
                if req["type"] == "single_post":
                    # pattern #2 single post
                    short = req["shortcode"]
                    ret = fetch_single_post_instagrapi(cl, short)
                    ret["original_link"] = req["original_link"]
                else:
                    # pattern #1 user all
                    user_id_or_name = req["user_id_or_name"]
                    ret = fetch_user_all_posts_instagrapi(cl, user_id_or_name, limit=5)
            else:
                # instaloader
                if req["type"] == "single_post":
                    short = req["shortcode"]
                    ret = fetch_single_post_instaloader(L, short)
                    ret["original_link"] = req["original_link"]
                else:
                    user_id_or_name = req["user_id_or_name"]
                    # In instaloader, we typically only handle username, not numeric ID
                    ret = fetch_user_all_posts_instaloader(L, user_id_or_name, limit=5)

        except Exception as exc:
            print(f"[ERROR] Failed to handle request {req}: {exc}")
            continue

        # possibly store the row data if you want
        ret["row_data"] = req["row_data"]

        # store partial
        all_results.append(ret)
        save_results_atomic(all_results, out_path)
        print(f"[INFO] Partial results saved. (total {len(all_results)})")

        random_delay()

    print(f"\n[INFO] Final results saved to {out_path}")
    print("[INFO] All done. Exiting.")


if __name__ == "__main__":
    main()
