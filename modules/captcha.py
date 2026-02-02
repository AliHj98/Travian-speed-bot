"""
Captcha Solver Module - Claude Vision-based captcha solving
"""

import os
import re
import time
import base64
from io import BytesIO
from typing import Optional

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from selenium.webdriver.common.by import By
from core.browser import BrowserManager
from config import config


class CaptchaSolver:
    """Claude Vision-based captcha solver for Travian"""

    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.screenshots_dir = 'screenshots'
        os.makedirs(self.screenshots_dir, exist_ok=True)

        # Initialize Claude client
        self.client = None
        if ANTHROPIC_AVAILABLE and config.anthropic_api_key:
            self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    def is_available(self) -> bool:
        """Check if Claude Vision is available"""
        return self.client is not None

    def find_captcha_image(self) -> Optional[object]:
        """Find the captcha image element on the page"""
        # Common captcha image selectors for Travian
        selectors = [
            (By.CSS_SELECTOR, 'img[src*="captcha"]'),
            (By.CSS_SELECTOR, 'img[alt*="captcha"]'),
            (By.CSS_SELECTOR, 'img[class*="captcha"]'),
            (By.CSS_SELECTOR, '.captcha img'),
            (By.CSS_SELECTOR, '#captcha img'),
            (By.CSS_SELECTOR, 'img[src*="security"]'),
            (By.CSS_SELECTOR, 'img[src*="code"]'),
            (By.CSS_SELECTOR, 'img[src*="human"]'),
            (By.CSS_SELECTOR, 'canvas'),  # Some captchas use canvas
            (By.XPATH, '//img[contains(@src, "captcha")]'),
            (By.XPATH, '//img[contains(@class, "captcha")]'),
            # Generic - find any small image that might be captcha
            (By.CSS_SELECTOR, 'form img'),
            (By.CSS_SELECTOR, '.loginForm img'),
            (By.CSS_SELECTOR, '#loginForm img'),
        ]

        for by, selector in selectors:
            try:
                elem = self.browser.find_element(by, selector, timeout=1)
                if elem and elem.is_displayed():
                    # Check if it's a reasonable size for a captcha (not too big, not too small)
                    size = elem.size
                    if size['width'] > 30 and size['height'] > 15:
                        print(f"  Found captcha with selector: {selector}")
                        return elem
            except:
                continue

        return None

    def find_captcha_input(self) -> Optional[object]:
        """Find the captcha input field"""
        selectors = [
            (By.NAME, 'captcha'),
            (By.NAME, 'code'),
            (By.NAME, 'security'),
            (By.NAME, 'securityCode'),
            (By.NAME, 'human'),
            (By.NAME, 'answer'),
            (By.ID, 'captcha'),
            (By.ID, 'code'),
            (By.ID, 'security'),
            (By.CSS_SELECTOR, 'input[name*="captcha"]'),
            (By.CSS_SELECTOR, 'input[name*="code"]'),
            (By.CSS_SELECTOR, 'input[name*="human"]'),
            (By.CSS_SELECTOR, 'input[placeholder*="code"]'),
            (By.CSS_SELECTOR, 'input[placeholder*="captcha"]'),
            (By.CSS_SELECTOR, 'input[placeholder*="security"]'),
            # Generic text inputs near captcha area
            (By.CSS_SELECTOR, '.captcha input[type="text"]'),
            (By.CSS_SELECTOR, 'form input[type="text"]:not([name="name"]):not([name="user"]):not([name="username"]):not([name="password"])'),
        ]

        for by, selector in selectors:
            try:
                elem = self.browser.find_element(by, selector, timeout=1)
                if elem and elem.is_displayed():
                    print(f"  Found captcha input with selector: {selector}")
                    return elem
            except:
                continue

        return None

    def capture_captcha_image(self, captcha_elem) -> Optional[str]:
        """Capture the captcha image to a file"""
        try:
            filepath = os.path.join(self.screenshots_dir, 'captcha_temp.png')

            # Method 1: Screenshot the element directly
            try:
                captcha_elem.screenshot(filepath)
                if os.path.exists(filepath) and os.path.getsize(filepath) > 100:
                    print(f"  Captured captcha via element screenshot")
                    return filepath
            except Exception as e:
                print(f"  Element screenshot failed: {e}")

            # Method 2: Get image from src attribute (base64)
            try:
                src = captcha_elem.get_attribute('src')
                if src and src.startswith('data:image'):
                    img_data = src.split(',')[1]
                    with open(filepath, 'wb') as f:
                        f.write(base64.b64decode(img_data))
                    print(f"  Captured captcha from base64 src")
                    return filepath
            except:
                pass

            # Method 3: Download from URL
            try:
                src = captcha_elem.get_attribute('src')
                if src and src.startswith('http'):
                    import requests
                    response = requests.get(src, timeout=5)
                    if response.status_code == 200:
                        with open(filepath, 'wb') as f:
                            f.write(response.content)
                        print(f"  Captured captcha from URL")
                        return filepath
            except:
                pass

            # Method 4: Full page screenshot and crop
            try:
                if PIL_AVAILABLE:
                    self.browser.screenshot('full_page_temp.png')
                    full_path = os.path.join(self.screenshots_dir, 'full_page_temp.png')

                    location = captcha_elem.location
                    size = captcha_elem.size

                    img = Image.open(full_path)
                    left = location['x']
                    top = location['y']
                    right = left + size['width']
                    bottom = top + size['height']

                    captcha_img = img.crop((left, top, right, bottom))
                    captcha_img.save(filepath)
                    print(f"  Captured captcha via crop")
                    return filepath
            except Exception as e:
                print(f"  Crop method failed: {e}")

            return None

        except Exception as e:
            print(f"  Error capturing captcha: {e}")
            return None

    def read_captcha_with_claude(self, image_path: str) -> Optional[str]:
        """Use Claude Vision to read the captcha"""
        if not self.client:
            print("  Claude API not configured")
            return None

        try:
            # Read and encode image
            with open(image_path, 'rb') as f:
                image_data = base64.standard_b64encode(f.read()).decode('utf-8')

            # Determine media type
            if image_path.lower().endswith('.png'):
                media_type = "image/png"
            elif image_path.lower().endswith('.jpg') or image_path.lower().endswith('.jpeg'):
                media_type = "image/jpeg"
            else:
                media_type = "image/png"

            print("  Sending captcha to Claude Vision...")

            # Call Claude API with vision
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": "Read the captcha text in this image. Reply with ONLY the captcha characters, nothing else. No explanation, no punctuation, just the exact characters you see."
                            }
                        ],
                    }
                ],
            )

            # Extract result
            result = message.content[0].text.strip()

            # Clean up - remove any extra characters
            result = re.sub(r'[^A-Za-z0-9]', '', result)

            print(f"  Claude read: {result}")
            return result

        except Exception as e:
            print(f"  Claude Vision error: {e}")
            return None

    def solve_captcha(self) -> Optional[str]:
        """Main method to solve the captcha on current page"""
        if not self.is_available():
            print("  Claude Vision not available - check ANTHROPIC_API_KEY")
            return None

        print("  Looking for captcha image...")

        # Find captcha image
        captcha_img_elem = self.find_captcha_image()
        if not captcha_img_elem:
            print("  No captcha image found on page")
            # Try taking full screenshot and asking Claude
            return self.solve_from_screenshot()

        print("  Captcha image found, capturing...")

        # Capture the image
        image_path = self.capture_captcha_image(captcha_img_elem)
        if not image_path:
            print("  Could not capture captcha image")
            return self.solve_from_screenshot()

        # Use Claude to read it
        result = self.read_captcha_with_claude(image_path)
        return result

    def solve_from_screenshot(self) -> Optional[str]:
        """Take a full screenshot and ask Claude to find and read the captcha"""
        if not self.client:
            return None

        print("  Taking full page screenshot for Claude...")

        screenshot_path = os.path.join(self.screenshots_dir, 'login_page.png')
        self.browser.driver.save_screenshot(screenshot_path)

        try:
            with open(screenshot_path, 'rb') as f:
                image_data = base64.standard_b64encode(f.read()).decode('utf-8')

            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=100,
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
                            {
                                "type": "text",
                                "text": "This is a login page. Find the captcha/security code image and read its text. Reply with ONLY the captcha characters, nothing else. If you can't find a captcha, reply with 'NOCAPTCHA'."
                            }
                        ],
                    }
                ],
            )

            result = message.content[0].text.strip()

            if 'NOCAPTCHA' in result.upper():
                print("  No captcha found in screenshot")
                return None

            # Clean up
            result = re.sub(r'[^A-Za-z0-9]', '', result)
            print(f"  Claude read from screenshot: {result}")
            return result

        except Exception as e:
            print(f"  Screenshot analysis error: {e}")
            return None

    def solve_and_fill(self) -> bool:
        """Solve captcha and fill in the input field"""
        solution = self.solve_captcha()

        if not solution:
            return False

        # Find and fill the input
        captcha_input = self.find_captcha_input()
        if not captcha_input:
            print("  Could not find captcha input field")
            return False

        print(f"  Filling captcha: {solution}")
        captcha_input.clear()
        captcha_input.send_keys(solution)

        return True

    def solve_with_retry(self, max_retries: int = 3) -> bool:
        """Try to solve captcha with retries"""
        for attempt in range(max_retries):
            print(f"  Captcha attempt {attempt + 1}/{max_retries}")

            if self.solve_and_fill():
                return True

            # Wait a bit before retry
            time.sleep(1)

            # Try to refresh captcha if there's a refresh button
            refresh_selectors = [
                (By.CSS_SELECTOR, 'a[onclick*="captcha"]'),
                (By.CSS_SELECTOR, 'button[onclick*="captcha"]'),
                (By.CSS_SELECTOR, '.captcha-refresh'),
                (By.CSS_SELECTOR, 'a.refresh'),
                (By.CSS_SELECTOR, 'img[onclick]'),  # Clickable captcha image to refresh
            ]

            for by, selector in refresh_selectors:
                try:
                    elem = self.browser.find_element(by, selector, timeout=1)
                    if elem:
                        elem.click()
                        print("  Refreshed captcha")
                        time.sleep(1)
                        break
                except:
                    continue

        return False
