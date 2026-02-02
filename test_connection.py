#!/usr/bin/env python3
"""
Simple test script to verify bot configuration and connection
"""

import sys
from config import config
from core.browser import BrowserManager


def test_config():
    """Test configuration"""
    print("Testing configuration...")
    print(f"  Server: {config.server}")
    print(f"  Username: {config.username}")
    print(f"  Password: {'*' * len(config.password) if config.password else 'NOT SET'}")
    print(f"  Base URL: {config.base_url}")

    if not config.validate_credentials():
        print("\n✗ Configuration invalid: Missing username or password")
        print("  Please edit .env file with your credentials")
        return False

    print("✓ Configuration valid")
    return True


def test_browser():
    """Test browser automation"""
    print("\nTesting browser automation...")

    try:
        browser = BrowserManager()
        browser.start()
        print("✓ Browser started successfully")

        # Try to navigate to Travian server
        print(f"\nNavigating to {config.base_url}...")
        browser.navigate_to(config.base_url)
        print("✓ Successfully loaded Travian page")

        # Take a screenshot
        browser.screenshot('test_connection.png')
        print("✓ Screenshot saved to screenshots/test_connection.png")

        # Clean up
        browser.stop()
        print("✓ Browser closed")

        return True

    except Exception as e:
        print(f"\n✗ Browser test failed: {e}")
        return False


def main():
    print("=" * 60)
    print("Travian AI Assistant - Connection Test")
    print("=" * 60)
    print()

    # Test configuration
    if not test_config():
        sys.exit(1)

    # Test browser
    if not test_browser():
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    print("\nYou can now run the bot with: python bot.py")


if __name__ == "__main__":
    main()
