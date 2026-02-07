"""
Village Cycler Module - Handles switching between multiple villages for tasks
"""

import re
import time
from typing import Dict, List, Optional, Callable
from selenium.webdriver.common.by import By
from core.browser import BrowserManager
from config import config


class VillageCycler:
    """Manages village switching and cycling for multi-village operations"""

    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self._villages_cache: List[Dict] = []
        self._cache_time: float = 0
        self._cache_ttl: int = 300  # Cache villages for 5 minutes

    def get_all_villages(self, force_refresh: bool = False) -> List[Dict]:
        """Get list of all villages from the sidebar (cached)"""
        # Use cache if valid
        if not force_refresh and self._villages_cache and (time.time() - self._cache_time < self._cache_ttl):
            return self._villages_cache

        villages = []

        # Navigate to main page first
        self.browser.navigate_to(f"{config.base_url}/dorf1.php")
        time.sleep(0.3)

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

        # Update cache
        self._villages_cache = unique_villages
        self._cache_time = time.time()

        return unique_villages

    def get_current_village(self) -> Dict:
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
            # Direct URL with newdid is most reliable
            self.browser.navigate_to(f"{config.base_url}/dorf1.php?newdid={village_id}")
            time.sleep(0.3)

            if self._verify_switch(village_id):
                return True

            # Fallback: Try villageId param
            self.browser.navigate_to(f"{config.base_url}/dorf1.php?villageId={village_id}")
            time.sleep(0.3)
            return self._verify_switch(village_id)

        except Exception as e:
            print(f"  Error switching village: {e}")
            return False

    def _verify_switch(self, village_id: str) -> bool:
        """Verify that the village switch actually happened"""
        try:
            # Check URL
            current_url = self.browser.driver.current_url
            if f'newdid={village_id}' in current_url or f'villageId={village_id}' in current_url:
                return True

            # Check active village in sidebar
            try:
                elem = self.browser.find_element_fast(By.CSS_SELECTOR, '.villageList li.active a')
                if elem:
                    href = elem.get_attribute('href') or ''
                    if re.search(rf'(?:newdid|villageId|did)={re.escape(village_id)}(?:\D|$)', href):
                        return True
            except:
                pass

            return False
        except:
            return False

    def cycle_villages(self, action: Callable[[Dict], bool], stop_callback: Callable[[], bool] = None,
                       description: str = "Processing") -> Dict:
        """
        Cycle through all villages and execute an action on each.

        Args:
            action: Function that takes village dict and returns success bool
            stop_callback: Optional function that returns True to stop
            description: Description for logging

        Returns:
            Dict with results: {villages_processed, successes, failures, details}
        """
        if stop_callback is None:
            stop_callback = lambda: False

        results = {
            'villages_processed': 0,
            'successes': 0,
            'failures': 0,
            'details': [],
        }

        villages = self.get_all_villages()
        if not villages:
            print("  No villages found!")
            return results

        # Remember starting village
        start_village = self.get_current_village()

        print(f"\n{description} in {len(villages)} village(s)...")
        print("=" * 50)

        for village in villages:
            if stop_callback():
                print("  Stopped by user")
                break

            print(f"\n  [{village['name']}]")
            results['villages_processed'] += 1

            # Switch to village
            if not self.switch_to_village(village['id']):
                print(f"    Failed to switch to village")
                results['failures'] += 1
                results['details'].append({
                    'village': village['name'],
                    'id': village['id'],
                    'success': False,
                    'error': 'switch_failed'
                })
                continue

            # Execute action
            try:
                success = action(village)
                if success:
                    results['successes'] += 1
                else:
                    results['failures'] += 1
                results['details'].append({
                    'village': village['name'],
                    'id': village['id'],
                    'success': success,
                })
            except Exception as e:
                print(f"    Error: {e}")
                results['failures'] += 1
                results['details'].append({
                    'village': village['name'],
                    'id': village['id'],
                    'success': False,
                    'error': str(e)
                })

        # Return to starting village
        if start_village['id']:
            self.switch_to_village(start_village['id'])

        print(f"\n{'='*50}")
        print(f"Processed: {results['villages_processed']} | Success: {results['successes']} | Failed: {results['failures']}")

        return results

    def cycle_villages_continuous(self, action: Callable[[Dict], bool], stop_callback: Callable[[], bool],
                                   interval: int = 30, description: str = "Processing") -> Dict:
        """
        Continuously cycle through all villages executing an action.
        Keeps going until stop_callback returns True.

        Args:
            action: Function that takes village dict and returns success bool
            stop_callback: Function that returns True to stop
            interval: Seconds to wait between full cycles
            description: Description for logging

        Returns:
            Dict with cumulative results
        """
        total_results = {
            'cycles': 0,
            'villages_processed': 0,
            'successes': 0,
            'failures': 0,
        }

        villages = self.get_all_villages()
        if not villages:
            print("  No villages found!")
            return total_results

        print(f"\nContinuous {description} in {len(villages)} village(s)")
        print(f"Interval: {interval}s between cycles")
        print("=" * 50)

        while not stop_callback():
            total_results['cycles'] += 1
            print(f"\n--- Cycle {total_results['cycles']} ---")

            for village in villages:
                if stop_callback():
                    break

                # Switch to village
                if not self.switch_to_village(village['id']):
                    total_results['failures'] += 1
                    continue

                total_results['villages_processed'] += 1

                # Execute action
                try:
                    success = action(village)
                    if success:
                        total_results['successes'] += 1
                        print(f"  [{village['name']}] Done")
                    else:
                        # Not necessarily a failure - might just be nothing to do
                        pass
                except Exception as e:
                    print(f"  [{village['name']}] Error: {e}")
                    total_results['failures'] += 1

            if stop_callback():
                break

            # Wait between cycles
            print(f"\n  Waiting {interval}s... [Q/S to stop]")
            for _ in range(interval):
                if stop_callback():
                    break
                time.sleep(1)

        return total_results
