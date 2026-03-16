#!/usr/bin/env python3
"""
Seed script – centred around a real user (e.g. trevormozingo).

Usage:
    python scripts/seed_users.py --uid <YOUR_UID> [--users N]

What it does (in order):
  1. Mints an ID-token for YOUR_UID via the Firebase emulator.
  2. Creates N fake users with profiles.
  3. YOU follow every fake user  →  they appear in your feed.
  4. Each fake user creates 1-3 posts.
  5. Fake users react / comment on each other's posts.
  6. Creates ~150 tracking posts for YOU spread over 1 year (backdated).
  7. Fake users react / comment on YOUR posts.

Requirements:
    pip install requests faker firebase-admin pymongo
"""

import argparse
import hashlib
import math
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Optional

import firebase_admin
from firebase_admin import auth as fb_auth, firestore as fb_firestore
from pymongo import MongoClient
import requests
from faker import Faker

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

fake = Faker()

# ── Config ───────────────────────────────────────────────────────────

ACTIVITY_TYPES = [
    "running", "cycling", "swimming", "weightlifting", "crossfit",
    "yoga", "pilates", "hiking", "rowing", "boxing",
    "martial_arts", "climbing", "dance", "stretching", "cardio",
    "hiit", "walking", "sports", "other",
]

INTEREST_OPTIONS = [
    "Weightlifting", "Powerlifting", "Bodybuilding", "Strongman",
    "Olympic Lifting", "Calisthenics", "CrossFit", "Running",
    "Cycling", "Swimming", "Rowing", "Jump Rope", "Stair Climbing",
    "Boxing", "MMA", "Wrestling", "Jiu-Jitsu", "Muay Thai",
    "Yoga", "Pilates", "Stretching", "Mobility Work",
    "Hiking", "Rock Climbing", "Trail Running",
    "Obstacle Course Racing", "Functional Fitness",
    "Basketball", "Soccer", "Tennis", "Volleyball",
    "Pickleball", "Flag Football",
]

FITNESS_LEVELS = ["novice", "intermediate", "experienced", "pro", "olympian"]

REACTION_TYPES = ["strong", "fire", "heart", "smile", "laugh",
                  "thumbsup", "thumbsdown", "angry"]

# Bay Area cities/towns within ~100 miles of SF for realistic labels
_BAY_AREA_CITIES = [
    "San Francisco, CA", "Oakland, CA", "San Jose, CA", "Berkeley, CA",
    "Palo Alto, CA", "Mountain View, CA", "Sunnyvale, CA", "Fremont, CA",
    "Santa Clara, CA", "Redwood City, CA", "San Mateo, CA", "Daly City, CA",
    "Hayward, CA", "Concord, CA", "Walnut Creek, CA", "Pleasanton, CA",
    "Santa Rosa, CA", "Napa, CA", "Vallejo, CA", "Richmond, CA",
    "San Rafael, CA", "Novato, CA", "Petaluma, CA", "Sausalito, CA",
    "Mill Valley, CA", "Livermore, CA", "Dublin, CA", "Milpitas, CA",
    "Cupertino, CA", "Campbell, CA", "Los Gatos, CA", "Saratoga, CA",
    "Half Moon Bay, CA", "Pacifica, CA", "San Leandro, CA", "Alameda, CA",
    "Union City, CA", "Newark, CA", "Foster City, CA", "Burlingame, CA",
    "San Carlos, CA", "Menlo Park, CA", "Los Altos, CA", "Gilroy, CA",
    "Morgan Hill, CA", "Santa Cruz, CA", "Monterey, CA", "Stockton, CA",
    "Modesto, CA", "Sacramento, CA",
]

POST_TITLES = [
    "Morning run", "Leg day", "New PR!", "Rest day vibes", "Chest & back",
    "HIIT session", "Yoga flow", "5K personal best", "First day back",
    "Gym selfie", "Meal prep Sunday", "Post-workout fuel", "Feeling strong",
    "Hill sprints", "Recovery day", "Deadlift PR", "Squat day",
    "Cardio blast", "Swimming laps", "Boxing class",
]

# Message templates for seed conversations
_SEED_MESSAGES = [
    ["Hey! Great workout today 💪", "Thanks! Felt amazing, hit a new PR on squats"],
    ["Want to do a run together this weekend?", "Absolutely! Saturday morning works for me", "Perfect, let's meet at Golden Gate Park at 8am"],
    ["Just tried that yoga class you recommended", "How was it?", "Loved it! My flexibility is already improving"],
    ["Nice deadlift PR! What program are you running?", "Thanks! I've been following 5/3/1 for the past 3 months", "That's awesome, I might give it a try"],
    ["Do you have any good pre-workout meal suggestions?", "I usually go with oatmeal and a banana about an hour before", "Simple but effective, I'll try that tomorrow"],
    ["Just signed up for a half marathon!", "That's amazing! When is it?", "In 3 months, so I need to start training seriously"],
    ["How's the recovery going?", "Much better, the PT exercises are really helping", "Glad to hear it, take it slow!"],
    ["Anyone want to join a cycling group?", "I'm in! What route were you thinking?", "The coastal loop, about 30 miles round trip"],
    ["Crushed my HIIT session today", "What exercises did you do?", "Burpees, box jumps, kettlebell swings, and battle ropes"],
    ["Meal prep tip: make a big batch of chicken and rice on Sunday", "Game changer, saves so much time during the week"],
]


# ── Location helpers ─────────────────────────────────────────────────

def random_location_near_sf() -> dict:
    """Return a GeoJSON-style location dict within 100 miles of SF."""
    SF_LAT, SF_LNG = 37.7749, -122.4194
    MAX_MILES = 100

    # sqrt for uniform distribution across circular area
    dist = MAX_MILES * math.sqrt(random.random())
    bearing = random.uniform(0, 2 * math.pi)

    lat_offset = (dist * math.cos(bearing)) / 69.0
    lng_offset = (dist * math.sin(bearing)) / (69.0 * math.cos(math.radians(SF_LAT)))

    return {
        "type": "Point",
        "coordinates": [round(SF_LNG + lng_offset, 6),
                        round(SF_LAT + lat_offset, 6)],
        "label": random.choice(_BAY_AREA_CITIES),
    }


# ── Firebase token helpers ───────────────────────────────────────────

def init_firebase(emulator_host: str, project_id: str = "fervora-local"):
    """Point firebase-admin at the emulator and initialise."""
    os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = emulator_host
    os.environ["FIRESTORE_EMULATOR_HOST"] = emulator_host.replace("9099", "8181")
    if not firebase_admin._apps:
        # The emulator ignores credentials, but the Firestore client
        # still requires a valid credential object.  Generate a throw-
        # away RSA key and wrap it in a Certificate credential.
        import json, tempfile
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        sa = {
            "type": "service_account",
            "project_id": project_id,
            "private_key_id": "emulator-dummy",
            "private_key": pem,
            "client_email": f"dummy@{project_id}.iam.gserviceaccount.com",
            "client_id": "0",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(sa, tmp)
        tmp.close()
        cred = firebase_admin.credentials.Certificate(tmp.name)
        firebase_admin.initialize_app(cred, options={"projectId": project_id})
        os.unlink(tmp.name)


def get_id_token_for_uid(emulator_host: str, uid: str) -> str:
    """Mint a custom-token for *uid* and exchange it for an ID-token."""
    custom_token = fb_auth.create_custom_token(uid)
    resp = requests.post(
        f"http://{emulator_host}/identitytoolkit.googleapis.com/v1"
        f"/accounts:signInWithCustomToken?key=fake-api-key",
        json={"token": custom_token.decode("utf-8"),
              "returnSecureToken": True},
    )
    resp.raise_for_status()
    return resp.json()["idToken"]


# ── Profile-photo helpers ────────────────────────────────────────────

# Curated background colours for generated avatars
_AVATAR_COLORS = [
    (56, 116, 203),   # blue
    (218, 78, 68),    # red
    (74, 172, 104),   # green
    (246, 166, 35),   # orange
    (142, 68, 204),   # purple
    (230, 74, 152),   # pink
    (44, 183, 187),   # teal
    (96, 96, 96),     # grey
]


def _generate_avatar(display_name: str, size: int = 256) -> bytes:
    """
    Generate a simple avatar PNG: coloured circle with the user's
    initials.  If Pillow is not installed, download from ui-avatars.com.
    """
    initials = "".join(
        part[0].upper() for part in display_name.split() if part
    )[:2] or "?"

    if _HAS_PIL:
        # Deterministic colour based on name
        idx = int(hashlib.md5(display_name.encode()).hexdigest(), 16)
        bg = _AVATAR_COLORS[idx % len(_AVATAR_COLORS)]

        img = Image.new("RGB", (size, size), bg)
        draw = ImageDraw.Draw(img)

        # Use a built-in font; scale roughly to image size
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size // 3)
        except (OSError, IOError):
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), initials, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((size - tw) / 2, (size - th) / 2 - bbox[1]),
            initials, fill="white", font=font,
        )

        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    # Fallback: fetch from ui-avatars.com
    resp = requests.get(
        "https://ui-avatars.com/api/",
        params={"name": display_name, "size": str(size),
                "background": "random", "color": "fff", "format": "png"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.content


def upload_profile_photo(gateway: str, token: str, display_name: str):
    """Generate an avatar and upload it as the user's profile photo."""
    try:
        data = _generate_avatar(display_name)
        resp = requests.post(
            f"{gateway}/profile/photo",
            files={"file": ("avatar.png", data, "image/png")},
            headers=_hdr(token),
        )
        return resp.status_code == 200
    except Exception:
        return False


# ── REST helpers ─────────────────────────────────────────────────────

def emulator_signup_url(emulator_host: str) -> str:
    return (
        f"http://{emulator_host}/identitytoolkit.googleapis.com/v1"
        f"/accounts:signUp?key=fake-api-key"
    )


def create_firebase_user(emulator_host: str, email: str,
                         password: str = "testpass123"):
    """Create a user in the Firebase emulator, return (uid, id_token)."""
    resp = requests.post(
        emulator_signup_url(emulator_host),
        json={"email": email, "password": password,
              "returnSecureToken": True},
    )
    resp.raise_for_status()
    data = resp.json()
    return data["localId"], data["idToken"]


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def create_profile(gateway: str, token: str, username: str,
                   display_name: str, birthday: str,
                   interests: list[str], fitness_level: str):
    payload = {
        "username": username,
        "displayName": display_name,
        "birthday": birthday,
        "profilePhoto": None,
        "interests": interests,
        "fitnessLevel": fitness_level,
    }
    resp = requests.post(f"{gateway}/profile", json=payload,
                         headers=_hdr(token))
    resp.raise_for_status()
    return resp.json()


def update_profile_location(gateway: str, token: str, location: dict):
    """PATCH the user's profile with a location."""
    resp = requests.patch(
        f"{gateway}/profile",
        json={"location": location},
        headers={**_hdr(token), "Content-Type": "application/json"},
    )
    return resp.status_code == 200


def create_post(gateway: str, token: str):
    body: dict = {"title": random.choice(POST_TITLES)}
    if random.random() < 0.7:
        body["body"] = fake.sentence(nb_words=random.randint(5, 25))
    if random.random() < 0.6:
        workout: dict = {
            "activityType": random.choice(ACTIVITY_TYPES),
            "durationSeconds": random.randint(600, 7200),
            "caloriesBurned": random.randint(50, 900),
        }
        if random.random() < 0.5:
            workout["distanceMiles"] = round(random.uniform(0.5, 15), 2)
        if random.random() < 0.4:
            workout["avgHeartRate"] = random.randint(110, 175)
        if random.random() < 0.3:
            workout["maxHeartRate"] = random.randint(160, 200)
        if random.random() < 0.2:
            workout["elevationFeet"] = random.randint(50, 3000)
        body["workout"] = workout
    if random.random() < 0.3:
        metrics: dict = {}
        if random.random() < 0.8:
            metrics["weightLbs"] = round(random.uniform(110, 280), 1)
        if random.random() < 0.5:
            metrics["bodyFatPercentage"] = round(random.uniform(8, 35), 1)
        if random.random() < 0.3:
            metrics["restingHeartRate"] = random.randint(45, 80)
        if random.random() < 0.2:
            metrics["leanBodyMassLbs"] = round(random.uniform(90, 200), 1)
        if metrics:
            body["bodyMetrics"] = metrics

    resp = requests.post(f"{gateway}/posts", json=body,
                         headers=_hdr(token))
    if resp.status_code == 201:
        return resp.json()
    return None


def follow_user(gateway: str, token: str, target_uid: str):
    resp = requests.post(f"{gateway}/follows/{target_uid}",
                         headers=_hdr(token))
    return resp.status_code in (200, 201)


def react_to_post(gateway: str, token: str, post_id: str):
    resp = requests.put(f"{gateway}/posts/{post_id}/reactions",
                        json={"type": random.choice(REACTION_TYPES)},
                        headers=_hdr(token))
    return resp.status_code == 200


def comment_on_post(gateway: str, token: str, post_id: str):
    resp = requests.post(
        f"{gateway}/posts/{post_id}/comments",
        json={"body": fake.sentence(nb_words=random.randint(3, 15))},
        headers=_hdr(token))
    return resp.status_code == 201


# ── MongoDB backdating ──────────────────────────────────────────────

_mongo_client: Optional[MongoClient] = None


def _get_mongo_db(mongo_uri: str, mongo_db: str):
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(mongo_uri)
    return _mongo_client[mongo_db]


def backdate_post(mongo_uri: str, mongo_db: str, post_id: str,
                  iso_date: str):
    """Update createdAt on a post and its feed entries in MongoDB."""
    from bson import ObjectId
    db = _get_mongo_db(mongo_uri, mongo_db)
    oid = ObjectId(post_id)
    db.posts.update_one({"_id": oid}, {"$set": {"createdAt": iso_date}})
    db.feed.update_many({"postId": oid}, {"$set": {"createdAt": iso_date}})


# ── Tracking-focused post creator ───────────────────────────────────

def create_tracking_post(gateway: str, token: str):
    """Create a post that always includes workout data and often body metrics.
    Used for generating rich tracking chart data."""
    body: dict = {"title": random.choice(POST_TITLES)}
    if random.random() < 0.5:
        body["body"] = fake.sentence(nb_words=random.randint(5, 25))

    # Always include workout
    workout: dict = {
        "activityType": random.choice(ACTIVITY_TYPES),
        "durationSeconds": random.randint(600, 7200),
        "caloriesBurned": random.randint(50, 900),
    }
    if random.random() < 0.7:
        workout["distanceMiles"] = round(random.uniform(0.5, 15), 2)
    if random.random() < 0.6:
        workout["avgHeartRate"] = random.randint(110, 175)
    if random.random() < 0.5:
        workout["maxHeartRate"] = random.randint(160, 200)
    if random.random() < 0.3:
        workout["elevationFeet"] = random.randint(50, 3000)
    body["workout"] = workout

    # 60% chance of body metrics
    if random.random() < 0.6:
        metrics: dict = {}
        if random.random() < 0.9:
            metrics["weightLbs"] = round(random.uniform(160, 200), 1)
        if random.random() < 0.6:
            metrics["bodyFatPercentage"] = round(random.uniform(12, 25), 1)
        if random.random() < 0.5:
            metrics["restingHeartRate"] = random.randint(50, 70)
        if random.random() < 0.4:
            metrics["leanBodyMassLbs"] = round(random.uniform(130, 175), 1)
        if metrics:
            body["bodyMetrics"] = metrics

    resp = requests.post(f"{gateway}/posts", json=body,
                         headers=_hdr(token))
    if resp.status_code == 201:
        return resp.json()
    print(f"  [!] tracking post failed ({resp.status_code}): {resp.text[:200]}",
          file=sys.stderr)
    return None


# ── Per-user creation ────────────────────────────────────────────────

def _random_birthday() -> str:
    """Generate a random birthday between 18 and 55 years ago."""
    d = fake.date_of_birth(minimum_age=18, maximum_age=55)
    return d.strftime("%Y-%m-%d")


def seed_one_user(idx: int, gateway: str, emulator_host: str):
    email = f"seed-{idx:05d}@test.com"
    username = f"{fake.user_name()}_{idx}"[:20]
    display_name = fake.name()
    birthday = _random_birthday()
    interests = random.sample(INTEREST_OPTIONS, k=random.randint(1, 6))
    fitness_level = random.choice(FITNESS_LEVELS)
    try:
        uid, token = create_firebase_user(emulator_host, email)
        create_profile(gateway, token, username, display_name,
                       birthday, interests, fitness_level)
        upload_profile_photo(gateway, token, display_name)
        update_profile_location(gateway, token, random_location_near_sf())
        return uid, token, username
    except Exception as e:
        print(f"  [!] user #{idx}: {e}", file=sys.stderr)
        return None


# ── Main ─────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Seed data centred around your user")
    ap.add_argument("--uid", required=True,
                    help="Your Firebase UID (trevormozingo)")
    ap.add_argument("--users", type=int, default=50,
                    help="Fake users to create (default 50)")
    ap.add_argument("--gateway", default="http://localhost:8080")
    ap.add_argument("--emulator", default="localhost:9099")
    ap.add_argument("--posts-per-user", type=int, default=3)
    ap.add_argument("--my-posts", type=int, default=150,
                    help="Tracking posts for YOU spread over 1 year (default 150)")
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--mongo-uri",
                    default="mongodb://localhost:27017/?directConnection=true",
                    help="MongoDB URI for backdating posts")
    ap.add_argument("--mongo-db", default="fervora_test",
                    help="MongoDB database name")
    args = ap.parse_args()

    my_uid = args.uid
    num_users = args.users
    gateway = args.gateway.rstrip("/")
    emulator = args.emulator
    max_posts = args.posts_per_user
    my_posts_count = args.my_posts
    workers = args.workers
    mongo_uri = args.mongo_uri
    mongo_db = args.mongo_db

    # ── Verify services ──────────────────────────────────────────────
    print(f"Gateway : {gateway}")
    print(f"Emulator: {emulator}")
    print(f"Your UID: {my_uid}")

    try:
        requests.get(f"{gateway}/health", timeout=5).raise_for_status()
    except Exception:
        sys.exit("ERROR: Gateway not reachable – is Docker running?")
    try:
        requests.get(f"http://{emulator}/", timeout=5)
    except Exception:
        sys.exit("ERROR: Firebase emulator not reachable.")

    # ── Get token for YOUR uid ───────────────────────────────────────
    print("\n=== Minting token for your UID ===")
    init_firebase(emulator)
    try:
        my_token = get_id_token_for_uid(emulator, my_uid)
    except Exception as e:
        sys.exit(f"ERROR: Could not get token for UID {my_uid}: {e}")
    print("  ✓ Got ID-token for your account")

    # ── Ensure YOUR profile exists ───────────────────────────────────
    print("\n=== Checking your profile ===")
    _check = requests.get(f"{gateway}/profile", headers=_hdr(my_token))
    if _check.status_code == 404:
        print("  Profile not found – creating one for you …")
        create_profile(
            gateway, my_token,
            username="trevormozingo",
            display_name="Trevor Mozingo",
            birthday="1995-01-01",
            interests=random.sample(INTEREST_OPTIONS, k=4),
            fitness_level="intermediate",
        )
        update_profile_location(gateway, my_token, random_location_near_sf())
        print("  ✓ Profile created")
    elif _check.status_code == 200:
        print("  ✓ Profile already exists")
    else:
        print(f"  ⚠ Unexpected status {_check.status_code}: {_check.text[:200]}")

    t0 = time.time()

    # ── Phase 1: Create fake users ───────────────────────────────────
    print(f"\n=== Phase 1: Creating {num_users} fake users ===")
    users: list[tuple[str, str, str]] = []  # (uid, token, username)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(seed_one_user, i, gateway, emulator): i
                for i in range(num_users)}
        done = 0
        for f in as_completed(futs):
            done += 1
            r = f.result()
            if r:
                users.append(r)
            if done % 50 == 0 or done == num_users:
                print(f"  [{done}/{num_users}]  {len(users)} created")

    print(f"  ✓ {len(users)} users in {time.time() - t0:.1f}s")
    if not users:
        print("  ⚠ No new users created (they may already exist). Skipping to your posts.")

    # ── Phase 2–4: Only run if we have fake users ─────────────────
    other_posts: list = []
    follow_ok = 0
    rxn_count = 0
    cmt_count = 0

    if users:
        # ── Phase 2: YOU follow every fake user ──────────────────────
        # Sequential to avoid WriteConflict – all follows lock the same profile doc
        print(f"\n=== Phase 2: You follow {len(users)} users ===")
        t1 = time.time()
        for i, (uid, _, _) in enumerate(users):
            if follow_user(gateway, my_token, uid):
                follow_ok += 1
            if (i + 1) % 50 == 0 or (i + 1) == len(users):
                print(f"  [{i + 1}/{len(users)}]  {follow_ok} follows")
        print(f"  ✓ {follow_ok} follows in {time.time() - t1:.1f}s")

        # ── Phase 3: Fake users create posts ─────────────────────────
        print(f"\n=== Phase 3: Fake users create posts (up to {max_posts} each) ===")
        t2 = time.time()

        def _make_posts(user_tuple):
            uid, token, _ = user_tuple
            out = []
            for _ in range(random.randint(1, max_posts)):
                p = create_post(gateway, token)
                if p:
                    out.append((uid, token, p))
            return out

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_make_posts, u) for u in users]
            done = 0
            for f in as_completed(futs):
                done += 1
                other_posts.extend(f.result())
                if done % 50 == 0 or done == len(users):
                    print(f"  [{done}/{len(users)}]  {len(other_posts)} posts")
        print(f"  ✓ {len(other_posts)} posts in {time.time() - t2:.1f}s")

        # ── Phase 4: Fake users react & comment on EACH OTHER's posts ─
        print("\n=== Phase 4: Cross-interactions among fake users ===")
        t3 = time.time()

        if other_posts:
            for i, (_, token, _) in enumerate(users):
                for _, _, post in random.sample(
                        other_posts, min(random.randint(3, 10), len(other_posts))):
                    if react_to_post(gateway, token, post["id"]):
                        rxn_count += 1
                for _, _, post in random.sample(
                        other_posts, min(random.randint(1, 5), len(other_posts))):
                    if comment_on_post(gateway, token, post["id"]):
                        cmt_count += 1
                if (i + 1) % 50 == 0 or (i + 1) == len(users):
                    print(f"  [{i + 1}/{len(users)}]  {rxn_count} reactions, "
                          f"{cmt_count} comments")

        print(f"  ✓ {rxn_count} reactions, {cmt_count} comments "
              f"in {time.time() - t3:.1f}s")

    # ── Phase 5: Create YOUR posts (spread over 1 year) ────────────
    print(f"\n=== Phase 5: Creating {my_posts_count} tracking posts for YOU (over 1 year) ===")
    t4 = time.time()

    # Generate dates spread over the past year with some randomness
    now_dt = datetime.now(timezone.utc)
    year_ago = now_dt - timedelta(days=365)
    post_dates: list[datetime] = []
    for _ in range(my_posts_count):
        random_dt = year_ago + timedelta(
            seconds=random.randint(0, int(365 * 86400))
        )
        post_dates.append(random_dt)
    post_dates.sort()  # oldest first

    my_posts: list[dict] = []
    for i, dt in enumerate(post_dates):
        p = create_tracking_post(gateway, my_token)
        if p:
            iso = dt.isoformat()
            backdate_post(mongo_uri, mongo_db, p["id"], iso)
            my_posts.append(p)
        if (i + 1) % 25 == 0 or (i + 1) == my_posts_count:
            print(f"  [{i + 1}/{my_posts_count}]  {len(my_posts)} created")

    print(f"  ✓ {len(my_posts)} tracking posts in {time.time() - t4:.1f}s")

    # ── Phase 6: Fake users react & comment on YOUR posts ────────────
    my_rxn = 0
    my_cmt = 0

    if users and my_posts:
        print("\n=== Phase 6: Fake users interact with YOUR posts ===")
        t5 = time.time()

        for i, (_, token, _) in enumerate(users):
            for post in my_posts:
                # ~70% chance each user reacts to each of your posts
                if random.random() < 0.7:
                    if react_to_post(gateway, token, post["id"]):
                        my_rxn += 1
                # ~30% chance each user comments
                if random.random() < 0.3:
                    if comment_on_post(gateway, token, post["id"]):
                        my_cmt += 1
            if (i + 1) % 50 == 0 or (i + 1) == len(users):
                print(f"  [{i + 1}/{len(users)}]  {my_rxn} reactions, "
                      f"{my_cmt} comments on your posts")

        print(f"  ✓ {my_rxn} reactions, {my_cmt} comments on your posts "
              f"in {time.time() - t5:.1f}s")

    # ── Phase 7: Fake users send YOU messages ────────────────────────
    convo_count = 0

    if users:
        print(f"\n=== Phase 7: Seeding conversations ===")
        t6 = time.time()
        fs = fb_firestore.client()
        msg_users = random.sample(users, min(10, len(users)))

        for uid, _token, uname in msg_users:
            try:
                participants = sorted([my_uid, uid])
                convo_ref = fs.collection("conversations").document()
                thread = random.choice(_SEED_MESSAGES)
                # Alternate messages between the fake user and you
                senders = [uid, my_uid]
                now = time.time()
                convo_ref.set({
                    "participants": participants,
                    "hiddenFor": [],
                    "lastMessage": thread[-1],
                    "lastMessageAt": fb_firestore.SERVER_TIMESTAMP,
                    "createdAt": fb_firestore.SERVER_TIMESTAMP,
                })
                msgs_coll = convo_ref.collection("messages")
                for i, msg_text in enumerate(thread):
                    sender = senders[i % 2]
                    msgs_coll.add({
                        "senderUid": sender,
                        "text": msg_text,
                        "createdAt": fb_firestore.SERVER_TIMESTAMP,
                    })
                convo_count += 1
            except Exception as e:
                print(f"  [!] convo with {uname}: {e}", file=sys.stderr)

        print(f"  ✓ {convo_count} conversations in {time.time() - t6:.1f}s")

    # ── Summary ──────────────────────────────────────────────────────
    total = time.time() - t0
    print(f"\n{'=' * 55}")
    print(f"  Done in {total:.1f}s")
    print(f"  Fake users created : {len(users)}")
    print(f"  You follow         : {follow_ok}")
    print(f"  Their posts        : {len(other_posts)}")
    print(f"  Cross-reactions    : {rxn_count}")
    print(f"  Cross-comments     : {cmt_count}")
    print(f"  Your posts         : {len(my_posts)}")
    print(f"  Reactions on yours : {my_rxn}")
    print(f"  Comments on yours  : {my_cmt}")
    print(f"  Conversations      : {convo_count}")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    main()
