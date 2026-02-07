#!/usr/bin/env python3
"""
Village Switcher Test - Tests multi-village switching functionality
"""

import time
import re
from selenium.webdriver.common.by import By
from core.browser import BrowserManager
from core.session import TravianSession
from config import config


class VillageSwitcherTest:
    """Test village switching functionality"""

    def __init__(self, browser: BrowserManager):
        self.browser = browser

    def get_all_villages(self) -> list:
        """Get list of all villages from the sidebar"""
        villages = []

        # Navigate to main page first
        self.browser.navigate_to(f"{config.base_url}/dorf1.php")
        time.sleep(0.5)

        # Try multiple selectors for village list
        selectors = [
            '#sidebarBoxVillagelist .villageList li a',
            '.villageList li a',
            '#villageList a',
            '.sidebarBoxInnerBox .villageList a',
            'a[href*="newdid="]',
        ]

        for selector in selectors:
            try:
                links = self.browser.find_elements(By.CSS_SELECTOR, selector)
                if links:
                    for link in links:
                        try:
                            href = link.get_attribute('href') or ''
                            name = link.text.strip()
                            if not name:
                                continue

                            # Extract village ID
                            vid_match = re.search(r'(?:newdid|villageId|did)=(\d+)', href)
                            if vid_match:
                                villages.append({
                                    'id': vid_match.group(1),
                                    'name': name,
                                    'href': href,
                                })
                        except:
                            continue
                    if villages:
                        break
            except:
                continue

        # Deduplicate by ID
        seen_ids = set()
        unique_villages = []
        for v in villages:
            if v['id'] not in seen_ids:
                seen_ids.add(v['id'])
                unique_villages.append(v)

        return unique_villages

    def get_current_village(self) -> dict:
        """Get info about currently active village"""
        result = {'id': None, 'name': None}

        # Try to get from URL
        current_url = self.browser.driver.current_url
        vid_match = re.search(r'(?:newdid|villageId|did)=(\d+)', current_url)
        if vid_match:
            result['id'] = vid_match.group(1)

        # Try to get name from page
        name_selectors = [
            '#villageNameField',
            '.villageList .active',
            '#currentVillage',
            '.villageList li.active a',
        ]

        for selector in name_selectors:
            try:
                elem = self.browser.find_element_fast(By.CSS_SELECTOR, selector)
                if elem and elem.text.strip():
                    result['name'] = elem.text.strip()
                    break
            except:
                continue

        # If no ID yet, try to get from active village link
        if not result['id']:
            try:
                active = self.browser.find_element_fast(By.CSS_SELECTOR, '.villageList li.active a')
                if active:
                    href = active.get_attribute('href') or ''
                    vid_match = re.search(r'(?:newdid|villageId|did)=(\d+)', href)
                    if vid_match:
                        result['id'] = vid_match.group(1)
            except:
                pass

        return result

    def switch_to_village(self, village_id: str) -> bool:
        """Switch to a specific village by ID"""
        try:
            # Method 1: Direct URL with newdid
            self.browser.navigate_to(f"{config.base_url}/dorf1.php?newdid={village_id}")
            time.sleep(0.5)

            if self.verify_village_switch(village_id):
                return True

            # Method 2: Try clicking in sidebar
            selectors = [
                f'a[href*="newdid={village_id}"]',
                f'a[href*="villageId={village_id}"]',
                f'a[href*="did={village_id}"]',
            ]

            for selector in selectors:
                try:
                    link = self.browser.find_element_fast(By.CSS_SELECTOR, selector)
                    if link:
                        link.click()
                        time.sleep(0.5)
                        if self.verify_village_switch(village_id):
                            return True
                except:
                    continue

            # Method 3: Try villageId param
            self.browser.navigate_to(f"{config.base_url}/dorf1.php?villageId={village_id}")
            time.sleep(0.5)
            return self.verify_village_switch(village_id)

        except Exception as e:
            print(f"  Error switching: {e}")
            return False

    def verify_village_switch(self, village_id: str) -> bool:
        """Verify that the village switch actually happened"""
        try:
            # Check URL
            current_url = self.browser.driver.current_url
            if f'newdid={village_id}' in current_url or f'villageId={village_id}' in current_url:
                return True

            # Check active village in sidebar
            active_selectors = [
                '.villageList li.active a',
                '#sidebarBoxVillagelist .villageList li.active a',
            ]

            for selector in active_selectors:
                try:
                    elem = self.browser.find_element_fast(By.CSS_SELECTOR, selector)
                    if elem:
                        href = elem.get_attribute('href') or ''
                        if re.search(rf'(?:newdid|villageId|did)={re.escape(village_id)}(?:\D|$)', href):
                            return True
                except:
                    continue

            return False

        except:
            return False

    def run_test(self) -> dict:
        """
        Run the village switcher test.
        Returns dict with test results.
        """
        results = {
            'villages_found': 0,
            'switches_attempted': 0,
            'switches_successful': 0,
            'switches_failed': 0,
            'details': [],
        }

        print("=" * 60)
        print("VILLAGE SWITCHER TEST")
        print("=" * 60)

        # Step 1: Get all villages
        print("\n[1] Getting list of villages...")
        villages = self.get_all_villages()
        results['villages_found'] = len(villages)

        if not villages:
            print("  ERROR: No villages found!")
            print("  Make sure you are logged in and have villages.")
            return results

        print(f"  Found {len(villages)} village(s):")
        for i, v in enumerate(villages, 1):
            print(f"    {i}. {v['name']} (ID: {v['id']})")

        # Step 2: Get current village
        print("\n[2] Getting current village...")
        current = self.get_current_village()
        print(f"  Current: {current['name']} (ID: {current['id']})")

        # Step 3: Test switching to each village
        print("\n[3] Testing village switching...")
        print("-" * 40)

        for village in villages:
            results['switches_attempted'] += 1
            print(f"\n  Switching to: {village['name']} (ID: {village['id']})...")

            success = self.switch_to_village(village['id'])

            if success:
                # Verify we're on the right village
                after = self.get_current_village()
                if after['id'] == village['id'] or after['name'] == village['name']:
                    print(f"    ✓ SUCCESS - Now on: {after['name']}")
                    results['switches_successful'] += 1
                    results['details'].append({
                        'village': village['name'],
                        'id': village['id'],
                        'status': 'success',
                    })
                else:
                    print(f"    ✗ MISMATCH - Expected {village['name']}, got {after['name']}")
                    results['switches_failed'] += 1
                    results['details'].append({
                        'village': village['name'],
                        'id': village['id'],
                        'status': 'mismatch',
                        'actual': after['name'],
                    })
            else:
                print(f"    ✗ FAILED - Could not switch")
                results['switches_failed'] += 1
                results['details'].append({
                    'village': village['name'],
                    'id': village['id'],
                    'status': 'failed',
                })

        # Step 4: Switch back to original village
        if current['id']:
            print(f"\n[4] Switching back to original village: {current['name']}...")
            if self.switch_to_village(current['id']):
                print("    ✓ Restored original village")
            else:
                print("    ✗ Could not restore original village")

        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        print(f"  Villages found:      {results['villages_found']}")
        print(f"  Switches attempted:  {results['switches_attempted']}")
        print(f"  Switches successful: {results['switches_successful']}")
        print(f"  Switches failed:     {results['switches_failed']}")

        if results['switches_failed'] == 0 and results['switches_successful'] > 0:
            print("\n  ✓ ALL TESTS PASSED!")
        elif results['switches_successful'] > 0:
            print(f"\n  ⚠ PARTIAL SUCCESS ({results['switches_successful']}/{results['switches_attempted']})")
        else:
            print("\n  ✗ ALL TESTS FAILED")

        print("=" * 60)

        return results


def main():
    """Main entry point for running the test standalone"""
    print("Initializing browser...")

    browser = BrowserManager(headless=config.headless)
    session = TravianSession(browser)

    try:
        # Login
        print("Logging in...")
        if not session.login():
            print("Login failed!")
            return

        print("Login successful!\n")
        time.sleep(1)

        # Run the test
        tester = VillageSwitcherTest(browser)
        results = tester.run_test()

        # Keep browser open for inspection
        input("\nPress Enter to close browser...")

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        browser.quit()


if __name__ == "__main__":
    main()
