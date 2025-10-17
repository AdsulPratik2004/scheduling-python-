from fastapi import FastAPI, Request, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import requests

load_dotenv()

app = FastAPI()

# ✅ Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- FACEBOOK ENDPOINTS --------------------

@app.post("/facebook/token")
async def exchange_token(request: Request):
    body = await request.json()
    code = body.get("code")
    print("🔁 Received Facebook code:", code)

    params = {
        "client_id": os.getenv("FACEBOOK_CLIENT_ID"),
        "client_secret": os.getenv("FACEBOOK_CLIENT_SECRET"),
        "redirect_uri": os.getenv("FACEBOOK_REDIRECT_URI"),
        "code": code,
    }

    try:
        res = requests.get("https://graph.facebook.com/v24.0/oauth/access_token", params=params)
        print("🔗 Token exchange status:", res.status_code)
        print("🔗 Token exchange response:", res.text)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        print("❌ Facebook token exchange error:", str(e))
        return {"error": "Facebook token exchange failed", "details": res.text}

@app.post("/facebook/post")
async def post_to_page(request: Request):
    body = await request.json()
    token = body.get("access_token")
    page_id = body.get("page_id")
    message = body.get("message")

    print("📝 Facebook post request received")
    print("🔐 User token:", token)
    print("📄 Page ID:", page_id)
    print("🗣️ Message:", message)

    if not token or not page_id or not message:
        print("⚠️ Missing required fields")
        return {"error": "Missing access_token, page_id, or message"}

    try:
        res = requests.get(
            f"https://graph.facebook.com/v24.0/{page_id}",
            params={"fields": "access_token", "access_token": token}
        )
        print("🔗 Page token fetch status:", res.status_code)
        print("🔗 Page token response:", res.text)
        res.raise_for_status()
        page_token = res.json().get("access_token")

        if not page_token:
            print("❌ Failed to retrieve page access token")
            return {"error": "Failed to retrieve page access token"}

        post_res = requests.post(
            f"https://graph.facebook.com/v24.0/{page_id}/feed",
            data={"message": message, "access_token": page_token}
        )
        print("📤 Facebook post status:", post_res.status_code)
        print("📤 Facebook post response:", post_res.text)
        post_res.raise_for_status()
        return post_res.json()

    except requests.exceptions.RequestException as e:
        print("❌ Facebook post error:", str(e))
        return {"error": "Facebook post failed", "details": str(e)}

# -------------------- LINKEDIN ENDPOINTS --------------------

@app.post("/linkedin/token")
async def exchange_token(request: Request):
    body = await request.json()
    code = body.get("code")

    print("🔁 Received LinkedIn code:", code)

    params = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": os.getenv("REDIRECT_URI"),
        "client_id": os.getenv("LINKEDIN_CLIENT_ID"),
        "client_secret": os.getenv("LINKEDIN_CLIENT_SECRET"),
    }

    try:
        res = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data=params)
        print("🔗 Token exchange status:", res.status_code)
        print("🔗 Token exchange response:", res.text)
        res.raise_for_status()
        token_data = res.json()
        return token_data
    except requests.exceptions.RequestException as e:
        print("❌ Token exchange error:", str(e))
        return {"error": "Token exchange failed", "details": str(e)}

@app.post("/linkedin/post")
async def post_text(request: Request):
    body = await request.json()
    token = body.get("access_token")
    text = body.get("text")

    print("📝 Received LinkedIn post request")
    print("🔐 Token:", token)
    print("🗣️ Text:", text)

    if not token or not text:
        print("⚠️ Missing token or text")
        return {"error": "Missing access_token or text"}

    try:
        profile_res = requests.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {token}"}
        )
        print("👤 Profile fetch status:", profile_res.status_code)
        print("👤 Profile fetch response:", profile_res.text)
        profile_res.raise_for_status()
        profile = profile_res.json()

        author_urn = f"urn:li:person:{profile['sub']}"
        print("✅ Author URN:", author_urn)

        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }

        print("📦 LinkedIn post payload:", payload)

        post_res = requests.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0"
            },
            json=payload
        )
        print("📤 LinkedIn post response status:", post_res.status_code)
        print("📤 LinkedIn post response body:", post_res.text)
        post_res.raise_for_status()
        return post_res.json()

    except requests.exceptions.RequestException as e:
        print("❌ LinkedIn post error:", str(e))
        return {"error": "LinkedIn post failed", "details": str(e)}

# -------------------- YOUTUBE ENDPOINT --------------------

@app.post("/youtube/upload")
async def upload_youtube_video(
    access_token: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    scheduled_at: str = Form(...),
    video: UploadFile = Form(...)
):
    print("🎬 Received YouTube upload request")
    print("🔐 Access Token:", access_token)
    print("📄 Title:", title)
    print("📝 Description:", description)
    print("📅 Scheduled At:", scheduled_at)
    print("📦 Video Filename:", video.filename)

    metadata = {
        "snippet": {
            "title": title,
            "description": description
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": scheduled_at
        }
    }

    try:
        files = {
            "metadata": (
                "metadata.json",
                str(metadata).replace("'", '"'),
                "application/json"
            ),
            "video": (
                video.filename,
                await video.read(),
                video.content_type
            )
        }

        res = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=multipart&part=snippet,status",
            headers={"Authorization": f"Bearer {access_token}"},
            files=files
        )

        print("📤 YouTube response status:", res.status_code)
        print("📤 YouTube response body:", res.text)

        res.raise_for_status()
        return res.json()

    except requests.exceptions.RequestException as e:
        print("❌ YouTube upload error:", str(e))
        return {"error": "YouTube upload failed", "details": str(e)}
