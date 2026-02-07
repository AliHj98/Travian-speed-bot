"""
Reports Module - Report management and bulk deletion
"""

import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from selenium.webdriver.common.by import By
from core.browser import BrowserManager
from config import config


@dataclass
class ReportEntry:
    """A single report from the reports list"""
    checkbox_elem: object  # Selenium element for the checkbox
    outcome: str  # 'success_no_loss', 'success_with_loss', 'defeat', 'scout', 'unknown'
    subject: str  # Report title/subject text
    is_new: bool  # Unread report


# Human-readable labels for outcome categories
OUTCOME_LABELS = {
    'success_no_loss': 'Successful raids (no losses)',
    'success_with_loss': 'Successful raids (with losses)',
    'defeat': 'Unsuccessful attacks (defeats)',
    'scout': 'Scout reports',
    'unknown': 'Other/unclassified reports',
}


class ReportManager:
    """Manages report viewing, filtering, and bulk deletion"""

    def __init__(self, browser: BrowserManager):
        self.browser = browser

    def navigate_to_reports(self, report_tab: int = 0) -> bool:
        """Navigate to reports page. report_tab=0 for all, 1-5 for specific tabs."""
        try:
            if report_tab > 0:
                url = f"{config.base_url}/berichte.php?t={report_tab}"
            else:
                url = f"{config.base_url}/berichte.php"
            self.browser.navigate_to(url)
            time.sleep(0.5)

            # Verify we're on reports page
            current = self.browser.current_url or ''
            if 'berichte' in current:
                return True

            # Fallback: try English URL
            self.browser.navigate_to(f"{config.base_url}/reports.php")
            time.sleep(0.5)
            return 'report' in (self.browser.current_url or '') or 'berichte' in (self.browser.current_url or '')
        except Exception as e:
            print(f"  Failed to navigate to reports: {e}")
            return False

    def _classify_report_icon(self, row_elem) -> str:
        """Examine the report icon/image to determine outcome category."""
        try:
            # Look for report icon images in the row
            imgs = row_elem.find_elements(By.CSS_SELECTOR, 'img')
            for img in imgs:
                src = (img.get_attribute('src') or '').lower()
                css_class = (img.get_attribute('class') or '').lower()
                alt = (img.get_attribute('alt') or '').lower()

                # Check src patterns
                if any(k in src for k in ['report1', 'green', 'success_no_loss', 'winner_no_loss']):
                    return 'success_no_loss'
                if any(k in src for k in ['report2', 'yellow', 'success_with_loss', 'winner_with_loss']):
                    return 'success_with_loss'
                if any(k in src for k in ['report3', 'red', 'defeat', 'loser']):
                    return 'defeat'
                if any(k in src for k in ['report4', 'scout', 'spy']):
                    return 'scout'

                # Check class-based patterns (iReport1, iReport2, etc.)
                if 'ireport1' in css_class or 'report1' in css_class:
                    return 'success_no_loss'
                if 'ireport2' in css_class or 'report2' in css_class:
                    return 'success_with_loss'
                if 'ireport3' in css_class or 'report3' in css_class:
                    return 'defeat'
                if 'ireport4' in css_class or 'report4' in css_class:
                    return 'scout'

                # Check alt text
                if 'no loss' in alt or 'without loss' in alt:
                    return 'success_no_loss'
                if 'with loss' in alt:
                    return 'success_with_loss'
                if 'defeat' in alt or 'lost' in alt:
                    return 'defeat'
                if 'scout' in alt or 'spy' in alt:
                    return 'scout'

            # Check for icon classes directly on the row or child divs/spans
            icon_selectors = [
                '.reportIcon', '.iReport', 'i[class*="report"]',
                'span[class*="report"]', 'div[class*="report"]',
            ]
            for sel in icon_selectors:
                icons = row_elem.find_elements(By.CSS_SELECTOR, sel)
                for icon in icons:
                    css_class = (icon.get_attribute('class') or '').lower()
                    if '1' in css_class and 'report' in css_class:
                        return 'success_no_loss'
                    if '2' in css_class and 'report' in css_class:
                        return 'success_with_loss'
                    if '3' in css_class and 'report' in css_class:
                        return 'defeat'
                    if '4' in css_class and 'report' in css_class:
                        return 'scout'

        except Exception:
            pass

        return 'unknown'

    def _parse_report_rows(self) -> List[ReportEntry]:
        """Parse all report rows on the current page."""
        reports = []

        # Try multiple selectors for report rows
        row_selectors = [
            'table.row_a, table.row_b',
            'tr.row_a, tr.row_b',
            'div.reportRow',
            '#overview table tbody tr',
            '.report-list tr',
            'table tbody tr',
        ]

        rows = []
        for sel in row_selectors:
            rows = self.browser.driver.find_elements(By.CSS_SELECTOR, sel)
            if rows:
                break

        for row in rows:
            try:
                # Find checkbox
                checkbox = None
                cb_selectors = [
                    'input[type="checkbox"][name*="n"]',
                    'input[type="checkbox"].check',
                    'input[type="checkbox"]',
                ]
                for sel in cb_selectors:
                    cbs = row.find_elements(By.CSS_SELECTOR, sel)
                    if cbs:
                        checkbox = cbs[0]
                        break

                if not checkbox:
                    continue  # Skip rows without checkboxes (headers, etc.)

                # Classify outcome
                outcome = self._classify_report_icon(row)

                # Extract subject text
                subject = ''
                subj_selectors = [
                    'td.sub a', '.reportSubject', 'a[href*="berichte"]',
                    'a[href*="report"]', 'td a',
                ]
                for sel in subj_selectors:
                    subj_elems = row.find_elements(By.CSS_SELECTOR, sel)
                    if subj_elems:
                        subject = subj_elems[0].text.strip()
                        break

                if not subject:
                    subject = row.text.strip()[:60]

                # Check if report is new/unread
                is_new = False
                row_class = (row.get_attribute('class') or '').lower()
                if 'new' in row_class or 'unread' in row_class:
                    is_new = True
                # Also check for bold text (common unread indicator)
                bolds = row.find_elements(By.CSS_SELECTOR, 'b, strong, .newMessage')
                if bolds:
                    is_new = True

                reports.append(ReportEntry(
                    checkbox_elem=checkbox,
                    outcome=outcome,
                    subject=subject,
                    is_new=is_new,
                ))

            except Exception:
                continue

        return reports

    def _select_reports(self, reports: List[ReportEntry]) -> int:
        """Click checkbox for each report in the list. Returns count selected."""
        count = 0
        for report in reports:
            try:
                if not report.checkbox_elem.is_selected():
                    report.checkbox_elem.click()
                count += 1
            except Exception:
                continue
        return count

    def _click_delete(self) -> bool:
        """Find and click the delete button. Handle confirmation if needed."""
        delete_selectors = [
            'button.del', 'button[name="del"]',
            'input[value="del"]', 'input[name="del"]',
            '#deleteButton', 'button#del',
            'button[value="delete"]', 'input[value="delete"]',
            'button.green[value="del"]',
            # Generic submit buttons near the bottom
            'button[type="submit"]',
        ]

        for sel in delete_selectors:
            btn = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
            if btn:
                try:
                    btn.click()
                    time.sleep(0.5)

                    # Handle confirmation dialog if one appears
                    confirm_selectors = [
                        'button.dialogButtonOk',
                        'button[type="submit"].green',
                        '.dialogConfirm button',
                        '#ok', '#yes',
                    ]
                    for csel in confirm_selectors:
                        confirm_btn = self.browser.find_element_fast(By.CSS_SELECTOR, csel)
                        if confirm_btn:
                            confirm_btn.click()
                            time.sleep(0.3)
                            break

                    return True
                except Exception:
                    continue

        return False

    def _has_next_page(self) -> bool:
        """Check if there's a next page of reports."""
        next_selectors = [
            'a.next', '.paginator a.next',
            'a[title="next"]', 'a[title="Next"]',
            '.pageNavigation a.next',
            '#reportsPage a.next',
        ]
        for sel in next_selectors:
            elem = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
            if elem:
                return True
        return False

    def _go_next_page(self) -> bool:
        """Navigate to the next page of reports."""
        next_selectors = [
            'a.next', '.paginator a.next',
            'a[title="next"]', 'a[title="Next"]',
            '.pageNavigation a.next',
            '#reportsPage a.next',
        ]
        for sel in next_selectors:
            elem = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
            if elem:
                try:
                    elem.click()
                    time.sleep(0.5)
                    return True
                except Exception:
                    continue
        return False

    def count_reports_by_category(self, report_tab: int = 0) -> Dict[str, int]:
        """Navigate to reports and count reports per outcome category."""
        counts = {
            'success_no_loss': 0,
            'success_with_loss': 0,
            'defeat': 0,
            'scout': 0,
            'unknown': 0,
        }

        if not self.navigate_to_reports(report_tab):
            print("  Failed to load reports page")
            return counts

        reports = self._parse_report_rows()
        for r in reports:
            counts[r.outcome] = counts.get(r.outcome, 0) + 1

        return counts

    def delete_reports_by_category(self, categories: List[str], report_tab: int = 0, stop_callback=None) -> Dict:
        """Delete reports matching given outcome categories across all pages.

        Args:
            categories: List of outcome strings to delete (e.g. ['success_no_loss', 'defeat'])
            report_tab: Report tab filter (0=all)
            stop_callback: Callable returning True to stop early

        Returns:
            Stats dict with 'deleted' and 'pages_processed' counts
        """
        stats = {'deleted': 0, 'pages_processed': 0}

        while True:
            if stop_callback and stop_callback():
                print("  Stopped by user")
                break

            if not self.navigate_to_reports(report_tab):
                print("  Failed to load reports page")
                break

            stats['pages_processed'] += 1
            reports = self._parse_report_rows()

            # Filter to matching categories
            matching = [r for r in reports if r.outcome in categories]

            if not matching:
                # No more matching reports on this page
                # Check if there are more pages with matches
                if self._has_next_page():
                    if not self._go_next_page():
                        break
                    # Re-parse the next page
                    reports = self._parse_report_rows()
                    matching = [r for r in reports if r.outcome in categories]
                    if not matching:
                        break
                else:
                    break

            # Select matching reports
            selected = self._select_reports(matching)
            if selected == 0:
                break

            print(f"  Selected {selected} reports for deletion...")

            # Click delete
            if self._click_delete():
                stats['deleted'] += selected
                print(f"  Deleted {selected} reports (total: {stats['deleted']})")
                time.sleep(0.5)
            else:
                print("  Failed to click delete button")
                break

        return stats

    def delete_all_on_page(self, report_tab: int = 0, stop_callback=None) -> int:
        """Select all reports on current page and delete them.
        Returns count of deleted reports."""
        if not self.navigate_to_reports(report_tab):
            print("  Failed to load reports page")
            return 0

        total_deleted = 0

        while True:
            if stop_callback and stop_callback():
                break

            reports = self._parse_report_rows()
            if not reports:
                break

            # Select all checkboxes - try "select all" checkbox first
            select_all_selectors = [
                'input#selectAll', 'input[name="selectAll"]',
                'input.markAll', 'thead input[type="checkbox"]',
                'input[onclick*="selectAll"]',
            ]
            used_select_all = False
            for sel in select_all_selectors:
                elem = self.browser.find_element_fast(By.CSS_SELECTOR, sel)
                if elem:
                    try:
                        if not elem.is_selected():
                            elem.click()
                        used_select_all = True
                        break
                    except Exception:
                        continue

            if not used_select_all:
                # Fall back to selecting each checkbox
                self._select_reports(reports)

            count = len(reports)
            if self._click_delete():
                total_deleted += count
                print(f"  Deleted {count} reports (total: {total_deleted})")
                time.sleep(0.5)

                # Re-navigate to check for more
                if not self.navigate_to_reports(report_tab):
                    break
            else:
                print("  Failed to click delete button")
                break

        return total_deleted
