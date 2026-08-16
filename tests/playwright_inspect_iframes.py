from pathlib import Path

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    browser = p.chromium.launch(headless=True, executable_path=str(chrome))
    page = browser.new_page(viewport={"width": 1500, "height": 900})
    page.goto("http://127.0.0.1:8524")
    page.wait_for_load_state("networkidle")
    select = page.locator('div[data-baseweb="select"]').first
    select.click()
    page.get_by_text("MEV02", exact=True).last.click()
    page.locator("label").filter(has_text="功能逻辑").first.click()
    page.get_by_text("功能与信号逻辑", exact=False).wait_for(timeout=20000)
    page.wait_for_timeout(4000)
    rows = []
    for index in range(page.locator("iframe").count()):
        item = page.locator("iframe").nth(index)
        box = item.bounding_box()
        rows.append({
            "index": index,
            "title": item.get_attribute("title"),
            "src": item.get_attribute("src"),
            "height": box["height"] if box else None,
        })
    print(rows)
    browser.close()
