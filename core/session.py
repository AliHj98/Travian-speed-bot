import time
from selenium.webdriver.common.by import By
from core.browser import BrowserManager
from config import config


class TravianSession:
    """Manages Travian game session - AUTO-FILLS USERNAME/PASSWORD + CAPTCHA"""

    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.is_logged_in = False
        self.captcha_solver = None

        # Try to initialize captcha solver
        try:
            from modules.captcha import CaptchaSolver
            self.captcha_solver = CaptchaSolver(browser)
        except ImportError:
            pass

    def login(self) -> bool:
        """Login to Travian - auto-fills credentials, user only enters captcha"""
        try:
            print(f"\n🔐 Opening Travian: {config.base_url}")
            self.browser.navigate_to(config.base_url)
            time.sleep(1)

            # Try to auto-fill username and password
            print("📝 Auto-filling credentials...")

            # Find and fill username field
            username_filled = False
            username_selectors = [
                (By.NAME, 'name'),
                (By.NAME, 'user'),
                (By.NAME, 'username'),
                (By.NAME, 'login'),
                (By.ID, 'name'),
                (By.ID, 'user'),
                (By.ID, 'username'),
                (By.CSS_SELECTOR, 'input[type="text"]'),
            ]

            for by, selector in username_selectors:
                try:
                    elem = self.browser.find_element(by, selector, timeout=1)
                    if elem and elem.is_displayed():
                        elem.clear()
                        elem.send_keys(config.username)
                        username_filled = True
                        print(f"  ✓ Username filled")
                        break
                except:
                    continue

            # Find and fill password field
            password_filled = False
            password_selectors = [
                (By.NAME, 'password'),
                (By.NAME, 'pass'),
                (By.NAME, 'pw'),
                (By.ID, 'password'),
                (By.ID, 'pass'),
                (By.CSS_SELECTOR, 'input[type="password"]'),
            ]

            for by, selector in password_selectors:
                try:
                    elem = self.browser.find_element(by, selector, timeout=1)
                    if elem and elem.is_displayed():
                        elem.clear()
                        elem.send_keys(config.password)
                        password_filled = True
                        print(f"  ✓ Password filled")
                        break
                except:
                    continue

            if username_filled and password_filled:
                print(f"\n{' '*4}✓ Credentials auto-filled!")
            else:
                print(f"\n{' '*4}⚠️  Could not auto-fill all credentials")

            # Try to solve captcha automatically
            captcha_solved = False
            if self.captcha_solver and self.captcha_solver.is_available():
                print("\n🔍 Attempting to solve captcha with Claude Vision...")
                captcha_solved = self.captcha_solver.solve_with_retry(max_retries=3)

                if captcha_solved:
                    print("✓ Captcha filled automatically!")

                    # Click the login button
                    time.sleep(0.5)
                    if self.click_login_button():
                        print("✓ Login button clicked!")
                        print("\nWaiting for login to complete...")
                    else:
                        print("⚠️  Could not click login button")
                        print("\n👉 PLEASE CLICK LOGIN MANUALLY")
                else:
                    print("⚠️  Could not solve captcha")
                    print("\n" + "=" * 50)
                    print("👉 ENTER THE CAPTCHA CODE AND CLICK LOGIN")
                    print("=" * 50)
            else:
                print("\n" + "=" * 50)
                print("👉 ENTER THE CAPTCHA CODE AND CLICK LOGIN")
                print("=" * 50)

            print("\nWaiting for login to complete...")

            # Check every 2 seconds
            max_wait = 300
            waited = 0

            while waited < max_wait:
                if self.verify_login():
                    self.is_logged_in = True
                    print("\n✓ Login successful!")
                    return True

                time.sleep(2)
                waited += 2

                if waited % 10 == 0:
                    print(f"  Waiting... ({waited}s)")

            print("✗ Login timeout")
            return False

        except Exception as e:
            print(f"✗ Login error: {e}")
            return False

    def click_login_button(self) -> bool:
        """Find and click the login button"""
        login_selectors = [
            (By.CSS_SELECTOR, 'button[type="submit"]'),
            (By.CSS_SELECTOR, 'input[type="submit"]'),
            (By.CSS_SELECTOR, 'button.green'),
            (By.CSS_SELECTOR, 'button.login'),
            (By.CSS_SELECTOR, 'input.login'),
            (By.CSS_SELECTOR, 'button[name="login"]'),
            (By.CSS_SELECTOR, 'input[name="login"]'),
            (By.CSS_SELECTOR, 'button[value="Login"]'),
            (By.CSS_SELECTOR, 'input[value="Login"]'),
            (By.CSS_SELECTOR, 'button[value="login"]'),
            (By.CSS_SELECTOR, 'input[value="login"]'),
            (By.CSS_SELECTOR, '.loginButton'),
            (By.CSS_SELECTOR, '#loginButton'),
            (By.CSS_SELECTOR, 'form button'),
            (By.XPATH, '//button[contains(text(), "Login")]'),
            (By.XPATH, '//button[contains(text(), "login")]'),
            (By.XPATH, '//input[@type="submit"]'),
        ]

        for by, selector in login_selectors:
            try:
                elem = self.browser.find_element(by, selector, timeout=1)
                if elem and elem.is_displayed():
                    elem.click()
                    print(f"  Clicked login with selector: {selector}")
                    return True
            except:
                continue

        return False

    def verify_login(self) -> bool:
        """Quick check if logged in"""
        try:
            url = self.browser.current_url
            if 'dorf1.php' in url or 'dorf2.php' in url or 'build.php' in url:
                return True

            if self.browser.find_element_fast(By.ID, 'l1'):
                return True
            if self.browser.find_element_fast(By.ID, 'villageNameField'):
                return True

            return False
        except:
            return False

    def logout(self):
        """Logout from Travian"""
        if self.is_logged_in:
            try:
                self.browser.click_element(By.ID, 'logout', timeout=2)
                self.is_logged_in = False
                print("✓ Logged out")
            except:
                pass

    def get_current_village(self) -> str:
        """Get village name"""
        try:
            elem = self.browser.find_element_fast(By.ID, 'villageNameField')
            if elem:
                return elem.text
            elem = self.browser.find_element_fast(By.ID, 'currentVillage')
            if elem:
                return elem.text
        except:
            pass
        return "Village"

    def navigate_to_village_overview(self):
        """Go to dorf1"""
        self.browser.navigate_to(f"{config.base_url}/dorf1.php")

    def navigate_to_village_center(self):
        """Go to dorf2"""
        self.browser.navigate_to(f"{config.base_url}/dorf2.php")
