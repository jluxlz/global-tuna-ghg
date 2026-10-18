# ========== 基础依赖 ==========
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
import html  # 处理HTML转义
import pandas as pd

# ========== 全局配置（批量处理+统一表头） ==========
# 1. 多账号配置
ACCOUNTS = [
    {"username": "alsxm", "password": "@Sjnzds20021211"},
    {"username": "xmu01", "password": "@Sjnzds20021211"},
    {"username": "xmu02", "password": "@Sjnzds20021211"},
    {"username": "xmu03", "password": "@Sjnzds20021211"},
]

# 2. 文件路径配置（改为当前工作目录下的路径）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # spider/
ROOT_DIR = os.path.dirname(BASE_DIR)  # 项目根目录
INPUT_FOLDER = os.path.join(ROOT_DIR, "vessel_data_extract", "new_extracted_vessel_data")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "output")
DRIVER_PATH = os.path.join(BASE_DIR, "msedgedriver.exe")

# 确保输出目录存在
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# 3. 关键配置：补充shipname变体 + 建造年份 + 总吨的常见表头变体
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
HEADLESS_MODE = False  # 无头模式

# ========== 自定义异常（搜索次数限制） ==========
class SearchLimitReachedException(Exception):
    """账号搜索次数达到上限的异常"""
    pass

# ========== 工具函数：解析Tooltipster API返回内容 ==========
def parse_tooltipster_data(tooltip_text):
    """
    全面解析Tooltipster API返回的原始字符串，精准提取以下5个核心字段：
    - Gross tonnage (总吨)
    - Call sign (呼号)
    - MMSI
    - Ship type (detailed) (详细船舶类型)
    - Year of build / Date of build (建造年份)
    同时保留 registered_owner 等辅助字段。
    """
    if not tooltip_text:
        return {}

    # 处理 HTML 转义并标准化换行
    decoded_text = html.unescape(str(tooltip_text))
    clean_text = decoded_text.replace("<br/>", "\n").replace("<br>", "\n").replace("<BR/>", "\n").replace("<BR>", "\n")

    lines = [line.strip() for line in clean_text.split("\n") if line.strip()]
    ship_info = {}
    for line in lines:
        if ":" in line:
            # 只分割第一个冒号，避免值里包含冒号
            key_part, value_part = line.split(":", 1)
            key = key_part.strip().lower().replace(" ", "_").replace("(", "").replace(")", "")
            value = value_part.strip()
            ship_info[key] = value

    # ── 正则兜底：如果分行解析未命中关键字段，尝试从原始文本中提取 ──
    def regex_fallback(pattern, text, default=""):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else default

    # 提取建造年份（优先从已解析字典取，其次正则匹配4位年份）
    build_date = (
        ship_info.get("year_of_build", "") or
        ship_info.get("date_of_build", "") or
        ship_info.get("built", "") or
        ship_info.get("year_built", "")
    )
    if not build_date:
        build_date = regex_fallback(r"(?:year\s*of\s*build|date\s*of\s*build|built)\s*[:\-]\s*(\d{4})", clean_text)

    # 提取总吨（支持 "Gross tonnage: 1234" 或 "GT: 1234"）
    gross_tonnage = (
        ship_info.get("gross_tonnage", "") or
        ship_info.get("gt", "") or
        ship_info.get("gross_registered_tonnage", "")
    )
    if not gross_tonnage:
        gross_tonnage = regex_fallback(r"(?:gross\s*tonnage|gt)\s*[:\-]\s*([\d,]+\.?\d*)", clean_text)
    # 清理逗号（千分位）
    gross_tonnage = gross_tonnage.replace(",", "").strip() if gross_tonnage else ""

    # 提取呼号
    call_sign = (
        ship_info.get("call_sign", "") or
        ship_info.get("callsign", "") or
        ship_info.get("call_sign_", "")
    )

    # 提取MMSI
    mmsi = ship_info.get("mmsi", "")

    # 提取详细船舶类型
    ship_type_detailed = (
        ship_info.get("ship_type_detailed", "") or
        ship_info.get("ship_type", "") or
        ship_info.get("vessel_type", "") or
        ship_info.get("type_of_ship", "")
    )

    # 提取注册船东
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

# ========== 爬虫类（仅Tooltipster API提取+分级查询） ==========
class IMO_Edge_Crawler:
    def __init__(self, username: str, password: str, headless: bool = False):
        self.username = username
        self.password = password
        self.headless = headless
        self.driver = self._init_edge_driver()
        self.wait = WebDriverWait(self.driver, 30, poll_frequency=0.5)
        self.is_logged = False  # 标记是否已登录

    def _init_edge_driver(self) -> webdriver.Edge:
        """初始化Edge驱动，保证会话稳定性"""
        edge_options = Options()
        # 核心稳定参数
        edge_options.add_argument("--disable-blink-features=AutomationControlled")
        edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        edge_options.add_experimental_option("useAutomationExtension", False)
        edge_options.add_argument("--start-maximized")
        edge_options.add_argument("--ignore-certificate-errors")
        # 禁用自动关闭/休眠
        edge_options.add_argument("--disable-background-timer-throttling")
        edge_options.add_argument("--disable-backgrounding-occluded-windows")

        # Edge浏览器路径（确认你的路径正确）
        edge_binary_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        if os.path.exists(edge_binary_path):
            edge_options.binary_location = edge_binary_path

        # 无头模式
        if self.headless:
            edge_options.add_argument("--headless=new")
            edge_options.add_argument("--window-size=1920,1080")

        # 禁用驱动日志，提升稳定性
        service = Service(
            executable_path=DRIVER_PATH,
            log_path=os.devnull
        )

        # 初始化驱动
        driver = webdriver.Edge(service=service, options=edge_options)
        driver.set_page_load_timeout(300)
        driver.set_script_timeout(300)

        # 移除webdriver标识
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"}
        )
        print(f"✅ 浏览器初始化完成（账号：{self.username}）")
        return driver

    def _reinit_driver(self):
        """会话失效时重新初始化驱动"""
        try:
            if self.driver:
                self.driver.quit()
                print(f"ℹ️ 关闭账号{self.username}的浏览器")
        except Exception as e:
            print(f"⚠️ 浏览器关闭异常：{str(e)}")

        self.driver = self._init_edge_driver()
        self.wait = WebDriverWait(self.driver, 30, poll_frequency=0.5)
        self.is_logged = False  # 重新初始化后标记为未登录
        print("✅ 重新初始化浏览器会话完成")

    def _check_search_limit(self) -> bool:
        """检测搜索限制"""
        try:
            content_td = self.wait.until(EC.presence_of_element_located((By.ID, "content")))
            content_text = content_td.text.strip()
            if "Search Limit Reached" in content_text and "You can try again on" in content_text:
                print(f"\n\U0001f6a8 账号{self.username}触发搜索限制！")
                print(f"\U0001f4dd 限制信息：{content_text[:120]}...")
                return True
        except (TimeoutException, NoSuchElementException):
            pass
        return False

    def _stable_login(self) -> bool:
        """核心登录逻辑（仅登录一次）"""
        if self.is_logged:
            return True  # 已登录则直接返回成功

        try:
            # Step1：访问登录页
            self.driver.get("https://webaccounts.imo.org/Common/WebLogin.aspx?LoggedOut=Yes")
            self.wait.until(EC.title_contains("IMO Web Accounts"))
            print(f"✅ 登录页加载完成 | URL: {self.driver.current_url}")

            # 选择Public User类型
            ddl_authority = self.wait.until(EC.element_to_be_clickable((By.ID, "ctl00_cpMain_ddlAuthorityType")))
            ddl_authority.click()
            self.wait.until(EC.element_to_be_clickable((By.XPATH, "//option[@value='PUBLIC']"))).click()
            print("✅ 已选择Public User类型")
            time.sleep(1)

            # 输入用户名
            username_input = self.wait.until(EC.visibility_of_element_located((By.ID, "ctl00_cpMain_txtUsername")))
            username_input.clear()
            username_input.send_keys(self.username)
            time.sleep(random.uniform(0.3, 0.8))
            print(f"✅ 已输入用户名: {self.username}")
            time.sleep(10)

            # 点击Step1（下一个）
            btn_step1 = self.wait.until(EC.element_to_be_clickable((By.ID, "ctl00_cpMain_btnStep1")))
            btn_step1.click()
            time.sleep(1.5)
            print(f"✅ 点击Step1按钮 | URL: {self.driver.current_url}")

            # Step2：输入密码
            try:
                password_input = self.wait.until(EC.visibility_of_element_located((By.ID, "ctl00_cpMain_txtPassword")))
            except:
                password_input = self.wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@type='password']")))
            password_input.clear()
            password_input.send_keys(self.password)
            time.sleep(random.uniform(0.3, 0.8))
            print("✅ 已输入密码")

            # 点击登录按钮（Step2）
            try:
                btn_step2 = self.driver.find_element(By.ID, "ctl00_cpMain_btnStep2")
            except:
                btn_step2 = self.driver.find_element(By.XPATH, "//input[@value='登录']")
            self.driver.execute_script("arguments[0].click();", btn_step2)
            print(f"✅ 点击登录按钮 | URL: {self.driver.current_url}")

            # 等待跳转并验证
            time.sleep(3)
            current_url = self.driver.current_url
            current_title = self.driver.title
            print(f"⚠️ 登录后状态 | URL: {current_url} | 标题: {current_title}")

            # 登录成功判定：进入账户页或GISIS页
            if "webaccounts.imo.org/Public/" in current_url or "IMO Web Accounts" in current_title:
                print("\U0001f389 登录操作完成（进入账户页/GISIS页）")
                # 导航到GISIS船舶页
                if "IMO Web Accounts" in self.driver.title:
                    print("ℹ️ 已登录到账户详情页，开始导航到GISIS...")
                    # 点击菜单按钮
                    menu_btn = self.wait.until(
                        EC.element_to_be_clickable((By.CLASS_NAME, "navbar-toggler"))
                    )
                    if menu_btn.is_displayed():
                        self.driver.execute_script("arguments[0].click();", menu_btn)
                        print("✅ 菜单按钮点击成功，等待展开...")
                        # 等待菜单展开
                        self.wait.until(
                            EC.visibility_of_element_located((By.XPATH, "//div[@class='drawer app-list-drawer shadow uk-dropdown uk-open']"))
                        )
                        time.sleep(1)
                    else:
                        print("❌ 菜单按钮不可见")
                        return False

                    # 精准定位GISIS链接
                    gisis_link = self.wait.until(
                        EC.element_to_be_clickable((By.XPATH,
                            "//ul[@class='list-underlined list-checkbox-items']/li/a[text()='GISIS' and @href='https://gisis.imo.org/']"
                        ))
                    )
                    if gisis_link.is_displayed():
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", gisis_link)
                        time.sleep(0.5)
                        gisis_link.click()
                        print("✅ GISIS链接点击成功，等待跳转...")
                    else:
                        print("❌ GISIS链接不可见")
                        return False

                    # 等待跳转到GISIS并导航到船舶页
                    self.wait.until(EC.url_contains("gisis.imo.org"))
                    time.sleep(2)
                    self.driver.get("https://gisis.imo.org/Public/SHIPS/Default.aspx")
                    time.sleep(2)
                    print(f"\U0001f389 成功导航到GISIS船舶页 | URL: {self.driver.current_url}")

                self.is_logged = True  # 标记为已登录
                return True
            else:
                self.driver.save_screenshot("login_failed_redirect.png")
                print(f"❌ 登录后未跳转目标页 | URL: {current_url}")
                return False

        except Exception as e:
            # 打印详细异常信息
            error_detail = traceback.format_exc()
            print(f"❌ _stable_login异常: {str(e)}")
            print(f"异常详情:\n{error_detail}")
            self.driver.save_screenshot("stable_login_error.png")
            raise e

    def login_imo(self) -> bool:
        """登录+导航到GISIS（仅登录一次）"""
        max_retry = 3
        for i in range(max_retry):
            try:
                login_result = self._stable_login()
                if login_result:
                    return True
                else:
                    print(f"⚠️ 第{i+1}次登录操作失败，重试中...")
                    time.sleep(3)

            except TimeoutException as e:
                print(f"⚠️ 第{i+1}次登录超时：{str(e)}")
                time.sleep(3)
            except WebDriverException as e:
                if "invalid session id" in str(e) or "disconnected" in str(e):
                    print(f"⚠️ 第{i+1}次会话失效，重新初始化...")
                    self._reinit_driver()
                else:
                    print(f"⚠️ 第{i+1}次WebDriver异常：{str(e)}")
                    time.sleep(3)
            except Exception as e:
                print(f"⚠️ 第{i+1}次未知异常：{str(e)}")
                self.driver.save_screenshot(f"gisis_nav_error_{i+1}.png")
                time.sleep(3)
        print("❌ 重试3次后仍登录失败")
        return False

    def _single_query(self, imo: str, call: str, name: str) -> dict:
        """单次查询逻辑（仅Tooltipster API提取，无点击跳转）"""
        try:
            # 确保在GISIS船舶页
            self.driver.get("https://gisis.imo.org/Public/SHIPS/Default.aspx")
            time.sleep(1)  # 页面加载稳定

            # 清空并填充指定参数
            # 填充IMO
            imo_input = self.wait.until(EC.visibility_of_element_located((By.ID, "ctl00_bodyPlaceHolder_Default_tbxShipImoNumber")))
            imo_input.clear()
            if imo:
                imo_input.send_keys(imo)

            # 填充Call sign
            call_input = self.wait.until(EC.visibility_of_element_located((By.ID, "ctl00_bodyPlaceHolder_Default_tbxShipCallSign")))
            call_input.clear()
            if call:
                call_input.send_keys(call)

            # 填充Ship name
            name_input = self.wait.until(EC.visibility_of_element_located((By.ID, "ctl00_bodyPlaceHolder_Default_tbxShipName")))
            name_input.clear()
            if name:
                name_input.send_keys(name)

            time.sleep(0.5)
            # 点击搜索按钮
            search_btn = self.driver.find_element(By.ID, "ctl00_bodyPlaceHolder_Default_btnSearchShips")
            self.driver.execute_script("arguments[0].click();", search_btn)
            time.sleep(3)
            print(f"✅ 执行查询 | IMO:{imo} | CallSign:{call} | ShipName:{name}")

            # 检测「无船舶数据」提示
            try:
                no_ship_elem = self.driver.find_element(By.XPATH, "//p[@class='disabled' and contains(text(), 'No ships found')]")
                if no_ship_elem.is_displayed():
                    print(f"⚠️ 无船舶数据 | IMO:{imo} | CallSign:{call} | ShipName:{name}")
                    return {"no_data": True}
            except NoSuchElementException:
                pass

            # 检测搜索次数限制
            if self._check_search_limit():
                raise SearchLimitReachedException(f"账号{self.username}搜索次数上限")

            # 等待结果表格加载并定位目标行
            self.wait.until(EC.presence_of_element_located((By.ID, "ctl00_bodyPlaceHolder_Default_gridShips")))
            target_row = self.wait.until(EC.presence_of_element_located((By.XPATH, "//tr[contains(@class, 'gridviewer_row')][1]")))
            print("✅ 找到结果行，调用Tooltipster API提取内存数据...")

            # ========== 仅保留：Tooltipster插件API提取核心逻辑 ==========
            raw_data = self.driver.execute_script("""
                var $el = $(arguments[0]);
                if ($el.hasClass('tooltipstered')) {
                    // 尝试 Tooltipster 标准 API 获取内容
                    try { return $el.tooltipster('content'); } catch(e) {}
                    // 尝试从 jQuery data 缓存获取
                    try { return $el.data('tooltipsterContent'); } catch(e) {}
                }
                return null;
            """, target_row)

            # ========== 解析Tooltipster API返回结果 ==========
            if raw_data:
                print(f"✅ Tooltipster API提取成功，开始解析数据...")
                ship_detail = parse_tooltipster_data(raw_data)
                ship_detail["query_process"] = f"查询成功(IMO:{imo}|Call:{call}|Name:{name})"
                ship_detail["need_manual_check"] = False
                return ship_detail
            else:
                print("❌ Tooltipster API提取失败（返回空数据）")
                return {"error": "Tooltipster API提取失败", "need_manual_check": True, "query_process": f"提取失败(IMO:{imo}|Call:{call}|Name:{name})"}

        except SearchLimitReachedException:
            raise
        except Exception as e:
            error_msg = str(e)[:50]
            print(f"❌ 单次查询异常：{error_msg}")
            return {"error": error_msg, "need_manual_check": True, "query_process": f"查询异常：{error_msg}"}

    def query_imo_ship(self, imo_number: str = "", call_sign: str = "", ship_name: str = "") -> dict:
        """查询单个船舶数据（修复分级逻辑：IMO→CallSign→ShipName依次查询）"""
        if not self.is_logged:
            print(f"⚠️ 会话未登录，先尝试登录...")
            if not self.login_imo():
                return {"error": f"账号{self.username}登录失败"}

        # ========== 修复后的分级查询执行流程 ==========
        query_id = imo_number or call_sign or (ship_name[:20] if ship_name else "无标识")
        print(f"\n===== 开始分级查询 [{query_id}] =====")

        final_result = None
        query_steps = []

        # 步骤1：查询IMO（如果有）
        if imo_number:
            query_steps.append(f"IMO:{imo_number}")
            imo_result = self._single_query(imo=imo_number, call="", name="")
            if not imo_result.get("no_data") and not imo_result.get("error"):
                final_result = imo_result
                final_result["query_process"] = f"优先查询(IMO)成功 | {final_result.get('query_process', '')}"

        # 步骤2：IMO查不到，查询CallSign（如果有）
        if not final_result and call_sign:
            query_steps.append(f"CallSign:{call_sign}")
            call_result = self._single_query(imo="", call=call_sign, name="")
            if not call_result.get("no_data") and not call_result.get("error"):
                final_result = call_result
                final_result["query_process"] = f"兜底查询(CallSign)成功 | {final_result.get('query_process', '')}"

        # 步骤3：CallSign查不到，查询ShipName（如果有）
        if not final_result and ship_name:
            query_steps.append(f"ShipName:{ship_name[:20]}")
            name_result = self._single_query(imo="", call="", name=ship_name)
            if not name_result.get("no_data") and not name_result.get("error"):
                final_result = name_result
                final_result["query_process"] = f"最后兜底查询(ShipName)成功 | {final_result.get('query_process', '')}"

        # 所有步骤都查不到
        if not final_result:
            final_result = {
                "no_data": True,
                "query_process": f"所有查询方式均无结果 | 尝试步骤：{','.join(query_steps)}",
                "need_manual_check": True
            }

        # ========== 打印结果逻辑 ==========
        if final_result.get("error") or final_result.get("no_data"):
            print(f"\n⚠️ 分级查询 [{query_id}] 无有效结果 | 状态：{final_result.get('query_process')}")
        else:
            print(f"\n\U0001f389 分级查询 [{query_id}] 成功！| 过程：{final_result['query_process']}")
            print("=" * 50)
            print("【提取信息】")
            for k, v in final_result.items():
                if k not in ["query_process", "need_manual_check", "error", "no_data"]:
                    print(f"  {k}: {v}")
            print("=" * 50)

        return final_result

    def close(self):
        """安全关闭浏览器"""
        try:
            if hasattr(self, 'driver') and self.driver:
                self.driver.quit()
                print(f"✅ 账号{self.username}浏览器已安全关闭")
        except Exception as e:
            print(f"⚠️ 账号{self.username}浏览器关闭失败：{str(e)}")

# ========== 断点处理（每个文件独立） ==========
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
    print(f"\U0001f4cc 保存断点：行{current_row} | 账号索引{account_index}（文件：{file_name}）")

def load_breakpoint(file_name: str) -> tuple:
    breakpoint_path = get_breakpoint_path(file_name)
    if os.path.exists(breakpoint_path):
        try:
            with open(breakpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            current_row = data.get("current_row", 2)
            account_index = data.get("account_index", 0)
            if account_index >= len(ACCOUNTS):
                print(f"⚠️ 账号索引{account_index}越界，重置为0")
                account_index = 0
            print(f"\U0001f4e5 加载断点：行{current_row} | 账号索引{account_index}（文件：{file_name}）")
            return current_row, account_index
        except Exception as e:
            print(f"⚠️ 断点文件损坏（{file_name}）：{str(e)}，用初始值")
    else:
        print(f"⚠️ 无断点文件（{file_name}），用初始值")
    return 2, 0

# ========== 值清洗工具 ==========
def safe_str(val) -> str:
    """将值转为字符串，处理 NaN 和浮点整数"""
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if s.lower() == "nan" or s.lower() == "none":
        return ""
    # 清理浮点整数（如 "2003.0" → "2003"）
    if s.endswith(".0") and s.count(".") == 1:
        try:
            float(s)
            s = s[:-2]
        except ValueError:
            pass
    return s

def normalize_for_compare(val) -> str:
    """标准化用于比对的值：去空格、去逗号、统一小写"""
    s = safe_str(val)
    if not s:
        return ""
    # 去掉千分位逗号
    s = s.replace(",", "").replace("，", "")
    # 统一空格
    s = s.strip()
    return s

# ========== Excel处理（支持CSV和XLSX输入 + 原始数据比对） ==========
def read_input_excel(file_path: str) -> list:
    """
    核心：遍历所有列，匹配所有字段（无关列顺序）。
    支持 .csv 和 .xlsx 格式。
    新增：读取原始 Builtdate（建造年份）和 Tonnage（总吨）列用于后续比对。
    """
    try:
        file_name = os.path.basename(file_path)
        file_ext = os.path.splitext(file_path)[1].lower()

        # ── CSV 文件：使用 pandas 读取 ──
        if file_ext == ".csv":
            df = pd.read_csv(file_path, encoding="utf-8-sig", dtype=str)
            # 标准化列名
            columns = list(df.columns)
            # 构建 header_map
            header_map = {"imo": None, "call_sign": None, "ship_name": None,
                          "build_date": None, "gross_tonnage": None}
            print(f"\n=== 开始识别{file_name}的统一表头（CSV模式） ===")
            for col_idx, original_header in enumerate(columns):
                processed_header = str(original_header).replace("_", " ").lower().strip()

                # 匹配IMO列
                if header_map["imo"] is None:
                    for imo_var in UNIFIED_HEADERS["imo"]:
                        if processed_header == imo_var.replace("_", " ").lower():
                            header_map["imo"] = col_idx
                            print(f"✅ 第{col_idx+1}列：'{original_header}' → 匹配为IMO列")
                            break

                # 匹配CallSign列
                if header_map["call_sign"] is None:
                    for call_var in UNIFIED_HEADERS["call_sign"]:
                        if processed_header == call_var.replace("_", " ").lower():
                            header_map["call_sign"] = col_idx
                            print(f"✅ 第{col_idx+1}列：'{original_header}' → 匹配为CallSign列")
                            break

                # 匹配ShipName列
                if header_map["ship_name"] is None:
                    for name_var in UNIFIED_HEADERS["ship_name"]:
                        if processed_header == name_var.replace("_", " ").lower():
                            header_map["ship_name"] = col_idx
                            print(f"✅ 第{col_idx+1}列：'{original_header}' → 匹配为ShipName列")
                            break

                # 匹配Builtdate列（建造年份）
                if header_map["build_date"] is None:
                    for bd_var in UNIFIED_HEADERS["build_date"]:
                        if processed_header == bd_var.replace("_", " ").lower():
                            header_map["build_date"] = col_idx
                            print(f"✅ 第{col_idx+1}列：'{original_header}' → 匹配为建造年份列")
                            break

                # 匹配Gross Tonnage列（总吨）
                if header_map["gross_tonnage"] is None:
                    for gt_var in UNIFIED_HEADERS["gross_tonnage"]:
                        if processed_header == gt_var.replace("_", " ").lower():
                            header_map["gross_tonnage"] = col_idx
                            print(f"✅ 第{col_idx+1}列：'{original_header}' → 匹配为总吨列")
                            break

            # 校验IMO/呼号/船名三个核心字段
            missing_fields = [k for k in ["imo", "call_sign", "ship_name"] if header_map[k] is None]
            if missing_fields:
                print(f"\n❌ 错误：{file_name} 未匹配到以下核心字段：{missing_fields}")
                print(f"   支持的列名变体：{ {k: UNIFIED_HEADERS[k] for k in missing_fields} }")
                return []

            # 读取数据行
            ship_data_list = []
            print(f"\n=== 开始读取{file_name}的数据 ===")
            for row_idx in range(len(df)):
                imo = safe_str(df.iloc[row_idx, header_map["imo"]])
                call_sign = safe_str(df.iloc[row_idx, header_map["call_sign"]])
                ship_name = safe_str(df.iloc[row_idx, header_map["ship_name"]])
                original_build_date = safe_str(df.iloc[row_idx, header_map["build_date"]]) if header_map["build_date"] is not None else ""
                original_gross_tonnage = safe_str(df.iloc[row_idx, header_map["gross_tonnage"]]) if header_map["gross_tonnage"] is not None else ""

                # 跳过所有字段为空的行
                if not imo and not call_sign and not ship_name:
                    print(f"⚠️ 跳过空行：第{row_idx+2}行（所有核心字段均为空）")
                    continue

                excel_row = row_idx + 2  # CSV行号+2 = Excel风格的行号（含表头）
                print(f"✅ 第{excel_row}行：ShipName='{ship_name}' | IMO='{imo}' | CallSign='{call_sign}' | 原建造年份='{original_build_date}' | 原总吨='{original_gross_tonnage}'")
                ship_data_list.append({
                    "row": excel_row,
                    "imo": imo,
                    "call_sign": call_sign,
                    "ship_name": ship_name,
                    "original_build_date": original_build_date,
                    "original_gross_tonnage": original_gross_tonnage
                })

            print(f"\n✅ 读取完成：{file_name} 共{len(ship_data_list)}条有效数据")
            return ship_data_list

        # ── XLSX 文件：保持原有 openpyxl 逻辑 ──
        else:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            sheet = wb.active
            ship_data_list = []
            header_map = {"imo": None, "call_sign": None, "ship_name": None,
                          "build_date": None, "gross_tonnage": None}

            print(f"\n=== 开始识别{file_name}的统一表头（XLSX模式） ===")
            for col in range(1, sheet.max_column + 1):
                original_header = str(sheet.cell(row=1, column=col).value).strip() if sheet.cell(row=1, column=col).value else ""
                processed_header = original_header.replace("_", " ").lower()

                if header_map["imo"] is None:
                    for imo_var in UNIFIED_HEADERS["imo"]:
                        if processed_header == imo_var.replace("_", " ").lower():
                            header_map["imo"] = col
                            print(f"✅ 第{col}列：'{original_header}' → 匹配为IMO列")
                            break

                if header_map["call_sign"] is None:
                    for call_var in UNIFIED_HEADERS["call_sign"]:
                        if processed_header == call_var.replace("_", " ").lower():
                            header_map["call_sign"] = col
                            print(f"✅ 第{col}列：'{original_header}' → 匹配为CallSign列")
                            break

                if header_map["ship_name"] is None:
                    for name_var in UNIFIED_HEADERS["ship_name"]:
                        if processed_header == name_var.replace("_", " ").lower():
                            header_map["ship_name"] = col
                            print(f"✅ 第{col}列：'{original_header}' → 匹配为ShipName列")
                            break

                if header_map["build_date"] is None:
                    for bd_var in UNIFIED_HEADERS["build_date"]:
                        if processed_header == bd_var.replace("_", " ").lower():
                            header_map["build_date"] = col
                            print(f"✅ 第{col}列：'{original_header}' → 匹配为建造年份列")
                            break

                if header_map["gross_tonnage"] is None:
                    for gt_var in UNIFIED_HEADERS["gross_tonnage"]:
                        if processed_header == gt_var.replace("_", " ").lower():
                            header_map["gross_tonnage"] = col
                            print(f"✅ 第{col}列：'{original_header}' → 匹配为总吨列")
                            break

            # 校验核心字段
            print(f"\n=== 表头匹配结果汇总 ===")
            for field in ["imo", "call_sign", "ship_name", "build_date", "gross_tonnage"]:
                col_idx = header_map[field]
                if col_idx is not None:
                    print(f"✅ {field} → 第{col_idx}列")
                else:
                    print(f"⚠️ {field} → 未匹配到（非核心字段可忽略）")

            missing_fields = [k for k in ["imo", "call_sign", "ship_name"] if header_map[k] is None]
            if missing_fields:
                print(f"\n❌ 错误：{file_name} 未匹配到以下核心字段：{missing_fields}")
                wb.close()
                return []
            print(f"✅ 所有核心表头匹配完成！")

            # 读取数据行
            print(f"\n=== 开始读取{file_name}的数据 ===")
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

                # 读取原始建造年份和总吨
                original_build_date = ""
                if header_map["build_date"]:
                    bd_val = sheet.cell(row=row, column=header_map["build_date"]).value
                    original_build_date = safe_str(bd_val)

                original_gross_tonnage = ""
                if header_map["gross_tonnage"]:
                    gt_val = sheet.cell(row=row, column=header_map["gross_tonnage"]).value
                    original_gross_tonnage = safe_str(gt_val)

                if not imo and not call_sign and not ship_name:
                    print(f"⚠️ 跳过空行：第{row}行（所有字段均为空）")
                    continue

                print(f"✅ 第{row}行：ShipName='{ship_name}' | IMO='{imo}' | CallSign='{call_sign}' | 原建造年份='{original_build_date}' | 原总吨='{original_gross_tonnage}'")
                ship_data_list.append({
                    "row": row,
                    "imo": imo,
                    "call_sign": call_sign,
                    "ship_name": ship_name,
                    "original_build_date": original_build_date,
                    "original_gross_tonnage": original_gross_tonnage
                })

            wb.close()
            print(f"\n✅ 读取完成：{file_name} 共{len(ship_data_list)}条有效数据")
            return ship_data_list

    except Exception as e:
        print(f"❌ 读取{os.path.basename(file_path)}失败：{str(e)}")
        traceback.print_exc()
        return []


def compare_and_judge(new_val: str, old_val: str, field_name: str) -> tuple:
    """
    比对单个字段的新旧值。
    返回: (比较状态码, 描述文本)
    状态码: "match" | "updated" | "filled" | "both_empty" | "new_empty"
    """
    new_norm = normalize_for_compare(new_val)
    old_norm = normalize_for_compare(old_val)

    if not old_norm and not new_norm:
        return ("both_empty", "")
    if not old_norm and new_norm:
        return ("filled", f"{field_name}原数据为空，已补充")
    if old_norm and not new_norm:
        return ("new_empty", f"{field_name}爬取为空(旧值:{old_val})")
    if old_norm == new_norm:
        return ("match", "")
    else:
        return ("updated", f"{field_name}(旧值:{old_val}->新值:{new_val})")


def build_comparison_judgment(new_build_date: str, new_gross_tonnage: str,
                               old_build_date: str, old_gross_tonnage: str) -> str:
    """
    综合比对建造年份和总吨，生成"数据比对判定"文本。
    """
    bd_status, bd_msg = compare_and_judge(new_build_date, old_build_date, "建造年份")
    gt_status, gt_msg = compare_and_judge(new_gross_tonnage, old_gross_tonnage, "总吨")

    all_statuses = [bd_status, gt_status]

    # 两个都匹配 → 完全一致
    if all(s in ("match", "both_empty") for s in all_statuses) and "match" in all_statuses:
        return "完全一致"

    # 两个都是原数据为空且爬取为空
    if all(s == "both_empty" for s in all_statuses):
        return "原数据为空，爬取数据亦为空"

    # 构建变更描述
    changes = []
    if bd_msg:
        changes.append(bd_msg)
    if gt_msg:
        changes.append(gt_msg)

    if not changes:
        return "完全一致"

    # 判断总体状态
    has_filled = "filled" in all_statuses
    has_updated = "updated" in all_statuses
    has_new_empty = "new_empty" in all_statuses

    if has_updated and has_filled:
        prefix = "数据有更新+补充: "
    elif has_updated:
        prefix = "数据有更新: "
    elif has_filled and not has_updated:
        prefix = "原数据为空，已补充: "
    elif has_new_empty:
        prefix = "注意-爬取数据缺失: "
    else:
        prefix = ""

    return prefix + "; ".join(changes)


def init_result_excel(file_name: str) -> tuple:
    """初始化结果Excel（含比对诊断列）"""
    result_excel_path = os.path.join(OUTPUT_FOLDER, f"{file_name}_result.xlsx")
    if os.path.exists(result_excel_path):
        wb = openpyxl.load_workbook(result_excel_path)
        print(f"\U0001f4ca 加载现有结果文件：{os.path.basename(result_excel_path)}")
    else:
        wb = openpyxl.Workbook()
        sheet = wb.active
        sheet.title = f"{file_name}船舶查询结果"
        # 完整结果表头（含新增的诊断列）
        headers = [
            "查询标识",           # 1
            "原始行号",           # 2
            "船名(输入)",          # 3
            "IMO编码(输入)",       # 4
            "呼号(输入)",          # 5
            "MMSI",               # 6
            "建造日期",            # 7
            "总吨",               # 8
            "详细船舶类型",         # 9
            "呼号(爬取)",          # 10
            "注册船东",            # 11
            "原建造年份",          # 12  ← 新增：输入文件中的原值
            "原总吨数",            # 13  ← 新增：输入文件中的原值
            "数据比对判定",         # 14  ← 新增：比对诊断结果
            "错误信息",            # 15
            "查询过程",            # 16
            "是否需人工查询"        # 17
        ]
        # 设置表头样式
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, size=11, color="FFFFFF")
        for col_idx, header in enumerate(headers, 1):
            cell = sheet.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.fill = header_fill
        # 设置列宽
        col_widths = {1: 22, 2: 10, 3: 22, 4: 16, 5: 14, 6: 14, 7: 12, 8: 12,
                      9: 20, 10: 14, 11: 26, 12: 14, 13: 12, 14: 48, 15: 26, 16: 50, 17: 14}
        for col_idx, width in col_widths.items():
            sheet.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width
        # 冻结首行
        sheet.freeze_panes = "A2"
        wb.save(result_excel_path)
        print(f"\U0001f4ca 新建结果文件：{os.path.basename(result_excel_path)}")
    return wb, result_excel_path


def write_result_to_excel(wb: openpyxl.Workbook, excel_path: str, ship_data: dict, query_result: dict):
    """写入查询结果（含比对诊断列）"""
    sheet = wb.active
    next_row = sheet.max_row + 1

    # 从查询结果中提取爬取到的字段
    new_build_date = query_result.get("build_date", "")
    new_gross_tonnage = query_result.get("gross_tonnage", "")
    new_call_sign = query_result.get("call_sign", "")
    new_mmsi = query_result.get("mmsi", "")
    new_ship_type = query_result.get("ship_type_detailed", "")
    new_owner = query_result.get("registered_owner", "")

    # 从输入文件中提取原始值
    old_build_date = ship_data.get("original_build_date", "")
    old_gross_tonnage = ship_data.get("original_gross_tonnage", "")

    # 生成数据比对判定
    comparison_judgment = build_comparison_judgment(
        new_build_date, new_gross_tonnage,
        old_build_date, old_gross_tonnage
    )

    # ── 写入各列 ──
    # 列1：查询标识
    sheet.cell(row=next_row, column=1, value=ship_data.get("imo") or ship_data.get("call_sign") or (ship_data.get("ship_name")[:20] if ship_data.get("ship_name") else "无标识"))
    # 列2：原始行号
    sheet.cell(row=next_row, column=2, value=ship_data.get("row"))
    # 列3：船名(输入)
    sheet.cell(row=next_row, column=3, value=ship_data.get("ship_name", ""))
    # 列4：IMO编码(输入)
    sheet.cell(row=next_row, column=4, value=ship_data.get("imo", ""))
    # 列5：呼号(输入)
    sheet.cell(row=next_row, column=5, value=ship_data.get("call_sign", ""))
    # 列6：MMSI（爬取）
    sheet.cell(row=next_row, column=6, value=new_mmsi)
    # 列7：建造日期（爬取）
    sheet.cell(row=next_row, column=7, value=new_build_date)
    # 列8：总吨（爬取）
    sheet.cell(row=next_row, column=8, value=new_gross_tonnage)
    # 列9：详细船舶类型（爬取）
    sheet.cell(row=next_row, column=9, value=new_ship_type)
    # 列10：呼号(爬取)
    sheet.cell(row=next_row, column=10, value=new_call_sign)
    # 列11：注册船东（爬取）
    sheet.cell(row=next_row, column=11, value=new_owner)
    # 列12：原建造年份（输入文件原值）
    sheet.cell(row=next_row, column=12, value=old_build_date)
    # 列13：原总吨数（输入文件原值）
    sheet.cell(row=next_row, column=13, value=old_gross_tonnage)
    # 列14：数据比对判定
    sheet.cell(row=next_row, column=14, value=comparison_judgment)
    # 列15：错误信息
    sheet.cell(row=next_row, column=15, value=query_result.get("error", "") or (query_result.get("no_data") and "无匹配数据" or ""))
    # 列16：查询过程
    sheet.cell(row=next_row, column=16, value=query_result.get("query_process", ""))
    # 列17：是否需人工查询
    sheet.cell(row=next_row, column=17, value="是" if query_result.get("need_manual_check") else "否")

    # ── 高亮比对判定列 ──
    judgment_cell = sheet.cell(row=next_row, column=14)
    judgment_cell.alignment = Alignment(wrap_text=True, vertical="center")
    if "完全一致" in comparison_judgment:
        judgment_cell.font = Font(color="006100")
        judgment_cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    elif "数据有更新" in comparison_judgment:
        judgment_cell.font = Font(color="9C5700", bold=True)
        judgment_cell.fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
    elif "原数据为空，已补充" in comparison_judgment:
        judgment_cell.font = Font(color="0066CC")
        judgment_cell.fill = PatternFill(start_color="DAEEF3", end_color="DAEEF3", fill_type="solid")
    elif "注意" in comparison_judgment:
        judgment_cell.font = Font(color="9C0006")
        judgment_cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

    wb.save(excel_path)
    print(f"\U0001f4dd 写入结果：第{next_row}行（原始行：{ship_data.get('row')}）| 比对判定：{comparison_judgment}")


# ========== 单文件处理 ==========
def process_single_excel(xlsx_file: str, current_idx: int, total_count: int):
    """处理单个Excel文件"""
    file_name = os.path.basename(xlsx_file).replace(".xlsx", "").replace(".csv", "")
    print(f"\n" + "="*100)
    print(f"\U0001f680 开始处理第{current_idx}/{total_count}个文件：{os.path.basename(xlsx_file)}")
    print("="*100)

    # 1. 读取数据
    ship_data_list = read_input_excel(xlsx_file)
    if not ship_data_list:
        print(f"❌ {os.path.basename(xlsx_file)} 无有效数据，跳过处理")
        return

    # 2. 初始化结果Excel
    result_wb, result_excel_path = init_result_excel(file_name)

    # 3. 加载断点
    start_row, current_account_idx = load_breakpoint(file_name)
    pending_data = [data for data in ship_data_list if data["row"] >= start_row]
    if not pending_data:
        print(f"\U0001f389 {os.path.basename(xlsx_file)} 所有数据已处理完成")
        result_wb.close()
        return
    print(f"\U0001f4cb 待处理：{len(pending_data)}条数据 | 从第{start_row}行开始 | 当前账号索引：{current_account_idx}")

    # 4. 初始化爬虫
    if current_account_idx >= len(ACCOUNTS):
        print(f"❌ 账号索引{current_account_idx}越界（共{len(ACCOUNTS)}个账号）")
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
            print(f"❌ 账号{current_account['username']}登录失败，切换账号")
            raise Exception("初始账号登录失败")
    except Exception as e:
        print(f"❌ 爬虫初始化失败：{str(e)}")
        if crawler:
            crawler.close()
        result_wb.close()
        return

    # 5. 处理数据
    try:
        for ship_data in pending_data:
            current_data_row = ship_data["row"]
            print(f"\n" + "-"*60)
            print(f"\U0001f504 处理进度：原始行{current_data_row}（账号：{current_account['username']}）")
            print("-"*60)

            try:
                # 执行分级查询
                query_result = crawler.query_imo_ship(
                    imo_number=ship_data["imo"],
                    call_sign=ship_data["call_sign"],
                    ship_name=ship_data["ship_name"]
                )

                # 写入结果
                write_result_to_excel(result_wb, result_excel_path, ship_data, query_result)

                # 保存断点
                save_breakpoint(file_name, current_data_row + 1, current_account_idx)

                # 反爬延迟
                time.sleep(random.uniform(2, 4))

            except SearchLimitReachedException:
                # 切换账号：循环遍历所有剩余账号，直到找到可用的
                print(f"\n\U0001f6a8 账号{current_account['username']}达到搜索限制，开始循环切换剩余账号")
                crawler.close()
                switch_success = False  # 标记是否切换到可用账号

                # 循环遍历剩余所有账号（从当前下一个开始）
                while current_account_idx + 1 < len(ACCOUNTS):
                    current_account_idx += 1
                    current_account = ACCOUNTS[current_account_idx]
                    print(f"\U0001f504 尝试切换到账号：{current_account['username']}（索引：{current_account_idx}）")

                    # 初始化新账号并尝试登录
                    crawler = IMO_Edge_Crawler(
                        username=current_account["username"],
                        password=current_account["password"],
                        headless=HEADLESS_MODE
                    )
                    if crawler.login_imo():
                        print(f"✅ 账号{current_account['username']}切换并登录成功")
                        switch_success = True
                        break  # 找到可用账号，终止循环
                    else:
                        print(f"❌ 账号{current_account['username']}登录失败，继续切换下一个")
                        crawler.close()  # 关闭登录失败的浏览器

                # 切换结果判断
                if not switch_success:
                    # 所有剩余账号都不可用
                    print(f"❌ 所有账号已用尽/登录失败，停止处理当前文件")
                    save_breakpoint(file_name, current_data_row, current_account_idx)
                    crawler.close() if crawler else None
                    break  # 终止当前文件处理
                else:
                    # 切换到可用账号，重新处理当前行
                    print(f"\U0001f504 用新账号{current_account['username']}重新处理行{current_data_row}")
                    query_result = crawler.query_imo_ship(
                        imo_number=ship_data["imo"],
                        call_sign=ship_data["call_sign"],
                        ship_name=ship_data["ship_name"]
                    )
                    # 写入结果+保存断点
                    write_result_to_excel(result_wb, result_excel_path, ship_data, query_result)
                    save_breakpoint(file_name, current_data_row + 1, current_account_idx)
                    time.sleep(random.uniform(2, 4))  # 反爬延迟

            except Exception as e:
                error_msg = str(e)[:100]
                print(f"❌ 处理行{current_data_row}异常：{error_msg}")
                # 写入错误结果
                error_result = {
                    "error": error_msg,
                    "query_process": f"处理异常：{error_msg}",
                    "need_manual_check": True
                }
                write_result_to_excel(result_wb, result_excel_path, ship_data, error_result)
                save_breakpoint(file_name, current_data_row + 1, current_account_idx)
                time.sleep(random.uniform(2, 4))

    except Exception as e:
        print(f"❌ 批量处理异常：{str(e)}")
    finally:
        if crawler:
            crawler.close()
        result_wb.close()

# ========== 主入口 ==========
if __name__ == "__main__":
    # 修复 Windows GBK 编码问题
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # 获取输入文件夹下的所有CSV和Excel文件（排除 Flag_Code_Mapping.csv）
    all_files = []
    for f in os.listdir(INPUT_FOLDER):
        if f.endswith(".csv") or f.endswith(".xlsx"):
            # 排除 Flag_Code_Mapping.csv（非船舶数据）
            if "flag_code_mapping" in f.lower() or "flag" in f.lower():
                print(f"⚠️ 跳过非船舶数据文件：{f}")
                continue
            all_files.append(os.path.join(INPUT_FOLDER, f))

    if not all_files:
        print(f"❌ 输入文件夹{INPUT_FOLDER}下未找到船舶数据文件（CSV/XLSX）")
        exit(1)

    # 按文件名排序
    all_files.sort()

    print(f"\n{'='*80}")
    print(f"  IMO 船舶数据爬虫 - 增强版")
    print(f"  输入目录: {INPUT_FOLDER}")
    print(f"  输出目录: {OUTPUT_FOLDER}")
    print(f"  待处理文件: {len(all_files)} 个")
    for f in all_files:
        print(f"    - {os.path.basename(f)}")
    print(f"{'='*80}")

    # 按顺序处理每个文件
    total_files = len(all_files)
    for idx, xlsx_file in enumerate(all_files, 1):
        process_single_excel(xlsx_file, idx, total_files)

    print(f"\n\U0001f389 所有{total_files}个文件处理完成！结果文件已保存到：{OUTPUT_FOLDER}")
