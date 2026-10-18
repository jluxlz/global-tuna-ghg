# ========== Basic Dependence ==========
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
import sys
import time
import json
import os
import re
import random
import traceback
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
import html  # Processing HTML Transfer
import pandas as pd

# ========== Global Configuration (Bulk processing+Unified Header)  ==========
# 1. Multi-Account Configuration
ACCOUNTS = [
    {"username": "alsxm", "password": "@Sjnzds20021211"},
    {"username": "xmu01", "password": "@Sjnzds20021211"},
    {"username": "xmu02", "password": "@Sjnzds20021211"},
    {"username": "xmu03", "password": "@Sjnzds20021211"},
]

# 2. File Path Configuration (Change to Path under Current Work Directory) 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # spider/
ROOT_DIR = os.path.dirname(BASE_DIR)  # Project Root Directory
INPUT_FOLDER = os.path.join(ROOT_DIR, "vessel_data_extract", "new_extracted_vessel_data")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "output")
DRIVER_PATH = os.path.join(BASE_DIR, "msedgedriver.exe")

# Ensure that output directory exists
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# 3. Key Configuration: Supplementary shipname Variable + year built + Common surface-head variants of gross tons
UNIFIED_HEADERS = {
    "imo": ["imo", "IMO", "Imo"],
    "call_sign": ["call_sign", "Call_Sign", "call sign", "Call Sign", "callsign", "Callsign"],
    "ship_name": ["ship_name", "Ship_Name", "ship name", "Ship Name", "shipname", "Shipname",
                  "vesselname", "Vesselname", "VesselName", "vessel name", "Vessel Name",
                  "name of fishing vessel", "Name of fishing vessel"],
    "build_date": ["builtdate", "Builtdate", "year_built", "year_of_build", "Year_of_build",
                   "year built", "Year Built", "build_date", "Build_Date", "built", "Built",
                   "when the vessel was built", "When the vessel was built"],
    "gross_tonnage": ["tonnage", "Tonnage", "gross_tonnage", "Gross_Tonnage",
                      "gross tonnage", "Gross Tonnage", "tonnage", "Tonnage", "gt", "GT",
                      "gross registered tonnage", "Gross Registered Tonnage"],
}
HEADLESS_MODE = False  # Headless Mode

# ========== Custom anomalies (limit on number of searches)  ==========
class SearchLimitReachedException(Exception):
    """Aberrations with the maximum number of account searches"""
    pass

# ========== Tool Functions: Parsing Tooltipster API Return to Content ==========
def parse_tooltipster_data(tooltip_text):
    """
    Full Parsing Tooltipster API Original string returned, Precision extraction below 5 Core Fields: 
    - Gross tonnage (gross tonnage)
    - Call sign (Call sign)
    - MMSI
    - Ship type (detailed) (Detailed type of ship)
    - Year of build / Date of build (year built)
    Keep it at the same time registered_owner Waiting for auxiliary fields. 
    """
    if not tooltip_text:
        return {}

    # Processing HTML Translating and standardizing line breaks
    decoded_text = html.unescape(str(tooltip_text))
    clean_text = decoded_text.replace("<br/>", "\n").replace("<br>", "\n").replace("<BR/>", "\n").replace("<BR>", "\n")

    lines = [line.strip() for line in clean_text.split("\n") if line.strip()]
    ship_info = {}
    for line in lines:
        if ":" in line:
            # Only split the first colon, Avoid including colons in the value
            key_part, value_part = line.split(":", 1)
            key = key_part.strip().lower().replace(" ", "_").replace("(", "").replace(")", "")
            value = value_part.strip()
            ship_info[key] = value

    # ── Its the bottom of the line: If the break-up parses the key fields that are not hit, Try to extract from the original text ──
    def regex_fallback(pattern, text, default=""):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else default

    # Year of extraction for construction (Prefer from parsed dictionary, Second regular match 4 Year in) 
    build_date = (
        ship_info.get("year_of_build", "") or
        ship_info.get("date_of_build", "") or
        ship_info.get("built", "") or
        ship_info.get("year_built", "")
    )
    if not build_date:
        build_date = regex_fallback(r"(?:year\s*of\s*build|date\s*of\s*build|built)\s*[:\-]\s*(\d{4})", clean_text)

    # Total ton extracted (Support "Gross tonnage: 1234" or "GT: 1234") 
    gross_tonnage = (
        ship_info.get("gross_tonnage", "") or
        ship_info.get("gt", "") or
        ship_info.get("gross_registered_tonnage", "")
    )
    if not gross_tonnage:
        gross_tonnage = regex_fallback(r"(?:gross\s*tonnage|gt)\s*[:\-]\s*([\d,]+\.?\d*)", clean_text)
    # Clear Comma (Thousands of places) 
    gross_tonnage = gross_tonnage.replace(",", "").strip() if gross_tonnage else ""

    # Extracting call sign
    call_sign = (
        ship_info.get("call_sign", "") or
        ship_info.get("callsign", "") or
        ship_info.get("call_sign_", "")
    )

    # Extract MMSI
    mmsi = ship_info.get("mmsi", "")

    # Type of ship to be extracted
    ship_type_detailed = (
        ship_info.get("ship_type_detailed", "") or
        ship_info.get("ship_type", "") or
        ship_info.get("vessel_type", "") or
        ship_info.get("type_of_ship", "")
    )

    # Registered shipowners extracted
    registered_owner = (
        ship_info.get("registered_owner", "") or
        ship_info.get("owner", "") or
        ship_info.get("registered_owner_name", "")
    )

    standardized_info = {
        "mmsi": mmsi,
        "build_date": build_date,
        "gross_tonnage": gross_tonnage,
        "call_sign": call_sign,
        "ship_type_detailed": ship_type_detailed,
        "registered_owner": registered_owner
    }
    return standardized_info

# ========== reptiles (Only Tooltipster API Extract+Queue Query)  ==========
class IMO_Edge_Crawler:
    def __init__(self, username: str, password: str, headless: bool = False):
        self.username = username
        self.password = password
        self.headless = headless
        self.driver = self._init_edge_driver()
        self.wait = WebDriverWait(self.driver, 30, poll_frequency=0.5)
        self.is_logged = False  # Whether the tag is entered or not

    def _init_edge_driver(self) -> webdriver.Edge:
        """Initialization Edge Driver, Guaranteed session stability"""
        edge_options = Options()
        # Core stabilization parameters
        edge_options.add_argument("--disable-blink-features=AutomationControlled")
        edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        edge_options.add_experimental_option("useAutomationExtension", False)
        edge_options.add_argument("--start-maximized")
        edge_options.add_argument("--ignore-certificate-errors")
        # Disable AutoClose/Sleeping
        edge_options.add_argument("--disable-background-timer-throttling")
        edge_options.add_argument("--disable-backgrounding-occluded-windows")

        # Edge Browser Path (Make sure your path is correct) 
        edge_binary_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        if os.path.exists(edge_binary_path):
            edge_options.binary_location = edge_binary_path

        # Headless Mode
        if self.headless:
            edge_options.add_argument("--headless=new")
            edge_options.add_argument("--window-size=1920,1080")

        # Disable Driver Log, Raise stability
        service = Service(
            executable_path=DRIVER_PATH,
            log_path=os.devnull
        )

        # Initialization driver
        driver = webdriver.Edge(service=service, options=edge_options)
        driver.set_page_load_timeout(300)
        driver.set_script_timeout(300)

        # Remove webdriver Marking
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"}
        )
        print(f"✅ Browser Initialization complete (Account: {self.username}）")
        return driver

    def _reinit_driver(self):
        """Re-initiating the driver when the session fails"""
        try:
            if self.driver:
                self.driver.quit()
                print(f"ℹ️ Close Account{self.username}Browser")
        except Exception as e:
            print(f"⚠️ Browser off abnormal: {str(e)}")

        self.driver = self._init_edge_driver()
        self.wait = WebDriverWait(self.driver, 30, poll_frequency=0.5)
        self.is_logged = False  # Mark after re-initialising as not login
        print("✅ Re-initialize browser session complete")

    def _check_search_limit(self) -> bool:
        """Check search limits"""
        try:
            content_td = self.wait.until(EC.presence_of_element_located((By.ID, "content")))
            content_text = content_td.text.strip()
            if "Search Limit Reached" in content_text and "You can try again on" in content_text:
                print(f"\n\U0001f6a8 Account{self.username}Activate search limits！")
                print(f"\U0001f4dd Limit Information: {content_text[:120]}...")
                return True
        except (TimeoutException, NoSuchElementException):
            pass
        return False

    def _stable_login(self) -> bool:
        """Core login logic (Login only once) """
        if self.is_logged:
            return True  # Login is a success

        try:
            # Step1: Access to Login Pages
            self.driver.get("https://webaccounts.imo.org/Common/WebLogin.aspx?LoggedOut=Yes")
            self.wait.until(EC.title_contains("IMO Web Accounts"))
            print(f"✅ Login complete | URL: {self.driver.current_url}")

            # Selection Public User Type
            ddl_authority = self.wait.until(EC.element_to_be_clickable((By.ID, "ctl00_cpMain_ddlAuthorityType")))
            ddl_authority.click()
            self.wait.until(EC.element_to_be_clickable((By.XPATH, "//option[@value='PUBLIC']"))).click()
            print("✅ Selected Public User Type")
            time.sleep(1)

            # Enter User Name
            username_input = self.wait.until(EC.visibility_of_element_located((By.ID, "ctl00_cpMain_txtUsername")))
            username_input.clear()
            username_input.send_keys(self.username)
            time.sleep(random.uniform(0.3, 0.8))
            print(f"✅ Username entered: {self.username}")
            time.sleep(10)

            # Click Step1 (Next) 
            btn_step1 = self.wait.until(EC.element_to_be_clickable((By.ID, "ctl00_cpMain_btnStep1")))
            btn_step1.click()
            time.sleep(1.5)
            print(f"✅ Click Step1 button | URL: {self.driver.current_url}")

            # Step2: Enter Password
            try:
                password_input = self.wait.until(EC.visibility_of_element_located((By.ID, "ctl00_cpMain_txtPassword")))
            except:
                password_input = self.wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@type='password']")))
            password_input.clear()
            password_input.send_keys(self.password)
            time.sleep(random.uniform(0.3, 0.8))
            print("✅ Password entered")

            # Click the login button (Step2) 
            try:
                btn_step2 = self.driver.find_element(By.ID, "ctl00_cpMain_btnStep2")
            except:
                btn_step2 = self.driver.find_element(By.XPATH, "//input[@value='Login']")
            self.driver.execute_script("arguments[0].click();", btn_step2)
            print(f"✅ Click the login button | URL: {self.driver.current_url}")

            # Waiting to jump and verify
            time.sleep(3)
            current_url = self.driver.current_url
            current_title = self.driver.title
            print(f"⚠️ Post-Link State | URL: {current_url} | Title: {current_title}")

            # Login successful: Enter account page or GISIS Page
            if "webaccounts.imo.org/Public/" in current_url or "IMO Web Accounts" in current_title:
                print("\U0001f389 Login complete (Enter Account Page/GISIS Page) ")
                # Navigate to GISIS Shippage
                if "IMO Web Accounts" in self.driver.title:
                    print("ℹ️ Logged into account details page, Starting navigation GISIS...")
                    # Click on the menu button
                    menu_btn = self.wait.until(
                        EC.element_to_be_clickable((By.CLASS_NAME, "navbar-toggler"))
                    )
                    if menu_btn.is_displayed():
                        self.driver.execute_script("arguments[0].click();", menu_btn)
                        print("✅ Menu button clicked successfully, Waiting for expansion...")
                        # Waiting for menu to expand
                        self.wait.until(
                            EC.visibility_of_element_located((By.XPATH, "//div[@class='drawer app-list-drawer shadow uk-dropdown uk-open']"))
                        )
                        time.sleep(1)
                    else:
                        print("❌ Menu buttons are invisible")
                        return False

                    # Precise positioning GISIS Link
                    gisis_link = self.wait.until(
                        EC.element_to_be_clickable((By.XPATH,
                            "//ul[@class='list-underlined list-checkbox-items']/li/a[text()='GISIS' and @href='https://gisis.imo.org/']"
                        ))
                    )
                    if gisis_link.is_displayed():
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", gisis_link)
                        time.sleep(0.5)
                        gisis_link.click()
                        print("✅ GISIS Link click successfully, ♪ Waiting for the jump ♪...")
                    else:
                        print("❌ GISIS Link Not Found")
                        return False

                    # Waiting to jump to GISIS ♪ And navigate to the ships page ♪
                    self.wait.until(EC.url_contains("gisis.imo.org"))
                    time.sleep(2)
                    self.driver.get("https://gisis.imo.org/Public/SHIPS/Default.aspx")
                    time.sleep(2)
                    print(f"\U0001f389 Successfully Navigated GISIS Shippage | URL: {self.driver.current_url}")

                self.is_logged = True  # Mark as Login
                return True
            else:
                self.driver.save_screenshot("login_failed_redirect.png")
                print(f"❌ Do not jump to target page after login | URL: {current_url}")
                return False

        except Exception as e:
            # Print Details of Abnormal Information
            error_detail = traceback.format_exc()
            print(f"❌ _stable_login Its an anomaly: {str(e)}")
            print(f"Unusual details:\n{error_detail}")
            self.driver.save_screenshot("stable_login_error.png")
            raise e

    def login_imo(self) -> bool:
        """Login+Navigate to GISIS (Login only once) """
        max_retry = 3
        for i in range(max_retry):
            try:
                login_result = self._stable_login()
                if login_result:
                    return True
                else:
                    print(f"⚠️ Its... its... its... its... its{i+1}The login operation failed, Retrying...")
                    time.sleep(3)

            except TimeoutException as e:
                print(f"⚠️ Its... its... its... its... its{i+1}Login timed out: {str(e)}")
                time.sleep(3)
            except WebDriverException as e:
                if "invalid session id" in str(e) or "disconnected" in str(e):
                    print(f"⚠️ Its... its... its... its... its{i+1}Session Expires, Re-introduction...")
                    self._reinit_driver()
                else:
                    print(f"⚠️ Its... its... its... its... its{i+1}Number of times WebDriver Its an anomaly: {str(e)}")
                    time.sleep(3)
            except Exception as e:
                print(f"⚠️ Its... its... its... its... its{i+1}Unknown anomalies: {str(e)}")
                self.driver.save_screenshot(f"gisis_nav_error_{i+1}.png")
                time.sleep(3)
        print("❌ Retry 3 After that, the login failed")
        return False

    def _single_query(self, imo: str, call: str, name: str) -> dict:
        """Single Query Logic (Only Tooltipster API Extract, No click to Jump) """
        try:
            # Ensure GISIS Shippage
            self.driver.get("https://gisis.imo.org/Public/SHIPS/Default.aspx")
            time.sleep(1)  # Page Loading Stable

            # Empty and fill specified parameters
            # Fill IMO
            imo_input = self.wait.until(EC.visibility_of_element_located((By.ID, "ctl00_bodyPlaceHolder_Default_tbxShipImoNumber")))
            imo_input.clear()
            if imo:
                imo_input.send_keys(imo)

            # Fill Call sign
            call_input = self.wait.until(EC.visibility_of_element_located((By.ID, "ctl00_bodyPlaceHolder_Default_tbxShipCallSign")))
            call_input.clear()
            if call:
                call_input.send_keys(call)

            # Fill Ship name
            name_input = self.wait.until(EC.visibility_of_element_located((By.ID, "ctl00_bodyPlaceHolder_Default_tbxShipName")))
            name_input.clear()
            if name:
                name_input.send_keys(name)

            time.sleep(0.5)
            # Click Search button
            search_btn = self.driver.find_element(By.ID, "ctl00_bodyPlaceHolder_Default_btnSearchShips")
            self.driver.execute_script("arguments[0].click();", search_btn)
            time.sleep(3)
            print(f"✅ Execute Query | IMO:{imo} | CallSign:{call} | ShipName:{name}")

            # Test「No ship data」Hint
            try:
                no_ship_elem = self.driver.find_element(By.XPATH, "//p[@class='disabled' and contains(text(), 'No ships found')]")
                if no_ship_elem.is_displayed():
                    print(f"⚠️ No ship data | IMO:{imo} | CallSign:{call} | ShipName:{name}")
                    return {"no_data": True}
            except NoSuchElementException:
                pass

            # Check limit on number of searches
            if self._check_search_limit():
                raise SearchLimitReachedException(f"Account{self.username}Maximum number of searches")

            # Waiting for result table to load and locate target rows
            self.wait.until(EC.presence_of_element_located((By.ID, "ctl00_bodyPlaceHolder_Default_gridShips")))
            target_row = self.wait.until(EC.presence_of_element_located((By.XPATH, "//tr[contains(@class, 'gridviewer_row')][1]")))
            print("✅ Find results, Call Tooltipster API Extracting Memory Data...")

            # ========== Only keep: Tooltipster Plugin API Draw core logic ==========
            raw_data = self.driver.execute_script("""
                var $el = $(arguments[0]);
                if ($el.hasClass('tooltipstered')) {
                    // Try Tooltipster standard API Retrieving content
                    try { return $el.tooltipster('content'); } catch(e) {}
                    // Try from jQuery data Cache Fetch
                    try { return $el.data('tooltipsterContent'); } catch(e) {}
                }
                return null;
            """, target_row)

            # ========== Parsing Tooltipster API Returns result ==========
            if raw_data:
                print(f"✅ Tooltipster API Extracted successfully, Start parsing data...")
                ship_detail = parse_tooltipster_data(raw_data)
                ship_detail["query_process"] = f"Query successful(IMO:{imo}|Call:{call}|Name:{name})"
                ship_detail["need_manual_check"] = False
                return ship_detail
            else:
                print("❌ Tooltipster API Failed to extract (Go back to empty data) ")
                return {"error": "Tooltipster API Failed to extract", "need_manual_check": True, "query_process": f"Failed to extract(IMO:{imo}|Call:{call}|Name:{name})"}

        except SearchLimitReachedException:
            raise
        except Exception as e:
            error_msg = str(e)[:50]
            print(f"❌ One query is abnormal: {error_msg}")
            return {"error": error_msg, "need_manual_check": True, "query_process": f"Query anomaly: {error_msg}"}

    def query_imo_ship(self, imo_number: str = "", call_sign: str = "", ship_name: str = "") -> dict:
        """Querying data on individual ships (Fix the hierarchical logic: IMO→CallSign→ShipName Query in turn) """
        if not self.is_logged:
            print(f"⚠️ Session not login, Try login first...")
            if not self.login_imo():
                return {"error": f"Account{self.username}Login failed"}

        # ========== Rehabilitated Query Execution Process ==========
        query_id = imo_number or call_sign or (ship_name[:20] if ship_name else "No marking")
        print(f"\n===== Start tiered query [{query_id}] =====")

        final_result = None
        query_steps = []

        # Steps 1: Query IMO (If there were) 
        if imo_number:
            query_steps.append(f"IMO:{imo_number}")
            imo_result = self._single_query(imo=imo_number, call="", name="")
            if not imo_result.get("no_data") and not imo_result.get("error"):
                final_result = imo_result
                final_result["query_process"] = f"Priority Query(IMO)Success | {final_result.get('query_process', '')}"

        # Steps 2: IMO I cant find it, Query CallSign (If there were) 
        if not final_result and call_sign:
            query_steps.append(f"CallSign:{call_sign}")
            call_result = self._single_query(imo="", call=call_sign, name="")
            if not call_result.get("no_data") and not call_result.get("error"):
                final_result = call_result
                final_result["query_process"] = f"Query(CallSign)Success | {final_result.get('query_process', '')}"

        # Steps 3: CallSign I cant find it, Query ShipName (If there were) 
        if not final_result and ship_name:
            query_steps.append(f"ShipName:{ship_name[:20]}")
            name_result = self._single_query(imo="", call="", name=ship_name)
            if not name_result.get("no_data") and not name_result.get("error"):
                final_result = name_result
                final_result["query_process"] = f"The last question(ShipName)Success | {final_result.get('query_process', '')}"

        # I cant find any of the steps
        if not final_result:
            final_result = {
                "no_data": True,
                "query_process": f"All access methods were inconclusive | Try Step: {','.join(query_steps)}",
                "need_manual_check": True
            }

        # ========== Print result logic ==========
        if final_result.get("error") or final_result.get("no_data"):
            print(f"\n⚠️ Queue Query [{query_id}] No effective outcome | Status: {final_result.get('query_process')}")
        else:
            print(f"\n\U0001f389 Queue Query [{query_id}] Success！| Process: {final_result['query_process']}")
            print("=" * 50)
            print("[Can not open message]")
            for k, v in final_result.items():
                if k not in ["query_process", "need_manual_check", "error", "no_data"]:
                    print(f"  {k}: {v}")
            print("=" * 50)

        return final_result

    def close(self):
        """Secure Close Browser"""
        try:
            if hasattr(self, 'driver') and self.driver:
                self.driver.quit()
                print(f"✅ Account{self.username}Browsers off secure")
        except Exception as e:
            print(f"⚠️ Account{self.username}Failed to close browser: {str(e)}")

# ========== Breakpoint Processing (Separate each file)  ==========
def get_breakpoint_path(file_name: str) -> str:
    return os.path.join(OUTPUT_FOLDER, f"{file_name}_breakpoint.json")

def save_breakpoint(file_name: str, current_row: int, account_index: int):
    breakpoint_path = get_breakpoint_path(file_name)
    breakpoint_data = {
        "current_row": current_row,
        "account_index": account_index,
        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(breakpoint_path, "w", encoding="utf-8") as f:
        json.dump(breakpoint_data, f, ensure_ascii=False, indent=4)
    print(f"\U0001f4cc Save Breakpoints: Okay{current_row} | Index of accounts{account_index} (Documentation: {file_name}）")

def load_breakpoint(file_name: str) -> tuple:
    breakpoint_path = get_breakpoint_path(file_name)
    if os.path.exists(breakpoint_path):
        try:
            with open(breakpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            current_row = data.get("current_row", 2)
            account_index = data.get("account_index", 0)
            if account_index >= len(ACCOUNTS):
                print(f"⚠️ Index of accounts{account_index}Cross-border, Reset As 0")
                account_index = 0
            print(f"\U0001f4e5 Load Breakpoint: Okay{current_row} | Index of accounts{account_index} (Documentation: {file_name}）")
            return current_row, account_index
        except Exception as e:
            print(f"⚠️ Breakpoint file damaged ({file_name}）：{str(e)}, Use initial value")
    else:
        print(f"⚠️ No Breakpoint File ({file_name}) , Use initial value")
    return 2, 0

# ========== Value Purge Tool ==========
def safe_str(val) -> str:
    """Convert value to string, Processing NaN & Float Integer"""
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if s.lower() == "nan" or s.lower() == "none":
        return ""
    # Clear Float Integer (Like "2003.0" → "2003") 
    if s.endswith(".0") and s.count(".") == 1:
        try:
            float(s)
            s = s[:-2]
        except ValueError:
            pass
    return s

def normalize_for_compare(val) -> str:
    """Standard value for matching: Go to space, Go to comma, Uniform lowercase"""
    s = safe_str(val)
    if not s:
        return ""
    # remove thousands separators
    s = s.replace(",", "").replace("，", "")
    # Unified Space
    s = s.strip()
    return s

# ========== Excel Processing (Support CSV and XLSX Enter + Raw Data Match)  ==========
def read_input_excel(file_path: str) -> list:
    """
    Core: Walk Through All Columns, Match All Fields (Irrelevance of the order of columns) . 
    Support .csv and .xlsx Format. 
    Add: Read Original Builtdate (year built) and Tonnage (gross tonnage) Column for Follow-up Matching. 
    """
    try:
        file_name = os.path.basename(file_path)
        file_ext = os.path.splitext(file_path)[1].lower()

        # ── CSV Documentation: Use pandas Read ──
        if file_ext == ".csv":
            df = pd.read_csv(file_path, encoding="utf-8-sig", dtype=str)
            # Standardized listing
            columns = list(df.columns)
            # Build header_map
            header_map = {"imo": None, "call_sign": None, "ship_name": None,
                          "build_date": None, "gross_tonnage": None}
            print(f"\n=== Start recognition{file_name}Uniform chart header (CSV mode)  ===")
            for col_idx, original_header in enumerate(columns):
                processed_header = str(original_header).replace("_", " ").lower().strip()

                # Match IMO Column
                if header_map["imo"] is None:
                    for imo_var in UNIFIED_HEADERS["imo"]:
                        if processed_header == imo_var.replace("_", " ").lower():
                            header_map["imo"] = col_idx
                            print(f"✅ Its... its... its... its... its{col_idx+1}Column: '{original_header}' → Match As IMO Column")
                            break

                # Match CallSign Column
                if header_map["call_sign"] is None:
                    for call_var in UNIFIED_HEADERS["call_sign"]:
                        if processed_header == call_var.replace("_", " ").lower():
                            header_map["call_sign"] = col_idx
                            print(f"✅ Its... its... its... its... its{col_idx+1}Column: '{original_header}' → Match As CallSign Column")
                            break

                # Match ShipName Column
                if header_map["ship_name"] is None:
                    for name_var in UNIFIED_HEADERS["ship_name"]:
                        if processed_header == name_var.replace("_", " ").lower():
                            header_map["ship_name"] = col_idx
                            print(f"✅ Its... its... its... its... its{col_idx+1}Column: '{original_header}' → Match As ShipName Column")
                            break

                # Match Builtdate Column (year built) 
                if header_map["build_date"] is None:
                    for bd_var in UNIFIED_HEADERS["build_date"]:
                        if processed_header == bd_var.replace("_", " ").lower():
                            header_map["build_date"] = col_idx
                            print(f"✅ Its... its... its... its... its{col_idx+1}Column: '{original_header}' → Match to the construction year columns")
                            break

                # Match Gross Tonnage Column (gross tonnage) 
                if header_map["gross_tonnage"] is None:
                    for gt_var in UNIFIED_HEADERS["gross_tonnage"]:
                        if processed_header == gt_var.replace("_", " ").lower():
                            header_map["gross_tonnage"] = col_idx
                            print(f"✅ Its... its... its... its... its{col_idx+1}Column: '{original_header}' → Match to Total Trail")
                            break

            # Verify IMO/Call sign/Three core fields for ship names
            missing_fields = [k for k in ["imo", "call_sign", "ship_name"] if header_map[k] is None]
            if missing_fields:
                print(f"\n❌ Error: {file_name} The following core fields were not matched: {missing_fields}")
                print(f"   Supported change in listing: { {k: UNIFIED_HEADERS[k] for k in missing_fields} }")
                return []

            # Read Data Rows
            ship_data_list = []
            print(f"\n=== Start reading{file_name}Data ===")
            for row_idx in range(len(df)):
                imo = safe_str(df.iloc[row_idx, header_map["imo"]])
                call_sign = safe_str(df.iloc[row_idx, header_map["call_sign"]])
                ship_name = safe_str(df.iloc[row_idx, header_map["ship_name"]])
                original_build_date = safe_str(df.iloc[row_idx, header_map["build_date"]]) if header_map["build_date"] is not None else ""
                original_gross_tonnage = safe_str(df.iloc[row_idx, header_map["gross_tonnage"]]) if header_map["gross_tonnage"] is not None else ""

                # Skip all fields to empty rows
                if not imo and not call_sign and not ship_name:
                    print(f"⚠️ Skip empty lines: Its... its... its... its... its{row_idx+2}Okay (All core fields are empty) ")
                    continue

                excel_row = row_idx + 2  # CSV Line Number+2 = Excel Line Numbers of Styles (Including tabular headers) 
                print(f"✅ Its... its... its... its... its{excel_row}Okay: ShipName='{ship_name}' | IMO='{imo}' | CallSign='{call_sign}' | Original year of construction='{original_build_date}' | Original gross tons='{original_gross_tonnage}'")
                ship_data_list.append({
                    "row": excel_row,
                    "imo": imo,
                    "call_sign": call_sign,
                    "ship_name": ship_name,
                    "original_build_date": original_build_date,
                    "original_gross_tonnage": original_gross_tonnage
                })

            print(f"\n✅ Read Completed: {file_name} Total{len(ship_data_list)}Effective data")
            return ship_data_list

        # ── XLSX Documentation: Maintain as before openpyxl Logic ──
        else:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            sheet = wb.active
            ship_data_list = []
            header_map = {"imo": None, "call_sign": None, "ship_name": None,
                          "build_date": None, "gross_tonnage": None}

            print(f"\n=== Start recognition{file_name}Uniform chart header (XLSX mode)  ===")
            for col in range(1, sheet.max_column + 1):
                original_header = str(sheet.cell(row=1, column=col).value).strip() if sheet.cell(row=1, column=col).value else ""
                processed_header = original_header.replace("_", " ").lower()

                if header_map["imo"] is None:
                    for imo_var in UNIFIED_HEADERS["imo"]:
                        if processed_header == imo_var.replace("_", " ").lower():
                            header_map["imo"] = col
                            print(f"✅ Its... its... its... its... its{col}Column: '{original_header}' → Match As IMO Column")
                            break

                if header_map["call_sign"] is None:
                    for call_var in UNIFIED_HEADERS["call_sign"]:
                        if processed_header == call_var.replace("_", " ").lower():
                            header_map["call_sign"] = col
                            print(f"✅ Its... its... its... its... its{col}Column: '{original_header}' → Match As CallSign Column")
                            break

                if header_map["ship_name"] is None:
                    for name_var in UNIFIED_HEADERS["ship_name"]:
                        if processed_header == name_var.replace("_", " ").lower():
                            header_map["ship_name"] = col
                            print(f"✅ Its... its... its... its... its{col}Column: '{original_header}' → Match As ShipName Column")
                            break

                if header_map["build_date"] is None:
                    for bd_var in UNIFIED_HEADERS["build_date"]:
                        if processed_header == bd_var.replace("_", " ").lower():
                            header_map["build_date"] = col
                            print(f"✅ Its... its... its... its... its{col}Column: '{original_header}' → Match to the construction year columns")
                            break

                if header_map["gross_tonnage"] is None:
                    for gt_var in UNIFIED_HEADERS["gross_tonnage"]:
                        if processed_header == gt_var.replace("_", " ").lower():
                            header_map["gross_tonnage"] = col
                            print(f"✅ Its... its... its... its... its{col}Column: '{original_header}' → Match to Total Trail")
                            break

            # Verify Core Fields
            print(f"\n=== Summary of results for table header matching ===")
            for field in ["imo", "call_sign", "ship_name", "build_date", "gross_tonnage"]:
                col_idx = header_map[field]
                if col_idx is not None:
                    print(f"✅ {field} → Its... its... its... its... its{col_idx}Column")
                else:
                    print(f"⚠️ {field} → Not matched (Non-core field is negligible) ")

            missing_fields = [k for k in ["imo", "call_sign", "ship_name"] if header_map[k] is None]
            if missing_fields:
                print(f"\n❌ Error: {file_name} The following core fields were not matched: {missing_fields}")
                wb.close()
                return []
            print(f"✅ All core table header matches complete！")

            # Read Data Rows
            print(f"\n=== Start reading{file_name}Data ===")
            for row in range(2, sheet.max_row + 1):
                imo = ""
                call_sign = ""
                ship_name = ""

                if header_map["imo"]:
                    imo_val = sheet.cell(row=row, column=header_map["imo"]).value
                    imo = safe_str(imo_val)

                if header_map["call_sign"]:
                    call_val = sheet.cell(row=row, column=header_map["call_sign"]).value
                    call_sign = safe_str(call_val)

                if header_map["ship_name"]:
                    name_val = sheet.cell(row=row, column=header_map["ship_name"]).value
                    ship_name = safe_str(name_val)

                # Read original construction year and gross tonnes
                original_build_date = ""
                if header_map["build_date"]:
                    bd_val = sheet.cell(row=row, column=header_map["build_date"]).value
                    original_build_date = safe_str(bd_val)

                original_gross_tonnage = ""
                if header_map["gross_tonnage"]:
                    gt_val = sheet.cell(row=row, column=header_map["gross_tonnage"]).value
                    original_gross_tonnage = safe_str(gt_val)

                if not imo and not call_sign and not ship_name:
                    print(f"⚠️ Skip empty lines: Its... its... its... its... its{row}Okay (All fields are empty) ")
                    continue

                print(f"✅ Its... its... its... its... its{row}Okay: ShipName='{ship_name}' | IMO='{imo}' | CallSign='{call_sign}' | Original year of construction='{original_build_date}' | Original gross tons='{original_gross_tonnage}'")
                ship_data_list.append({
                    "row": row,
                    "imo": imo,
                    "call_sign": call_sign,
                    "ship_name": ship_name,
                    "original_build_date": original_build_date,
                    "original_gross_tonnage": original_gross_tonnage
                })

            wb.close()
            print(f"\n✅ Read Completed: {file_name} Total{len(ship_data_list)}Effective data")
            return ship_data_list

    except Exception as e:
        print(f"❌ Read{os.path.basename(file_path)}Failed: {str(e)}")
        traceback.print_exc()
        return []


def compare_and_judge(new_val: str, old_val: str, field_name: str) -> tuple:
    """
    Compares old and new values to single fields. 
    Back: (Compare status code, Description Text)
    Status Code: "match" | "updated" | "filled" | "both_empty" | "new_empty"
    """
    new_norm = normalize_for_compare(new_val)
    old_norm = normalize_for_compare(old_val)

    if not old_norm and not new_norm:
        return ("both_empty", "")
    if not old_norm and new_norm:
        return ("filled", f"{field_name}original value missing, filled")
    if old_norm and not new_norm:
        return ("new_empty", f"{field_name}Crawl as Empty(Old value:{old_val})")
    if old_norm == new_norm:
        return ("match", "")
    else:
        return ("updated", f"{field_name}(Old value:{old_val}->New value:{new_val})")


def build_comparison_judgment(new_build_date: str, new_gross_tonnage: str,
                               old_build_date: str, old_gross_tonnage: str) -> str:
    """
    Year of construction combined and gross tonnes, Generate"Data match determination"Text. 
    """
    bd_status, bd_msg = compare_and_judge(new_build_date, old_build_date, "year built")
    gt_status, gt_msg = compare_and_judge(new_gross_tonnage, old_gross_tonnage, "gross tonnage")

    all_statuses = [bd_status, gt_status]

    # Both of them → identical
    if all(s in ("match", "both_empty") for s in all_statuses) and "match" in all_statuses:
        return "identical"

    # Both of them were empty and crawled empty
    if all(s == "both_empty" for s in all_statuses):
        return "original value missing, Crawling data is empty"

    # Build Change Description
    changes = []
    if bd_msg:
        changes.append(bd_msg)
    if gt_msg:
        changes.append(gt_msg)

    if not changes:
        return "identical"

    # To judge the overall state
    has_filled = "filled" in all_statuses
    has_updated = "updated" in all_statuses
    has_new_empty = "new_empty" in all_statuses

    if has_updated and has_filled:
        prefix = "data updated+Supplementary: "
    elif has_updated:
        prefix = "data updated: "
    elif has_filled and not has_updated:
        prefix = "original value missing, filled: "
    elif has_new_empty:
        prefix = "attention-Crawling data missing: "
    else:
        prefix = ""

    return prefix + "; ".join(changes)


def init_result_excel(file_name: str) -> tuple:
    """Initialization of results Excel (Diagnosis column) """
    result_excel_path = os.path.join(OUTPUT_FOLDER, f"{file_name}_result.xlsx")
    if os.path.exists(result_excel_path):
        wb = openpyxl.load_workbook(result_excel_path)
        print(f"\U0001f4ca Loading existing outcome documents: {os.path.basename(result_excel_path)}")
    else:
        wb = openpyxl.Workbook()
        sheet = wb.active
        sheet.title = f"{file_name}Ship search results"
        # Full Results Table (Include new diagnostic columns) 
        headers = [
            "Query Identification",           # 1
            "Original Line Number",           # 2
            "Name of ship(Enter)",          # 3
            "IMO Encoding(Enter)",       # 4
            "Call sign(Enter)",          # 5
            "MMSI",               # 6
            "Built_Date",            # 7
            "gross tonnage",               # 8
            "Detailed type of ship",         # 9
            "Call sign(Crawl)",          # 10
            "Registered shipowner",            # 11
            "Original year of construction",          # 12  ← Add: Enter the original value of the file
            "Original total tons",            # 13  ← Add: Enter the original value of the file
            "Data match determination",         # 14  ← Add: Compared to the diagnosis
            "Error message",            # 15
            "Query process",            # 16
            "Whether manual queries are required"        # 17
        ]
        # Set table header styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, size=11, color="FFFFFF")
        for col_idx, header in enumerate(headers, 1):
            cell = sheet.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.fill = header_fill
        # Set Column Width
        col_widths = {1: 22, 2: 10, 3: 22, 4: 16, 5: 14, 6: 14, 7: 12, 8: 12,
                      9: 20, 10: 14, 11: 26, 12: 14, 13: 12, 14: 48, 15: 26, 16: 50, 17: 14}
        for col_idx, width in col_widths.items():
            sheet.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width
        # Freeze first row
        sheet.freeze_panes = "A2"
        wb.save(result_excel_path)
        print(f"\U0001f4ca New outcome document: {os.path.basename(result_excel_path)}")
    return wb, result_excel_path


def write_result_to_excel(wb: openpyxl.Workbook, excel_path: str, ship_data: dict, query_result: dict):
    """Writing Query Results (Diagnosis column) """
    sheet = wb.active
    next_row = sheet.max_row + 1

    # Extracting the crawling field from the query result
    new_build_date = query_result.get("build_date", "")
    new_gross_tonnage = query_result.get("gross_tonnage", "")
    new_call_sign = query_result.get("call_sign", "")
    new_mmsi = query_result.get("mmsi", "")
    new_ship_type = query_result.get("ship_type_detailed", "")
    new_owner = query_result.get("registered_owner", "")

    # Extract original values from input files
    old_build_date = ship_data.get("original_build_date", "")
    old_gross_tonnage = ship_data.get("original_gross_tonnage", "")

    # Generate data matching determinations
    comparison_judgment = build_comparison_judgment(
        new_build_date, new_gross_tonnage,
        old_build_date, old_gross_tonnage
    )

    # ── Write Columns ──
    # Column 1: Query Identification
    sheet.cell(row=next_row, column=1, value=ship_data.get("imo") or ship_data.get("call_sign") or (ship_data.get("ship_name")[:20] if ship_data.get("ship_name") else "No marking"))
    # Column 2: Original Line Number
    sheet.cell(row=next_row, column=2, value=ship_data.get("row"))
    # Column 3: Name of ship(Enter)
    sheet.cell(row=next_row, column=3, value=ship_data.get("ship_name", ""))
    # Column 4: IMO Encoding(Enter)
    sheet.cell(row=next_row, column=4, value=ship_data.get("imo", ""))
    # Column 5: Call sign(Enter)
    sheet.cell(row=next_row, column=5, value=ship_data.get("call_sign", ""))
    # Column 6: MMSI (Crawl) 
    sheet.cell(row=next_row, column=6, value=new_mmsi)
    # Column 7: Built_Date (Crawl) 
    sheet.cell(row=next_row, column=7, value=new_build_date)
    # Column 8: gross tonnage (Crawl) 
    sheet.cell(row=next_row, column=8, value=new_gross_tonnage)
    # Column 9: Detailed type of ship (Crawl) 
    sheet.cell(row=next_row, column=9, value=new_ship_type)
    # Column 10: Call sign(Crawl)
    sheet.cell(row=next_row, column=10, value=new_call_sign)
    # Column 11: Registered shipowner (Crawl) 
    sheet.cell(row=next_row, column=11, value=new_owner)
    # Column 12: Original year of construction (Enter the original value of the file) 
    sheet.cell(row=next_row, column=12, value=old_build_date)
    # Column 13: Original total tons (Enter the original value of the file) 
    sheet.cell(row=next_row, column=13, value=old_gross_tonnage)
    # Column 14: Data match determination
    sheet.cell(row=next_row, column=14, value=comparison_judgment)
    # Column 15: Error message
    sheet.cell(row=next_row, column=15, value=query_result.get("error", "") or (query_result.get("no_data") and "No match" or ""))
    # Column 16: Query process
    sheet.cell(row=next_row, column=16, value=query_result.get("query_process", ""))
    # Column 17: Whether manual queries are required
    sheet.cell(row=next_row, column=17, value="is" if query_result.get("need_manual_check") else "no")

    # ── Highlights vs. Decision Rows ──
    judgment_cell = sheet.cell(row=next_row, column=14)
    judgment_cell.alignment = Alignment(wrap_text=True, vertical="center")
    if "identical" in comparison_judgment:
        judgment_cell.font = Font(color="006100")
        judgment_cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    elif "data updated" in comparison_judgment:
        judgment_cell.font = Font(color="9C5700", bold=True)
        judgment_cell.fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    elif "original value missing, filled" in comparison_judgment:
        judgment_cell.font = Font(color="0066CC")
        judgment_cell.fill = PatternFill(start_color="DAEEF3", end_color="DAEEF3", fill_type="solid")
    elif "attention" in comparison_judgment:
        judgment_cell.font = Font(color="9C0006")
        judgment_cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

    wb.save(excel_path)
    print(f"\U0001f4dd Writing Results: Its... its... its... its... its{next_row}Okay (Original Line: {ship_data.get('row')}) | Matching of determinations: {comparison_judgment}")


# ========== Single file processing ==========
def process_single_excel(xlsx_file: str, current_idx: int, total_count: int):
    """Deal with Single Excel Documentation"""
    file_name = os.path.basename(xlsx_file).replace(".xlsx", "").replace(".csv", "")
    print(f"\n" + "="*100)
    print(f"\U0001f680 Start processing number one{current_idx}/{total_count}File: {os.path.basename(xlsx_file)}")
    print("="*100)

    # 1. Read Data
    ship_data_list = read_input_excel(xlsx_file)
    if not ship_data_list:
        print(f"❌ {os.path.basename(xlsx_file)} No valid data, Skip Processing")
        return

    # 2. Initialization of results Excel
    result_wb, result_excel_path = init_result_excel(file_name)

    # 3. Load Breakpoint
    start_row, current_account_idx = load_breakpoint(file_name)
    pending_data = [data for data in ship_data_list if data["row"] >= start_row]
    if not pending_data:
        print(f"\U0001f389 {os.path.basename(xlsx_file)} All data processed")
        result_wb.close()
        return
    print(f"\U0001f4cb Pending: {len(pending_data)}Data | From the first{start_row}Line Start | Index to Current Account: {current_account_idx}")

    # 4. Initial reptiles
    if current_account_idx >= len(ACCOUNTS):
        print(f"❌ Index of accounts{current_account_idx}Cross-border (Total{len(ACCOUNTS)}Account) ")
        result_wb.close()
        return
    current_account = ACCOUNTS[current_account_idx]
    crawler = None
    try:
        crawler = IMO_Edge_Crawler(
            username=current_account["username"],
            password=current_account["password"],
            headless=HEADLESS_MODE
        )
        if not crawler.login_imo():
            print(f"❌ Account{current_account['username']}Login failed, Switch account number")
            raise Exception("Initial account login failed")
    except Exception as e:
        print(f"❌ The reptiles have failed to start: {str(e)}")
        if crawler:
            crawler.close()
        result_wb.close()
        return

    # 5. Processing of data
    try:
        for ship_data in pending_data:
            current_data_row = ship_data["row"]
            print(f"\n" + "-"*60)
            print(f"\U0001f504 Processing progress: Original Line{current_data_row} (Account: {current_account['username']}）")
            print("-"*60)

            try:
                # Execute Queries
                query_result = crawler.query_imo_ship(
                    imo_number=ship_data["imo"],
                    call_sign=ship_data["call_sign"],
                    ship_name=ship_data["ship_name"]
                )

                # Writing Results
                write_result_to_excel(result_wb, result_excel_path, ship_data, query_result)

                # Save Breakpoints
                save_breakpoint(file_name, current_data_row + 1, current_account_idx)

                # Recline Delay
                time.sleep(random.uniform(2, 4))

            except SearchLimitReachedException:
                # Switch account number: Recycle through all remaining accounts, Until we find out whats available
                print(f"\n\U0001f6a8 Account{current_account['username']}Access to search limit, Start recycling to switch the remaining account")
                crawler.close()
                switch_success = False  # Mark whether to switch to a valid account

                # Queue through all the remaining accounts (From the current next) 
                while current_account_idx + 1 < len(ACCOUNTS):
                    current_account_idx += 1
                    current_account = ACCOUNTS[current_account_idx]
                    print(f"\U0001f504 Try to switch to account: {current_account['username']} (Index: {current_account_idx}）")

                    # Initialize a new account and try login
                    crawler = IMO_Edge_Crawler(
                        username=current_account["username"],
                        password=current_account["password"],
                        headless=HEADLESS_MODE
                    )
                    if crawler.login_imo():
                        print(f"✅ Account{current_account['username']}Toggle and login successfully")
                        switch_success = True
                        break  # Found Available Account, Disable the loop
                    else:
                        print(f"❌ Account{current_account['username']}Login failed, Continue Switching Next")
                        crawler.close()  # Closed login failed browser

                # Switch results to judgement
                if not switch_success:
                    # All remaining accounts are not available
                    print(f"❌ All accounts are exhausted/Login failed, Stop processing the current file")
                    save_breakpoint(file_name, current_data_row, current_account_idx)
                    crawler.close() if crawler else None
                    break  # Disable current file processing
                else:
                    # Switch to Available Account, Recursing the current line
                    print(f"\U0001f504 Use new account{current_account['username']}Reprocess Rows{current_data_row}")
                    query_result = crawler.query_imo_ship(
                        imo_number=ship_data["imo"],
                        call_sign=ship_data["call_sign"],
                        ship_name=ship_data["ship_name"]
                    )
                    # Writing Results+Save Breakpoints
                    write_result_to_excel(result_wb, result_excel_path, ship_data, query_result)
                    save_breakpoint(file_name, current_data_row + 1, current_account_idx)
                    time.sleep(random.uniform(2, 4))  # Recline Delay

            except Exception as e:
                error_msg = str(e)[:100]
                print(f"❌ Handle Rows{current_data_row}Its an anomaly: {error_msg}")
                # Writing Error
                error_result = {
                    "error": error_msg,
                    "query_process": f"Deal with anomalies: {error_msg}",
                    "need_manual_check": True
                }
                write_result_to_excel(result_wb, result_excel_path, ship_data, error_result)
                save_breakpoint(file_name, current_data_row + 1, current_account_idx)
                time.sleep(random.uniform(2, 4))

    except Exception as e:
        print(f"❌ Batch processing anomalies: {str(e)}")
    finally:
        if crawler:
            crawler.close()
        result_wb.close()

# ========== Main entrance ==========
if __name__ == "__main__":
    # Repair Windows GBK Encoding problem
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # Fetch All Under Input Folder CSV and Excel Documentation (Exclude Flag_Code_Mapping.csv) 
    all_files = []
    for f in os.listdir(INPUT_FOLDER):
        if f.endswith(".csv") or f.endswith(".xlsx"):
            # Exclude Flag_Code_Mapping.csv (Non-ship data) 
            if "flag_code_mapping" in f.lower() or "flag" in f.lower():
                print(f"⚠️ Skip non-ship data files: {f}")
                continue
            all_files.append(os.path.join(INPUT_FOLDER, f))

    if not all_files:
        print(f"❌ Enter Folder{INPUT_FOLDER}No ship data file found (CSV/XLSX) ")
        exit(1)

    # Sort by File Name
    all_files.sort()

    print(f"\n{'='*80}")
    print(f"  IMO Ship data reptiles - Enhanced version")
    print(f"  Input Directory: {INPUT_FOLDER}")
    print(f"  Output Directory: {OUTPUT_FOLDER}")
    print(f"  Documents to be processed: {len(all_files)} One")
    for f in all_files:
        print(f"    - {os.path.basename(f)}")
    print(f"{'='*80}")

    # Sort each document sequentially
    total_files = len(all_files)
    for idx, xlsx_file in enumerate(all_files, 1):
        process_single_excel(xlsx_file, idx, total_files)

    print(f"\n\U0001f389 All{total_files}Documents processed！Outcome document saved: {OUTPUT_FOLDER}")
