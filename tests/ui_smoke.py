"""Portable regression against the generated demo, never against customer data."""

import os
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

URL = os.environ["EE_REQ_TEST_URL"]
OUTPUT = Path(os.environ.get("EE_REQ_TEST_OUTPUT", "test-results"))
OUTPUT.mkdir(parents=True, exist_ok=True)


def navigate(page, text):
    page.locator('[data-testid="stSidebar"] label').filter(has_text=text).first.click()


with sync_playwright() as playwright:
    executable = os.environ.get("EE_REQ_TEST_BROWSER")
    browser = playwright.chromium.launch(headless=True, **({"executable_path": executable} if executable else {}))
    page = browser.new_page(viewport={"width": 1600, "height": 1050})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(URL)
        page.wait_for_load_state("networkidle")
        expect(page.get_by_text("需求与架构总览", exact=True)).to_be_visible(timeout=20000)
        page.locator('[data-testid="stSidebar"] div[data-baseweb="select"]').first.click()
        page.get_by_role("option", name="开发演示车", exact=True).click()

        navigate(page, "需求规范")
        expect(page.get_by_text("需求规范工作台", exact=True)).to_be_visible(timeout=20000)
        expect(page.get_by_text("DEMO-SYS", exact=False).first).to_be_visible()

        navigate(page, "功能逻辑")
        expect(page.get_by_text("LIVE DATA-FLOW CANVAS", exact=True)).to_be_visible(timeout=20000)
        frame = page.frame_locator('iframe[title="signal_flow.ee_req_signal_flow_editor"]')
        if os.environ.get("EE_REQ_COMPONENT_DEV_URL"):
            expect(frame.locator('script[src*="@vite/client"]')).to_have_count(1, timeout=15000)
        expect(frame.locator(".signal-node")).to_have_count(5, timeout=20000)
        signal = frame.locator(".signal-node").nth(4)
        name = signal.locator(".node-code").inner_text()
        signal_id = signal.get_attribute("data-signal-id")
        signal.click()
        expect(frame.locator(".node-signal.selected")).to_have_count(1)
        expect(frame.locator(".node-signal.selected")).to_have_attribute("data-signal-id", signal_id)
        expect(page.get_by_text(name, exact=True).first).to_be_visible(timeout=20000)

        # Viewport and manual node positions must survive a server selection event.
        frame.locator(".react-flow__controls-zoomin").click()
        page.wait_for_timeout(300)
        transform = frame.locator(".react-flow__viewport").get_attribute("style")
        frame.locator(".signal-node").nth(3).click()
        expect(page.get_by_text("LockRequest", exact=True).first).to_be_visible(timeout=20000)
        expect(frame.locator(".react-flow__viewport")).to_have_attribute("style", transform)

        heading = page.get_by_text(re.compile(r"^接收端点 · \d+$")).first
        expect(heading).to_be_visible()
        before = int(heading.inner_text().rsplit(" ", 1)[-1])
        page.get_by_role("button", name="开始编辑", exact=True).click()
        add = page.locator("button:not([disabled])").filter(has_text=re.compile(r"^新增接收分支$"))
        expect(add).to_be_enabled(timeout=20000)
        expect(page.get_by_label("新增原因 *")).to_have_count(1)
        page.get_by_label("新增原因 *").fill("独立演示库浏览器回归")
        add.click()
        expect(page.get_by_text(f"接收端点 · {before + 1}", exact=True)).to_be_visible(timeout=20000)
        page.get_by_text("删除连接", exact=True).click()
        page.get_by_label("需要删除的连接").click()
        page.get_by_role("option").filter(has_text="人工新增").last.click()
        page.get_by_label("删除原因 *").fill("浏览器回归恢复原始端点数量")
        page.get_by_role("button", name="删除接收连接", exact=True).click()
        expect(page.get_by_text(f"接收端点 · {before}", exact=True)).to_be_visible(timeout=20000)
        page.screenshot(path=str(OUTPUT / "signal-flow.png"), full_page=True)

        navigate(page, "通信矩阵对比")
        expect(page.get_by_text("通信矩阵版本对比", exact=False)).to_be_visible(timeout=20000)
        base = b'VERSION ""\nNS_ :\nBS_:\nBU_: BCM ICM\nBO_ 769 Door: 8 BCM\n SG_ Lock : 0|8@1+ (1,0) [0|255] "" ICM\n'
        changed = base.replace(b"(1,0)", b"(0.5,0)")
        uploaders = page.locator('input[type="file"]')
        uploaders.nth(0).set_input_files({"name": "base.dbc", "mimeType": "application/octet-stream", "buffer": base})
        uploaders.nth(1).set_input_files({"name": "changed.dbc", "mimeType": "application/octet-stream", "buffer": changed})
        expect(page.get_by_text("差异明细", exact=True)).to_be_visible(timeout=20000)
        with page.expect_download() as download:
            page.get_by_role("button", name="导出差异 CSV", exact=False).click()
        text = Path(download.value.path()).read_text(encoding="utf-8-sig")
        assert "精度 Factor" in text and "0.5" in text, text
        page.screenshot(path=str(OUTPUT / "matrix-compare.png"), full_page=True)
        assert not page.locator('[data-testid="stException"]').count()
        assert not errors, errors
        print("UI_SMOKE=OK demo-project selection viewport add/delete matrix-diff download")
    except Exception:
        page.screenshot(path=str(OUTPUT / "failure.png"), full_page=True)
        raise
    finally:
        browser.close()
