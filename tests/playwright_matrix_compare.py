import os
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = os.environ.get("MATRIX_COMPARE_TEST_URL", "http://127.0.0.1:8526")
SCREENSHOT = Path(r"E:\hermes\ee_req_matrix_compare.png")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")

BASELINE = '''VERSION ""
NS_ :
BS_:
BU_: VCU ICM
BO_ 256 VCU_Status: 8 VCU
 SG_ VehicleSpeed : 0|16@1+ (0.1,0) [0|250] "km/h" ICM
'''

CANDIDATE = '''VERSION ""
NS_ :
BS_:
BU_: VCU ICM ADAS
BO_ 256 VCU_Status: 8 VCU
 SG_ VehicleSpeed : 0|16@1+ (0.01,0) [0|300] "km/h" ICM,ADAS
 SG_ DriveReady : 16|1@1+ (1,0) [0|1] "" ICM
'''


with tempfile.TemporaryDirectory() as folder, sync_playwright() as playwright:
    baseline = Path(folder) / "baseline.dbc"
    candidate = Path(folder) / "candidate.dbc"
    baseline.write_text(BASELINE, encoding="utf-8")
    candidate.write_text(CANDIDATE, encoding="utf-8")

    browser = playwright.chromium.launch(
        headless=True,
        executable_path=str(CHROME) if CHROME.exists() else None,
    )
    page = browser.new_page(viewport={"width": 1500, "height": 960})
    console_errors = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.goto(URL)
    page.wait_for_load_state("networkidle")
    page.locator("label").filter(has_text="通信矩阵对比").first.click()
    page.get_by_text("通信矩阵版本对比", exact=False).wait_for(timeout=20000)

    uploaders = page.locator('input[type="file"]')
    assert uploaders.count() == 2, uploaders.count()
    uploaders.nth(0).set_input_files(str(baseline))
    uploaders.nth(1).set_input_files(str(candidate))

    page.get_by_text("差异明细", exact=True).wait_for(timeout=20000)
    body = page.locator("body").inner_text()
    assert "新增信号" in body
    assert "修改信号" in body
    assert "差异项" in body
    assert "导出差异 CSV" in body
    assert "通信矩阵解析失败" not in body
    assert not console_errors, console_errors
    page.screenshot(path=str(SCREENSHOT), full_page=True)
    print(f"MATRIX_COMPARE_UI=OK screenshot={SCREENSHOT}")
    browser.close()
