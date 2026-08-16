"""Browser smoke test for the Streamlit requirements workspace."""
from playwright.sync_api import sync_playwright


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 1000})
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

    page.goto("http://127.0.0.1:8512")
    page.wait_for_load_state("networkidle")
    page.get_by_text("需求与架构总览", exact=True).wait_for(timeout=15000)

    page.get_by_text("▤ 需求规范", exact=True).click()
    page.get_by_text("需求规范工作台", exact=True).wait_for(timeout=15000)
    page.get_by_role("tab", name="＋ 新建规范").click()
    page.get_by_label("规范编号 *").fill("UI-FRS")
    page.get_by_label("规范名称 *").fill("界面冒烟测试规范")
    page.get_by_role("button", name="创建规范").click()
    page.get_by_text("需求规范工作台", exact=True).wait_for(timeout=15000)

    page.get_by_role("tab", name="▤ 规范视图").click()
    page.get_by_text("UI-FRS", exact=False).first.wait_for(timeout=10000)
    page.screenshot(path="ui-smoke.png", full_page=True)
    print(f"UI_SMOKE=OK console_errors={len(console_errors)}")
    if console_errors:
        print("\n".join(console_errors[:5]))
    browser.close()
