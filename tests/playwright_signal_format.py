import re
from pathlib import Path

from playwright.sync_api import sync_playwright


URL = "http://127.0.0.1:8522"
SCREENSHOT = Path(r"E:\hermes\ee_req_signal_format_edit.png")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True,
        executable_path=str(CHROME) if CHROME.exists() else None,
    )
    page = browser.new_page(viewport={"width": 1600, "height": 1100})
    page.goto(URL)
    page.wait_for_load_state("networkidle")

    project_select = page.locator('div[data-baseweb="select"]').first
    project_select.click()
    page.get_by_text("MEV02", exact=True).last.click()
    page.get_by_role("textbox", name="协作者名称").fill("格式测试")
    page.get_by_role("textbox", name="协作者名称").press("Enter")
    page.locator("label").filter(has_text="信号管理").first.click()
    page.get_by_text("CAN信号管理", exact=False).wait_for(timeout=20000)
    page.locator("label").filter(has_text="编辑信号").first.click()

    page.get_by_role("button", name="开始编辑").click()
    page.get_by_text(re.compile(r"你正在编辑：.+编辑权保留 5 分钟")).wait_for(
        timeout=15000
    )

    byte_order = page.locator('[data-testid="stSelectbox"]').filter(
        has_text="字节序"
    )
    assert byte_order.count() == 1
    value_type = page.locator('[data-testid="stSelectbox"]').filter(
        has_text="值类型"
    )
    assert value_type.count() == 1

    current_motorola = page.get_by_text("Motorola（Big Endian）", exact=True).count()
    expected = "Intel（Little Endian）" if current_motorola else "Motorola（Big Endian）"
    byte_order.locator('div[data-baseweb="select"]').click()
    page.get_by_text(expected, exact=True).last.click()
    page.get_by_role("button", name=re.compile("保存修改")).click()
    page.get_by_text(re.compile(r"已更新")).wait_for(timeout=15000)

    page.locator("label").filter(has_text="编辑信号").first.click()
    page.get_by_text(expected, exact=True).wait_for(timeout=15000)
    page.screenshot(path=str(SCREENSHOT), full_page=True)
    print(f"SIGNAL_FORMAT_UI=OK expected={expected} screenshot={SCREENSHOT}")
    browser.close()
