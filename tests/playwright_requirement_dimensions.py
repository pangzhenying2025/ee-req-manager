from pathlib import Path

from playwright.sync_api import sync_playwright


SCREENSHOT = Path(r"E:\hermes\requirement_dimensions.png")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


with sync_playwright() as playwright:
    # 优先复用本机 Chrome，避免测试环境变化后重复下载 Playwright 浏览器。
    browser = playwright.chromium.launch(
        headless=True,
        executable_path=str(CHROME) if CHROME.exists() else None,
    )
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    console_errors = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.goto("http://127.0.0.1:8514")
    page.wait_for_load_state("networkidle")

    # 当前车型切换到已导入完整需求数据的 MEV02。
    page.locator('div[data-baseweb="select"]').first.click()
    page.get_by_text("MEV02", exact=True).last.click()
    page.wait_for_timeout(2000)

    page.locator("label").filter(has_text="需求规范").first.click()
    page.get_by_text("需求规范工作台", exact=False).wait_for(timeout=15000)

    # 两个正交维度必须同时存在，表格也不能再只显示一个模糊的“类型”。
    page.get_by_text("需求层级", exact=True).first.wait_for()
    page.get_by_text("需求性质", exact=True).first.wait_for()
    page.get_by_text("系统层", exact=True).first.wait_for()
    page.get_by_text("子系统层", exact=True).first.wait_for()
    page.get_by_text("功能层", exact=True).first.wait_for()

    body = page.locator("body").inner_text()
    assert "Exception" not in body
    assert "Traceback" not in body
    assert not console_errors, console_errors
    page.screenshot(path=str(SCREENSHOT), full_page=True)
    print(SCREENSHOT)
    browser.close()
