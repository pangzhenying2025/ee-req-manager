import re
from pathlib import Path

from playwright.sync_api import sync_playwright

SCREENSHOT = Path(r"E:\hermes\ee_req_collaboration.png")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
URL = "http://127.0.0.1:8521"


def open_requirement_editor(page, user_name):
    page.goto(URL)
    page.wait_for_load_state("networkidle")
    project_select = page.locator('div[data-baseweb="select"]').first
    project_select.click()
    page.get_by_text("MEV02", exact=True).last.click()
    page.get_by_role("textbox", name="协作者名称").fill(user_name)
    page.get_by_role("textbox", name="协作者名称").press("Enter")
    page.locator("label").filter(has_text="需求规范").first.click()
    page.get_by_text("需求规范工作台", exact=True).wait_for(timeout=20000)
    page.get_by_role("tab", name=re.compile("编辑需求")).click()
    page.get_by_text("选择需求", exact=True).wait_for(timeout=15000)
    page.get_by_role("button", name="开始编辑").wait_for(timeout=15000)


def rerun_current_page(page):
    page.locator("label").filter(has_text="工程总览").first.click()
    page.wait_for_timeout(800)
    page.locator("label").filter(has_text="需求规范").first.click()
    page.get_by_text("需求规范工作台", exact=True).wait_for(timeout=20000)
    page.get_by_role("tab", name=re.compile("编辑需求")).click()


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True,
        executable_path=str(CHROME) if CHROME.exists() else None,
    )
    alice_context = browser.new_context(viewport={"width": 1600, "height": 1000})
    bob_context = browser.new_context(viewport={"width": 1600, "height": 1000})
    alice = alice_context.new_page()
    bob = bob_context.new_page()

    open_requirement_editor(alice, "Alice")
    open_requirement_editor(bob, "Bob")

    alice.get_by_role("button", name="开始编辑").click()
    alice.get_by_text(re.compile(r"你正在编辑：.+编辑权保留 5 分钟")).wait_for(timeout=15000)

    rerun_current_page(bob)
    bob.get_by_text(re.compile(r"正由「Alice」编辑")).wait_for(timeout=15000)
    assert bob.get_by_role("button", name="保存新版本").is_disabled()

    alice.get_by_role("button", name="释放").click()
    alice.get_by_role("tab", name=re.compile("编辑需求")).click()
    alice.get_by_role("button", name="开始编辑").wait_for(timeout=15000)

    rerun_current_page(bob)
    bob.get_by_role("button", name="开始编辑").click()
    bob.get_by_text(re.compile(r"你正在编辑：.+编辑权保留 5 分钟")).wait_for(timeout=15000)
    assert bob.get_by_role("button", name="保存新版本").is_enabled()

    bob.screenshot(path=str(SCREENSHOT), full_page=True)
    print(f"COLLABORATION_UI=OK alice_blocked_bob_then_handoff screenshot={SCREENSHOT}")
    alice_context.close()
    bob_context.close()
    browser.close()
