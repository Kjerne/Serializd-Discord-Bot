# Serializd Discord Bot 📺

A feature-rich Discord bot that automatically tracks and posts TV show diary entries from [Serializd](https://www.serializd.com/) to your Discord server. Get beautifully formatted embeds whenever you or your friends log new episodes!

![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)
![Discord.py](https://img.shields.io/badge/discord.py-2.3.0+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## ✨ Features

### 📊 Automatic Diary Tracking
- **Multi-user support** - Track multiple Serializd users simultaneously
- **Real-time updates** - Polls diaries at configurable intervals (default: 5 minutes)
- **Smart filtering** - Only posts new entries, prevents duplicates
- **Initial scan** - Posts last 24 hours of activity when adding a new user

### 🎨 Rich Discord Embeds
- **Beautiful formatting** with show banners, ratings, and metadata
- **Custom star ratings** - Configurable emoji stars with 5-point scale
- **Season & episode info** - Properly formatted as "Season X · Episode Y"
- **Rewatch indicators** - Shows 🔄 Rewatched or 👀 First Watch
- **Like/dislike status** - Displays ❤️ Liked or 💔 Not Liked
- **Tags support** - Shows user-defined tags from diary entries
- **Spoiler protection** - Automatically hides reviews marked as containing spoilers
- **Direct links** - Click title to jump to the diary entry

### 🎮 Comprehensive Commands

#### Admin Commands (Slash & Prefix)
- `/setchannel` - Set channel for automatic diary posts
- `/adduser` - Add a Serializd user to track
- `/removeuser` - Stop tracking a user
- `/listusers` - View all tracked users
- `/testuser` - Test if a Serializd profile is accessible
- `/botstatus` - View bot configuration and uptime

#### User Commands
- `/profile` - Interactive profile viewer with pagination
  - Recently logged shows
  - Currently watching
  - Watchlist
- `/watching` - View what a user is currently watching
- `/watchlist` - View a user's watchlist
- `/watched` - View a user's completed shows
- `/paused` - View a user's paused shows
- `/dropped` - View a user's dropped shows
- `/sharelink` - Share your Serializd & Letterboxd profiles

#### Permission System
- **Role restrictions** - Limit commands to specific roles
- **Channel restrictions** - Restrict commands to designated channels
- **Customizable permissions** - Configure per-command access levels

### ⚙️ Highly Configurable
- **Custom bot name and icons** via environment variables
- **Configurable status rotation** with custom messages
- **Flexible polling interval** (1-60 minutes)
- **Persistent configuration** - All settings saved in `config.json`
- **No restart needed** - Configuration updates apply immediately

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- A Discord Bot Token ([Get one here](https://discord.com/developers/applications))
- Discord server with admin permissions

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/serializd-discord-bot.git
cd serializd-discord-bot
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure the bot**
```bash
cp env.example .env
```

Edit `.env` and add your Discord bot token:
```env
DISCORD_TOKEN=your_bot_token_here
```

4. **Run the bot**
```bash
python bot.py
```

### First-Time Setup

1. **Invite the bot** to your server using this URL (replace `YOUR_CLIENT_ID`):
```
https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=274877991936&scope=bot%20applications.commands
```

2. **Set the posting channel:**
```
/setchannel #tv-shows
```

3. **Add users to track:**
```
/adduser username
```

That's it! The bot will start posting new diary entries automatically.

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
# ─── Required ─────────────────────────────────────────
DISCORD_TOKEN=your_bot_token_here

# ─── Optional - Bot Behavior ──────────────────────────
POLL_INTERVAL_MINUTES=5
BOT_NAME=Serializd Bot
BOT_ICON_URL=https://www.serializd.com/android-chrome-192x192.png

# ─── Optional - Status Rotation ───────────────────────
STATUS_ROTATION_SECONDS=30
CUSTOM_STATUS_1=Enjoying Shows 📺
CUSTOM_STATUS_2=
CUSTOM_STATUS_3=

# ─── Optional - Icons ─────────────────────────────────
AUTHOR_ICON_URL=https://cdn.discordapp.com/.../icon.png

# ─── Optional - Star Rating Emojis ────────────────────
# Get emoji IDs by typing \:emoji_name: in Discord
FULL_STAR_EMOJI_ID=1475958462457446552
HALF_STAR_EMOJI_ID=1475958876053573812

# ─── Optional - Admin Role ────────────────────────────
ADMIN_ROLE_ID=123456789012345678
```

### Getting Custom Emoji IDs

1. Enable **Developer Mode** in Discord:
   - Settings → Advanced → Developer Mode
2. Type `\:EmojiName:` in any channel
3. It will show as `<:EmojiName:1234567890>`
4. Copy just the number part: `1234567890`

### Configuration File

All bot settings are stored in `config.json`:
- Tracked users
- Channel IDs
- Role restrictions
- Command permissions
- User sharelinks

This file is automatically created on first run.

## 📋 Commands Reference

### Admin Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/setchannel` | Set diary posting channel | `/setchannel #tv-diary` |
| `/adduser` | Track a Serializd user | `/adduser johndoe` |
| `/removeuser` | Stop tracking a user | `/removeuser johndoe` |
| `/listusers` | Show all tracked users | `/listusers` |
| `/testuser` | Test if profile is accessible | `/testuser johndoe` |
| `/setchannelcmd` | Restrict commands to a channel | `/setchannelcmd #bot-commands` |
| `/toggleroles` | Enable/disable role restrictions | `/toggleroles true` |
| `/addrole` | Add allowed role | `/addrole @TV Watchers` |
| `/removerole` | Remove allowed role | `/removerole @TV Watchers` |
| `/viewroles` | View role configuration | `/viewroles` |
| `/botstatus` | Show bot status | `/botstatus` |
| `/setchannelsharelink` | Set sharelink channel | `/setchannelsharelink #intros` |
| `/clearsharelink` | Clear a user's sharelink | `/clearsharelink @user` |
| `/setpermission` | Set command permissions | `/setpermission profile any` |

### User Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/profile` | Interactive profile viewer | `/profile johndoe` |
| `/watching` | Currently watching shows | `/watching johndoe` |
| `/watchlist` | User's watchlist | `/watchlist johndoe` |
| `/watched` | Completed shows | `/watched johndoe` |
| `/paused` | Paused shows | `/paused johndoe` |
| `/dropped` | Dropped shows | `/dropped johndoe` |
| `/sharelink` | Share profile links | `/sharelink serializd:johndoe` |

### Prefix Commands

All slash commands also work with the `!` prefix:
```
!setchannel #tv-shows
!adduser johndoe
!profile johndoe
```

## 🎨 Customization

### Custom Status Messages

Set up to 3 custom status messages that rotate with tracking/uptime info:

```env
CUSTOM_STATUS_1=Enjoying Shows 📺
CUSTOM_STATUS_2=Binge-watching 🍿
CUSTOM_STATUS_3=Couch Potato Mode 🛋️
```

The bot will cycle through:
1. Tracking X users
2. Uptime: Xh Xm
3. Your custom messages

### Custom Star Emojis

Upload your own star emojis to your Discord server:

1. Create/find star images (full and half)
2. Upload to Discord server
3. Get emoji IDs: `\:YourStarEmoji:`
4. Add to `.env`:
```env
FULL_STAR_EMOJI_ID=your_full_star_id
HALF_STAR_EMOJI_ID=your_half_star_id
```

## 🔧 Advanced Features

### Permission System

Control who can use specific commands:

```
/setpermission profile any        # Anyone can use /profile
/setpermission watching admin     # Only admins can use /watching
/setpermission watchlist roles    # Only users with allowed roles
```

### Sharelink System

Let users share their Serializd and Letterboxd profiles:

1. Set a sharelink channel: `/setchannelsharelink #intros`
2. Users can submit: `/sharelink serializd:username letterboxd:username`
3. Bot posts a formatted embed with their links
4. Each user can only submit once (admins can clear with `/clearsharelink`)

### Interactive Profile Viewer

The `/profile` command provides an interactive widget:
- **3 tabs**: Recently Logged, Currently Watching, Watchlist
- **Pagination**: Navigate through items (10 per page)
- **Live data**: Fetches fresh data when switching tabs
- **Automatic timeout**: Widget expires after 5 minutes

## 🐛 Troubleshooting

### Bot doesn't post entries

1. Check bot has permission to post in the channel
2. Verify user profile is public on Serializd
3. Use `/testuser username` to check API access
4. Check bot logs for errors

### Stars show as text instead of emojis

1. Verify bot has access to the emoji server
2. Check emoji IDs are correct: `\:EmojiName:` in Discord
3. Ensure emojis are named exactly `FullStar` and `HalfStar`

### Season names not showing

1. Check bot logs for debug output
2. Verify the show has season info on Serializd
3. Some shows may not have season names in the API

### "No users configured" message

1. Use `/adduser username` to add users
2. Check `config.json` has users in the array
3. Restart bot if configuration seems corrupted

## 📊 Example Embed

```
📺  The Lincoln Lawyer  ·  Season 1  ·  Episode 3

Logged: 17 hours ago (24 February 2026 07:07)
Rating: ⭐ ⭐ ⭐ ⭐  (4.0/5)
❤️ Liked
🔄 Rewatched
Tags: #courtroom-drama #legal

Review: Outstanding episode! The courtroom scenes were intense...

────────────────────────────
Kjerne's Serializd Bot  •  Yesterday at 07:07
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Setup

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Test thoroughly
5. Commit: `git commit -m 'Add amazing feature'`
6. Push: `git push origin feature/amazing-feature`
7. Open a Pull Request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Credits & Acknowledgments

This bot was built using insights and code patterns from:

- **[unserializd](https://github.com/skyth3r/unserializd)** - Go package for Serializd API by [@skyth3r](https://github.com/skyth3r)
  - API endpoint discovery and header configurations
  - Data structure documentation
  - API response parsing patterns

- **[automate-now](https://github.com/skyth3r/automate-now)** - Now page automation by [@skyth3r](https://github.com/skyth3r)
  - Serializd scraping implementation
  - Show data extraction techniques

Special thanks to the Serializd community for their incredible TV tracking platform!

## 🔗 Links

- [Serializd](https://www.serializd.com/) - The TV show tracking platform
- [Discord.py Documentation](https://discordpy.readthedocs.io/)
- [Discord Developer Portal](https://discord.com/developers/applications)

## 📞 Support

If you encounter any issues or have questions:

1. Check the [Troubleshooting](#-troubleshooting) section
2. Search existing [Issues](https://github.com/yourusername/serializd-discord-bot/issues)
3. Open a new issue with:
   - Bot version
   - Error message (if any)
   - Steps to reproduce
   - Relevant log output

## ⭐ Star History

If you find this bot useful, please consider giving it a star on GitHub!

---

**Made with ❤️ for the TV watching community**
