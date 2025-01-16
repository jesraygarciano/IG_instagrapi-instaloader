import os
from dotenv import load_dotenv
from instagrapi import Client

# Load .env file
load_dotenv()

IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")

def scrape_instagrapi(username_to_scrape):
    cl = Client()

    # Start the login process
    try:
        cl.login(IG_USERNAME, IG_PASSWORD)
    except Exception as e:
        # If 2FA is required, Instagrapi raises TwoFactorRequired.
        # Here, we catch that exception and retry with a verification code.
        if "TwoFactorRequired" in str(e):
            print("Two-factor authentication required.")
            # Prompt for your 2FA code (6-digit code from text message or authenticator)
            verification_code = input("Enter your 2FA verification code: ")

            # The 'verification_code' parameter is used to complete the 2FA login.
            cl.login(IG_USERNAME, IG_PASSWORD, verification_code=verification_code)
        else:
            raise e

    # Now you're logged in with Instagrapi
    user_info = cl.user_info_by_username(username_to_scrape)
    print("Profile Info")
    print("------------")
    print(f"Name: {user_info.full_name}")
    print(f"Bio: {user_info.biography}")
    print(f"Avatar: {user_info.profile_pic_url}")
    print(f"Followers: {user_info.follower_count}")
    print(f"Following: {user_info.following_count}")
    print("")

    # Retrieve some user posts (feed)
    print("Recent Posts")
    print("------------")
    user_id = user_info.pk
    user_medias = cl.user_medias(user_id, amount=5)  # limit for demo
    for media in user_medias:
        print(f"Caption: {media.caption_text}")
        print(f"Date of Publication: {media.taken_at}")
        print(f"Like Count: {media.like_count}")
        print(f"Comment Count: {media.comment_count}")

        # View count if it's a video (media_type=2)
        if media.media_type == 2:
            print(f"View Count: {media.video_view_count}")
        print("------------")

if __name__ == "__main__":
    # Change to whichever username you want to scrape
    username_to_scrape = "instagram"
    scrape_instagrapi(username_to_scrape)
