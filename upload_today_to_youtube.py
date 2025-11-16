import os
import io
import tempfile
from datetime import datetime
from typing import Optional

import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


def env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "y")


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def build_youtube_client() -> any:
    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
        ],
    )
    return build("youtube", "v3", credentials=creds)


def download_video_to_temp(video_url: str) -> Optional[str]:
    print(f"Downloading video from {video_url}")
    resp = requests.get(video_url, stream=True)
    if resp.status_code == 404:
        print("  -> File not found (404), skipping.")
        return None
    resp.raise_for_status()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    for chunk in resp.iter_content(chunk_size=1024 * 1024):
        if chunk:
            tmp.write(chunk)
    tmp.close()
    print(f"  -> Saved to {tmp.name}")
    return tmp.name


def upload_one_video(
    youtube,
    file_path: str,
    title: str,
    description: str,
    category_id: str,
    privacy_status: str,
    made_for_kids: bool,
    altered_content: bool,
):
    print(f"Uploading {file_path} to YouTube...")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }

    # For altered / synthetic content flag (policy requirement)
    if altered_content:
        body["contentDetails"] = {"hasCustomThumbnail": False}  # placeholder
        # NOTE: The strict A/S flag is enabled via UI / policies.
        # Here we just mark in description for transparency.
        body["snippet"]["description"] += "\n\n[Contains AI-generated or edited content]"

    with open(file_path, "rb") as f:
        media = MediaIoBaseUpload(
            io.BufferedReader(f),
            mimetype="video/mp4",
            chunksize=-1,
            resumable=True,
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = request.execute()
        video_id = response.get("id")
        print(f"  -> Uploaded successfully, video id: {video_id}")


def main():
    today = datetime.utcnow().strftime("%Y-%m-%d")

    base_url = os.environ["R2_BASE_URL"].rstrip("/")
    prefix = os.environ["R2_PREFIX_PATH"].strip("/")

    title_prefix = os.getenv("YT_TITLE_PREFIX", "Daily Video")
    description = os.getenv("YT_DESCRIPTION", "")
    category_id = os.getenv("YT_CATEGORY_ID", "22")
    privacy_status = os.getenv("YT_PRIVACY_STATUS", "public")
    made_for_kids = env_bool("YT_MADE_FOR_KIDS", False)
    altered_content = env_bool("YT_ALTERED_CONTENT", True)
    max_daily_uploads = env_int("YT_MAX_DAILY_UPLOADS", 1)

    youtube = build_youtube_client()

    uploaded_any = False

    for index in range(1, max_daily_uploads + 1):
        if max_daily_uploads == 1:
            filename = f"{today}.mp4"
            title = f"{title_prefix} - {today}"
        else:
            filename = f"{today}-{index}.mp4"
            title = f"{title_prefix} - {today} Part {index}"

        video_url = f"{base_url}/{prefix}/{filename}"
        print(f"\n=== Checking file: {video_url} ===")

        try:
            temp_path = download_video_to_temp(video_url)
            if temp_path is None:
                continue

            upload_one_video(
                youtube=youtube,
                file_path=temp_path,
                title=title,
                description=description,
                category_id=category_id,
                privacy_status=privacy_status,
                made_for_kids=made_for_kids,
                altered_content=altered_content,
            )
            uploaded_any = True
        except Exception as e:
            print(f"  -> Error with {filename}: {e}")

    if not uploaded_any:
        print("No files were uploaded today (nothing found in R2).")


if __name__ == "__main__":
    main()
