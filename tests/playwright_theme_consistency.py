import os
from pathlib import Path

from playwright.sync_api import sync_playwright


URL = os.environ.get("THEME_TEST_URL", "http://127.0.0.1:8523")
SCREENSHOT = Path(r"E:\hermes\ee_req_dark_client_fixed.png")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


def rgb_tuple(css_value: str) -> tuple[int, int, int]:
    values = css_value.removeprefix("rgb(").removesuffix(")").split(",")
    return tuple(int(value.strip()) for value in values[:3])


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True,
        executable_path=str(CHROME) if CHROME.exists() else None,
    )
    context = browser.new_context(
        viewport={"width": 1600, "height": 1000},
        color_scheme="dark",
    )
    page = context.new_page()
    page.goto(URL)
    page.wait_for_load_state("networkidle")

    project_select = page.locator('div[data-baseweb="select"]').first
    project_select.click()
    page.get_by_text("MEV02", exact=True).last.click()
    page.locator("label").filter(has_text="需求规范").first.click()
    page.get_by_text("需求规范工作台", exact=True).wait_for(timeout=20000)

    metric = page.locator('[data-testid="stMetric"]').first
    metric.wait_for(timeout=15000)
    metric_value = metric.locator('[data-testid="stMetricValue"]')
    metric_label = metric.locator('[data-testid="stMetricLabel"]')
    value_color = rgb_tuple(metric_value.evaluate("el => getComputedStyle(el).color"))
    label_color = rgb_tuple(metric_label.evaluate("el => getComputedStyle(el).color"))
    metric_background = metric.evaluate("el => getComputedStyle(el).backgroundColor")

    widget_labels = {}
    for text in ("当前规范", "需求层级", "需求性质", "状态", "搜索"):
        label = page.locator('[data-testid="stWidgetLabel"]').filter(has_text=text).first
        label.wait_for(timeout=15000)
        widget_labels[text] = rgb_tuple(
            label.evaluate("el => getComputedStyle(el).color")
        )

    dataframe = page.locator('[data-testid="stDataFrame"]').first
    dataframe.wait_for(timeout=20000)

    assert sum(value_color) < 300, value_color
    assert sum(label_color) < 450, label_color
    assert metric_background not in {"rgb(24, 35, 43)", "rgba(0, 0, 0, 0)"}
    assert all(sum(color) < 450 for color in widget_labels.values()), widget_labels

    page.screenshot(path=str(SCREENSHOT), full_page=True)
    print(
        "DARK_CLIENT_THEME=OK "
        f"value={value_color} label={label_color} background={metric_background} "
        f"widget_labels={widget_labels} "
        f"screenshot={SCREENSHOT}"
    )
    context.close()
    browser.close()
