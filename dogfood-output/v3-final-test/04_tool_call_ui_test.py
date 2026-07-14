#!/usr/bin/env python3
"""
工具调用 UI 专项测试
验证 AI 调用工具（如 read、bash）时前端是否有专门的显示组件
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path("/Users/mac/AI/CScode/dogfood-output/v3-final-test")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=50)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        console_logs = []
        page.on("console", lambda msg: console_logs.append({
            "type": msg.type, "text": msg.text, "time": datetime.now().isoformat()
        }))

        await page.goto("http://localhost:8000", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # 创建新 session
        new_btn = page.locator('button[aria-label="Create new session"]')
        await new_btn.click()
        await page.wait_for_timeout(800)

        print("=== 测试工具调用 UI ===")
        print()

        # 发送一个会触发工具调用的消息
        # 要求 AI 读取一个文件，这应该触发 read 工具
        textarea = page.locator('textarea[placeholder*="Ask anything"]')
        
        test_msg = "请读取 /Users/mac/AI/CScode/src/cscode/__init__.py 文件，告诉我里面的版本号是什么？"
        
        await textarea.fill(test_msg)
        await textarea.press("Enter")
        
        print(f"发送消息: {test_msg}")
        print("等待 AI 响应和工具调用...")
        
        # 等待足够长时间让 AI 完成工具调用
        await page.wait_for_timeout(30000)

        await page.screenshot(path=str(OUTPUT_DIR / "tool_call_ui.png"), full_page=True)

        # 分析页面内容，查找工具调用相关的 UI 元素
        tool_ui_analysis = await page.evaluate('''() => {
            // 查找可能的工具调用 UI 元素
            const possibleSelectors = [
                '[class*="tool"]',
                '[class*="Tool"]',
                '[data-tool]',
                '[class*="bash"]',
                '[class*="read"]',
                '[class*="command"]',
                '[class*="Command"]',
                '[class*="execution"]',
                '[class*="Execution"]',
                'pre',
                'code',
                '.tool-result',
                '.tool-call',
                '.tool-output',
                '.step',
                '.Step',
            ];
            
            let found = {};
            for (const sel of possibleSelectors) {
                const elements = document.querySelectorAll(sel);
                if (elements.length > 0) {
                    found[sel] = {
                        count: elements.length,
                        samples: Array.from(elements).slice(0, 3).map(e => ({
                            tag: e.tagName,
                            class: e.className.slice(0, 80),
                            text: e.innerText.slice(0, 100)
                        }))
                    };
                }
            }
            
            // 查找消息中的特殊元素
            const messages = document.querySelectorAll('[role="list"] > div, .message, [class*="Message"]');
            let messageAnalysis = [];
            for (const msg of messages) {
                const hasPre = msg.querySelectorAll('pre').length > 0;
                const hasCode = msg.querySelectorAll('code').length > 0;
                const text = msg.innerText.slice(0, 200);
                messageAnalysis.push({
                    hasPre,
                    hasCode,
                    textPreview: text
                });
            }
            
            return {
                toolElements: found,
                messageCount: messages.length,
                messageAnalysis
            };
        }''')

        print("=== 工具调用 UI 分析结果 ===")
        print()
        
        if tool_ui_analysis['toolElements']:
            print("找到以下工具相关元素:")
            for sel, info in tool_ui_analysis['toolElements'].items():
                print(f"  {sel}: {info['count']} 个")
                for sample in info['samples']:
                    print(f"    - {sample['tag']} class='{sample['class']}' text='{sample['text'][:50]}'")
        else:
            print("❌ 未找到任何工具调用相关的 UI 元素")
        
        print()
        print(f"消息数量: {tool_ui_analysis['messageCount']}")
        
        for i, msg in enumerate(tool_ui_analysis['messageAnalysis']):
            print(f"  消息 {i+1}: hasPre={msg['hasPre']}, hasCode={msg['hasCode']}")
            print(f"    内容预览: {msg['textPreview'][:80]}")

        # 检查 console 日志中的工具调用记录
        print()
        print("=== Console 日志中的工具调用记录 ===")
        
        tool_logs = [l for l in console_logs if any(kw in l['text'].lower() for kw in ['tool', 'read', 'bash', 'call', 'execute'])]
        for l in tool_logs[:10]:
            print(f"  [{l['type']}] {l['text'][:120]}")

        # 检查是否有版本号被正确读取
        content = await page.content()
        has_version = "0.3" in content or "__version__" in content
        
        print()
        print("=== 验证结果 ===")
        if has_version:
            print("✅ AI 成功读取了文件并返回了版本号信息")
        else:
            print("❌ 未检测到版本号信息，可能工具调用未成功或 LLM 未连接")

        # 分析是否有专门的工具调用 UI
        has_tool_ui = bool(tool_ui_analysis['toolElements'])
        if has_tool_ui:
            print("✅ 存在工具调用相关的 UI 元素")
        else:
            print("⚠️ 未发现专门的工具调用 UI 元素（可能使用普通消息样式）")

        await browser.close()

        # 保存分析结果
        report = {
            "timestamp": datetime.now().isoformat(),
            "tool_ui_analysis": tool_ui_analysis,
            "has_version_in_response": has_version,
            "has_tool_ui_elements": has_tool_ui,
            "console_logs": console_logs[-100:]
        }
        
        with open(OUTPUT_DIR / "tool_call_ui_analysis.json", "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print()
        print(f"📁 分析结果保存到: {OUTPUT_DIR / 'tool_call_ui_analysis.json'}")


if __name__ == "__main__":
    asyncio.run(main())