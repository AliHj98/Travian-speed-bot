import os
import time
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.firefox import GeckoDriverManager
from config import config


class BrowserManager:
    """Manages the browser instance for web automation - OPTIMIZED FOR SPEED"""

    def __init__(self):
        self.driver = None
        self.wait = None
        self.tabs = {}  # name -> window_handle mapping
        self.main_tab = None

    def start(self):
        """Initialize and start the browser"""
        firefox_options = Options()

        if config.headless:
            firefox_options.add_argument('--headless')

        # Performance optimizations
        firefox_options.add_argument('--no-sandbox')
        firefox_options.add_argument('--disable-dev-shm-usage')
        firefox_options.set_preference('dom.webdriver.enabled', False)
        firefox_options.set_preference('useAutomationExtension', False)

        # Disable images for faster loading (optional - comment out if you need images)
        # firefox_options.set_preference('permissions.default.image', 2)

        # Disable CSS (optional - might break some things)
        # firefox_options.set_preference('permissions.default.stylesheet', 2)

        # Faster page load
        firefox_options.set_preference('network.http.pipelining', True)
        firefox_options.set_preference('network.http.proxy.pipelining', True)
        firefox_options.set_preference('browser.cache.disk.enable', True)
        firefox_options.set_preference('browser.cache.memory.enable', True)

        # Set user agent
        firefox_options.set_preference('general.useragent.override',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0')

        # Create screenshots directory
        os.makedirs(config.screenshots_dir, exist_ok=True)

        # Initialize driver
        self.driver = webdriver.Firefox(options=firefox_options)
        self.driver.maximize_window()

        # MINIMAL implicit wait for speed
        self.driver.implicitly_wait(0.5)
        self.wait = WebDriverWait(self.driver, 3)

        print("✓ Browser started successfully (Firefox)")

        # Store main tab handle
        self.main_tab = self.driver.current_window_handle
        self.tabs['main'] = self.main_tab

    def stop(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()
            print("✓ Browser closed")

    def navigate_to(self, url: str):
        """Navigate to a URL - NO SLEEP"""
        self.driver.get(url)

    def find_element(self, by: By, value: str, timeout: int = 3):
        """Find an element with SHORT timeout"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return element
        except TimeoutException:
            return None

    def find_elements(self, by: By, value: str):
        """Find multiple elements"""
        try:
            return self.driver.find_elements(by, value)
        except NoSuchElementException:
            return []

    def find_element_fast(self, by: By, value: str):
        """Find element with NO wait - instant"""
        try:
            return self.driver.find_element(by, value)
        except NoSuchElementException:
            return None

    def click_element(self, by: By, value: str, timeout: int = 3):
        """Find and click an element"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, value))
            )
            element.click()
            return True
        except (TimeoutException, Exception) as e:
            return False

    def input_text(self, by: By, value: str, text: str):
        """Input text into an element"""
        element = self.find_element(by, value, timeout=2)
        if element:
            element.clear()
            element.send_keys(text)
            return True
        return False

    def screenshot(self, filename: str):
        """Take a screenshot"""
        filepath = os.path.join(config.screenshots_dir, filename)
        self.driver.save_screenshot(filepath)

    def get_page_source(self) -> str:
        """Get the current page source"""
        return self.driver.page_source

    @property
    def current_url(self) -> str:
        """Get current URL"""
        return self.driver.current_url

    def execute_script(self, script: str):
        """Execute JavaScript"""
        return self.driver.execute_script(script)

    def wait_for_page_load(self, timeout: int = 5):
        """Wait for page to fully load"""
        WebDriverWait(self.driver, timeout).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )

    # ==================== MULTI-TAB SUPPORT ====================

    def new_tab(self, name: str, url: str = None) -> str:
        """Open a new tab with optional URL"""
        # Open new tab using JavaScript
        self.driver.execute_script("window.open('');")

        # Switch to the new tab (last handle)
        new_handle = self.driver.window_handles[-1]
        self.driver.switch_to.window(new_handle)

        # Store the handle
        self.tabs[name] = new_handle

        # Navigate if URL provided
        if url:
            self.driver.get(url)

        print(f"✓ Opened new tab: {name}")
        return new_handle

    def switch_tab(self, name: str) -> bool:
        """Switch to a named tab"""
        if name not in self.tabs:
            print(f"✗ Tab '{name}' not found")
            return False

        try:
            self.driver.switch_to.window(self.tabs[name])
            return True
        except Exception as e:
            print(f"✗ Error switching to tab '{name}': {e}")
            return False

    def close_tab(self, name: str) -> bool:
        """Close a named tab"""
        if name == 'main':
            print("✗ Cannot close main tab")
            return False

        if name not in self.tabs:
            print(f"✗ Tab '{name}' not found")
            return False

        try:
            # Switch to the tab first
            self.driver.switch_to.window(self.tabs[name])
            self.driver.close()
            del self.tabs[name]

            # Switch back to main
            self.driver.switch_to.window(self.main_tab)
            print(f"✓ Closed tab: {name}")
            return True
        except Exception as e:
            print(f"✗ Error closing tab: {e}")
            return False

    def get_current_tab(self) -> str:
        """Get the name of the current tab"""
        current_handle = self.driver.current_window_handle
        for name, handle in self.tabs.items():
            if handle == current_handle:
                return name
        return "unknown"

    def list_tabs(self) -> list:
        """List all open tabs"""
        return list(self.tabs.keys())

    def run_in_tab(self, name: str, func, *args, **kwargs):
        """Run a function in a specific tab, then return to original tab"""
        original_tab = self.get_current_tab()

        if not self.switch_tab(name):
            return None

        try:
            result = func(*args, **kwargs)
        finally:
            self.switch_tab(original_tab)

        return result
