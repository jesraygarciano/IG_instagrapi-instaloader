#!/usr/bin/env python3
"""
main.py

- Loads IG_USERNAME, IG_PASSWORD from .env (same credentials used for both Instaloader + Instagrapi).
- Optionally loads PROXIES (comma-separated) for random proxy usage.
- Uses session files/cookies to avoid repeated logins:
    - Instagrapi: user_settings_path => cl.load_settings() / cl.dump_settings()
    - Instaloader: L.load_session_from_file(), L.save_session_to_file()
- Alternates randomly between using Instaloader and Instagrapi for each requested username, 
  to distribute scraping tasks.
- Adds random delays (sleep) between tasks to reduce block risk.
"""

import os
import sys
import time
import random
from pathlib import Path
from typing import Optional, List

# For environment variables
from dotenv import load_dotenv

# Instagrapi
from instagrapi import Client as IGClient
from instagrapi.exceptions import LoginRequired

# Instaloader
import instaloader
from instaloader import Instaloader, Profile

# If you also want a fallback to standard requests
import requests

############################
# 1) Environment / Config
############################
load_dotenv()

IG_USERNAME = os.getenv("IG_USERNAME", "")
IG_PASSWORD = os.getenv("IG_PASSWORD", "")

# Proxies, e.g. "http://1.2.3.4:8888, http://user:pass@5.6.7.8:9999"
PROXIES_RAW = os.getenv("PROXIES", "")
PROXY_LIST: List[str] = [p.strip() for p in PROXIES_RAW.split(",") if p.strip()]

def get_random_proxy() -> Optional[str]:
    """Return a random proxy from the list, or None if empty."""
    return random.choice(PROXY_LIST) if PROXY_LIST else None

############################
# 2) Instagrapi Helpers
############################
def init_instagrapi_session(session_path: str = "ig_settings.json") -> IGClient:
    """
    Create an Instagrapi client, optionally loading from session file if it exists.
    If login is needed, we do so once and store the session.
    """
    cl = IGClient()

    # If you want to apply a proxy:
    # random_proxy = get_random_proxy()
    # if random_proxy:
    #     cl.set_proxy(random_proxy)

    # Attempt to load existing settings
    if Path(session_path).exists():
        try:
            cl.load_settings(session_path)
            # Attempt a test to see if we're still logged in
            cl.get_timeline_feed()  # might raise LoginRequired if session is invalid
        except LoginRequired:
            pass
        except Exception as e:
            print(f"[Instagrapi] Warning: could not load existing settings properly: {e}")

    if not cl.user_id:  # means not logged in
        print(f"[Instagrapi] Logging in with {IG_USERNAME}...")
        cl.login(IG_USERNAME, IG_PASSWORD)
        print("[Instagrapi] Login successful. Saving session.")
        cl.dump_settings(session_path)

    return cl

def fetch_user_info_instagrapi(cl: IGClient, target_username: str) -> dict:
    """
    Example: fetch user info (bio, name, followers, etc.) using instagrapi client.
    """
    user_data = cl.user_info_by_username(target_username)
    return {
        "username": user_data.username,
        "full_name": user_data.full_name,
        "bio": user_data.biography,
        "profile_pic_url": user_data.profile_pic_url,
        "follower_count": user_data.follower_count,
        "following_count": user_data.following_count,
    }

############################
# 3) Instaloader Helpers
############################
def init_instaloader_session(session_dir: str = "data/sessions") -> Instaloader:
    """
    Create an Instaloader instance, optionally load from a session file.
    We use a session file named after IG_USERNAME for convenience.
    """
    L = Instaloader()
    session_file = Path(session_dir) / f"{IG_USERNAME}.session"
    session_file.parent.mkdir(parents=True, exist_ok=True)

    # Optional: random proxy usage
    # random_proxy = get_random_proxy()
    # if random_proxy:
    #     L.context.request.proxies = {"http": random_proxy, "https": random_proxy}

    if session_file.exists():
        try:
            L.load_session_from_file(IG_USERNAME, str(session_file))
            print("[Instaloader] Session loaded from file.")
        except Exception as e:
            print(f"[Instaloader] Could not load session: {e}")
    else:
        print(f"[Instaloader] Logging in with {IG_USERNAME}...")
        L.login(IG_USERNAME, IG_PASSWORD)
        L.save_session_to_file(str(session_file))
        print("[Instaloader] Session saved.")

    return L

def fetch_user_info_instaloader(L: Instaloader, target_username: str) -> dict:
    """
    Show how to fetch user info with Instaloader (profile object).
    For advanced data (followers, posts, etc.), we'd do more queries.
    """
    profile = Profile.from_username(L.context, target_username)
    return {
        "username": profile.username,
        "full_name": profile.full_name,
        "bio": profile.biography,
        "profile_pic_url": profile.profile_pic_url,
        "follower_count": profile.followers,
        "following_count": profile.followees,
    }

def download_posts_instaloader(L: Instaloader, target_username: str, max_posts: int = 3):
    """
    Download up to max_posts from user's feed into data/downloads/<username>.
    """
    profile = Profile.from_username(L.context, target_username)
    posts = profile.get_posts()
    target_dir = Path("data/downloads") / target_username
    target_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for post in posts:
        if count >= max_posts:
            break
        print(f"[Instaloader] Downloading post shortcode={post.shortcode}, likes={post.likes}, comments={post.comments}")
        L.download_post(post, target=str(target_dir))
        count += 1

############################
# 4) Combined Logic
############################
def random_delay(min_sec=3, max_sec=7):
    """
    Sleep a random number of seconds to reduce risk of blocking.
    """
    delay = random.uniform(min_sec, max_sec)
    print(f"[Delay] Sleeping for {delay:.1f} seconds...")
    time.sleep(delay)

def main():
    # Example target users
    # In practice, read from a file, DB, or pass as arguments
    target_usernames = ["instagram", "natgeo", "github", "nytimes"]

    # 1) Initialize sessions
    cl = init_instagrapi_session("ig_settings.json")
    L = init_instaloader_session("data/sessions")

    # 2) For each target username, randomly pick which library to use
    for user in target_usernames:
        random_delay()  # add a random delay before each user

        # 50% chance to use instagrapi, 50% chance to use instaloader
        pick = random.choice(["instagrapi", "instaloader"])

        if pick == "instagrapi":
            print(f"\n==== [Instagrapi Mode] => {user}")
            user_info = fetch_user_info_instagrapi(cl, user)
            print(f"[Instagrapi] {user} => {user_info}")
        else:
            print(f"\n==== [Instaloader Mode] => {user}")
            user_info = fetch_user_info_instaloader(L, user)
            print(f"[Instaloader] {user} => {user_info}")
            # Maybe also download a few posts if we want
            download_posts_instaloader(L, user, max_posts=2)

        # Additional random delay after finishing
        random_delay()

    print("\nAll tasks done.")
    print("Scaling tips:")
    print("- For large volume: multiple IG accounts, advanced error handling, rotating among them.")
    print("- Introduce more random delays, detect challenge/2FA, store sessions/cookies carefully.")
    print("- Potentially handle retries if rate-limited or blocked.\n")

if __name__ == "__main__":
    main()
