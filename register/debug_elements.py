"""
调试工具 - 查找页面上所有可点击元素
"""
import asyncio
from camoufox.async_api import AsyncCamoufox


async def debug_page_elements(url):
    """调试页面元素"""
    async with AsyncCamoufox(headless=False) as browser:
        page = await browser.new_page()

        print(f"访问页面: {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        print("\n" + "="*50)
        print("查找所有可点击元素")
        print("="*50)

        # 查找所有按钮
        buttons = await page.query_selector_all('button, div[role="button"], div[class*="button"], a[role="button"]')
        print(f"\n找到 {len(buttons)} 个按钮/可点击元素:\n")

        for idx, btn in enumerate(buttons):
            try:
                text = await btn.inner_text()
                is_visible = await btn.is_visible()
                classes = await btn.get_attribute('class')
                role = await btn.get_attribute('role')

                print(f"[{idx}] 可见:{is_visible} | 文本:'{text}' | class:'{classes}' | role:'{role}'")
            except Exception as e:
                print(f"[{idx}] 无法获取信息: {e}")

        print("\n" + "="*50)
        print("查找所有输入框")
        print("="*50)

        inputs = await page.query_selector_all('input')
        print(f"\n找到 {len(inputs)} 个输入框:\n")

        for idx, inp in enumerate(inputs):
            try:
                type_attr = await inp.get_attribute('type')
                placeholder = await inp.get_attribute('placeholder')
                is_visible = await inp.is_visible()
                is_editable = await inp.is_editable()

                print(f"[{idx}] type:'{type_attr}' | placeholder:'{placeholder}' | 可见:{is_visible} | 可编辑:{is_editable}")
            except Exception as e:
                print(f"[{idx}] 无法获取信息: {e}")

        print("\n按任意键继续...")
        input()


if __name__ == "__main__":
    # 调试注册页面
    url = input("输入要调试的 URL (默认: Monica 注册页): ").strip()
    if not url:
        url = "https://monica.im/sign-up?redirectTo=https%3A%2F%2Fmonica.im%2Fhome"

    asyncio.run(debug_page_elements(url))
