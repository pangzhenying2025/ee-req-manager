import os
from pathlib import Path

from playwright.sync_api import sync_playwright


URL = os.environ.get("SIGNAL_FLOW_TEST_URL", "http://127.0.0.1:8524")
SCREENSHOT = Path(r"E:\hermes\ee_req_signal_flow_responsive.png")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True,
        executable_path=str(CHROME) if CHROME.exists() else None,
    )
    page = browser.new_page(viewport={"width": 1500, "height": 900})
    page.goto(URL)
    page.wait_for_load_state("networkidle")

    project_select = page.locator('div[data-baseweb="select"]').first
    project_select.click()
    page.get_by_text("MEV02", exact=True).last.click()
    page.locator("label").filter(has_text="功能逻辑").first.click()
    page.get_by_text("功能与信号逻辑", exact=False).wait_for(timeout=20000)

    iframe = page.locator('iframe[title="signal_flow.ee_req_signal_flow_editor"]')
    iframe.wait_for(timeout=30000)
    frame = page.frame_locator('iframe[title="signal_flow.ee_req_signal_flow_editor"]')
    viewport = frame.locator(".viewport")
    viewport.wait_for(timeout=20000)
    frame_height = iframe.bounding_box()["height"]
    assert 550 <= frame_height <= 870, frame_height
    assert frame.get_by_role("button", name="全屏").is_visible()

    scroll_height = viewport.evaluate("el => el.scrollHeight")
    assert scroll_height > 700, scroll_height
    target_top = min(360, scroll_height - 300)
    viewport.evaluate("(el, top) => { el.scrollTop = top; }", target_top)
    page.wait_for_timeout(300)
    before = viewport.evaluate("el => el.scrollTop")
    before_bottom_gap = viewport.evaluate(
        "el => el.scrollHeight - el.clientHeight - el.scrollTop"
    )
    assert before > 100, before

    signal = frame.locator(".signal-node").nth(4)
    clicked_id = signal.get_attribute("data-signal-id")
    clicked_name = signal.locator(".node-code").text_content().strip()
    signal.click()
    page.wait_for_timeout(1800)
    iframe = page.locator('iframe[title="signal_flow.ee_req_signal_flow_editor"]')
    iframe.wait_for(timeout=20000)
    frame = page.frame_locator('iframe[title="signal_flow.ee_req_signal_flow_editor"]')
    viewport = frame.locator(".viewport")
    viewport.wait_for(timeout=20000)
    after = viewport.evaluate("el => el.scrollTop")
    after_bottom_gap = viewport.evaluate(
        "el => el.scrollHeight - el.clientHeight - el.scrollTop"
    )
    assert after > 80, (before, after)
    assert abs(after_bottom_gap - before_bottom_gap) <= 30, (
        before_bottom_gap,
        after_bottom_gap,
    )

    selected_nodes = frame.locator(".node-signal.selected")
    assert selected_nodes.count() == 1, selected_nodes.count()
    selected_id = selected_nodes.first.locator("xpath=..").get_attribute("data-signal-id")
    assert selected_id == clicked_id, (clicked_id, selected_id)
    page.get_by_text(clicked_name, exact=True).last.wait_for(timeout=20000)
    selected_color = selected_nodes.first.evaluate(
        "el => getComputedStyle(el).stroke"
    )
    hover_node = frame.locator(".node-signal:not(.selected)").first
    hover_node.hover()
    hover_color = hover_node.evaluate("el => getComputedStyle(el).stroke")
    assert selected_color != hover_color, (selected_color, hover_color)

    fullscreen_button = frame.get_by_role("button", name="全屏")
    fullscreen_button.click()
    page.wait_for_timeout(500)
    is_fullscreen = frame.locator("html").evaluate(
        "el => document.fullscreenElement === el"
    )
    assert is_fullscreen
    frame.get_by_role("button", name="退出全屏").click()

    page.screenshot(path=str(SCREENSHOT), full_page=True)
    print(
        "SIGNAL_FLOW_VIEWPORT=OK "
        f"frame_height={frame_height} scroll_before={before} scroll_after={after} "
        f"bottom_gap={before_bottom_gap}->{after_bottom_gap} fullscreen=OK "
        f"selected_count=1 selected={selected_color} hover={hover_color} "
        f"screenshot={SCREENSHOT}"
    )
    browser.close()
