import re
from typing import Dict, Optional
from selenium.webdriver.common.by import By
from core.browser import BrowserManager


class ResourceMonitor:
    """Monitors and manages village resources for Travian Speed Server"""

    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.resources = {
            'wood': 0,
            'clay': 0,
            'iron': 0,
            'crop': 0
        }
        self.storage_capacity = {
            'wood': 8000000,
            'clay': 8000000,
            'iron': 8000000,
            'crop': 8000000
        }
        self.production = {
            'wood': 0,
            'clay': 0,
            'iron': 0,
            'crop': 0
        }
        self.crop_consumption = 0
        self.free_crop = 0

    def close_popups(self):
        """Close any popups/dialogs that might be open"""
        try:
            close_selectors = [
                '.dialogCancelBtn',
                '.closeButton',
                'button.cancel',
                '.popupClose',
            ]
            for selector in close_selectors:
                elements = self.browser.find_elements(By.CSS_SELECTOR, selector)
                for elem in elements:
                    try:
                        if elem.is_displayed():
                            elem.click()
                            print("✓ Closed popup")
                            return True
                    except:
                        pass
        except:
            pass
        return False

    def update_resources(self) -> Dict[str, int]:
        """Fetch current resource levels from the page"""
        try:
            self.close_popups()

            # Resource IDs: l1=wood, l2=clay, l3=iron, l4=crop, l5=crop consumption
            resource_map = {
                'wood': 'l1',
                'clay': 'l2',
                'iron': 'l3',
                'crop': 'l4'
            }

            for resource, elem_id in resource_map.items():
                try:
                    element = self.browser.find_element(By.ID, elem_id, timeout=3)
                    if element:
                        text = element.text.strip()
                        # Format is "current/max" e.g. "4542540/8000000"
                        if '/' in text:
                            parts = text.split('/')
                            current = int(re.sub(r'[^\d]', '', parts[0]))
                            capacity = int(re.sub(r'[^\d]', '', parts[1]))
                            self.resources[resource] = current
                            self.storage_capacity[resource] = capacity
                        else:
                            # Just a number
                            number = re.sub(r'[^\d-]', '', text)
                            if number:
                                self.resources[resource] = int(number)
                except Exception as e:
                    pass

            # Get crop consumption (l5)
            try:
                l5_elem = self.browser.find_element(By.ID, 'l5', timeout=2)
                if l5_elem:
                    text = l5_elem.text.strip()
                    if '/' in text:
                        parts = text.split('/')
                        self.crop_consumption = int(re.sub(r'[^\d]', '', parts[0]))
                        self.free_crop = int(re.sub(r'[^\d]', '', parts[1]))
            except:
                pass

            self._print_resources()
            return self.resources

        except Exception as e:
            print(f"✗ Error updating resources: {e}")
            return self.resources

    def update_production(self) -> Dict[str, int]:
        """Get resource production rates from page JavaScript"""
        try:
            # Production is stored in JavaScript: resources.production = {'l1': 1440000, ...}
            # We can extract it using JavaScript execution
            script = """
            if (typeof resources !== 'undefined' && resources.production) {
                return JSON.stringify(resources.production);
            }
            return null;
            """
            result = self.browser.driver.execute_script(script)

            if result:
                import json
                prod_data = json.loads(result)
                self.production['wood'] = prod_data.get('l1', 0)
                self.production['clay'] = prod_data.get('l2', 0)
                self.production['iron'] = prod_data.get('l3', 0)
                self.production['crop'] = prod_data.get('l4', 0)

                self._print_production()

            return self.production

        except Exception as e:
            print(f"✗ Error updating production: {e}")
            return self.production

    def _format_num(self, n: int) -> str:
        """Format large numbers for display"""
        if n >= 1_000_000_000_000:
            return f"{n/1_000_000_000_000:.1f}T"
        elif n >= 1_000_000_000:
            return f"{n/1_000_000_000:.1f}B"
        elif n >= 1_000_000:
            return f"{n/1_000_000:.1f}M"
        elif n >= 1_000:
            return f"{n/1_000:.0f}K"
        return str(n)

    def _print_resources(self):
        """Print current resources"""
        print(f"📊 Resources: "
              f"Wood={self._format_num(self.resources['wood'])}/{self._format_num(self.storage_capacity['wood'])}, "
              f"Clay={self._format_num(self.resources['clay'])}/{self._format_num(self.storage_capacity['clay'])}, "
              f"Iron={self._format_num(self.resources['iron'])}/{self._format_num(self.storage_capacity['iron'])}, "
              f"Crop={self._format_num(self.resources['crop'])}/{self._format_num(self.storage_capacity['crop'])}")
        if self.crop_consumption > 0:
            print(f"🌾 Troops: {self.crop_consumption} consuming / {self._format_num(self.free_crop)} free crop")

    def _print_production(self):
        """Print production rates"""
        print(f"⚙️  Production/h: "
              f"Wood={self._format_num(self.production['wood'])}, "
              f"Clay={self._format_num(self.production['clay'])}, "
              f"Iron={self._format_num(self.production['iron'])}, "
              f"Crop={self._format_num(self.production['crop'])}")

    def update_storage(self) -> Dict[str, int]:
        """Storage is now updated in update_resources()"""
        return self.storage_capacity

    def get_storage_percentage(self, resource: str) -> float:
        """Get storage fill percentage"""
        if resource in self.resources and resource in self.storage_capacity:
            if self.storage_capacity[resource] > 0:
                return self.resources[resource] / self.storage_capacity[resource] * 100
        return 0

    def is_storage_full(self, resource: str, threshold: float = 0.9) -> bool:
        """Check if storage is almost full"""
        return self.get_storage_percentage(resource) >= threshold * 100

    def has_resources(self, required: Dict[str, int]) -> bool:
        """Check if we have enough resources"""
        for resource, amount in required.items():
            if resource in self.resources:
                if self.resources[resource] < amount:
                    return False
        return True

    def get_resource_shortage(self, required: Dict[str, int]) -> Dict[str, int]:
        """Calculate resource shortage"""
        shortage = {}
        for resource, amount in required.items():
            if resource in self.resources:
                if self.resources[resource] < amount:
                    shortage[resource] = amount - self.resources[resource]
        return shortage

    def time_until_resources(self, required: Dict[str, int]) -> Optional[int]:
        """Calculate seconds until we have required resources"""
        max_time = 0
        for resource, amount in required.items():
            if resource in self.resources and resource in self.production:
                current = self.resources[resource]
                prod_per_hour = self.production[resource]
                if current >= amount:
                    continue
                if prod_per_hour <= 0:
                    return None
                needed = amount - current
                hours = needed / prod_per_hour
                seconds = int(hours * 3600)
                max_time = max(max_time, seconds)
        return max_time if max_time > 0 else 0

    def format_resources(self) -> str:
        """Format resources as a readable string"""
        return (f"🪵 {self._format_num(self.resources['wood'])} | "
                f"🧱 {self._format_num(self.resources['clay'])} | "
                f"⚒️  {self._format_num(self.resources['iron'])} | "
                f"🌾 {self._format_num(self.resources['crop'])}")
