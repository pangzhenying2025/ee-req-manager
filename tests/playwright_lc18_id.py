from pathlib import Path

from playwright.sync_api import sync_playwright


SCREENSHOT = Path(r"E:\hermes\lc18_id_repair.png")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True,
        executable_path=str(CHROME) if CHROME.exists() else None,
    )
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    console_errors = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.goto("http://127.0.0.1:8516")
    page.wait_for_load_state("networkidle")
    page.locator('div[data-baseweb="select"]').first.click()
    page.get_by_text("MEV02", exact=True).last.click()
    page.wait_for_timeout(2000)
    page.locator("label").filter(has_text="需求追溯").first.click()
    page.get_by_text("追溯与分配工作台", exact=False).wait_for(timeout=15000)
    page.get_by_role("tab", name="功能—需求树").click()
    page.get_by_text("选择系统（SL）", exact=True).wait_for()

    page.get_by_text("SL01 · 整车高压控制子系统", exact=True).first.click()
    page.keyboard.type("SL18")
    page.get_by_text("SL18 · 泊车辅助子系统", exact=True).last.click()
    page.get_by_text("LC18-01", exact=False).first.wait_for()
    page.get_by_text("LC18-01", exact=False).first.click()
    page.get_by_text("SYS-LC18-01", exact=False).first.wait_for()

    body = page.locator("body").inner_text()
    assert "LC-AUTO-249" not in body
    assert "SYS-LC-AUTO-249" not in body
    assert "Exception" not in body
    assert "Traceback" not in body
    assert not console_errors, console_errors
    page.screenshot(path=str(SCREENSHOT), full_page=True)
    print(SCREENSHOT)
    browser.close()
