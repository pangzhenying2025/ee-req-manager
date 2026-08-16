from pathlib import Path

from playwright.sync_api import sync_playwright


SCREENSHOT = Path(r"E:\hermes\function_requirement_trace_tree.png")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True,
        executable_path=str(CHROME) if CHROME.exists() else None,
    )
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    console_errors = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.goto("http://127.0.0.1:8512")
    page.wait_for_load_state("networkidle")
    page.locator('div[data-baseweb="select"]').first.click()
    page.get_by_text("MEV02", exact=True).last.click()
    page.wait_for_timeout(2000)
    page.locator("label").filter(has_text="需求追溯").first.click()
    page.wait_for_timeout(4000)
    page.get_by_text("追溯与分配工作台", exact=False).wait_for()
    page.get_by_role("tab", name="功能—需求树").click()
    page.get_by_text("具体功能", exact=True).first.wait_for()
    page.get_by_text("LC01-01", exact=False).first.wait_for()
    page.get_by_text("AF-008", exact=False).first.wait_for()
    page.get_by_text("SYS-AF-008", exact=False).first.wait_for()
    page.get_by_text("VER-AF-008", exact=False).first.wait_for()
    page.screenshot(path=str(SCREENSHOT), full_page=True)
    assert "Exception" not in page.locator("body").inner_text()
    assert not console_errors, console_errors
    print(SCREENSHOT)
    browser.close()
