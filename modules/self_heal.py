import os
import base64
import json
from typing import Optional, Dict, List
from anthropic import Anthropic
from config import config


class SelfHealingBot:
    """AI-powered self-debugging and self-healing capabilities"""

    def __init__(self, browser):
        self.browser = browser
        self.client = None
        api_key = os.getenv('ANTHROPIC_API_KEY')

        if api_key and api_key != 'your_api_key_here':
            try:
                self.client = Anthropic(api_key=api_key)
                print("✓ Self-healing AI initialized")
            except Exception as e:
                print(f"⚠️  Self-healing AI could not initialize: {e}")

    def is_available(self) -> bool:
        return self.client is not None

    def analyze_page_for_selector(self,
                                   element_description: str,
                                   failed_selector: str,
                                   screenshot_path: Optional[str] = None) -> Optional[Dict]:
        """
        Analyze the current page to find the correct selector for an element.

        Args:
            element_description: What element we're looking for (e.g., "username input field")
            failed_selector: The selector that didn't work
            screenshot_path: Optional path to screenshot

        Returns:
            Dict with suggested selectors and explanation
        """
        if not self.is_available():
            return None

        try:
            # Get page source
            page_source = self.browser.get_page_source()

            # Truncate if too long
            if len(page_source) > 50000:
                page_source = page_source[:50000] + "\n... (truncated)"

            # Build the prompt
            prompt = f"""You are a Selenium expert debugging a web automation bot for Travian game.

The bot tried to find an element but failed.

**Element we're looking for:** {element_description}
**Failed selector:** {failed_selector}

**Page HTML (partial):**
```html
{page_source[:30000]}
```

Please analyze the HTML and provide:
1. The correct CSS selector(s) to find this element
2. Alternative selectors (XPath, ID, class, etc.)
3. Brief explanation of why the original selector failed

Respond in this JSON format:
{{
    "primary_selector": {{"by": "css", "value": "the selector"}},
    "alternatives": [
        {{"by": "xpath", "value": "xpath selector"}},
        {{"by": "id", "value": "element id"}}
    ],
    "explanation": "Why original failed and how new one works"
}}

Only respond with valid JSON, no other text."""

            # Call Claude API
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text

            # Parse JSON response
            try:
                result = json.loads(response_text)
                print(f"🔧 AI found selector: {result.get('primary_selector', {}).get('value', 'unknown')}")
                return result
            except json.JSONDecodeError:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                return None

        except Exception as e:
            print(f"✗ Self-heal analysis error: {e}")
            return None

    def analyze_screenshot(self, screenshot_path: str, question: str) -> Optional[str]:
        """
        Analyze a screenshot with Claude Vision to understand the page.

        Args:
            screenshot_path: Path to the screenshot
            question: What to analyze

        Returns:
            Claude's analysis
        """
        if not self.is_available():
            return None

        try:
            # Read and encode screenshot
            with open(screenshot_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")

            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2048,
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
                                "text": f"""You are analyzing a Travian game screenshot for a bot.

{question}

Be specific about:
- Element locations and how to identify them
- CSS selectors or XPath that would work
- Any popups or overlays that might be blocking
- Current game state visible on screen"""
                            }
                        ],
                    }
                ],
            )

            return message.content[0].text

        except Exception as e:
            print(f"✗ Screenshot analysis error: {e}")
            return None

    def debug_and_fix(self,
                      error_description: str,
                      current_code: str,
                      page_html: str) -> Optional[Dict]:
        """
        Analyze an error and suggest code fixes.

        Args:
            error_description: What went wrong
            current_code: The code that failed
            page_html: Current page HTML

        Returns:
            Dict with suggested fix
        """
        if not self.is_available():
            return None

        try:
            prompt = f"""You are debugging a Travian game bot written in Python with Selenium.

**Error:** {error_description}

**Current code:**
```python
{current_code}
```

**Page HTML (partial):**
```html
{page_html[:20000]}
```

Analyze the issue and provide a fix. Respond in JSON:
{{
    "issue": "What's wrong",
    "fix": "The corrected Python code",
    "explanation": "Why this fixes it"
}}"""

            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text

            try:
                return json.loads(response_text)
            except:
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                return {"explanation": response_text}

        except Exception as e:
            print(f"✗ Debug analysis error: {e}")
            return None

    def get_game_strategy(self, game_state: Dict) -> Optional[str]:
        """Get strategic advice based on current game state"""
        if not self.is_available():
            return None

        try:
            prompt = f"""You are an expert Travian player advising on strategy.

Current game state:
- Resources: {game_state.get('resources', {})}
- Production: {game_state.get('production', {})}
- Buildings: {game_state.get('buildings', [])}
- Troops: {game_state.get('troops', {})}

This is a SPEED SERVER (10000x) so resources accumulate extremely fast.

Provide specific actionable advice:
1. What to build/upgrade next
2. Troop training priorities
3. Offensive or defensive focus
4. Any urgent actions needed

Keep it concise and actionable."""

            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )

            return message.content[0].text

        except Exception as e:
            print(f"✗ Strategy error: {e}")
            return None


class SmartElementFinder:
    """Smart element finder that uses AI when selectors fail"""

    def __init__(self, browser, healer: SelfHealingBot):
        self.browser = browser
        self.healer = healer
        self.selector_cache = {}  # Cache working selectors

    def find_element(self, description: str, selectors: List[Dict], timeout: int = 10):
        """
        Try to find an element, using AI to find correct selector if all fail.

        Args:
            description: Human description of what we're looking for
            selectors: List of selectors to try, e.g. [{"by": "id", "value": "myId"}]
            timeout: Timeout for each attempt
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        by_map = {
            "id": By.ID,
            "css": By.CSS_SELECTOR,
            "xpath": By.XPATH,
            "class": By.CLASS_NAME,
            "name": By.NAME,
            "tag": By.TAG_NAME,
            "link_text": By.LINK_TEXT,
            "partial_link": By.PARTIAL_LINK_TEXT,
        }

        # Check cache first
        if description in self.selector_cache:
            cached = self.selector_cache[description]
            try:
                element = WebDriverWait(self.browser.driver, timeout).until(
                    EC.presence_of_element_located((by_map[cached["by"]], cached["value"]))
                )
                return element
            except:
                del self.selector_cache[description]  # Cache invalid

        # Try provided selectors
        for selector in selectors:
            try:
                by = by_map.get(selector["by"], By.CSS_SELECTOR)
                element = WebDriverWait(self.browser.driver, timeout).until(
                    EC.presence_of_element_located((by, selector["value"]))
                )
                # Cache working selector
                self.selector_cache[description] = selector
                return element
            except:
                continue

        # All selectors failed - ask AI for help
        if self.healer.is_available():
            print(f"🤖 AI analyzing page to find: {description}")

            failed_selectors = ", ".join([s["value"] for s in selectors])
            result = self.healer.analyze_page_for_selector(description, failed_selectors)

            if result and "primary_selector" in result:
                try:
                    primary = result["primary_selector"]
                    by = by_map.get(primary["by"], By.CSS_SELECTOR)
                    element = WebDriverWait(self.browser.driver, timeout).until(
                        EC.presence_of_element_located((by, primary["value"]))
                    )
                    # Cache the AI-found selector
                    self.selector_cache[description] = primary
                    print(f"✓ AI found element with: {primary['value']}")
                    return element
                except:
                    # Try alternatives
                    for alt in result.get("alternatives", []):
                        try:
                            by = by_map.get(alt["by"], By.CSS_SELECTOR)
                            element = WebDriverWait(self.browser.driver, timeout).until(
                                EC.presence_of_element_located((by, alt["value"]))
                            )
                            self.selector_cache[description] = alt
                            print(f"✓ AI found element with alternative: {alt['value']}")
                            return element
                        except:
                            continue

        print(f"✗ Could not find element: {description}")
        return None
