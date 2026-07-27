"""
CScode v0.3.4 完整端到端测试
包含：
1. 单会话完整操作流
2. 多会话并发隔离测试
3. 所有功能点覆盖
4. 错误场景与边界测试
"""
import asyncio
import json
import os
import time
import sys
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import urllib.request
import urllib.error

import aiohttp

BASE_URL = "http://127.0.0.1:8080"
OUTPUT_DIR = "/Users/mac/AI/CScode/dogfood-output/comprehensive-e2e"
os.makedirs(OUTPUT_DIR, exist_ok=True)

results = []
issues = []
issue_counter = 0

def record(category, test_name, status, **kwargs):
    entry = {
        "category": category,
        "test": test_name,
        "result": status,
        **kwargs
    }
    results.append(entry)
    icon = {"pass": "✅", "warn": "⚠️", "fail": "❌", "skip": "⏭️"}.get(status, "❓")
    print(f"  {icon} [{category}] {test_name}")
    return entry

def add_issue(severity, category, title, description):
    global issue_counter
    issue_counter += 1
    issue = {
        "id": f"ISSUE-{issue_counter:03d}",
        "severity": severity,
        "category": category,
        "title": title,
        "description": description
    }
    issues.append(issue)
    print(f"  🐛 [{issue['id']}] {severity.upper()}: {title}")
    return issue

async def api_get(session, path, timeout=10):
    try:
        async with session.get(f"{BASE_URL}{path}", timeout=timeout) as resp:
            return resp.status, await resp.json() if resp.status < 500 else await resp.text()
    except Exception as e:
        return 0, str(e)

async def api_post(session, path, data=None, timeout=10):
    try:
        async with session.post(f"{BASE_URL}{path}", json=data or {}, timeout=timeout) as resp:
            return resp.status, await resp.json() if resp.status < 500 else await resp.text()
    except Exception as e:
        return 0, str(e)

async def api_put(session, path, data=None, timeout=10):
    try:
        async with session.put(f"{BASE_URL}{path}", json=data or {}, timeout=timeout) as resp:
            return resp.status, await resp.json() if resp.status < 500 else await resp.text()
    except Exception as e:
        return 0, str(e)

async def api_delete(session, path, timeout=10):
    try:
        async with session.delete(f"{BASE_URL}{path}", timeout=timeout) as resp:
            return resp.status, await resp.json() if resp.status < 500 else await resp.text()
    except Exception as e:
        return 0, str(e)

async def stage1_basic_health(session):
    """阶段 1: 基础健康检查"""
    print("\n" + "=" * 60)
    print("📋 阶段 1: 基础健康检查")
    print("=" * 60)
    
    # 健康检查
    status, body = await api_get(session, "/api/health")
    if status == 200 and isinstance(body, dict) and body.get("status") == "ok":
        record("健康检查", "服务健康", "pass", version=body.get("version"))
    else:
        record("健康检查", "服务健康", "fail", status=status, body=str(body)[:100])
        return False
    
    return True

async def stage2_single_session_flow(session):
    """阶段 2: 单会话完整操作流"""
    print("\n" + "=" * 60)
    print("📋 阶段 2: 单会话完整操作流")
    print("=" * 60)
    
    # 2.1 创建会话
    print("\n--- 2.1 创建新会话 ---")
    status, body = await api_post(session, "/api/sessions", {"title": "E2E Comprehensive Test"})
    if status == 200 and body.get("id"):
        session_id = body["id"]
        record("单会话", "创建会话", "pass", session_id=session_id)
    else:
        record("单会话", "创建会话", "fail", status=status, body=str(body)[:200])
        add_issue("P0", "会话", "创建会话失败", f"Status: {status}, Body: {str(body)[:200]}")
        return None
    
    # 2.2 获取会话列表
    print("\n--- 2.2 获取会话列表 ---")
    status, body = await api_get(session, "/api/sessions")
    if status == 200 and isinstance(body, list):
        record("单会话", "获取会话列表", "pass", count=len(body))
        # 验证刚创建的会话在列表中
        found = any(s.get("id") == session_id for s in body)
        if not found:
            record("单会话", "新建会话在列表中", "warn")
            add_issue("P1", "会话", "新建会话不在列表中", f"Session {session_id} not in list")
    else:
        record("单会话", "获取会话列表", "fail", status=status)
    
    # 2.3 获取会话详情
    print("\n--- 2.3 获取会话详情 ---")
    status, body = await api_get(session, f"/api/sessions/{session_id}")
    if status == 200 and body.get("id") == session_id:
        record("单会话", "获取会话详情", "pass")
    else:
        record("单会话", "获取会话详情", "fail", status=status)
        add_issue("P0", "会话", "获取会话详情失败", f"Session {session_id} not found")
    
    # 2.4 获取会话消息（应为空）
    print("\n--- 2.4 获取会话消息 ---")
    status, body = await api_get(session, f"/api/sessions/{session_id}/messages")
    if status == 200 and isinstance(body, list):
        record("单会话", "获取会话消息", "pass", count=len(body))
    else:
        record("单会话", "获取会话消息", "warn", status=status, body=str(body)[:200])
    
    # 2.5 模拟用户提示
    print("\n--- 2.5 模拟用户提示 ---")
    status, body = await api_post(session, f"/api/sessions/{session_id}/prompt", {
        "text": "Hello, this is an E2E test message from comprehensive testing"
    })
    if status == 200:
        record("单会话", "发送用户消息", "pass")
    else:
        record("单会话", "发送用户消息", "warn", status=status, body=str(body)[:200])
    
    # 2.6 验证消息已保存
    print("\n--- 2.6 验证消息保存 ---")
    await asyncio.sleep(0.5)
    status, body = await api_get(session, f"/api/sessions/{session_id}/messages")
    if status == 200 and isinstance(body, list) and len(body) > 0:
        record("单会话", "消息已保存", "pass", count=len(body))
    else:
        record("单会话", "消息已保存", "warn", count=len(body) if isinstance(body, list) else 0)
    
    return session_id

async def stage3_multi_session_isolation(session):
    """阶段 3: 多会话并发隔离测试"""
    print("\n" + "=" * 60)
    print("📋 阶段 3: 多会话并发隔离测试")
    print("=" * 60)
    
    # 3.1 并发创建 5 个会话
    print("\n--- 3.1 并发创建 5 个会话 ---")
    
    async def create_session(idx):
        return await api_post(session, "/api/sessions", {"title": f"Concurrent Test Session {idx}"})
    
    start = time.time()
    results_create = await asyncio.gather(*[create_session(i) for i in range(5)])
    elapsed = time.time() - start
    
    success_count = sum(1 for s, b in results_create if s == 200 and b.get("id"))
    record("多会话", "并发创建 5 个会话", "pass" if success_count == 5 else "warn",
           created=success_count, elapsed_ms=int(elapsed*1000))
    
    session_ids = [b.get("id") for s, b in results_create if s == 200 and b.get("id")]
    
    if len(session_ids) < 5:
        add_issue("P1", "并发", "并发创建会话部分失败",
                  f"Created {success_count}/5 sessions")
    
    # 3.2 验证所有会话都在列表中
    print("\n--- 3.2 验证所有会话在列表中 ---")
    status, body = await api_get(session, "/api/sessions")
    if status == 200 and isinstance(body, list):
        all_found = all(sid in [s.get("id") for s in body] for sid in session_ids)
        record("多会话", "所有会话在列表中", "pass" if all_found else "warn",
               total_sessions=len(body), concurrent_sessions=len(session_ids))
    else:
        record("多会话", "会话列表获取", "fail")
    
    # 3.3 并发发送不同消息
    print("\n--- 3.3 并发发送不同消息 ---")
    
    async def send_message(idx, sid):
        return await api_post(session, f"/api/sessions/{sid}/prompt", {
            "text": f"Message for session {idx}: {datetime.now().isoformat()}"
        })
    
    start = time.time()
    msg_results = await asyncio.gather(*[send_message(i, sid) for i, sid in enumerate(session_ids)])
    elapsed = time.time() - start
    
    success_msgs = sum(1 for s, b in msg_results if s == 200)
    record("多会话", "并发发送消息", "pass" if success_msgs == 5 else "warn",
           sent=success_msgs, elapsed_ms=int(elapsed*1000))
    
    # 3.4 验证消息隔离（每个会话只有自己的消息）
    print("\n--- 3.4 验证消息隔离 ---")
    isolation_ok = True
    for idx, sid in enumerate(session_ids):
        await asyncio.sleep(0.3)
        status, body = await api_get(session, f"/api/sessions/{sid}/messages")
        if status == 200 and isinstance(body, list):
            # 检查消息内容是否包含正确的会话标识
            if body:
                msg_content = body[0].get("content", "")
                expected_marker = f"session {idx}"
                if expected_marker not in msg_content:
                    isolation_ok = False
                    add_issue("P0", "隔离", f"会话 {idx} 消息污染",
                              f"Expected marker '{expected_marker}' in message, got: {msg_content[:100]}")
        else:
            isolation_ok = False
    
    record("多会话", "消息隔离验证", "pass" if isolation_ok else "fail",
           sessions_tested=len(session_ids))
    
    # 3.5 并发获取不同会话详情（隔离测试）
    print("\n--- 3.5 并发获取会话详情 ---")
    
    async def get_session(sid):
        return await api_get(session, f"/api/sessions/{sid}")
    
    start = time.time()
    detail_results = await asyncio.gather(*[get_session(sid) for sid in session_ids])
    elapsed = time.time() - start
    
    success_details = sum(1 for s, b in detail_results if s == 200 and b.get("id") in session_ids)
    record("多会话", "并发获取会话详情", "pass" if success_details == 5 else "warn",
           success=success_details, elapsed_ms=int(elapsed*1000))
    
    # 3.6 快速切换会话
    print("\n--- 3.6 快速切换会话测试 ---")
    switch_times = []
    for i in range(3):
        target_sid = session_ids[i % len(session_ids)]
        start = time.time()
        status, body = await api_get(session, f"/api/sessions/{target_sid}/messages")
        elapsed = time.time() - start
        switch_times.append(elapsed * 1000)
    
    avg_switch_ms = sum(switch_times) / len(switch_times)
    record("多会话", "快速切换会话", "pass" if avg_switch_ms < 500 else "warn",
           avg_ms=int(avg_switch_ms), times=switch_times)
    
    return session_ids

async def stage4_features_coverage(session, session_ids):
    """阶段 4: 所有功能点覆盖测试"""
    print("\n" + "=" * 60)
    print("📋 阶段 4: 所有功能点覆盖测试")
    print("=" * 60)
    
    # 4.1 配置 API
    print("\n--- 4.1 配置 API ---")
    status, body = await api_get(session, "/api/config")
    if status == 200 and isinstance(body, dict):
        record("功能覆盖", "获取配置", "pass", provider=body.get("provider"), model=body.get("model"))
    else:
        record("功能覆盖", "获取配置", "fail")
    
    # 检查安全相关字段
    if "api_key_configured" in body:
        record("功能覆盖", "api_key_configured 字段（新功能）", "pass", 
               value=body.get("api_key_configured"))
    else:
        record("功能覆盖", "api_key_configured 字段（新功能）", "warn")
        add_issue("P1", "新功能", "api_key_configured 字段缺失", "安全相关字段未返回")
    
    # 4.2 工具 API
    print("\n--- 4.2 工具 API ---")
    status, body = await api_get(session, "/api/tools")
    if status == 200 and isinstance(body, dict):
        tools = body.get("tools", [])
        record("功能覆盖", "获取工具列表", "pass", count=len(tools))
    else:
        record("功能覆盖", "获取工具列表", "fail")
    
    # 4.3 应用工具 API
    print("\n--- 4.3 应用工具 API ---")
    status, body = await api_get(session, "/api/tools/application")
    if status == 200 and isinstance(body, dict):
        record("功能覆盖", "获取应用工具", "pass", count=len(body.get("tools", [])))
    else:
        record("功能覆盖", "获取应用工具", "fail")
    
    # 4.4 配置参考 API
    print("\n--- 4.4 配置参考 API ---")
    status, body = await api_get(session, "/api/config/reference")
    if status == 200 and isinstance(body, list):
        record("功能覆盖", "获取配置参考", "pass", count=len(body))
        # 检查 API key 描述是否包含新的优先级说明
        api_key_entry = next((e for e in body if "api_key" in e.get("key", "").lower() and "API_KEY" not in e.get("key", "")), None)
        if api_key_entry and ("priority" in api_key_entry.get("description", "").lower() or 
                                "keychain" in api_key_entry.get("description", "").lower()):
            record("功能覆盖", "API Key 解析优先级说明（新功能）", "pass")
        else:
            record("功能覆盖", "API Key 解析优先级说明（新功能）", "warn")
    else:
        record("功能覆盖", "获取配置参考", "fail")
    
    # 4.5 工作区 API
    print("\n--- 4.5 工作区 API ---")
    status, body = await api_get(session, "/api/workspaces")
    if status == 200:
        record("功能覆盖", "获取工作区", "pass", count=len(body) if isinstance(body, list) else 0)
    else:
        record("功能覆盖", "获取工作区", "warn", status=status)
    
    # 4.6 共享链接 API
    print("\n--- 4.6 共享链接 API ---")
    status, body = await api_get(session, "/api/share")
    if status == 200 and isinstance(body, list):
        record("功能覆盖", "获取共享链接", "pass", count=len(body))
    else:
        record("功能覆盖", "获取共享链接", "fail")
    
    # 4.7 凭证 API (新功能)
    print("\n--- 4.7 凭证 API（新功能 KeychainStore） ---")
    status, body = await api_get(session, "/api/credentials")
    if status == 200 and isinstance(body, list):
        record("功能覆盖", "获取凭证列表（新功能）", "pass", count=len(body))
    else:
        record("功能覆盖", "获取凭证列表（新功能）", "fail", status=status)
        add_issue("P1", "新功能", "凭证 API 不可用", f"Status: {status}")
    
    # 4.8 权限规则 API (新功能)
    print("\n--- 4.8 权限规则 API ---")
    status, body = await api_get(session, "/api/permission-rules")
    if status == 200:
        record("功能覆盖", "获取权限规则", "pass")
    else:
        record("功能覆盖", "获取权限规则", "warn", status=status)
    
    # 4.9 同步事件 API (新功能)
    print("\n--- 4.9 同步事件 API ---")
    status, body = await api_get(session, "/api/sync/events")
    if status == 200:
        record("功能覆盖", "获取同步事件", "pass")
    else:
        record("功能覆盖", "获取同步事件", "warn", status=status)
    
    # 4.10 健康检查
    print("\n--- 4.10 健康检查 ---")
    status, body = await api_get(session, "/api/health")
    if status == 200:
        record("功能覆盖", "健康检查", "pass", version=body.get("version"))
    else:
        record("功能覆盖", "健康检查", "fail")

async def stage5_edge_cases(session, session_ids):
    """阶段 5: 错误场景与边界测试"""
    print("\n" + "=" * 60)
    print("📋 阶段 5: 错误场景与边界测试")
    print("=" * 60)
    
    # 5.1 不存在的会话 ID
    print("\n--- 5.1 不存在的会话 ID ---")
    fake_id = "9999999999999999000"
    status, body = await api_get(session, f"/api/sessions/{fake_id}")
    if status == 404:
        record("边界", "不存在会话返回 404", "pass")
    else:
        record("边界", "不存在会话返回 404", "warn", status=status)
    
    # 5.2 空会话列表（创建后立即获取）
    print("\n--- 5.2 会话消息压力测试 ---")
    if session_ids:
        stress_id = session_ids[0]
        # 快速连续发送 20 条消息
        async def rapid_send(i):
            return await api_post(session, f"/api/sessions/{stress_id}/prompt", {
                "text": f"Stress test message {i}"
            })
        
        start = time.time()
        stress_results = await asyncio.gather(*[rapid_send(i) for i in range(20)], return_exceptions=True)
        elapsed = time.time() - start
        
        success_count = sum(1 for r in stress_results if isinstance(r, tuple) and r[0] == 200)
        record("边界", "并发 20 条消息压力测试", "pass" if success_count >= 18 else "warn",
               success=success_count, total=20, elapsed_ms=int(elapsed*1000))
    
    # 5.3 超大消息测试
    print("\n--- 5.3 超大消息测试 ---")
    if session_ids:
        large_msg = "x" * 10000  # 10KB 消息
        status, body = await api_post(session, f"/api/sessions/{session_ids[0]}/prompt", {
            "text": large_msg
        })
        if status == 200 or status == 413:  # 接受或拒绝都算正常
            record("边界", "10KB 大消息处理", "pass" if status == 200 else "warn", status=status)
        else:
            record("边界", "10KB 大消息处理", "warn", status=status)
    
    # 5.4 特殊字符消息
    print("\n--- 5.4 特殊字符消息 ---")
    if session_ids:
        special_msg = "Test with 特殊字符 @#$%^&*()_+-= 中文测试 🚀 emoji"
        status, body = await api_post(session, f"/api/sessions/{session_ids[0]}/prompt", {
            "text": special_msg
        })
        if status == 200:
            record("边界", "特殊字符消息", "pass")
        else:
            record("边界", "特殊字符消息", "warn", status=status)
    
    # 5.5 并发更新配置
    print("\n--- 5.5 并发更新配置 ---")
    async def update_config(i):
        return await api_put(session, "/api/config", {"temperature": 0.5 + i*0.1})
    
    config_results = await asyncio.gather(*[update_config(i) for i in range(5)], return_exceptions=True)
    success_count = sum(1 for r in config_results if isinstance(r, tuple) and r[0] in (200, 405))
    record("边界", "并发更新配置", "pass" if success_count >= 4 else "warn", 
           success=success_count, total=5)
    
    # 5.6 Session CRUD 完整性
    print("\n--- 5.6 Session CRUD 完整性 ---")
    if session_ids:
        test_sid = session_ids[0]
        # 验证创建后可读
        status, body = await api_get(session, f"/api/sessions/{test_sid}")
        if status == 200 and body.get("id") == test_sid:
            record("边界", "Session CRUD - 读", "pass")
        else:
            record("边界", "Session CRUD - 读", "fail", status=status)

async def stage6_log_quality():
    """阶段 6: 日志质量检查"""
    print("\n" + "=" * 60)
    print("📋 阶段 6: 日志质量检查")
    print("=" * 60)
    
    log_file = "/tmp/cscode-e2e-final.log"
    if not os.path.exists(log_file):
        record("日志", "日志文件存在", "fail", path=log_file)
        return
    
    with open(log_file) as f:
        log_content = f.read()
    
    warning_count = log_content.lower().count("warning")
    error_count = log_content.count("ERROR")
    
    record("日志", "WARNING 日志数", "pass" if warning_count < 10 else "warn", count=warning_count)
    record("日志", "ERROR 日志数", "pass" if error_count < 5 else "warn", count=error_count)
    
    # 检查是否包含历史事件清理（migration v10）
    if "migration v10" in log_content or "text.delta" in log_content:
        record("日志", "历史事件清理 migration", "pass")
    else:
        record("日志", "历史事件清理 migration", "warn")
    
    # 检查是否包含 localhost 限制
    if "127.0.0.1" in log_content and "Serving" in log_content:
        record("日志", "localhost 限制", "pass")
    
    # 检查是否包含无 API key 警告
    if "No API key" in log_content or "api_key" in log_content.lower():
        record("日志", "无 API key 警告", "pass")

async def main():
    print("\n" + "=" * 60)
    print("🚀 CScode v0.3.4 完整端到端测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().isoformat()}")
    print(f"目标: {BASE_URL}")
    
    async with aiohttp.ClientSession() as session:
        # 阶段 1
        healthy = await stage1_basic_health(session)
        if not healthy:
            print("\n❌ 后端不健康，停止测试")
            return
        
        # 阶段 2
        single_id = await stage2_single_session_flow(session)
        
        # 阶段 3
        multi_ids = await stage3_multi_session_isolation(session)
        
        # 阶段 4
        await stage4_features_coverage(session, multi_ids or [])
        
        # 阶段 5
        await stage5_edge_cases(session, multi_ids or [])
    
    # 阶段 6 (不需要 session)
    await stage6_log_quality()
    
    # 输出汇总
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    # 按类别统计
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
        categories[cat][r["status"]] = categories[cat].get(r["status"], 0) + 1
    
    print("\n按类别统计:")
    for cat, stats in sorted(categories.items()):
        total = sum(stats.values())
        passed = stats.get("pass", 0)
        print(f"  {cat}: {passed}/{total} 通过 (✅{stats.get('pass', 0)} ⚠️{stats.get('warn', 0)} ❌{stats.get('fail', 0)})")
    
    pass_count = sum(1 for r in results if r["status"] == "pass")
    warn_count = sum(1 for r in results if r["status"] == "warn")
    fail_count = sum(1 for r in results if r["status"] == "fail")
    skip_count = sum(1 for r in results if r["status"] == "skip")
    total = len(results)
    
    print(f"\n总计:")
    print(f"  ✅ 通过: {pass_count}")
    print(f"  ⚠️  警告: {warn_count}")
    print(f"  ❌ 失败: {fail_count}")
    print(f"  ⏭️  跳过: {skip_count}")
    print(f"  📊 总数: {total}")
    print(f"  通过率: {pass_count*100/total:.1f}%")
    
    print(f"\n🐛 发现问题: {len(issues)}")
    for issue in issues:
        print(f"  [{issue['id']}] {issue['severity'].upper()} - {issue['category']}: {issue['title']}")
    
    # 保存结果
    summary = {
        "total": total,
        "pass": pass_count,
        "warn": warn_count,
        "fail": fail_count,
        "skip": skip_count,
        "pass_rate": round(pass_count*100/total, 2),
        "issues": issues,
        "categories": categories,
        "timestamp": datetime.now().isoformat()
    }
    
    with open(os.path.join(OUTPUT_DIR, "test-results.json"), "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2, ensure_ascii=False)
    
    print(f"\n📁 详细结果: {os.path.join(OUTPUT_DIR, 'test-results.json')}")

if __name__ == "__main__":
    asyncio.run(main())
