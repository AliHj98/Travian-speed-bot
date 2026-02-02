# Travian AI Assistant

An AI-powered automation assistant for Travian (ts1.travian-speed.com).

## Features

- 🏗️ **Automatic Building Management**: Optimizes building queues and resource production
- ⚔️ **Military Strategy**: Manages troop training and military operations
- 📊 **Resource Optimization**: Monitors and optimizes resource collection
- 🤖 **AI Decision Making**: Uses AI to make strategic decisions
- 🔔 **Event Monitoring**: Tracks game state and sends alerts

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure settings:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Run the bot:
```bash
python bot.py
```

## Disclaimer

This bot is for educational purposes only. Using automation tools may violate Travian's Terms of Service and could result in account penalties or bans. Use at your own risk.

## Project Structure

- `bot.py` - Main entry point
- `config.py` - Configuration management
- `core/` - Core bot functionality
  - `browser.py` - Browser automation
  - `session.py` - Session management
- `modules/` - Game-specific modules
  - `buildings.py` - Building management
  - `resources.py` - Resource monitoring
  - `military.py` - Troop and military management
  - `ai_strategy.py` - AI decision making
- `utils/` - Utility functions
