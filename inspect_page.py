#!/usr/bin/env python3
"""
Page Inspector - Analyze Travian page elements using AI
"""

import os
import sys
import base64
from core.browser import BrowserManager
from core.session import TravianSession
from config import config

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None


def inspect_with_ai(browser, question: str = None):
    """Use Claude to analyze the current page"""
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key or api_key == 'your_api_key_here':
        print("⚠️  No API key - showing raw HTML instead")
        return None

    client = Anthropic(api_key=api_key)

    # Take screenshot
    browser.screenshot('inspect.png')

    # Read screenshot
    with open('screenshots/inspect.png', 'rb') as f:
        image_data = base64.standard_b64encode(f.read()).decode('utf-8')

    # Get page source
    html = browser.get_page_source()

    if not question:
        question = "List ALL interactive elements on this page with their CSS selectors"

    prompt = f"""{question}

For each element provide:
1. Element description (what it does)
2. CSS selector
3. XPath (alternative)
4. ID or class names

Page HTML (partial):
```html
{html[:40000]}
```

Format as a clear list."""

    print("\n🤖 AI analyzing page...\n")

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": prompt}
                ],
            }
        ],
    )

    return message.content[0].text


def dump_html(browser, filename: str = 'page_dump.html'):
    """Save current page HTML to file"""
    html = browser.get_page_source()
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✓ HTML saved to {filename}")
    print(f"  Open in browser and use DevTools (F12) to inspect")


def find_elements_by_type(browser):
    """List common element types on page"""
    from selenium.webdriver.common.by import By

    print("\n📋 Elements on current page:\n")

    # Buttons
    buttons = browser.find_elements(By.TAG_NAME, 'button')
    print(f"Buttons ({len(buttons)}):")
    for i, btn in enumerate(buttons[:10]):
        text = btn.text[:30] if btn.text else "[no text]"
        classes = btn.get_attribute('class') or ''
        btn_id = btn.get_attribute('id') or ''
        print(f"  {i+1}. '{text}' | id='{btn_id}' | class='{classes[:50]}'")

    # Links
    links = browser.find_elements(By.TAG_NAME, 'a')
    print(f"\nLinks ({len(links)}):")
    for i, link in enumerate(links[:15]):
        text = link.text[:30] if link.text else "[no text]"
        href = link.get_attribute('href') or ''
        if href:
            href = href.split('/')[-1][:40]
        print(f"  {i+1}. '{text}' -> {href}")

    # Input fields
    inputs = browser.find_elements(By.TAG_NAME, 'input')
    print(f"\nInput fields ({len(inputs)}):")
    for i, inp in enumerate(inputs[:10]):
        inp_type = inp.get_attribute('type') or 'text'
        inp_name = inp.get_attribute('name') or ''
        inp_id = inp.get_attribute('id') or ''
        print(f"  {i+1}. type='{inp_type}' | name='{inp_name}' | id='{inp_id}'")

    # Divs with IDs (important elements)
    divs_with_ids = browser.driver.execute_script(
        "return Array.from(document.querySelectorAll('div[id]')).map(e => ({id: e.id, class: e.className})).slice(0, 20)"
    )
    print(f"\nDiv elements with IDs:")
    for div in divs_with_ids:
        print(f"  #{div['id']} | class='{div['class'][:50]}'")

    # Resource-related elements
    print(f"\nResource elements:")
    for i in range(1, 5):
        elem = browser.find_elements(By.ID, f'l{i}')
        if elem:
            print(f"  #l{i} = {elem[0].text}")

    # Look for specific Travian elements
    print(f"\nTravian-specific elements:")
    travian_selectors = [
        ('#stockBar', 'Stock bar'),
        ('.villageList', 'Village list'),
        ('.buildingSlot', 'Building slots'),
        ('.resource', 'Resources'),
        ('#navigation', 'Navigation'),
        ('.green', 'Green buttons'),
    ]
    for selector, desc in travian_selectors:
        elems = browser.find_elements(By.CSS_SELECTOR, selector)
        if elems:
            print(f"  {selector} ({desc}): {len(elems)} found")


def interactive_inspector(browser):
    """Interactive mode to inspect elements"""
    print("\n" + "=" * 60)
    print("🔍 INTERACTIVE PAGE INSPECTOR")
    print("=" * 60)
    print("Commands:")
    print("  elements  - List all interactive elements")
    print("  html      - Dump HTML to file")
    print("  screenshot- Take screenshot")
    print("  ai <question> - Ask AI about the page")
    print("  find <selector> - Test a CSS selector")
    print("  click <selector> - Click an element")
    print("  quit      - Exit")
    print("=" * 60)

    from selenium.webdriver.common.by import By

    while True:
        try:
            cmd = input("\n> ").strip()

            if not cmd:
                continue
            elif cmd == 'quit' or cmd == 'q':
                break
            elif cmd == 'elements':
                find_elements_by_type(browser)
            elif cmd == 'html':
                dump_html(browser)
            elif cmd == 'screenshot' or cmd == 'ss':
                browser.screenshot('inspect.png')
                print("✓ Screenshot saved to screenshots/inspect.png")
            elif cmd.startswith('ai'):
                question = cmd[3:].strip() if len(cmd) > 3 else None
                result = inspect_with_ai(browser, question)
                if result:
                    print(result)
            elif cmd.startswith('find '):
                selector = cmd[5:].strip()
                try:
                    elems = browser.find_elements(By.CSS_SELECTOR, selector)
                    print(f"✓ Found {len(elems)} element(s)")
                    for i, e in enumerate(elems[:5]):
                        print(f"  {i+1}. text='{e.text[:50]}' tag={e.tag_name}")
                except Exception as e:
                    print(f"✗ Error: {e}")
            elif cmd.startswith('click '):
                selector = cmd[6:].strip()
                try:
                    elem = browser.find_element(By.CSS_SELECTOR, selector)
                    if elem:
                        elem.click()
                        print(f"✓ Clicked element")
                except Exception as e:
                    print(f"✗ Error: {e}")
            elif cmd == 'url':
                print(f"Current URL: {browser.current_url}")
            elif cmd.startswith('goto '):
                url = cmd[5:].strip()
                if not url.startswith('http'):
                    url = f"{config.base_url}/{url}"
                browser.navigate_to(url)
                print(f"✓ Navigated to {url}")
            else:
                print(f"Unknown command: {cmd}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    print("=" * 60)
    print("🔍 TRAVIAN PAGE INSPECTOR")
    print("=" * 60)

    # Start browser
    browser = BrowserManager()
    browser.start()

    # Create session and wait for login
    session = TravianSession(browser)

    if not session.login():
        print("Login failed or timed out")
        browser.stop()
        return

    print("\n✓ Logged in! Starting inspector...\n")

    # Run interactive inspector
    interactive_inspector(browser)

    # Cleanup
    browser.stop()


if __name__ == "__main__":
    main()
