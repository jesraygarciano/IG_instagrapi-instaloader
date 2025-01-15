# Instagram Scraper: Instagrapi + Instaloader

This sample project demonstrates how to use **both** Instagrapi **and** Instaloader **with the same Instagram account**:

- Randomly pick which library to use for each user (helps reduce detection/blocks).
- Use session/cookie files to avoid repeated logins.
- Integrate random delays and optional proxy rotation.

## Features

1. **Single Credentials** – Same `IG_USERNAME`/`IG_PASSWORD` for both libraries.
2. **Session Persistence** – Avoid re-logins using `ig_settings.json` for Instagrapi, and `.session` files for Instaloader.
3. **Randomization** – Random delays, random library choice, optional proxies.
4. **Scalability** – Template for adding multi-account rotation, advanced error handling, etc.

## Setup

1. Clone this repository (or copy the files).
2. Create a `.env` file with:
   ```bash
   IG_USERNAME=some_ig_username
   IG_PASSWORD=some_ig_password
   PROXIES=http://1.2.3.4:8888, http://5.6.7.8:9999
   ```
3. Install dependencies:
```bash
python -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```
4. Run the script:
```bash
python main.py

```



