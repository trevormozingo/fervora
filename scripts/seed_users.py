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
  6. Creates 3-5 posts for YOU.
  7. Fake users react / comment on YOUR posts.

Requirements:
    pip install requests faker firebase-admin
"""

import argparse
import hashlib
import math
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

import firebase_admin
from firebase_admin import auth as fb_auth
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
    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": project_id})


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
                   display_name: str):
    resp = requests.post(f"{gateway}/profile",
                         json={"username": username,
                               "displayName": display_name},
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
        body["workout"] = {
            "activityType": random.choice(ACTIVITY_TYPES),
            "durationSeconds": random.randint(600, 7200),
            "caloriesBurned": random.randint(50, 900),
        }
    if random.random() < 0.3:
        metrics: dict = {}
        if random.random() < 0.8:
            metrics["weightLbs"] = round(random.uniform(110, 280), 1)
        if random.random() < 0.5:
            metrics["bodyFatPercentage"] = round(random.uniform(8, 35), 1)
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


# ── Per-user creation ────────────────────────────────────────────────

def seed_one_user(idx: int, gateway: str, emulator_host: str):
    email = f"seed-{idx:05d}@test.com"
    username = f"{fake.user_name()}_{idx}"[:20]
    display_name = fake.name()
    try:
        uid, token = create_firebase_user(emulator_host, email)
        create_profile(gateway, token, username, display_name)
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
    ap.add_argument("--my-posts", type=int, default=5,
                    help="Posts to create for YOU (default 5)")
    ap.add_argument("--workers", type=int, default=20)
    args = ap.parse_args()

    my_uid = args.uid
    num_users = args.users
    gateway = args.gateway.rstrip("/")
    emulator = args.emulator
    max_posts = args.posts_per_user
    my_posts_count = args.my_posts
    workers = args.workers

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
        sys.exit("No users created – aborting.")

    # ── Phase 2: YOU follow every fake user ──────────────────────────
    print(f"\n=== Phase 2: You follow {len(users)} users ===")
    t1 = time.time()
    follow_ok = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(follow_user, gateway, my_token, uid)
                for uid, _, _ in users]
        for f in as_completed(futs):
            if f.result():
                follow_ok += 1
    print(f"  ✓ {follow_ok} follows in {time.time() - t1:.1f}s")

    # ── Phase 3: Fake users create posts ─────────────────────────────
    print(f"\n=== Phase 3: Fake users create posts (up to {max_posts} each) ===")
    t2 = time.time()
    other_posts: list[tuple[str, str, dict]] = []  # (uid, token, post)

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

    # ── Phase 4: Fake users react & comment on EACH OTHER's posts ────
    print("\n=== Phase 4: Cross-interactions among fake users ===")
    t3 = time.time()
    rxn_count = 0
    cmt_count = 0

    if other_posts:
        def _interact(user_tuple):
            _, token, _ = user_tuple
            rc, cc = 0, 0
            for _, _, post in random.sample(
                    other_posts, min(random.randint(3, 10), len(other_posts))):
                if react_to_post(gateway, token, post["id"]):
                    rc += 1
            for _, _, post in random.sample(
                    other_posts, min(random.randint(1, 5), len(other_posts))):
                if comment_on_post(gateway, token, post["id"]):
                    cc += 1
            return rc, cc

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_interact, u) for u in users]
            done = 0
            for f in as_completed(futs):
                done += 1
                r, c = f.result()
                rxn_count += r
                cmt_count += c
                if done % 50 == 0 or done == len(users):
                    print(f"  [{done}/{len(users)}]  {rxn_count} reactions, "
                          f"{cmt_count} comments")

    print(f"  ✓ {rxn_count} reactions, {cmt_count} comments "
          f"in {time.time() - t3:.1f}s")

    # ── Phase 5: Create YOUR posts ───────────────────────────────────
    print(f"\n=== Phase 5: Creating {my_posts_count} posts for YOU ===")
    t4 = time.time()
    my_posts: list[dict] = []
    for _ in range(my_posts_count):
        p = create_post(gateway, my_token)
        if p:
            my_posts.append(p)
    print(f"  ✓ {len(my_posts)} posts in {time.time() - t4:.1f}s")

    # ── Phase 6: Fake users react & comment on YOUR posts ────────────
    print("\n=== Phase 6: Fake users interact with YOUR posts ===")
    t5 = time.time()
    my_rxn = 0
    my_cmt = 0

    if my_posts:
        def _interact_mine(user_tuple):
            _, token, _ = user_tuple
            rc, cc = 0, 0
            for post in my_posts:
                # ~70% chance each user reacts to each of your posts
                if random.random() < 0.7:
                    if react_to_post(gateway, token, post["id"]):
                        rc += 1
                # ~30% chance each user comments
                if random.random() < 0.3:
                    if comment_on_post(gateway, token, post["id"]):
                        cc += 1
            return rc, cc

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_interact_mine, u) for u in users]
            done = 0
            for f in as_completed(futs):
                done += 1
                r, c = f.result()
                my_rxn += r
                my_cmt += c
                if done % 50 == 0 or done == len(users):
                    print(f"  [{done}/{len(users)}]  {my_rxn} reactions, "
                          f"{my_cmt} comments on your posts")

    print(f"  ✓ {my_rxn} reactions, {my_cmt} comments on your posts "
          f"in {time.time() - t5:.1f}s")

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
    print(f"{'=' * 55}")


if __name__ == "__main__":
    main()
