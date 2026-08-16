import re
from pathlib import Path
from time import perf_counter

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

SCREENSHOT = Path(r"E:\hermes\signal_flow_editor.png")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def current_component_frame(page):
    for _ in range(60):
        for frame in reversed(page.frames):
            if "ee_req_signal_flow_editor" not in frame.url or frame.is_detached():
                continue
            try:
                if frame.locator(".signal-node").count():
                    return frame
            except PlaywrightError:
                continue
        page.wait_for_timeout(300)
    frame_urls = [frame.url for frame in page.frames]
    page.screenshot(path=str(SCREENSHOT), full_page=True)
    body_excerpt = page.locator("body").inner_text()[-2000:]
    raise AssertionError(
        "editable signal-flow component did not stabilize\n"
        f"frames={frame_urls}\nbody={body_excerpt}"
    )


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True,
        executable_path=str(CHROME) if CHROME.exists() else None,
    )
    page = browser.new_page(viewport={"width": 1900, "height": 1080})
    console_errors = []
    page.on(
        "console",
        lambda message: console_errors.append(message.text) if message.type == "error" else None,
    )
    page.goto("http://127.0.0.1:8519")
    page.wait_for_load_state("networkidle")

    page.locator('div[data-baseweb="select"]').first.click()
    page.get_by_text("MEV02", exact=True).last.click()
    page.wait_for_timeout(1500)
    page.locator("label").filter(has_text="功能逻辑").first.click()
    page.get_by_text("功能与信号逻辑", exact=False).wait_for(timeout=15000)
    page.get_by_role("tab", name="信号数据流图").click()
    page.get_by_text("LIVE DATA-FLOW CANVAS", exact=True).wait_for(timeout=15000)

    page.get_by_text("信号明细", exact=True).click()
    page.wait_for_timeout(1200)
    component_frame = current_component_frame(page)
    component_frame.locator(".signal-node").first.wait_for(timeout=15000)
    page.get_by_text("信号属性", exact=True).wait_for(timeout=10000)
    # The surrounding Streamlit page renders several legacy tabs eagerly on the
    # first visit. Do not count that cold-load work as endpoint edit latency.
    page.wait_for_timeout(4000)
    receiver_heading = page.get_by_text(re.compile(r"^接收端点 · \d+$")).first
    initial_receiver_count = int(receiver_heading.inner_text().rsplit(" ", 1)[-1])

    endpoint = component_frame.locator(".endpoint[data-endpoint-id]:not([data-endpoint-id=''])").first
    old_ecu = endpoint.get_attribute("data-old-ecu")
    save_latency_ms = float("nan")
    page.get_by_text("新增原因 *", exact=True).wait_for(timeout=10000)
    page.get_by_label("新增原因 *").fill("Playwright验证一个信号连接多个ECU")
    save_started = perf_counter()
    page.get_by_role("button", name="新增接收分支").click()
    expected_heading = f"接收端点 · {initial_receiver_count + 1}"
    page.get_by_text(expected_heading, exact=True).wait_for(timeout=15000)
    save_latency_ms = (perf_counter() - save_started) * 1000

    page.get_by_text("删除连接", exact=True).click()
    page.get_by_text("删除原因 *", exact=True).wait_for(timeout=10000)
    page.get_by_label("需要删除的连接").click()
    page.get_by_text(re.compile(r".+ · 人工新增$")).last.click()
    page.get_by_label("删除原因 *").fill("Playwright删除性能验证")
    delete_started = perf_counter()
    page.get_by_role("button", name="删除接收连接").click()
    page.get_by_text(f"接收端点 · {initial_receiver_count}", exact=True).wait_for(timeout=15000)
    delete_latency_ms = (perf_counter() - delete_started) * 1000

    page.screenshot(path=str(SCREENSHOT), full_page=True)
    body = page.locator("body").inner_text()
    assert "精度 Factor" in body
    assert "偏移量 Offset" in body
    assert "删除接收连接" in body
    assert f"接收端点 · {initial_receiver_count}" in body, body[-2000:]
    assert "恢复已删除连接" in body
    assert "Exception" not in body
    assert "Traceback" not in body
    assert not console_errors, console_errors
    print(
        f"SIGNAL_FLOW_MULTI_RX_UI=OK source_rx={old_ecu} "
        f"receivers={initial_receiver_count}->{initial_receiver_count + 1}->{initial_receiver_count} "
        f"add_ms={save_latency_ms:.0f} delete_ms={delete_latency_ms:.0f} screenshot={SCREENSHOT}"
    )
    browser.close()
