# Contributing to Serializd Discord Bot

First off, thank you for considering contributing to the Serializd Discord Bot! 🎉

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Commit Message Guidelines](#commit-message-guidelines)

## Code of Conduct

This project and everyone participating in it is governed by our commitment to providing a welcoming and harassment-free experience for everyone. By participating, you are expected to uphold these values.

## How Can I Contribute?

### 🐛 Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates. When you create a bug report, include as many details as possible:

- **Use a clear and descriptive title**
- **Describe the exact steps to reproduce the problem**
- **Provide specific examples** (commands used, screenshots, etc.)
- **Describe the behavior you observed** and what you expected
- **Include bot logs** if applicable
- **Specify your environment** (Python version, OS, Discord.py version)

### 💡 Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion, include:

- **Use a clear and descriptive title**
- **Provide a detailed description** of the suggested enhancement
- **Explain why this enhancement would be useful**
- **List examples** of how it would work
- **Mention if you're willing to implement it yourself**

### 🔧 Pull Requests

Good pull requests (patches, improvements, new features) are a fantastic help. They should remain focused in scope and avoid containing unrelated commits.

**Please ask first** before embarking on any significant pull request (e.g., implementing features, refactoring code), otherwise you risk spending time working on something that might not be merged.

## Development Setup

### Prerequisites

- Python 3.8 or higher
- Git
- A Discord bot token for testing
- A Serializd account for testing

### Setup Instructions

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/your-username/serializd-discord-bot.git
   cd serializd-discord-bot
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up your environment**
   ```bash
   cp env.example .env
   # Edit .env with your test bot token
   ```

5. **Create a test Discord server**
   - Create a new Discord server for testing
   - Invite your bot with appropriate permissions
   - Set up test channels

6. **Run the bot**
   ```bash
   python bot.py
   ```

### Testing Your Changes

1. **Test all affected commands** thoroughly
2. **Check for errors** in the console
3. **Verify Discord embeds** render correctly
4. **Test edge cases** (empty data, API errors, etc.)
5. **Ensure backward compatibility** with existing configurations

## Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/amazing-feature
   ```

2. **Make your changes**
   - Write clear, commented code
   - Follow the existing code style
   - Update documentation if needed

3. **Test your changes**
   - Test all modified functionality
   - Check for any breaking changes
   - Verify no regressions occurred

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "Add amazing feature"
   ```
   See [Commit Message Guidelines](#commit-message-guidelines) below.

5. **Push to your fork**
   ```bash
   git push origin feature/amazing-feature
   ```

6. **Open a Pull Request**
   - Use a clear title describing the change
   - Reference any related issues
   - Describe what changed and why
   - Include screenshots if UI changes are involved
   - List any breaking changes

7. **Address review feedback**
   - Be responsive to code review comments
   - Make requested changes promptly
   - Ask questions if feedback is unclear

## Coding Standards

### Python Style Guide

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guidelines
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 120 characters (soft limit)
- Use descriptive variable names
- Add docstrings to functions and classes

### Code Organization

```python
# Good
async def fetch_user_diary(username: str, hours_limit: int = None) -> list:
    """
    Fetch diary entries for a user from Serializd API.
    
    Args:
        username: Serializd username
        hours_limit: Optional time filter in hours
        
    Returns:
        List of diary entry dictionaries
    """
    # Implementation
    pass

# Avoid
async def get_stuff(u, h=None):
    # No docstring, unclear names
    pass
```

### Discord Bot Best Practices

- Always defer long-running interactions: `await interaction.response.defer()`
- Use ephemeral messages for errors: `ephemeral=True`
- Provide clear error messages to users
- Log errors with context for debugging
- Handle API failures gracefully

### Error Handling

```python
# Good - Graceful error handling
try:
    data = await fetch_api_data(url)
    if not data:
        await interaction.followup.send("⚠️ No data found.", ephemeral=True)
        return
except Exception as e:
    log.error(f"API error: {e}")
    await interaction.followup.send("❌ Something went wrong. Please try again.", ephemeral=True)
    return

# Avoid - Bare exceptions that hide errors
try:
    data = await fetch_api_data(url)
except:
    pass
```

## Commit Message Guidelines

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation changes
- **style**: Code style changes (formatting, semicolons, etc.)
- **refactor**: Code refactoring
- **perf**: Performance improvements
- **test**: Adding or updating tests
- **chore**: Maintenance tasks, dependency updates

### Examples

```
feat(commands): add /stats command for user statistics

- Fetches total shows watched, episodes logged
- Shows average rating and top genres
- Includes pagination for large datasets

Closes #42
```

```
fix(embeds): correct season name display logic

- Add fallback to showSeasons array
- Fix empty season name handling
- Add debug logging for season extraction

Fixes #38
```

```
docs(readme): update installation instructions

- Add Python version requirement
- Clarify Discord bot permissions
- Add troubleshooting section
```

## Questions?

Feel free to:
- Open an issue with the `question` label
- Reach out in GitHub Discussions
- Comment on existing issues or PRs

Thank you for contributing! 🙏
