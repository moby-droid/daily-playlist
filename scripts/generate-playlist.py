#!/usr/bin/env python3
"""
Daily Playlist Generator
Analyzes Spotify listening history, researches new music, creates a playlist.
Outputs a JSON file for the Vercel site.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# Config
TOKENS_FILE = os.path.expanduser("~/.config/spotify/tokens.json")
CLIENT_ID = os.environ["SPOTIFY_CLIENT_ID"]
CLIENT_SECRET = os.environ["SPOTIFY_CLIENT_SECRET"]
BRAVE_API_KEY = os.environ["BRAVE_API_KEY"]
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
PLAYLIST_SIZE = 20  # tracks per daily playlist


def load_tokens():
    with open(TOKENS_FILE) as f:
        return json.load(f)


def refresh_token(tokens):
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }).encode()
    req = urllib.request.Request("https://accounts.spotify.com/api/token", data=data, method="POST")
    with urllib.request.urlopen(req) as r:
        new = json.loads(r.read())
    tokens["access_token"] = new["access_token"]
    if "refresh_token" in new:
        tokens["refresh_token"] = new["refresh_token"]
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    return tokens


def spotify_get(endpoint, token):
    url = f"https://api.spotify.com/v1{endpoint}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return None  # token expired
        raise


def spotify_post(endpoint, token, data):
    url = f"https://api.spotify.com/v1{endpoint}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    })
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def brave_search(query, max_results=3):
    url = f"https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(query)}&count={max_results}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_API_KEY,
    })
    try:
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
        return [{"title": r["title"], "desc": r.get("description", "")} for r in data.get("web", {}).get("results", [])]
    except:
        return []


def get_listening_profile(token):
    """Analyze recent listening to understand current mood/taste."""
    recent = spotify_get("/me/player/recently-played?limit=50", token) or {}
    top_short = spotify_get("/me/top/tracks?limit=30&time_range=short_term", token) or {}
    top_artists = spotify_get("/me/top/artists?limit=20&time_range=short_term", token) or {}

    # Extract genres and artists
    genres = {}
    artists = {}
    recent_track_ids = set()

    for item in recent.get("items", []):
        t = item["track"]
        recent_track_ids.add(t["id"])
        for a in t["artists"]:
            artists[a["id"]] = a["name"]

    for a in top_artists.get("items", []):
        for g in a.get("genres", []):
            genres[g] = genres.get(g, 0) + 1
        artists[a["id"]] = a["name"]

    top_genres = sorted(genres.items(), key=lambda x: -x[1])[:10]
    top_artist_names = list(artists.values())[:10]

    return {
        "genres": [g[0] for g in top_genres],
        "artists": top_artist_names,
        "recent_track_ids": recent_track_ids,
        "top_tracks": top_short.get("items", []),
    }


def search_spotify(query, token, limit=5):
    results = spotify_get(f"/search?q={urllib.parse.quote(query)}&type=track&limit={limit}", token)
    return results.get("tracks", {}).get("items", []) if results else []


def get_recommendations(token, seed_tracks, seed_artists, seed_genres):
    """Use Spotify's recommendation engine."""
    params = []
    if seed_tracks:
        params.append(f"seed_tracks={','.join(seed_tracks[:2])}")
    if seed_artists:
        params.append(f"seed_artists={','.join(seed_artists[:2])}")
    if seed_genres:
        # URL-encode genre names (they can have spaces)
        encoded = [urllib.parse.quote(g) for g in seed_genres[:1]]
        params.append(f"seed_genres={','.join(encoded)}")
    
    # Need at least one seed
    if not params:
        return []
    
    # Max 5 seeds total
    params.append("limit=30")
    endpoint = f"/recommendations?{'&'.join(params)}"
    try:
        result = spotify_get(endpoint, token)
        return result.get("tracks", []) if result else []
    except Exception as e:
        print(f"   ⚠️ Recommendations failed: {e}")
        return []


def research_new_music(profile):
    """Search for new/underground artists similar to listening profile."""
    discoveries = []
    
    # Build search queries from top genres and artists
    queries = []
    for genre in profile["genres"][:3]:
        queries.append(f"best new {genre} artists 2025 2026 underground")
        queries.append(f"emerging {genre} musicians similar to {profile['artists'][0] if profile['artists'] else ''}")
    
    for artist in profile["artists"][:3]:
        queries.append(f"artists similar to {artist} underground new")

    seen_urls = set()
    for q in queries[:6]:  # Limit API calls
        results = brave_search(q, 3)
        for r in results:
            if r["title"] not in seen_urls:
                seen_urls.add(r["title"])
                discoveries.append(r)

    return discoveries[:10]


def build_playlist(token, profile, research):
    """Build a playlist mixing recommendations and research discoveries."""
    tracks = []
    seen_ids = set(profile["recent_track_ids"])  # Avoid recently played

    # 1. Get related artists' tracks via search (recommendations endpoint removed Feb 2026)
    for artist_name in profile["artists"][:6]:
        if len(tracks) >= PLAYLIST_SIZE // 2:
            break
        # Search for the artist's popular tracks we haven't heard
        results = search_spotify(f"artist:{artist_name}", token, 10)
        for t in results:
            if t["id"] not in seen_ids and len(tracks) < PLAYLIST_SIZE // 2:
                seen_ids.add(t["id"])
                tracks.append({
                    "id": t["id"],
                    "uri": t["uri"],
                    "name": t["name"],
                    "artist": t["artists"][0]["name"],
                    "album": t["album"]["name"],
                    "art": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
                    "url": t["external_urls"]["spotify"],
                    "reason": f"Deep cut from {artist_name} — you've been listening to them lately",
                    "isNew": False,
                })
                break  # One per artist to keep variety

    # 2. Search for discoveries from research
    for disc in research:
        if len(tracks) >= PLAYLIST_SIZE:
            break
        # Extract artist/track names from research titles
        search_q = disc["title"].split(" - ")[0].split(" | ")[0][:60]
        results = search_spotify(search_q, token, 3)
        for t in results:
            if t["id"] not in seen_ids:
                seen_ids.add(t["id"])
                tracks.append({
                    "id": t["id"],
                    "uri": t["uri"],
                    "name": t["name"],
                    "artist": t["artists"][0]["name"],
                    "album": t["album"]["name"],
                    "art": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
                    "url": t["external_urls"]["spotify"],
                    "reason": f"🔍 Discovery: {disc['desc'][:100]}" if disc['desc'] else "New find based on your taste",
                    "isNew": True,
                })
                break

    # 3. Fill remaining with genre/mood searches
    genre_searches = [
        "new deep house 2026",
        "underground funk soul 2026",
        "japanese city pop new",
        "electronic jazz fusion",
        "lo-fi beats chill",
    ]
    # Customize based on their genres
    for genre in profile["genres"][:3]:
        genre_searches.insert(0, f"new {genre} 2026 underground")
    
    for search_q in genre_searches:
        if len(tracks) >= PLAYLIST_SIZE:
            break
        results = search_spotify(search_q, token, 5)
        for t in results:
            if t["id"] not in seen_ids and len(tracks) < PLAYLIST_SIZE:
                seen_ids.add(t["id"])
                tracks.append({
                    "id": t["id"],
                    "uri": t["uri"],
                    "name": t["name"],
                    "artist": t["artists"][0]["name"],
                    "album": t["album"]["name"],
                    "art": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
                    "url": t["external_urls"]["spotify"],
                    "reason": f"Fresh from the {search_q.split(' ')[1] if len(search_q.split()) > 1 else 'music'} scene",
                    "isNew": True,
                })
                break

    return tracks


def create_spotify_playlist(token, tracks, date_str, vibe):
    """Create the playlist on Spotify."""
    name = f"Daily Discoveries — {date_str}"
    
    playlist = spotify_post("/me/playlists", token, {
        "name": name,
        "description": f"{vibe} | Curated by Moby 🏂",
        "public": False,
    })
    
    playlist_id = playlist["id"]
    uris = [t["uri"] for t in tracks]
    
    # Use /items endpoint (Feb 2026 change)
    if uris:
        spotify_post(f"/playlists/{playlist_id}/items", token, {"uris": uris})
    
    return {
        "id": playlist_id,
        "url": playlist["external_urls"]["spotify"],
        "name": name,
    }


def generate_vibe(profile):
    """Generate a one-line vibe description."""
    genres = profile["genres"][:3]
    artists = profile["artists"][:3]
    
    if genres and artists:
        return f"You've been vibing with {', '.join(artists[:2])} lately — today's mix leans into {', '.join(genres[:2])} with some fresh discoveries."
    elif artists:
        return f"Based on your recent {', '.join(artists[:2])} rotation — here's what's next."
    else:
        return "Fresh picks based on your listening history."


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"🎵 Generating daily playlist for {today}...")

    # Load and refresh token
    tokens = load_tokens()
    tokens = refresh_token(tokens)
    token = tokens["access_token"]

    # Analyze listening
    print("📊 Analyzing your listening history...")
    profile = get_listening_profile(token)
    print(f"   Top genres: {', '.join(profile['genres'][:5])}")
    print(f"   Top artists: {', '.join(profile['artists'][:5])}")

    # Research new music
    print("🔍 Researching new music...")
    research = research_new_music(profile)
    print(f"   Found {len(research)} research leads")

    # Build playlist
    print("🎶 Building playlist...")
    tracks = build_playlist(token, profile, research)
    print(f"   {len(tracks)} tracks selected")

    # Generate vibe
    vibe = generate_vibe(profile)

    # Create Spotify playlist
    print("📝 Creating Spotify playlist...")
    sp_playlist = create_spotify_playlist(token, tracks, today, vibe)
    print(f"   ✅ {sp_playlist['url']}")

    # Save data for Vercel site
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output = {
        "date": today,
        "vibe": vibe,
        "playlistUrl": sp_playlist["url"],
        "playlistName": sp_playlist["name"],
        "tracks": [{
            "name": t["name"],
            "artist": t["artist"],
            "album": t["album"],
            "art": t["art"],
            "url": t["url"],
            "reason": t["reason"],
            "isNew": t["isNew"],
        } for t in tracks],
    }

    output_file = os.path.join(OUTPUT_DIR, f"{today}.json")
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"   💾 Saved to {output_file}")

    return output


if __name__ == "__main__":
    result = main()
    print(f"\n🏂 Done! {len(result['tracks'])} tracks in today's playlist.")
