import os
from dotenv import load_dotenv
from instagrapi import Client

# Load .env file
load_dotenv()

IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")

def scrape_instagrapi(username_to_scrape):
    cl = Client()

    # Login to retrieve private or more detailed data
    cl.login(IG_USERNAME, IG_PASSWORD)

    # Retrieve user info
    user_info = cl.user_info_by_username(username_to_scrape)
    print("Profile Info")
    print("------------")
    print(f"Name: {user_info.full_name}")
    print(f"Bio: {user_info.biography}")
    print(f"Avatar: {user_info.profile_pic_url}")
    print(f"Followers: {user_info.follower_count}")
    print(f"Following: {user_info.following_count}")
    print("")

    # Retrieve user feed (posts)
    print("Recent Posts")
    print("------------")
    user_id = user_info.pk
    user_medias = cl.user_medias(user_id, amount=5)  # limit for demo
    for media in user_medias:
        print(f"Caption: {media.caption_text}")
        print(f"Date of Publication: {media.taken_at}")
        print(f"Like Count: {media.like_count}")
        print(f"Comment Count: {media.comment_count}")

        # For videos (media_type == 2), you can retrieve view count
        if media.media_type == 2:
            print(f"View Count: {media.video_view_count}")
        print("------------")

if __name__ == "__main__":
    username_to_scrape = "instagram"  # change to your target username
    scrape_instagrapi(username_to_scrape)
