import os
from dotenv import load_dotenv
import instaloader
from datetime import datetime

# Load .env file
load_dotenv()

IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")

def scrape_instaloader(username_to_scrape):
    # Create an Instaloader instance
    L = instaloader.Instaloader()

    # Optional: Log in to handle private profiles or extended data
    if IG_USERNAME and IG_PASSWORD:
        L.login(IG_USERNAME, IG_PASSWORD)

    # Get profile metadata
    profile = instaloader.Profile.from_username(L.context, username_to_scrape)

    print("Profile Info")
    print("------------")
    print(f"Name: {profile.full_name}")
    print(f"Bio: {profile.biography}")
    print(f"Avatar: {profile.profile_pic_url}")
    print(f"Followers: {profile.followers}")
    print(f"Following: {profile.followees}")
    print("")

    # Scrape post metadata
    print("Recent Posts")
    print("------------")
    # Limit to first few posts for demo
    for post in profile.get_posts():
        # You can add a limit or break for demonstration
        publication_date = datetime.fromtimestamp(post.date_utc.timestamp()).strftime('%Y-%m-%d %H:%M:%S')
        print(f"Caption: {post.caption}")
        print(f"Date of Publication: {publication_date}")
        print(f"Likes: {post.likes}")
        print(f"Comments: {post.comments}")

        # Instaloader tries to parse JSON data for view count if it's a video,
        # but sometimes you need a logged-in session or exceptions might occur.
        if post.is_video:
            print(f"Video/IGTV/Reel detected. View Count: {post.video_view_count}")
        print("------------")

if __name__ == "__main__":
    username_to_scrape = "instagram"  # change to your target username
    scrape_instaloader(username_to_scrape)
