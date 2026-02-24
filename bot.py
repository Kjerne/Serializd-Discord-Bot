"""
Serializd → Discord Bot  (v2)
────────────────────────────
Polls Serializd diaries for multiple users and posts rich embeds to Discord.
All settings are persisted in config.json — no restart needed after changes.
"""

import json
import logging
import os
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

# ─── Static env config ────────────────────────────────────────────────────────
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_MINUTES", "5"))
BOT_NAME = os.getenv("BOT_NAME", "Serializd Bot")
BOT_ICON_URL = os.getenv("BOT_ICON_URL", "https://www.serializd.com/android-chrome-192x192.png")
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0")) if os.getenv("ADMIN_ROLE_ID") else None
STATUS_ROTATION_SECONDS = int(os.getenv("STATUS_ROTATION_SECONDS", "30"))
AUTHOR_ICON_URL = os.getenv("AUTHOR_ICON_URL", "https://cdn.discordapp.com/attachments/446258800069181440/1475938857878032384/Serializd_Icon_3801.png?ex=699f4ead&is=699dfd2d&hm=a3abff3c8b71821fc310631dfa5fbf13a84ab3e91ee56a4714baa096ddb8d57b&animated=true")

# Star emoji IDs
FULL_STAR_EMOJI_ID = os.getenv("FULL_STAR_EMOJI_ID", "1475958462457446552")
HALF_STAR_EMOJI_ID = os.getenv("HALF_STAR_EMOJI_ID", "1475958876053573812")

# Custom status messages (up to 3)
CUSTOM_STATUSES = []
for i in range(1, 4):
    status = os.getenv(f"CUSTOM_STATUS_{i}", "").strip()
    if status:
        CUSTOM_STATUSES.append(status)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("serializd-bot")

# ─── Paths ────────────────────────────────────────────────────────────────────
CONFIG_FILE = Path("config.json")
SEEN_FILE   = Path("seen_entries.json")

# ─── Default config ───────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "post_channel_id": None,
    "commands_channel_id": None,
    "sharelink_channel_id": None,
    "users": [],
    "restrict_to_role": False,
    "allowed_role_ids": [],
    "command_permissions": {},  # {command_name: "admin" | "any" | "roles"}
    "sharelinks": {},  # {user_id: {"serializd": "username", "letterboxd": "username"}}
}

SERIALIZD_COLOUR = 0x6C63FF
START_TIME = datetime.now(timezone.utc)

# ─── API Constants ────────────────────────────────────────────────────────────
BASE_API = "https://www.serializd.com/api"
BASE_SHOWS_URL = "https://www.serializd.com/api/user/"

# ─── Bot initialization ───────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ─── Config helpers ───────────────────────────────────────────────────────────
def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            return {**DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

# ─── Seen-entry persistence ───────────────────────────────────────────────────
def load_seen() -> dict:
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text())
        except Exception:
            pass
    return {}

def save_seen(seen: dict) -> None:
    SEEN_FILE.write_text(json.dumps(seen, indent=2))

def get_seen_for(username: str) -> set:
    return set(load_seen().get(username, []))

def mark_seen(username: str, ids: set) -> None:
    seen = load_seen()
    existing = set(seen.get(username, []))
    seen[username] = list(existing | ids)
    save_seen(seen)

# ─── Serializd API / Scraping ────────────────────────────────────────────────
async def fetch_diary(session: aiohttp.ClientSession, username: str, hours_limit: int = None) -> list:
    """
    Fetch diary entries using the Serializd API.
    Uses the same endpoint and headers as the working implementation.
    
    Args:
        session: aiohttp session
        username: Serializd username
        hours_limit: If provided, only return entries from last N hours
    """
    # Use the correct API endpoint that works
    api_url = f"https://www.serializd.com/api/user/{username}/diary"
    
    # Headers that match the working Go implementation
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Dnt": "1",
        "Referer": api_url,
        "Sec-Ch-Ua": '"Chromium";v="123", "Not:A-Brand";v="8"',
        "Sec-Ch-Ua-Mobile": "?1",
        "Sec-Ch-Ua-Platform": '"Android"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
        "X-Requested-With": "serializd_vercel",  # CRITICAL: This header is required
    }
    
    try:
        async with session.get(
            api_url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status == 200:
                # aiohttp automatically handles gzip decompression
                data = await resp.json(content_type=None)
                
                # DEBUG: Log raw API response to see actual structure
                if data and "reviews" in data:
                    log.debug(f"=== RAW API RESPONSE FOR {username} ===")
                    log.debug(f"Total reviews in response: {len(data.get('reviews', []))}")
                    if data.get('reviews'):
                        first_entry = data['reviews'][0]
                        log.debug(f"First entry sample:")
                        log.debug(f"  - dateAdded: {first_entry.get('dateAdded')}")
                        log.debug(f"  - backdate: {first_entry.get('backdate')}")
                        log.debug(f"  - tags: {first_entry.get('tags')}")
                        log.debug(f"  - containsSpoiler: {first_entry.get('containsSpoiler')}")
                        log.debug(f"  - All keys: {list(first_entry.keys())}")
                    log.debug(f"========================================")
                
                # The API returns a structure with 'reviews' array
                entries = extract_entries(data)
                
                # Filter by time if requested
                if hours_limit and entries:
                    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_limit)
                    filtered = []
                    for entry in entries:
                        # Use backdate (when watched) or dateAdded (when logged)
                        date_str = entry.get("backdate") or entry.get("dateAdded", "")
                        try:
                            entry_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            if entry_time >= cutoff_time:
                                filtered.append(entry)
                            else:
                                log.debug(f"  Filtered out entry from {entry_time} (older than {cutoff_time})")
                        except Exception as e:
                            # If we can't parse date, exclude it to be safe during initial scan
                            log.debug(f"  Could not parse date '{date_str}': {e}")
                            continue
                    entries = filtered
                    log.debug(f"  After 24h filter: {len(entries)} entries remain")
                
                if entries:
                    log.debug(f"✓ Successfully fetched {len(entries)} diary entries for {username}")
                    return entries
                else:
                    log.debug(f"⚠ API returned empty data for {username}")
                    return []
            else:
                log.warning(f"⚠️  API request failed with status {resp.status} for '{username}'")
                log.warning(f"💡 Check if profile exists: https://www.serializd.com/user/{username}/profile")
                return []
                
    except asyncio.TimeoutError:
        log.warning(f"⚠️  API request timed out for '{username}'")
        return []
    except Exception as e:
        log.error(f"❌ Error fetching diary for {username}: {type(e).__name__}: {str(e)}")
        return []


def extract_entries(data) -> list:
    """
    Extract diary entries from Serializd API response.
    The API returns data with a 'reviews' array.
    """
    if isinstance(data, list):
        return data
    
    # Serializd API uses 'reviews' as the main key
    if "reviews" in data and isinstance(data["reviews"], list):
        return data["reviews"]
    
    # Fallback: check other possible keys
    for key in ("entries", "logs", "diary", "items", "results", "data"):
        if key in data and isinstance(data[key], list):
            return data[key]
    
    return []

def entry_id(entry: dict, username: str) -> str:
    """
    Generate a unique ID for a diary entry.
    Uses 'id' field from Serializd API, falls back to composite key.
    """
    # Serializd API provides an 'id' field
    if "id" in entry:
        return f"{username}:{entry['id']}"
    
    # Fallback for other possible ID fields
    for field in ("logId", "log_id", "entryId", "entry_id"):
        if field in entry:
            return f"{username}:{entry[field]}"
    
    # Last resort: create composite key
    show = entry.get("showName", "")
    date = entry.get("dateAdded") or entry.get("backdate", "")
    ep = entry.get("episodeNumber", "")
    return f"{username}:{show}-{date}-{ep}"

# ─── Embed builder ────────────────────────────────────────────────────────────
def build_embed(entry: dict, username: str) -> discord.Embed:
    """
    Build a Discord embed from a Serializd diary entry.
    Handles the actual field names from the Serializd API.
    """
    # Get show name - API uses 'showName' directly
    show_name = entry.get("showName", "Unknown Show")
    
    # Get show ID and URL
    show_id = entry.get("showId", "")
    show_url = (
        f"https://www.serializd.com/show/{show_id}"
        if show_id else f"https://www.serializd.com/user/{username}/diary"
    )
    
    # Get season and episode info
    season_name = entry.get("seasonName", "")
    season_num = entry.get("seasonNumber")
    episode_num = entry.get("episodeNumber")
    season_id = entry.get("seasonId")
    
    # Fallback: If seasonName is empty but we have seasonId, try to find it in showSeasons array
    if (not season_name or not season_name.strip()) and season_id:
        show_seasons = entry.get("showSeasons", [])
        for season in show_seasons:
            if season.get("id") == season_id:
                season_name = season.get("name", "")
                if not season_num:
                    season_num = season.get("seasonNumber")
                log.info(f"Found season info in showSeasons array: {season_name} (#{season_num})")
                break
    
    # Comprehensive debug logging
    log.info(f"=== Building embed for: {show_name} ===")
    log.info(f"Entry ID: {entry.get('id')}")
    log.info(f"Season ID: {season_id}")
    log.info(f"Season Name: '{season_name}' (type: {type(season_name)})")
    log.info(f"Season Number: {season_num} (type: {type(season_num)})")
    log.info(f"Episode Number: {episode_num} (type: {type(episode_num)})")
    
    # Check if season info exists in showSeasons
    show_seasons = entry.get("showSeasons", [])
    if show_seasons:
        log.info(f"showSeasons array has {len(show_seasons)} season(s)")
        for i, s in enumerate(show_seasons):
            log.info(f"  Season {i}: id={s.get('id')}, name={s.get('name')}, seasonNumber={s.get('seasonNumber')}")
    
    log.info("=" * 50)
    
    # Get rating (convert from 10-point to 5-point scale with emoji stars)
    rating = entry.get("rating")
    stars = ""
    if rating is not None and rating > 0:
        try:
            # Convert 10-point scale to 5-point scale
            r = float(rating) / 2.0
            full = int(r)
            half = 1 if (r - full) >= 0.5 else 0
            
            # Use custom Discord emojis from .env with spaces between them
            full_star = f"<:FullStar:{FULL_STAR_EMOJI_ID}>"
            half_star = f"<:HalfStar:{HALF_STAR_EMOJI_ID}>"
            
            # Build star string with spaces
            star_emojis = " ".join([full_star] * full)
            if half:
                star_emojis += f" {half_star}" if star_emojis else half_star
            
            # Add rating number
            stars = f"{star_emojis}  ({r}/5)" if star_emojis else f"({r}/5)"
        except (ValueError, TypeError):
            # If conversion fails, just skip rating display
            pass

    # Get date - API uses 'dateAdded' or 'backdate'
    raw_date = entry.get("dateAdded") or entry.get("backdate", "")
    date_str = ""
    timestamp = None
    try:
        dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        date_str = dt.strftime("%d %b %Y")
        timestamp = int(dt.timestamp())
    except Exception:
        date_str = raw_date or "Unknown date"

    # Get entry ID for diary link
    entry_id_val = entry.get("id", "")
    
    # Build URL - link to diary entry if we have an ID, otherwise fall back to show
    if entry_id_val:
        entry_url = f"https://www.serializd.com/user/{username}/diary/{entry_id_val}"
    elif show_id:
        entry_url = f"https://www.serializd.com/show/{show_id}"
    else:
        entry_url = f"https://www.serializd.com/user/{username}/diary"

    # Get poster/banner image
    poster = entry.get("showBannerImage", "")
    if poster and not poster.startswith("http"):
        poster = f"https://image.tmdb.org/t/p/w300{poster}"
    
    # Build title with proper season/episode handling
    title = f"📺  {show_name}"
    
    # Check if we have season information
    has_season_name = season_name and season_name.strip()
    has_season_num = season_num is not None
    has_episode_num = episode_num is not None
    
    log.info(f"Title building flags: season_name={has_season_name}, season_num={has_season_num}, episode_num={has_episode_num}")
    
    # Add season information
    if has_season_name:
        log.info(f"Adding season name: {season_name}")
        title += f"  ·  {season_name}"
    elif has_season_num:
        log.info(f"Adding season number: {season_num}")
        title += f"  ·  Season {int(season_num)}"
    else:
        log.warning(f"No season information available for {show_name}")
    
    # Add episode information if this is an episode log (with dot separator)
    if has_episode_num:
        log.info(f"Adding episode number: {episode_num}")
        title += f"  ·  Episode {int(episode_num)}"
    
    log.info(f"Final title: {title}")

    # Build description
    parts = []
    
    # Timestamp
    if timestamp:
        parts.append(f"**Logged:** <t:{timestamp}:R> (<t:{timestamp}:f>)")
    elif date_str:
        parts.append(f"**Logged:** {date_str}")
    
    # Rating
    if stars:
        parts.append(f"**Rating:** {stars}")
    
    # Liked status - show both liked and not liked
    like_status = entry.get("like")
    if like_status is True:
        parts.append("**❤️ Liked**")
    elif like_status is False:
        parts.append("**💔 Not Liked**")
    
    # Rewatch indicator - API uses both 'isRewatched' and 'isRewatch'
    is_rewatched = entry.get("isRewatched") or entry.get("isRewatch", False)
    log.debug(f"Rewatch status: isRewatched={entry.get('isRewatched')}, isRewatch={entry.get('isRewatch')}, final={is_rewatched}")
    
    if is_rewatched:
        parts.append("**🔄 Rewatched**")
    else:
        parts.append("**👀 First Watch**")
    
    # Tags
    tags = entry.get("tags", [])
    if tags and isinstance(tags, list) and len(tags) > 0:
        tag_text = ", ".join(f"#{tag}" for tag in tags[:5])  # Limit to 5 tags
        parts.append(f"**Tags:** {tag_text}")
    
    # Debug log if tags field exists but is empty/wrong format
    if "tags" in entry:
        log.debug(f"Tags field present: {entry.get('tags')} (type: {type(entry.get('tags'))})")
    
    # Review text with spoiler support
    review = entry.get("reviewText", "")
    if review:
        review_text = review if len(review) <= 300 else review[:297] + "…"
        # Check for spoilers - field might be 'containsSpoiler' or 'containsSpoilers'
        has_spoilers = entry.get("containsSpoiler") or entry.get("containsSpoilers")
        if has_spoilers:
            parts.append(f"\n**Review:** ||{review_text}||")
        else:
            parts.append(f"\n**Review:** {review_text}")

    embed = discord.Embed(
        title=title,
        url=entry_url,
        description="\n".join(parts) or None,
        color=SERIALIZD_COLOUR,
    )
    
    # Use author icon from environment variable
    embed.set_author(
        name=f"{username} logged on Serializd",
        url=f"https://www.serializd.com/user/{username}/diary",
        icon_url=AUTHOR_ICON_URL if AUTHOR_ICON_URL else None,
    )
    if poster:
        embed.set_thumbnail(url=poster)
    
    # Footer icon from .env (can be left empty to not show an icon)
    footer_icon = BOT_ICON_URL if BOT_ICON_URL else None
    embed.set_footer(text=BOT_NAME, icon_url=footer_icon)
    
    # Set timestamp if available
    if timestamp:
        embed.timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    
    return embed

# ─── Permission helpers ───────────────────────────────────────────────────────
def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator

async def check_user_command_allowed(interaction: discord.Interaction) -> bool:
    cfg = load_config()

    cmd_ch = cfg.get("commands_channel_id")
    if cmd_ch and interaction.channel_id != cmd_ch:
        await interaction.response.send_message(
            f"❌ Commands can only be used in <#{cmd_ch}>.", ephemeral=True
        )
        return False

    if cfg.get("restrict_to_role"):
        allowed_ids = cfg.get("allowed_role_ids", [])
        if not allowed_ids:
            await interaction.response.send_message(
                "❌ Role restriction is enabled but no roles have been added. Ask an admin to use `/addrole`.",
                ephemeral=True,
            )
            return False
        member = interaction.guild.get_member(interaction.user.id)
        member_role_ids = {r.id for r in member.roles} if member else set()
        if not member_role_ids.intersection(allowed_ids):
            role_mentions = " or ".join(
                f"**{interaction.guild.get_role(rid).name}**"
                if interaction.guild.get_role(rid) else f"<@&{rid}>"
                for rid in allowed_ids
            )
            await interaction.response.send_message(
                f"❌ You need one of the following roles to use this command: {role_mentions}",
                ephemeral=True,
            )
            return False

    return True

# ─── Serializd API Functions ─────────────────────────────────────────────────
def get_api_headers(url: str) -> dict:
    """
    Get standard headers for Serializd API requests.
    """
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Dnt": "1",
        "Referer": url,
        "Sec-Ch-Ua": '"Chromium";v="123", "Not:A-Brand";v="8"',
        "Sec-Ch-Ua-Mobile": "?1",
        "Sec-Ch-Ua-Platform": '"Android"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
        "X-Requested-With": "serializd_vercel",
    }

async def fetch_api_data(session: aiohttp.ClientSession, url: str, endpoint_name: str, username: str) -> dict:
    """
    Generic function to fetch data from Serializd API.
    Returns the parsed JSON data or empty dict on failure.
    """
    try:
        async with session.get(
            url,
            headers=get_api_headers(url),
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                return data
            else:
                log.debug(f"{endpoint_name} fetch failed with status {resp.status} for {username}")
                return {}
    except asyncio.TimeoutError:
        log.debug(f"{endpoint_name} request timed out for {username}")
        return {}
    except Exception as e:
        log.debug(f"Exception while fetching {endpoint_name} for {username}: {e}")
        return {}

async def get_currently_watching(username: str) -> dict:
    """
    Fetch currently watching shows for a user.
    Returns dict with 'items', 'totalItems', 'totalPages'.
    """
    url = f"{BASE_SHOWS_URL}{username}/currently_watching_page/1?sort_by=date_added_desc"
    async with aiohttp.ClientSession() as session:
        return await fetch_api_data(session, url, "Currently Watching", username)

async def get_watchlist(username: str, page: int = 1) -> dict:
    """
    Fetch watchlist for a user.
    Returns dict with 'items', 'numberOfShows', 'totalPages'.
    """
    url = f"{BASE_SHOWS_URL}{username}/watchlistpage_v2/{page}?sort_by=date_added_desc"
    async with aiohttp.ClientSession() as session:
        return await fetch_api_data(session, url, "Watchlist", username)

async def get_watched(username: str, page: int = 1) -> dict:
    """
    Fetch watched shows for a user.
    Returns dict with 'items', 'numberOfShows', 'numberOfSeasons', 'totalPages'.
    """
    url = f"{BASE_SHOWS_URL}{username}/watchedpage_v2/{page}?sort_by=date_added_desc"
    async with aiohttp.ClientSession() as session:
        return await fetch_api_data(session, url, "Watched", username)

async def get_paused(username: str) -> dict:
    """
    Fetch paused shows for a user.
    Returns dict with 'items', 'totalItems', 'totalPages'.
    """
    url = f"{BASE_SHOWS_URL}{username}/paused_shows_page/1?sort_by=date_added_desc"
    async with aiohttp.ClientSession() as session:
        return await fetch_api_data(session, url, "Paused", username)

async def get_dropped(username: str) -> dict:
    """
    Fetch dropped shows for a user.
    Returns dict with 'items', 'totalItems', 'totalPages'.
    """
    url = f"{BASE_SHOWS_URL}{username}/dropped_shows_page/1?sort_by=date_added_desc"
    async with aiohttp.ClientSession() as session:
        return await fetch_api_data(session, url, "Dropped", username)

# ─── Polling task ─────────────────────────────────────────────────────────────
@tasks.loop(minutes=POLL_INTERVAL)
async def poll_diaries():
    """Poll all tracked users and post new diary entries"""
    cfg = load_config()
    users = cfg.get("users", [])
    post_ch_id = cfg.get("post_channel_id")

    log.info("=" * 60)
    log.info(f"🔍 Starting diary poll check at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    if not users:
        log.warning("⚠️  No users configured, skipping poll.")
        log.info("=" * 60)
        return

    if not post_ch_id:
        log.warning("⚠️  No post channel configured, skipping poll.")
        log.info("=" * 60)
        return

    channel = bot.get_channel(post_ch_id)
    if not channel:
        log.error(f"❌ Could not find channel {post_ch_id}")
        log.info("=" * 60)
        return

    log.info(f"👥 Checking {len(users)} user(s): {', '.join(users)}")

    total_new_entries = 0
    async with aiohttp.ClientSession() as session:
        for username in users:
            try:
                log.info(f"   📡 Fetching diary for: {username}")
                # Always filter to last 7 days to prevent posting old entries
                # (in case seen list gets corrupted or is empty)
                entries = await fetch_diary(session, username, hours_limit=168)  # 7 days
                
                if not entries:
                    log.info(f"   ℹ️  No entries found for {username}")
                    continue

                log.info(f"   ✓ Retrieved {len(entries)} total entry/entries for {username}")
                
                seen = get_seen_for(username)
                new_entries = []

                for entry in entries:
                    eid = entry_id(entry, username)
                    show_name = entry.get("showName", "Unknown")
                    
                    if eid not in seen:
                        # Double-check date is recent (last 7 days)
                        date_str = entry.get("backdate") or entry.get("dateAdded", "")
                        log.debug(f"      Checking {show_name}: dateAdded={entry.get('dateAdded')}, backdate={entry.get('backdate')}")
                        
                        try:
                            entry_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
                            
                            log.debug(f"        Entry time: {entry_time}, Cutoff: {cutoff}, Is recent: {entry_time >= cutoff}")
                            
                            if entry_time >= cutoff:
                                new_entries.append(entry)
                                seen.add(eid)
                                log.debug(f"        ✓ Added to new_entries")
                            else:
                                log.info(f"      ⏭️  Skipping old entry: {show_name} from {entry_time.strftime('%Y-%m-%d %H:%M')}")
                        except Exception as e:
                            # If can't parse date, skip it to be safe
                            log.info(f"      ⚠️  Skipping entry with unparseable date: {show_name} (date: {date_str}, error: {e})")
                            continue
                    else:
                        log.debug(f"      Already seen: {show_name}")

                if new_entries:
                    total_new_entries += len(new_entries)
                    log.info(f"   ✨ Found {len(new_entries)} NEW entry/entries for {username}")
                    # Post in chronological order (oldest first)
                    for entry in reversed(new_entries):
                        show_name = entry.get("showName") or (entry.get("show") or {}).get("name", "Unknown")
                        ep_num = entry.get("episodeNumber")
                        season_num = entry.get("seasonNumber")
                        season_name = entry.get("seasonName", "")
                        
                        # Build log message with season/episode info
                        if season_name and ep_num is not None:
                            ep_info = f" - {season_name} Ep{int(ep_num)}"
                        elif season_num is not None and ep_num is not None:
                            ep_info = f" S{int(season_num):02d}E{int(ep_num):02d}"
                        elif season_name:
                            ep_info = f" - {season_name}"
                        elif season_num is not None:
                            ep_info = f" - Season {int(season_num)}"
                        else:
                            ep_info = ""
                        
                        log.info(f"      → Posting: {show_name}{ep_info}")
                        
                        # Debug: Log entry data to help troubleshoot
                        log.debug(f"      Entry data - seasonName: '{season_name}', seasonNumber: {season_num}, episodeNumber: {ep_num}")
                        log.debug(f"      Tags: {entry.get('tags')}, HasReview: {bool(entry.get('reviewText'))}, Spoilers: {entry.get('containsSpoiler')}")
                        
                        embed = build_embed(entry, username)
                        await channel.send(embed=embed)
                    
                    mark_seen(username, seen)
                else:
                    log.info(f"   ✓ No new entries for {username} (all previously seen)")

            except Exception as e:
                log.error(f"   ❌ Error polling {username}: {e}")

    if total_new_entries > 0:
        log.info(f"📝 Poll complete: Posted {total_new_entries} new entry/entries total")
    else:
        log.info(f"✓ Poll complete: No new entries found")
    log.info("=" * 60)

@poll_diaries.before_loop
async def before_poll():
    await bot.wait_until_ready()
    log.info("=" * 60)
    log.info(f"🔄 Polling task initialized")
    log.info(f"⏱️  Check interval: Every {POLL_INTERVAL} minute(s)")
    log.info(f"⏰ First check will occur in {POLL_INTERVAL} minute(s)")
    log.info("=" * 60)

# ─── Status rotation task ─────────────────────────────────────────────────────
@tasks.loop(seconds=STATUS_ROTATION_SECONDS)
async def rotate_status():
    """Rotate bot status between different messages"""
    cfg = load_config()
    users = cfg.get("users", [])
    
    # Calculate uptime
    now = datetime.now(timezone.utc)
    uptime = now - START_TIME
    hours, rem = divmod(int(uptime.total_seconds()), 3600)
    mins, _ = divmod(rem, 60)
    
    # Build status list - always include Tracking and Uptime
    statuses = [
        f"Tracking {len(users)} user{'s' if len(users) != 1 else ''}",
        f"Uptime: {hours}h {mins}m"
    ]
    
    # Add custom statuses from .env if any are configured
    statuses.extend(CUSTOM_STATUSES)
    
    # Use modulo to cycle through statuses
    status_index = (rotate_status.current_loop % len(statuses))
    status_text = statuses[status_index]
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=status_text
        )
    )

@rotate_status.before_loop
async def before_rotate_status():
    await bot.wait_until_ready()
    log.info("🔄 Status rotation task initialized")

# ─── Bot events ───────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    log.info("=" * 60)
    log.info(f"✅ Bot logged in as {bot.user}")
    log.info(f"🌐 Connected to {len(bot.guilds)} guild(s)")
    
    # Load and display config
    cfg = load_config()
    users = cfg.get("users", [])
    post_ch_id = cfg.get("post_channel_id")
    
    if users:
        log.info(f"👥 Tracking {len(users)} user(s): {', '.join(users)}")
    else:
        log.warning("⚠️  No users configured yet. Use /adduser to add users.")
    
    if post_ch_id:
        log.info(f"📢 Post channel ID: {post_ch_id}")
    else:
        log.warning("⚠️  No post channel set. Use /setchannel to configure.")
    
    # Sync slash commands
    try:
        synced = await tree.sync()
        log.info(f"✅ Synced {len(synced)} slash command(s)")
    except Exception as e:
        log.error(f"❌ Failed to sync commands: {e}")
    
    # Start polling task
    if not poll_diaries.is_running():
        poll_diaries.start()
    
    # Start status rotation task
    if not rotate_status.is_running():
        rotate_status.start()
    
    log.info("=" * 60)

# ═══════════════════════════════════════════════════════════════════════════════
#  SLASH COMMANDS (Admin)
# ═══════════════════════════════════════════════════════════════════════════════

@tree.command(name="setchannel", description="[Admin] Set the channel for diary posts")
@app_commands.describe(channel="The channel where diary entries will be posted")
async def cmd_setchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    cfg = load_config()
    cfg["post_channel_id"] = channel.id
    save_config(cfg)
    await interaction.response.send_message(f"✅ Diary entries will now be posted in {channel.mention}.")

@tree.command(name="adduser", description="[Admin] Add a Serializd user to track")
@app_commands.describe(username="Serializd username (as it appears in the profile URL)")
async def cmd_adduser(interaction: discord.Interaction, username: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    cfg = load_config()
    username = username.strip().lstrip("@")
    if username in cfg["users"]:
        await interaction.response.send_message(f"⚠️ **{username}** is already being tracked.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    # Do initial scan for last 24 hours
    post_ch_id = cfg.get("post_channel_id")
    if post_ch_id:
        channel = bot.get_channel(post_ch_id)
        if channel:
            async with aiohttp.ClientSession() as session:
                # Fetch entries from last 24 hours
                entries = await fetch_diary(session, username, hours_limit=24)
                
                if entries:
                    await interaction.followup.send(
                        f"✅ Now tracking **{username}**\n"
                        f"🔗 <https://www.serializd.com/user/{username}/profile>\n"
                        f"📝 Found {len(entries)} entry/entries from last 24 hours. Posting to {channel.mention}..."
                    )
                    
                    # Post entries in chronological order (oldest first)
                    seen_ids = set()
                    for entry in reversed(entries):
                        embed = build_embed(entry, username)
                        await channel.send(embed=embed)
                        # Mark as seen
                        eid = entry_id(entry, username)
                        seen_ids.add(eid)
                    
                    # Mark all as seen
                    mark_seen(username, seen_ids)
                    
                    log.info(f"✅ Added {username} and posted {len(entries)} initial entries")
                else:
                    await interaction.followup.send(
                        f"✅ Now tracking **{username}**\n"
                        f"🔗 <https://www.serializd.com/user/{username}/profile>\n"
                        f"ℹ️ No entries found from last 24 hours."
                    )
        else:
            await interaction.followup.send(
                f"✅ Now tracking **{username}**\n"
                f"🔗 <https://www.serializd.com/user/{username}/profile>\n"
                f"⚠️ Post channel not found - configure with /setchannel first"
            )
    else:
        await interaction.followup.send(
            f"✅ Now tracking **{username}**\n"
            f"🔗 <https://www.serializd.com/user/{username}/profile>\n"
            f"⚠️ No post channel set - use /setchannel first to see diary entries"
        )
    
    # Add user to config
    cfg["users"].append(username)
    save_config(cfg)

@tree.command(name="removeuser", description="[Admin] Remove a tracked Serializd user")
@app_commands.describe(username="Serializd username to stop tracking")
async def cmd_removeuser(interaction: discord.Interaction, username: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    cfg = load_config()
    username = username.strip()
    if username not in cfg["users"]:
        await interaction.response.send_message(f"⚠️ **{username}** is not in the tracked list.", ephemeral=True)
        return
    
    cfg["users"].remove(username)
    save_config(cfg)
    await interaction.response.send_message(f"✅ Removed **{username}** from tracking.")

@tree.command(name="listusers", description="[Admin] Show all tracked users")
async def cmd_listusers(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    cfg = load_config()
    users = cfg.get("users", [])
    
    if not users:
        await interaction.response.send_message("⚠️ No users are currently being tracked.", ephemeral=True)
        return
    
    embed = discord.Embed(title="👥 Tracked Serializd Users", color=SERIALIZD_COLOUR)
    user_list = "\n".join(f"• [{u}](https://www.serializd.com/user/{u}/profile)" for u in users)
    embed.description = user_list
    embed.set_footer(text=f"Total: {len(users)} user(s)")
    await interaction.response.send_message(embed=embed)

@tree.command(name="setchannelcmd", description="[Admin] Restrict user commands to a specific channel")
@app_commands.describe(channel="Channel for user commands (leave empty to allow everywhere)")
async def cmd_setchannelcmd(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    cfg = load_config()
    if channel:
        cfg["commands_channel_id"] = channel.id
        save_config(cfg)
        await interaction.response.send_message(f"✅ User commands restricted to {channel.mention}.")
    else:
        cfg["commands_channel_id"] = None
        save_config(cfg)
        await interaction.response.send_message("✅ Commands restriction removed — commands work everywhere.")

@tree.command(name="toggleroles", description="[Admin] Enable/disable role restriction for user commands")
@app_commands.describe(enabled="True to enable role restriction, False to disable")
async def cmd_toggleroles(interaction: discord.Interaction, enabled: bool):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    cfg = load_config()
    cfg["restrict_to_role"] = enabled
    save_config(cfg)
    
    if enabled:
        allowed_ids = cfg.get("allowed_role_ids", [])
        if not allowed_ids:
            await interaction.response.send_message(
                "✅ Role restriction **enabled**.\n⚠️ No roles added yet — use `/addrole @Role`."
            )
        else:
            roles_str = ", ".join(f"<@&{rid}>" for rid in allowed_ids)
            await interaction.response.send_message(
                f"✅ Role restriction **enabled**. Allowed: {roles_str}"
            )
    else:
        await interaction.response.send_message("✅ Role restriction **disabled** — all members can use commands.")

@tree.command(name="addrole", description="[Admin] Add a role allowed to use user commands")
@app_commands.describe(role="Role to add to the allowed list")
async def cmd_addrole(interaction: discord.Interaction, role: discord.Role):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    cfg = load_config()
    allowed_ids = cfg.get("allowed_role_ids", [])
    if role.id in allowed_ids:
        await interaction.response.send_message(f"⚠️ **{role.name}** is already in the allowed list.", ephemeral=True)
        return
    
    allowed_ids.append(role.id)
    cfg["allowed_role_ids"] = allowed_ids
    save_config(cfg)
    
    restriction_note = (
        "" if cfg.get("restrict_to_role") 
        else "\n⚠️ Role restriction is **off** — use `/toggleroles True` to enable it."
    )
    await interaction.response.send_message(f"✅ **{role.name}** added to allowed roles.{restriction_note}")

@tree.command(name="removerole", description="[Admin] Remove a role from the allowed list")
@app_commands.describe(role="Role to remove from the allowed list")
async def cmd_removerole(interaction: discord.Interaction, role: discord.Role):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    cfg = load_config()
    allowed_ids = cfg.get("allowed_role_ids", [])
    if role.id not in allowed_ids:
        await interaction.response.send_message(f"⚠️ **{role.name}** is not in the allowed list.", ephemeral=True)
        return
    
    allowed_ids.remove(role.id)
    cfg["allowed_role_ids"] = allowed_ids
    save_config(cfg)
    await interaction.response.send_message(f"✅ **{role.name}** removed from allowed roles.")

@tree.command(name="viewroles", description="[Admin] View role restriction settings")
async def cmd_viewroles(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    cfg = load_config()
    enabled = cfg.get("restrict_to_role", False)
    allowed_ids = cfg.get("allowed_role_ids", [])
    
    embed = discord.Embed(title="🔒  Role Restriction Settings", color=SERIALIZD_COLOUR)
    embed.add_field(name="Status", value="🟢 **Enabled**" if enabled else "🔴 **Disabled**", inline=False)
    
    if allowed_ids:
        role_lines = []
        for rid in allowed_ids:
            role = interaction.guild.get_role(rid)
            if role:
                role_lines.append(f"• {role.mention}  (`{role.name}`)")
            else:
                role_lines.append(f"• ~~Unknown~~ (ID: `{rid}`) — may have been deleted")
        embed.add_field(name=f"Allowed Roles ({len(allowed_ids)})", value="\n".join(role_lines), inline=False)
    else:
        embed.add_field(name="Allowed Roles", value="⚠️ None added yet. Use `/addrole @Role`.", inline=False)
    
    embed.set_footer(text=BOT_NAME, icon_url=BOT_ICON_URL)
    await interaction.response.send_message(embed=embed)

@tree.command(name="botstatus", description="[Admin] View bot status and configuration")
async def cmd_status(interaction: discord.Interaction):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    cfg = load_config()
    users = cfg.get("users", [])
    now = datetime.now(timezone.utc)
    uptime = now - START_TIME
    hours, rem = divmod(int(uptime.total_seconds()), 3600)
    mins, secs = divmod(rem, 60)
    
    post_ch = cfg.get("post_channel_id")
    cmd_ch = cfg.get("commands_channel_id")
    allowed_ids = cfg.get("allowed_role_ids", [])
    restricted = cfg.get("restrict_to_role", False)
    
    embed = discord.Embed(title="📊  Serializd Bot Status", color=SERIALIZD_COLOUR)
    embed.add_field(name="⏱ Uptime", value=f"{hours}h {mins}m {secs}s", inline=True)
    embed.add_field(name="🔄 Poll interval", value=f"Every {POLL_INTERVAL} min", inline=True)
    embed.add_field(name="👥 Tracked users", value=str(len(users)) if users else "None", inline=True)
    embed.add_field(name="📢 Post channel", value=f"<#{post_ch}>" if post_ch else "Not set", inline=True)
    embed.add_field(name="💬 Commands channel", value=f"<#{cmd_ch}>" if cmd_ch else "Everywhere", inline=True)
    
    roles_val = (
        (", ".join(f"<@&{rid}>" for rid in allowed_ids) if allowed_ids else "⚠️ On (no roles set)") 
        if restricted else "Off"
    )
    embed.add_field(name="🔒 Role restriction", value=roles_val, inline=True)
    embed.set_footer(text=BOT_NAME, icon_url=BOT_ICON_URL)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  SLASH COMMANDS (Admin - Testing & Info)
# ═══════════════════════════════════════════════════════════════════════════════

@tree.command(name="testuser", description="[Admin] Test if API can fetch a user's diary")
@app_commands.describe(username="Serializd username to test")
async def cmd_testuser(interaction: discord.Interaction, username: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    username = username.strip().lstrip("@")
    if not username:
        await interaction.response.send_message("❌ Please provide a Serializd username.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    # Test the diary API
    async with aiohttp.ClientSession() as session:
        entries = await fetch_diary(session, username)
        
        # Build response embed
        embed = discord.Embed(
            title=f"🔍 API Test Results for: {username}",
            color=0x00FF00 if entries else 0xFF0000
        )
        
        embed.add_field(
            name="Profile URL",
            value=f"[Check Profile](https://www.serializd.com/user/{username}/profile)",
            inline=False
        )
        
        embed.add_field(
            name="Diary URL",
            value=f"[Check Diary](https://www.serializd.com/user/{username}/diary)",
            inline=False
        )
        
        if entries:
            embed.add_field(
                name="✅ Result",
                value=f"**SUCCESS!** Found {len(entries)} diary entries.\nThis user can be tracked.",
                inline=False
            )
            
            # Show first 3 entries as examples
            if len(entries) >= 1:
                first = entries[0]
                show_name = first.get("showName", "Unknown")
                season = first.get("seasonName", "")
                ep = first.get("episodeNumber", "")
                example = f"• {show_name}"
                if season:
                    example += f", {season}"
                if ep:
                    example += f" - Ep {ep}"
                embed.add_field(name="Example Entry", value=example, inline=False)
        else:
            embed.add_field(
                name="❌ Result",
                value=(
                    "**FAILED** - Could not fetch diary entries.\n\n"
                    "**Possible causes:**\n"
                    "• Username is incorrect (check spelling/case)\n"
                    "• Profile doesn't exist\n"
                    "• Profile/diary is private\n"
                    "• User has no diary entries yet\n\n"
                    "**Solutions:**\n"
                    "• Verify username at the profile URL above\n"
                    "• Check if diary is viewable in incognito mode\n"
                    "• Try a different username"
                ),
                inline=False
            )
        
        await interaction.followup.send(embed=embed)

@tree.command(name="watching", description="[Admin] View what a user is currently watching")
@app_commands.describe(username="Serializd username")
async def cmd_watching(interaction: discord.Interaction, username: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    username = username.strip().lstrip("@")
    await interaction.response.defer()
    
    data = await get_currently_watching(username)
    items = data.get("items", [])
    
    if not items:
        await interaction.followup.send(f"📺 **{username}** is not currently watching anything, or their profile is private.")
        return
    
    embed = discord.Embed(
        title=f"📺 Currently Watching - {username}",
        description=f"Total: {data.get('totalItems', len(items))} show(s)",
        color=SERIALIZD_COLOUR,
        url=f"https://www.serializd.com/user/{username}/profile"
    )
    
    for item in items[:10]:  # Show first 10
        show_name = item.get("showName", "Unknown Show")
        show_id = item.get("showId")
        show_url = f"https://www.serializd.com/show/{show_id}" if show_id else ""
        date_added = item.get("dateAdded", "")
        
        # Format date
        try:
            dt = datetime.fromisoformat(date_added.replace("Z", "+00:00"))
            date_str = dt.strftime("%d %b %Y")
        except:
            date_str = ""
        
        value = f"[View Show]({show_url})" if show_url else "No link"
        if date_str:
            value += f" • Added {date_str}"
        
        embed.add_field(name=show_name, value=value, inline=False)
    
    if len(items) > 10:
        embed.set_footer(text=f"Showing 10 of {len(items)} shows")
    
    await interaction.followup.send(embed=embed)

@tree.command(name="watchlist", description="[Admin] View a user's watchlist")
@app_commands.describe(username="Serializd username")
async def cmd_watchlist(interaction: discord.Interaction, username: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    username = username.strip().lstrip("@")
    await interaction.response.defer()
    
    data = await get_watchlist(username)
    items = data.get("items", [])
    
    if not items:
        await interaction.followup.send(f"📋 **{username}**'s watchlist is empty, or their profile is private.")
        return
    
    embed = discord.Embed(
        title=f"📋 Watchlist - {username}",
        description=f"Total: {data.get('numberOfShows', len(items))} show(s)",
        color=SERIALIZD_COLOUR,
        url=f"https://www.serializd.com/user/{username}/profile"
    )
    
    for item in items[:10]:  # Show first 10
        show_name = item.get("showName", "Unknown Show")
        show_id = item.get("showId")
        show_url = f"https://www.serializd.com/show/{show_id}" if show_id else ""
        num_seasons = item.get("numSeasons", 0)
        
        value = f"[View Show]({show_url})" if show_url else "No link"
        if num_seasons:
            value += f" • {num_seasons} season(s)"
        
        embed.add_field(name=show_name, value=value, inline=False)
    
    if len(items) > 10:
        embed.set_footer(text=f"Showing 10 of {len(items)} shows")
    
    await interaction.followup.send(embed=embed)

@tree.command(name="watched", description="[Admin] View a user's watched shows")
@app_commands.describe(username="Serializd username")
async def cmd_watched(interaction: discord.Interaction, username: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    username = username.strip().lstrip("@")
    await interaction.response.defer()
    
    data = await get_watched(username)
    items = data.get("items", [])
    
    if not items:
        await interaction.followup.send(f"✅ **{username}** hasn't marked any shows as watched, or their profile is private.")
        return
    
    embed = discord.Embed(
        title=f"✅ Watched - {username}",
        description=f"Total: {data.get('numberOfShows', len(items))} show(s) • {data.get('numberOfSeasons', 0)} season(s)",
        color=SERIALIZD_COLOUR,
        url=f"https://www.serializd.com/user/{username}/profile"
    )
    
    for item in items[:10]:  # Show first 10
        show_name = item.get("showName", "Unknown Show")
        show_id = item.get("showId")
        show_url = f"https://www.serializd.com/show/{show_id}" if show_id else ""
        num_episodes = item.get("numEpisodes", 0)
        num_seasons = item.get("numSeasons", 0)
        
        value = f"[View Show]({show_url})" if show_url else "No link"
        if num_seasons and num_episodes:
            value += f" • {num_seasons} season(s), {num_episodes} episode(s)"
        
        embed.add_field(name=show_name, value=value, inline=False)
    
    if len(items) > 10:
        embed.set_footer(text=f"Showing 10 of {len(items)} shows")
    
    await interaction.followup.send(embed=embed)

@tree.command(name="paused", description="[Admin] View a user's paused shows")
@app_commands.describe(username="Serializd username")
async def cmd_paused(interaction: discord.Interaction, username: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    username = username.strip().lstrip("@")
    await interaction.response.defer()
    
    data = await get_paused(username)
    items = data.get("items", [])
    
    if not items:
        await interaction.followup.send(f"⏸️ **{username}** has no paused shows, or their profile is private.")
        return
    
    embed = discord.Embed(
        title=f"⏸️ Paused - {username}",
        description=f"Total: {data.get('totalItems', len(items))} show(s)",
        color=SERIALIZD_COLOUR,
        url=f"https://www.serializd.com/user/{username}/profile"
    )
    
    for item in items[:10]:  # Show first 10
        show_name = item.get("showName", "Unknown Show")
        show_id = item.get("showId")
        show_url = f"https://www.serializd.com/show/{show_id}" if show_id else ""
        date_added = item.get("dateAdded", "")
        
        # Format date
        try:
            dt = datetime.fromisoformat(date_added.replace("Z", "+00:00"))
            date_str = dt.strftime("%d %b %Y")
        except:
            date_str = ""
        
        value = f"[View Show]({show_url})" if show_url else "No link"
        if date_str:
            value += f" • Paused {date_str}"
        
        embed.add_field(name=show_name, value=value, inline=False)
    
    if len(items) > 10:
        embed.set_footer(text=f"Showing 10 of {len(items)} shows")
    
    await interaction.followup.send(embed=embed)

@tree.command(name="dropped", description="[Admin] View a user's dropped shows")
@app_commands.describe(username="Serializd username")
async def cmd_dropped(interaction: discord.Interaction, username: str):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    username = username.strip().lstrip("@")
    await interaction.response.defer()
    
    data = await get_dropped(username)
    items = data.get("items", [])
    
    if not items:
        await interaction.followup.send(f"🚫 **{username}** has no dropped shows, or their profile is private.")
        return
    
    embed = discord.Embed(
        title=f"🚫 Dropped - {username}",
        description=f"Total: {data.get('totalItems', len(items))} show(s)",
        color=SERIALIZD_COLOUR,
        url=f"https://www.serializd.com/user/{username}/profile"
    )
    
    for item in items[:10]:  # Show first 10
        show_name = item.get("showName", "Unknown Show")
        show_id = item.get("showId")
        show_url = f"https://www.serializd.com/show/{show_id}" if show_id else ""
        date_added = item.get("dateAdded", "")
        
        # Format date
        try:
            dt = datetime.fromisoformat(date_added.replace("Z", "+00:00"))
            date_str = dt.strftime("%d %b %Y")
        except:
            date_str = ""
        
        value = f"[View Show]({show_url})" if show_url else "No link"
        if date_str:
            value += f" • Dropped {date_str}"
        
        embed.add_field(name=show_name, value=value, inline=False)
    
    if len(items) > 10:
        embed.set_footer(text=f"Showing 10 of {len(items)} shows")
    
    await interaction.followup.send(embed=embed)

# ═══════════════════════════════════════════════════════════════════════════════
#  COMMAND PERMISSION SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

def has_admin_role(interaction: discord.Interaction) -> bool:
    """Check if user has the admin role ID from .env"""
    if not ADMIN_ROLE_ID:
        return is_admin(interaction)
    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        return False
    return any(role.id == ADMIN_ROLE_ID for role in member.roles) or is_admin(interaction)

async def check_command_permission(interaction: discord.Interaction, command_name: str) -> bool:
    """Check if user has permission to use a command based on config"""
    cfg = load_config()
    perm_level = cfg.get("command_permissions", {}).get(command_name, "admin")
    
    if perm_level == "any":
        return True
    elif perm_level == "admin":
        if not is_admin(interaction):
            await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
            return False
        return True
    elif perm_level == "roles":
        if not cfg.get("restrict_to_role"):
            return True
        allowed_ids = cfg.get("allowed_role_ids", [])
        if not allowed_ids:
            await interaction.response.send_message(
                "❌ Role restriction is enabled but no roles have been added.", ephemeral=True
            )
            return False
        member = interaction.guild.get_member(interaction.user.id)
        member_role_ids = {r.id for r in member.roles} if member else set()
        if not member_role_ids.intersection(allowed_ids):
            await interaction.response.send_message(
                "❌ You need an allowed role to use this command.", ephemeral=True
            )
            return False
        return True
    return False

@tree.command(name="setpermission", description="[Admin] Set permission level for a command")
@app_commands.describe(
    command="Command name (e.g., 'watching', 'profile')",
    level="Permission level: admin, any, or roles"
)
@app_commands.choices(level=[
    app_commands.Choice(name="Admin Only", value="admin"),
    app_commands.Choice(name="Any User", value="any"),
    app_commands.Choice(name="Restricted Roles", value="roles")
])
async def cmd_setpermission(interaction: discord.Interaction, command: str, level: str):
    if not has_admin_role(interaction):
        await interaction.response.send_message(
            "❌ You need the admin role configured in ADMIN_ROLE_ID to use this command.", 
            ephemeral=True
        )
        return
    
    cfg = load_config()
    if "command_permissions" not in cfg:
        cfg["command_permissions"] = {}
    
    cfg["command_permissions"][command] = level
    save_config(cfg)
    
    level_desc = {
        "admin": "Administrator only",
        "any": "Any user",
        "roles": "Restricted roles only"
    }
    
    await interaction.response.send_message(
        f"✅ Set **/{command}** permission to: **{level_desc.get(level, level)}**",
        ephemeral=True
    )

# ═══════════════════════════════════════════════════════════════════════════════
#  SHARELINK SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

@tree.command(name="setchannelsharelink", description="[Admin] Set channel where sharelinks are posted")
@app_commands.describe(channel="Channel for sharelinks")
async def cmd_setchannelsharelink(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    cfg = load_config()
    if channel:
        cfg["sharelink_channel_id"] = channel.id
        save_config(cfg)
        await interaction.response.send_message(f"✅ Sharelinks will be posted in {channel.mention}.")
    else:
        cfg["sharelink_channel_id"] = None
        save_config(cfg)
        await interaction.response.send_message("✅ Sharelink channel removed.")

@tree.command(name="sharelink", description="Submit your Serializd and Letterboxd profile links")
@app_commands.describe(
    serializd="Your Serializd username (optional)",
    letterboxd="Your Letterboxd username (optional)"
)
async def cmd_sharelink(interaction: discord.Interaction, serializd: str = None, letterboxd: str = None):
    # Validate that at least one username is provided
    if not serializd and not letterboxd:
        await interaction.response.send_message(
            "❌ You must provide at least one username (Serializd or Letterboxd).\n"
            "**Usage:** `/sharelink serializd:username` or `/sharelink letterboxd:username` or both",
            ephemeral=True
        )
        return
    
    # Validate username lengths (max 25 characters per platform)
    if serializd and len(serializd) > 25:
        await interaction.response.send_message(
            "❌ Serializd username must be 25 characters or less.",
            ephemeral=True
        )
        return
    
    if letterboxd and len(letterboxd) > 25:
        await interaction.response.send_message(
            "❌ Letterboxd username must be 25 characters or less.",
            ephemeral=True
        )
        return
    
    cfg = load_config()
    user_id = str(interaction.user.id)
    
    # Check if already submitted
    if user_id in cfg.get("sharelinks", {}):
        await interaction.response.send_message(
            "❌ You've already submitted your sharelink! Ask an admin to use `/clearsharelink` if you need to update.",
            ephemeral=True
        )
        return
    
    # Check channel is set
    channel_id = cfg.get("sharelink_channel_id")
    if not channel_id:
        await interaction.response.send_message(
            "❌ Sharelink channel hasn't been set yet. Ask an admin to use `/setchannelsharelink`.",
            ephemeral=True
        )
        return
    
    channel = bot.get_channel(channel_id)
    if not channel:
        await interaction.response.send_message(
            "❌ Sharelink channel not found! Ask an admin to reconfigure it.",
            ephemeral=True
        )
        return
    
    # Create embed
    embed = discord.Embed(
        title=f"📺 {interaction.user.display_name}'s Profile Links",
        color=SERIALIZD_COLOUR
    )
    
    links = []
    if serializd:
        links.append(f"**Serializd:** [View Profile](https://www.serializd.com/user/{serializd})")
    if letterboxd:
        links.append(f"**Letterboxd:** [View Profile](https://letterboxd.com/{letterboxd}/)")
    
    embed.description = "\n".join(links)
    embed.set_footer(text=BOT_NAME, icon_url=BOT_ICON_URL)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    
    # Post to channel
    await channel.send(embed=embed)
    
    # Save to config
    if "sharelinks" not in cfg:
        cfg["sharelinks"] = {}
    cfg["sharelinks"][user_id] = {
        "serializd": serializd,
        "letterboxd": letterboxd,
        "discord_user": interaction.user.display_name
    }
    save_config(cfg)
    
    await interaction.response.send_message(
        f"✅ Your sharelink has been posted in {channel.mention}!",
        ephemeral=True
    )

@tree.command(name="clearsharelink", description="[Admin] Clear a user's sharelink so they can resubmit")
@app_commands.describe(user="User whose sharelink to clear")
async def cmd_clearsharelink(interaction: discord.Interaction, user: discord.User):
    if not is_admin(interaction):
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    cfg = load_config()
    user_id = str(user.id)
    
    if "sharelinks" not in cfg:
        cfg["sharelinks"] = {}
    
    if user_id in cfg["sharelinks"]:
        del cfg["sharelinks"][user_id]
        save_config(cfg)
        await interaction.response.send_message(
            f"✅ Cleared sharelink for {user.mention}. They can now submit a new one.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"❌ {user.mention} hasn't submitted a sharelink yet.",
            ephemeral=True
        )

# ═══════════════════════════════════════════════════════════════════════════════
#  PROFILE COMMAND WITH PAGINATION
# ═══════════════════════════════════════════════════════════════════════════════

class ProfileView(discord.ui.View):
    def __init__(self, username: str, initial_data_type: str = "logged"):
        super().__init__(timeout=300)  # 5 minute timeout
        self.username = username
        self.data_type = initial_data_type
        self.page = 0
        self.items = []
        self.total_count = 0
        self.loading = False
        
    async def fetch_data(self, data_type: str):
        """Fetch data based on type"""
        self.loading = True
        
        if data_type == "logged":
            async with aiohttp.ClientSession() as session:
                entries = await fetch_diary(session, self.username)
                self.items = entries[:100]  # Limit to 100
                self.total_count = len(entries)
        elif data_type == "watching":
            data = await get_currently_watching(self.username)
            self.items = data.get("items", [])[:100]
            self.total_count = data.get("totalItems", len(self.items))
        elif data_type == "watchlist":
            data = await get_watchlist(self.username)
            self.items = data.get("items", [])[:100]
            self.total_count = data.get("numberOfShows", len(self.items))
        
        self.loading = False
        return self.items
    
    def create_embed(self):
        """Create embed for current page"""
        start_idx = self.page * 10
        end_idx = min(start_idx + 10, len(self.items))
        page_items = self.items[start_idx:end_idx]
        
        # Title based on type
        titles = {
            "logged": "📝 Recently Logged",
            "watching": "📺 Currently Watching",
            "watchlist": "📋 Watchlist"
        }
        
        embed = discord.Embed(
            title=f"{titles.get(self.data_type, 'Profile')} - {self.username}",
            color=SERIALIZD_COLOUR,
            url=f"https://www.serializd.com/user/{self.username}/profile"
        )
        
        # Add stats in description
        stats_parts = [f"**Total:** {self.total_count} item(s)"]
        if len(self.items) >= 100:
            stats_parts.append("(showing first 100)")
        stats_parts.append(f"**Page:** {self.page + 1}/{max(1, (len(self.items) + 9) // 10)}")
        embed.description = " • ".join(stats_parts)
        
        # Add items
        if not page_items:
            embed.add_field(name="No items", value="Nothing to display", inline=False)
        else:
            for item in page_items:
                if self.data_type == "logged":
                    # Diary entry
                    show_name = item.get("showName", "Unknown Show")
                    
                    # Extract season info with fallback (same logic as build_embed)
                    season_name = item.get("seasonName", "")
                    season_num = item.get("seasonNumber")
                    episode_num = item.get("episodeNumber")
                    season_id = item.get("seasonId")
                    
                    # Fallback: If seasonName is empty but we have seasonId, try showSeasons array
                    if (not season_name or not season_name.strip()) and season_id:
                        show_seasons = item.get("showSeasons", [])
                        for season in show_seasons:
                            if season.get("id") == season_id:
                                season_name = season.get("name", "")
                                if not season_num:
                                    season_num = season.get("seasonNumber")
                                break
                    
                    rating = item.get("rating", "")
                    like_status = item.get("like")
                    
                    # Build title with proper season/episode formatting
                    title = show_name
                    
                    # Add season info (prefer name over number)
                    if season_name and season_name.strip():
                        title += f"  ·  {season_name}"
                    elif season_num is not None:
                        title += f"  ·  Season {int(season_num)}"
                    
                    # Add episode info with dot separator
                    if episode_num:
                        title += f"  ·  Episode {int(episode_num)}"
                    
                    value_parts = []
                    
                    # Add like/dislike indicator
                    if like_status is True:
                        value_parts.append("❤️")
                    elif like_status is False:
                        value_parts.append("💔")
                    
                    if rating and rating > 0:
                        # Convert 10-point scale to 5-point scale
                        r = float(rating) / 2.0
                        full = int(r)
                        half = 1 if (r - full) >= 0.5 else 0
                        
                        # Use custom Discord emojis from .env with spaces
                        full_star = f"<:FullStar:{FULL_STAR_EMOJI_ID}>"
                        half_star = f"<:HalfStar:{HALF_STAR_EMOJI_ID}>"
                        
                        # Build star string with spaces
                        star_emojis = " ".join([full_star] * full)
                        if half:
                            star_emojis += f" {half_star}" if star_emojis else half_star
                        
                        # Add to value parts
                        if star_emojis:
                            value_parts.append(f"{star_emojis}  ({r}/5)")
                        else:
                            value_parts.append(f"({r}/5)")
                    
                    show_id = item.get("showId")
                    if show_id:
                        value_parts.append(f"[View](https://www.serializd.com/show/{show_id})")
                    
                    embed.add_field(
                        name=title[:256],
                        value=" • ".join(value_parts) if value_parts else "No details",
                        inline=False
                    )
                else:
                    # Watching or Watchlist
                    show_name = item.get("showName", "Unknown Show")
                    show_id = item.get("showId")
                    
                    value = f"[View Show](https://www.serializd.com/show/{show_id})" if show_id else "No link"
                    
                    if self.data_type == "watchlist":
                        num_seasons = item.get("numSeasons", 0)
                        if num_seasons:
                            value += f" • {num_seasons} season(s)"
                    
                    embed.add_field(name=show_name[:256], value=value, inline=False)
        
        embed.set_footer(text=BOT_NAME, icon_url=BOT_ICON_URL)
        return embed
    
    @discord.ui.button(label="📝 Recently Logged", style=discord.ButtonStyle.primary, row=0)
    async def logged_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.data_type = "logged"
        self.page = 0
        await self.fetch_data("logged")
        embed = self.create_embed()
        await interaction.edit_original_response(embed=embed, view=self)
    
    @discord.ui.button(label="📺 Currently Watching", style=discord.ButtonStyle.primary, row=0)
    async def watching_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.data_type = "watching"
        self.page = 0
        await self.fetch_data("watching")
        embed = self.create_embed()
        await interaction.edit_original_response(embed=embed, view=self)
    
    @discord.ui.button(label="📋 Watchlist", style=discord.ButtonStyle.primary, row=0)
    async def watchlist_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.data_type = "watchlist"
        self.page = 0
        await self.fetch_data("watchlist")
        embed = self.create_embed()
        await interaction.edit_original_response(embed=embed, view=self)
    
    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary, row=1)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            await interaction.response.defer()
            self.page -= 1
            embed = self.create_embed()
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.send_message("Already on first page!", ephemeral=True)
    
    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary, row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, (len(self.items) - 1) // 10)
        if self.page < max_page:
            await interaction.response.defer()
            self.page += 1
            embed = self.create_embed()
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.send_message("Already on last page!", ephemeral=True)

@tree.command(name="profile", description="View a user's Serializd profile with interactive navigation")
@app_commands.describe(username="Serializd username")
async def cmd_profile(interaction: discord.Interaction, username: str):
    # Check permissions
    if not await check_command_permission(interaction, "profile"):
        return
    
    username = username.strip().lstrip("@")
    await interaction.response.defer()
    
    # Create view and fetch initial data
    view = ProfileView(username, "logged")
    await view.fetch_data("logged")
    
    if not view.items:
        await interaction.followup.send(
            f"❌ Could not fetch profile data for **{username}**. "
            f"Check if the profile exists: https://www.serializd.com/user/{username}/profile"
        )
        return
    
    embed = view.create_embed()
    await interaction.followup.send(embed=embed, view=view)

# ═══════════════════════════════════════════════════════════════════════════════
#  PREFIX FALLBACKS  (!command)
#  These mirror the slash commands for immediate configuration
# ═══════════════════════════════════════════════════════════════════════════════

def prefix_is_admin(ctx) -> bool:
    return ctx.author.guild_permissions.administrator

@bot.command(name="setchannel")
async def prefix_setchannel(ctx, channel: discord.TextChannel = None):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    if channel is None:
        await ctx.send("❌ Usage: `!setchannel #channel`")
        return
    cfg = load_config()
    cfg["post_channel_id"] = channel.id
    save_config(cfg)
    await ctx.send(f"✅ Diary entries will now be posted in {channel.mention}.")

@bot.command(name="adduser")
async def prefix_adduser(ctx, username: str = None):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    if username is None:
        await ctx.send("❌ Usage: `!adduser <serializd_username>`")
        return
    cfg = load_config()
    username = username.strip().lstrip("@")
    if username in cfg["users"]:
        await ctx.send(f"⚠️ **{username}** is already being tracked.")
        return
    cfg["users"].append(username)
    save_config(cfg)
    await ctx.send(f"✅ Now tracking **{username}**\n🔗 <https://www.serializd.com/user/{username}/profile>")

@bot.command(name="removeuser")
async def prefix_removeuser(ctx, username: str = None):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    if username is None:
        await ctx.send("❌ Usage: `!removeuser <serializd_username>`")
        return
    cfg = load_config()
    username = username.strip()
    if username not in cfg["users"]:
        await ctx.send(f"⚠️ **{username}** is not in the tracked list.")
        return
    cfg["users"].remove(username)
    save_config(cfg)
    await ctx.send(f"✅ Removed **{username}** from tracking.")

@bot.command(name="setchannelcmd")
async def prefix_setchannelcmd(ctx, channel: discord.TextChannel = None):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    cfg = load_config()
    if channel:
        cfg["commands_channel_id"] = channel.id
        save_config(cfg)
        await ctx.send(f"✅ User commands restricted to {channel.mention}.")
    else:
        cfg["commands_channel_id"] = None
        save_config(cfg)
        await ctx.send("✅ Commands restriction removed — commands work everywhere.")

@bot.command(name="toggleroles")
async def prefix_toggleroles(ctx, enabled: str = None):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    if enabled is None or enabled.lower() not in ("true", "false"):
        await ctx.send("❌ Usage: `!toggleroles true` or `!toggleroles false`")
        return
    cfg = load_config()
    cfg["restrict_to_role"] = enabled.lower() == "true"
    save_config(cfg)
    if cfg["restrict_to_role"]:
        allowed_ids = cfg.get("allowed_role_ids", [])
        if not allowed_ids:
            await ctx.send("✅ Role restriction **enabled**.\n⚠️ No roles added yet — use `!addrole @Role`.")
        else:
            roles_str = ", ".join(f"<@&{rid}>" for rid in allowed_ids)
            await ctx.send(f"✅ Role restriction **enabled**. Allowed: {roles_str}")
    else:
        await ctx.send("✅ Role restriction **disabled** — all members can use commands.")

@bot.command(name="addrole")
async def prefix_addrole(ctx, role: discord.Role = None):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    if role is None:
        await ctx.send("❌ Usage: `!addrole @Role`")
        return
    cfg = load_config()
    allowed_ids = cfg.get("allowed_role_ids", [])
    if role.id in allowed_ids:
        await ctx.send(f"⚠️ **{role.name}** is already in the allowed list.")
        return
    allowed_ids.append(role.id)
    cfg["allowed_role_ids"] = allowed_ids
    save_config(cfg)
    restriction_note = "" if cfg.get("restrict_to_role") else "\n⚠️ Role restriction is **off** — use `!toggleroles true` to enable it."
    await ctx.send(f"✅ **{role.name}** added to allowed roles.{restriction_note}")

@bot.command(name="removerole")
async def prefix_removerole(ctx, role: discord.Role = None):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    if role is None:
        await ctx.send("❌ Usage: `!removerole @Role`")
        return
    cfg = load_config()
    allowed_ids = cfg.get("allowed_role_ids", [])
    if role.id not in allowed_ids:
        await ctx.send(f"⚠️ **{role.name}** is not in the allowed list.")
        return
    allowed_ids.remove(role.id)
    cfg["allowed_role_ids"] = allowed_ids
    save_config(cfg)
    await ctx.send(f"✅ **{role.name}** removed from allowed roles.")

@bot.command(name="viewroles")
async def prefix_viewroles(ctx):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    cfg = load_config()
    enabled = cfg.get("restrict_to_role", False)
    allowed_ids = cfg.get("allowed_role_ids", [])
    embed = discord.Embed(title="🔒  Role Restriction Settings", color=SERIALIZD_COLOUR)
    embed.add_field(name="Status", value="🟢 **Enabled**" if enabled else "🔴 **Disabled**", inline=False)
    if allowed_ids:
        role_lines = []
        for rid in allowed_ids:
            role = ctx.guild.get_role(rid)
            role_lines.append(f"• {role.mention}  (`{role.name}`)" if role else f"• ~~Unknown~~ (ID: `{rid}`) — may have been deleted")
        embed.add_field(name=f"Allowed Roles ({len(allowed_ids)})", value="\n".join(role_lines), inline=False)
    else:
        embed.add_field(name="Allowed Roles", value="⚠️ None added yet. Use `!addrole @Role`.", inline=False)
    embed.set_footer(text=BOT_NAME, icon_url=BOT_ICON_URL)
    await ctx.send(embed=embed)

@bot.command(name="botstatus")
async def prefix_status(ctx):
    cfg = load_config()
    users = cfg.get("users", [])
    now = datetime.now(timezone.utc)
    uptime = now - START_TIME
    hours, rem = divmod(int(uptime.total_seconds()), 3600)
    mins, secs = divmod(rem, 60)
    post_ch = cfg.get("post_channel_id")
    cmd_ch = cfg.get("commands_channel_id")
    allowed_ids = cfg.get("allowed_role_ids", [])
    restricted = cfg.get("restrict_to_role", False)
    embed = discord.Embed(title="📊  Serializd Bot Status", color=SERIALIZD_COLOUR)
    embed.add_field(name="⏱ Uptime",           value=f"{hours}h {mins}m {secs}s",          inline=True)
    embed.add_field(name="🔄 Poll interval",    value=f"Every {POLL_INTERVAL} min",         inline=True)
    embed.add_field(name="👥 Tracked users",    value=str(len(users)) if users else "None", inline=True)
    embed.add_field(name="📢 Post channel",     value=f"<#{post_ch}>" if post_ch else "Not set", inline=True)
    embed.add_field(name="💬 Commands channel", value=f"<#{cmd_ch}>" if cmd_ch else "Everywhere", inline=True)
    roles_val = (", ".join(f"<@&{rid}>" for rid in allowed_ids) if allowed_ids else "⚠️ On (no roles set)") if restricted else "Off"
    embed.add_field(name="🔒 Role restriction", value=roles_val, inline=True)
    embed.set_footer(text=BOT_NAME, icon_url=BOT_ICON_URL)
    await ctx.send(embed=embed)

@bot.command(name="watching")
async def prefix_watching(ctx, username: str = None):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    if not username:
        await ctx.send("❌ Usage: `!watching <username>`")
        return
    
    username = username.strip().lstrip("@")
    msg = await ctx.send(f"🔍 Fetching currently watching shows for **{username}**...")
    
    data = await get_currently_watching(username)
    items = data.get("items", [])
    
    if not items:
        await msg.edit(content=f"📺 **{username}** is not currently watching anything, or their profile is private.")
        return
    
    embed = discord.Embed(
        title=f"📺 Currently Watching - {username}",
        description=f"Total: {data.get('totalItems', len(items))} show(s)",
        color=SERIALIZD_COLOUR,
        url=f"https://www.serializd.com/user/{username}/profile"
    )
    
    for item in items[:10]:
        show_name = item.get("showName", "Unknown Show")
        show_id = item.get("showId")
        show_url = f"https://www.serializd.com/show/{show_id}" if show_id else ""
        value = f"[View Show]({show_url})" if show_url else "No link"
        embed.add_field(name=show_name, value=value, inline=False)
    
    if len(items) > 10:
        embed.set_footer(text=f"Showing 10 of {len(items)} shows")
    
    await msg.delete()
    await ctx.send(embed=embed)

@bot.command(name="watchlist")
async def prefix_watchlist(ctx, username: str = None):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    if not username:
        await ctx.send("❌ Usage: `!watchlist <username>`")
        return
    
    username = username.strip().lstrip("@")
    msg = await ctx.send(f"🔍 Fetching watchlist for **{username}**...")
    
    data = await get_watchlist(username)
    items = data.get("items", [])
    
    if not items:
        await msg.edit(content=f"📋 **{username}**'s watchlist is empty, or their profile is private.")
        return
    
    embed = discord.Embed(
        title=f"📋 Watchlist - {username}",
        description=f"Total: {data.get('numberOfShows', len(items))} show(s)",
        color=SERIALIZD_COLOUR,
        url=f"https://www.serializd.com/user/{username}/profile"
    )
    
    for item in items[:10]:
        show_name = item.get("showName", "Unknown Show")
        show_id = item.get("showId")
        show_url = f"https://www.serializd.com/show/{show_id}" if show_id else ""
        num_seasons = item.get("numSeasons", 0)
        value = f"[View Show]({show_url})" if show_url else "No link"
        if num_seasons:
            value += f" • {num_seasons} season(s)"
        embed.add_field(name=show_name, value=value, inline=False)
    
    if len(items) > 10:
        embed.set_footer(text=f"Showing 10 of {len(items)} shows")
    
    await msg.delete()
    await ctx.send(embed=embed)

@bot.command(name="watched")
async def prefix_watched(ctx, username: str = None):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    if not username:
        await ctx.send("❌ Usage: `!watched <username>`")
        return
    
    username = username.strip().lstrip("@")
    msg = await ctx.send(f"🔍 Fetching watched shows for **{username}**...")
    
    data = await get_watched(username)
    items = data.get("items", [])
    
    if not items:
        await msg.edit(content=f"✅ **{username}** hasn't marked any shows as watched, or their profile is private.")
        return
    
    embed = discord.Embed(
        title=f"✅ Watched - {username}",
        description=f"Total: {data.get('numberOfShows', len(items))} show(s) • {data.get('numberOfSeasons', 0)} season(s)",
        color=SERIALIZD_COLOUR,
        url=f"https://www.serializd.com/user/{username}/profile"
    )
    
    for item in items[:10]:
        show_name = item.get("showName", "Unknown Show")
        show_id = item.get("showId")
        show_url = f"https://www.serializd.com/show/{show_id}" if show_id else ""
        num_episodes = item.get("numEpisodes", 0)
        num_seasons = item.get("numSeasons", 0)
        value = f"[View Show]({show_url})" if show_url else "No link"
        if num_seasons and num_episodes:
            value += f" • {num_seasons} season(s), {num_episodes} episode(s)"
        embed.add_field(name=show_name, value=value, inline=False)
    
    if len(items) > 10:
        embed.set_footer(text=f"Showing 10 of {len(items)} shows")
    
    await msg.delete()
    await ctx.send(embed=embed)

@bot.command(name="paused")
async def prefix_paused(ctx, username: str = None):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    if not username:
        await ctx.send("❌ Usage: `!paused <username>`")
        return
    
    username = username.strip().lstrip("@")
    msg = await ctx.send(f"🔍 Fetching paused shows for **{username}**...")
    
    data = await get_paused(username)
    items = data.get("items", [])
    
    if not items:
        await msg.edit(content=f"⏸️ **{username}** has no paused shows, or their profile is private.")
        return
    
    embed = discord.Embed(
        title=f"⏸️ Paused - {username}",
        description=f"Total: {data.get('totalItems', len(items))} show(s)",
        color=SERIALIZD_COLOUR,
        url=f"https://www.serializd.com/user/{username}/profile"
    )
    
    for item in items[:10]:
        show_name = item.get("showName", "Unknown Show")
        show_id = item.get("showId")
        show_url = f"https://www.serializd.com/show/{show_id}" if show_id else ""
        value = f"[View Show]({show_url})" if show_url else "No link"
        embed.add_field(name=show_name, value=value, inline=False)
    
    if len(items) > 10:
        embed.set_footer(text=f"Showing 10 of {len(items)} shows")
    
    await msg.delete()
    await ctx.send(embed=embed)

@bot.command(name="dropped")
async def prefix_dropped(ctx, username: str = None):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    if not username:
        await ctx.send("❌ Usage: `!dropped <username>`")
        return
    
    username = username.strip().lstrip("@")
    msg = await ctx.send(f"🔍 Fetching dropped shows for **{username}**...")
    
    data = await get_dropped(username)
    items = data.get("items", [])
    
    if not items:
        await msg.edit(content=f"🚫 **{username}** has no dropped shows, or their profile is private.")
        return
    
    embed = discord.Embed(
        title=f"🚫 Dropped - {username}",
        description=f"Total: {data.get('totalItems', len(items))} show(s)",
        color=SERIALIZD_COLOUR,
        url=f"https://www.serializd.com/user/{username}/profile"
    )
    
    for item in items[:10]:
        show_name = item.get("showName", "Unknown Show")
        show_id = item.get("showId")
        show_url = f"https://www.serializd.com/show/{show_id}" if show_id else ""
        value = f"[View Show]({show_url})" if show_url else "No link"
        embed.add_field(name=show_name, value=value, inline=False)
    
    if len(items) > 10:
        embed.set_footer(text=f"Showing 10 of {len(items)} shows")
    
    await msg.delete()
    await ctx.send(embed=embed)

@bot.command(name="sharelink")
async def prefix_sharelink(ctx, serializd: str = None, letterboxd: str = None):
    if not serializd and not letterboxd:
        await ctx.send("❌ You must provide at least one username (Serializd or Letterboxd).\n**Usage:** `!sharelink <serializd_username>` or `!sharelink <serializd> <letterboxd>`")
        return
    
    # Validate username lengths (max 25 characters per platform)
    if serializd and len(serializd) > 25:
        await ctx.send("❌ Serializd username must be 25 characters or less.")
        return
    
    if letterboxd and len(letterboxd) > 25:
        await ctx.send("❌ Letterboxd username must be 25 characters or less.")
        return
    
    cfg = load_config()
    user_id = str(ctx.author.id)
    
    # Check if already submitted
    if user_id in cfg.get("sharelinks", {}):
        await ctx.send("❌ You've already submitted your sharelink! Ask an admin to use `!clearsharelink` if you need to update.")
        return
    
    # Check channel is set
    channel_id = cfg.get("sharelink_channel_id")
    if not channel_id:
        await ctx.send("❌ Sharelink channel hasn't been set yet. Ask an admin to use `!setchannelsharelink`.")
        return
    
    channel = bot.get_channel(channel_id)
    if not channel:
        await ctx.send("❌ Sharelink channel not found!")
        return
    
    # Create embed
    embed = discord.Embed(
        title=f"📺 {ctx.author.display_name}'s Profile Links",
        color=SERIALIZD_COLOUR
    )
    
    links = []
    if serializd:
        links.append(f"**Serializd:** [View Profile](https://www.serializd.com/user/{serializd})")
    if letterboxd:
        links.append(f"**Letterboxd:** [View Profile](https://letterboxd.com/{letterboxd}/)")
    
    embed.description = "\n".join(links)
    embed.set_footer(text=BOT_NAME, icon_url=BOT_ICON_URL)
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    
    # Post to channel
    await channel.send(embed=embed)
    
    # Save to config
    if "sharelinks" not in cfg:
        cfg["sharelinks"] = {}
    cfg["sharelinks"][user_id] = {
        "serializd": serializd,
        "letterboxd": letterboxd,
        "discord_user": ctx.author.display_name
    }
    save_config(cfg)
    
    await ctx.send(f"✅ Your sharelink has been posted in {channel.mention}!")

@bot.command(name="setchannelsharelink")
async def prefix_setchannelsharelink(ctx, channel: discord.TextChannel = None):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    
    cfg = load_config()
    if channel:
        cfg["sharelink_channel_id"] = channel.id
        save_config(cfg)
        await ctx.send(f"✅ Sharelinks will be posted in {channel.mention}.")
    else:
        cfg["sharelink_channel_id"] = None
        save_config(cfg)
        await ctx.send("✅ Sharelink channel removed.")

@bot.command(name="clearsharelink")
async def prefix_clearsharelink(ctx, user: discord.User = None):
    if not prefix_is_admin(ctx):
        await ctx.send("❌ Administrator permission required.")
        return
    if not user:
        await ctx.send("❌ Usage: `!clearsharelink @user`")
        return
    
    cfg = load_config()
    user_id = str(user.id)
    
    if "sharelinks" not in cfg:
        cfg["sharelinks"] = {}
    
    if user_id in cfg["sharelinks"]:
        del cfg["sharelinks"][user_id]
        save_config(cfg)
        await ctx.send(f"✅ Cleared sharelink for {user.mention}. They can now submit a new one.")
    else:
        await ctx.send(f"❌ {user.mention} hasn't submitted a sharelink yet.")

# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("ERROR: DISCORD_TOKEN is not set in .env")
    bot.run(DISCORD_TOKEN)