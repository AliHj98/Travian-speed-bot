# Travian AI Assistant - Usage Guide

## Quick Start

### 1. Installation

Run the setup script:
```bash
chmod +x setup.sh
./setup.sh
```

Or manually:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Configuration

Edit `.env` file with your credentials:
```bash
nano .env
```

Required settings:
- `TRAVIAN_USERNAME`: Your Travian username
- `TRAVIAN_PASSWORD`: Your Travian password
- `TRAVIAN_SERVER`: Server URL (default: ts1.travian-speed.com)

Optional settings:
- `ANTHROPIC_API_KEY`: For advanced AI decision-making
- `HEADLESS`: Run browser in headless mode (true/false)
- `CHECK_INTERVAL`: Seconds between bot cycles (default: 300)
- `AUTO_BUILD`: Enable automatic building (true/false)
- `AUTO_TRAIN_TROOPS`: Enable automatic troop training (true/false)

### 3. Running the Bot

```bash
source venv/bin/activate
python bot.py
```

## Features

### Automatic Resource Management
- Monitors resource levels in real-time
- Tracks production rates
- Warns when storage is nearly full

### Automatic Building
- Upgrades resource fields automatically
- Prioritizes buildings based on strategy
- Manages building queue efficiently

### Military Management
- Trains troops automatically based on available resources
- Monitors incoming attacks
- Manages troop deployments

### AI Strategy (Optional)
- Uses Claude AI for strategic decision-making
- Analyzes game state and provides recommendations
- Optimizes building and military priorities

## Command Line Options

The bot currently runs with settings from `.env` file. Future versions may include:
- `--config`: Specify custom config file
- `--village`: Specify which village to manage
- `--mode`: Run in different modes (defense, offense, builder)

## Customization

### Adjusting Building Priorities

Edit `modules/buildings.py`, modify the `BUILDING_PRIORITIES` dictionary:
```python
BUILDING_PRIORITIES = {
    'Cropland': 150,  # Higher = more important
    'Main Building': 100,
    # ... etc
}
```

### Adjusting Check Interval

In `.env`:
```
CHECK_INTERVAL=300  # 5 minutes
```

Lower values = more frequent checks, but higher server load.

### Headless Mode

For running on a server without display:
```
HEADLESS=true
```

## Monitoring

### Screenshots
The bot automatically takes screenshots during important events:
- `before_login.png`: Before attempting login
- `after_login.png`: After successful login
- `login_failed.png`: If login fails
- `error_*.png`: When errors occur

Check the `screenshots/` directory.

### Logs
The bot outputs logs to console with timestamps:
- ℹ️  Info messages
- ✓ Success messages
- ⚠️  Warnings
- ✗ Errors

## Troubleshooting

### Login Fails
1. Check credentials in `.env`
2. Verify server URL is correct
3. Check `login_failed.png` screenshot
4. Some servers may have CAPTCHA - bot cannot bypass this

### Element Not Found Errors
Travian's HTML structure may vary by version/server. You may need to:
1. Inspect the actual page elements
2. Update selectors in the code
3. Check browser console for errors

### Browser Won't Start
1. Make sure Chrome/Chromium is installed
2. Run: `pip install --upgrade selenium webdriver-manager`
3. Try non-headless mode first

### Bot Stops Unexpectedly
1. Check error screenshots
2. Verify internet connection
3. Check if you were logged out (session timeout)

## Safety Tips

### Avoid Detection
1. Use reasonable check intervals (5+ minutes)
2. Don't run 24/7 - use business hours
3. Randomize timing (future feature)
4. Use headless mode sparingly

### Resource Management
1. Monitor crop production - negative crop kills troops
2. Don't let warehouses fill completely
3. Keep some resources for emergencies

### Military Strategy
1. Don't auto-train expensive troops early
2. Monitor incoming attacks manually
3. Use AI recommendations as guidance, not absolute rules

## Advanced Usage

### Using AI Strategy

To enable AI-powered decision making:
1. Get an Anthropic API key from https://console.anthropic.com/
2. Add to `.env`: `ANTHROPIC_API_KEY=your_key_here`
3. The bot will use Claude AI for strategic analysis

### Multiple Villages (Future)
Currently supports single village. Multi-village support planned.

### Custom Strategies
Create your own strategy by extending `AIStrategist` class in `modules/ai_strategy.py`.

## Legal Disclaimer

This bot is for **educational purposes only**.

Using automation tools **violates Travian's Terms of Service** and may result in:
- Account warnings
- Temporary bans
- Permanent account deletion

**Use at your own risk.** The developers are not responsible for any consequences of using this bot.

## Support

For issues and questions:
1. Check this usage guide
2. Review the code comments
3. Check screenshots for visual debugging
4. Modify selectors for your specific server version

## Contributing

To improve the bot:
1. Test on your server
2. Update selectors if needed
3. Add new features (market trading, alliance management, etc.)
4. Share improvements

## Future Enhancements

Planned features:
- Multi-village support
- Market automation
- Advanced attack coordination
- Farm list management
- Alliance features
- Web dashboard
- Mobile notifications
