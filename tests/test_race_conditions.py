"""CScode 全面测试 - 覆盖异步竞态条件、边界情况、并发场景"""
import asyncio
import json
import time
import uuid
import requests
import sys
from datetime import datetime

BASE_URL = "http://localhost:8000"
TEST_PREFIX = "__TEST__"


class TestResults:
    def __init__(self):
        self.tests = []

    def record(self, name, passed, detail=""):
        self.tests.append({"name": name, "passed": passed, "detail": detail})
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}  {name}")
        if detail and not passed:
            print(f"          {detail}")

    def summary(self):
        total = len(self.tests)
        passed = sum(1 for t in self.tests if t["passed"])
        failed = total - passed
        print(f"\n{'='*60}")
        print(f"测试总览: {passed}/{total} 通过, {failed} 失败")
        print(f"{'='*60}\n")
        if failed > 0:
            print("失败的测试:")
            for t in self.tests:
                if not t["passed"]:
                    print(f"  - {t['name']}: {t['detail']}")
        return failed == 0


def cleanup_test_sessions():
    """清理测试会话"""
    try:
        resp = requests.get(f"{BASE_URL}/api/sessions", timeout=10)
        sessions = resp.json()
        test_sessions = [s for s in sessions if s.get("title", "").startswith(TEST_PREFIX)]
        for s in test_sessions:
            requests.delete(f"{BASE_URL}/api/sessions/{s['id']}", timeout=10)
        return len(test_sessions)
    except Exception:
        return 0


def create_session(title):
    """创建测试会话"""
    resp = requests.post(f"{BASE_URL}/api/sessions", timeout=10)
    data = resp.json()
    sid = data.get("id", data.get("session_id", str(uuid.uuid4())))
    if "id" not in data:
        print(f"  WARNING: session response missing 'id': {data.keys()}")
    return sid, data


def get_messages(session_id):
    """获取会话消息"""
    resp = requests.get(f"{BASE_URL}/api/sessions/{session_id}/messages", timeout=10)
    if resp.status_code == 200:
        return resp.json()
    return None


def delete_session(session_id):
    """删除会话"""
    resp = requests.delete(f"{BASE_URL}/api/sessions/{session_id}", timeout=10)
    return resp.status_code == 200


def list_sessions():
    """列出所有会话"""
    resp = requests.get(f"{BASE_URL}/api/sessions", timeout=10)
    return resp.json()


def send_chat_message(message, session_id=None):
    """发送聊天消息 - 模拟发送第一条消息"""
    body = {"message": message}
    if session_id:
        body["session_id"] = session_id
    resp = requests.post(f"{BASE_URL}/api/chat/stream", json=body, timeout=30, stream=True)
    return resp


def test_api_basic(results):
    """测试1: 基本API健康检查"""
    print("\n[测试1] 基本API健康检查")
    
    try:
        resp = requests.get(f"{BASE_URL}/api/health", timeout=5)
        data = resp.json()
        results.record("/api/health 返回正常", 
                      resp.status_code == 200 and data.get("status") == "ok",
                      f"status={data.get('status')}, version={data.get('version', 'N/A')}")
    except Exception as e:
        results.record("/api/health 可达", False, f"连接失败: {e}")
    
    try:
        resp = requests.get(f"{BASE_URL}/api/sessions", timeout=5)
        results.record("/api/sessions 返回列表",
                      resp.status_code == 200 and isinstance(resp.json(), list),
                      f"status={resp.status_code}, count={len(resp.json()) if resp.status_code == 200 else 'N/A'}")
    except Exception as e:
        results.record("/api/sessions 返回列表", False, f"失败: {e}")
    
    try:
        resp = requests.get(f"{BASE_URL}/api/config", timeout=5)
        data = resp.json()
        results.record("/api/config 返回配置",
                      resp.status_code == 200 and "provider" in data,
                      f"provider={data.get('provider', 'N/A')}")
    except Exception as e:
        results.record("/api/config 返回配置", False, f"失败: {e}")


def test_session_crud(results):
    """测试2: Session CRUD 操作"""
    print("\n[测试2] Session CRUD 操作")
    
    title = f"{TEST_PREFIX}CRUD测试"
    try:
        sid, data = create_session(title)
        results.record("创建Session成功", True, f"id={sid}")
    except Exception as e:
        results.record("创建Session成功", False, f"失败: {e}")
        return
    
    # 列出会话验证
    try:
        sessions = list_sessions()
        exists = any(s.get("id") == sid for s in sessions)
        results.record("新Session出现在列表中", exists,
                      f"total_sessions={len(sessions)}")
    except Exception as e:
        results.record("新Session出现在列表中", False, f"失败: {e}")
    
    # 获取消息（新会话应该是空的）
    try:
        msgs = get_messages(sid)
        results.record("新Session消息列表为空",
                      msgs is not None and len(msgs) == 0,
                      f"messages={len(msgs) if msgs else 'None'}")
    except Exception as e:
        results.record("新Session消息列表为空", False, f"失败: {e}")
    
    # 删除会话
    try:
        deleted = delete_session(sid)
        results.record("删除Session成功", deleted, f"deleted={deleted}")
    except Exception as e:
        results.record("删除Session成功", False, f"失败: {e}")
    
    # 验证删除后不存在
    try:
        sessions_after = list_sessions()
        still_exists = any(s.get("id") == sid for s in sessions_after)
        results.record("删除后Session不在列表中", not still_exists,
                      f"still_exists={still_exists}")
    except Exception as e:
        results.record("删除后Session不在列表中", False, f"失败: {e}")


def test_deleted_session_message_race(results):
    """测试3: 竞态条件 - 选择会话后立即删除（原Bug场景）
    
    模拟: handleSelectSession 启动 -> await api.sessions.messages(id) 等待
           -> 同时 handleDeleteSession 运行 -> 消息应该不被错误恢复
    """
    print("\n[测试3] 竞态条件: 选择会话后立即删除（原Bug场景）")
    
    # 先创建一个测试会话
    try:
        sid, _ = create_session(f"{TEST_PREFIX}RaceTest")
    except Exception as e:
        results.record("创建测试会话", False, f"失败: {e}")
        return
    results.record("创建测试会话", True, f"id={sid}")
    
    # 场景模拟:
    # 1. 前端状态: activeSessionId = sid
    # 2. handleSelectSession 调用: setActiveSession(sid) -> 已同步完成
    # 3. await api.sessions.messages(sid) -> 异步请求
    # 4. 同时用户删除: api.sessions.delete(sid) -> 后端删除
    # 5. messages(sid) resolve -> 检查 activeSessionId === sid
    # 6. 如果删除时 activeSessionId 被清空，则不会 setMessages
    
    try:
        # 模拟: messages请求（应该返回空列表）
        msgs = get_messages(sid)
        results.record("获取会话消息（删除前）",
                      msgs is not None,
                      f"messages={len(msgs) if msgs else 'None'}")
        
        # 删除会话
        deleted = delete_session(sid)
        results.record("删除会话", deleted, f"deleted={deleted}")
        
        # 再次请求已删除会话的消息
        # 后端可能返回 404 或 空列表
        resp = requests.get(f"{BASE_URL}/api/sessions/{sid}/messages", timeout=10)
        results.record("获取已删除会话的消息 - 后端正确处理",
                      resp.status_code in [404, 200],
                      f"status={resp.status_code}, body={resp.text[:100]}")
        
        # 如果返回200且有消息，说明后端可能没有正确清理
        if resp.status_code == 200:
            try:
                msgs_after = resp.json()
                results.record("已删除会话的消息为空或不存在",
                              len(msgs_after) == 0,
                              f"returned {len(msgs_after)} messages - 这可能是后端问题")
            except:
                results.record("已删除会话的消息响应可解析", False, f"JSON解析失败")
        else:
            results.record("已删除会话返回404", True, "正确的错误处理")
        
    except Exception as e:
        results.record("竞态条件测试执行失败", False, f"异常: {e}")


def test_session_switch_race(results):
    """测试4: 竞态条件 - 快速切换多会话
    
    模拟: 用户快速点击 Session A -> Session B -> Session C
    每个 handleSelectSession 都有 await api.sessions.messages(id)
    如果没有检查，可能出现: Session A的消息出现在Session C中
    """
    print("\n[测试4] 竞态条件: 快速切换多会话")
    
    sessions = []
    for i in range(3):
        try:
            sid, _ = create_session(f"{TEST_PREFIX}Switch{i}")
            sessions.append(sid)
        except Exception as e:
            results.record(f"创建会话{i}", False, f"失败: {e}")
            return
    
    results.record(f"创建{len(sessions)}个测试会话", len(sessions) == 3)
    
    # 模拟快速切换 - 连续请求消息
    message_counts = []
    for sid in sessions:
        try:
            msgs = get_messages(sid)
            message_counts.append(len(msgs) if msgs else 0)
        except Exception:
            message_counts.append(-1)
    
    results.record("每个会话都能获取消息",
                  all(c >= 0 for c in message_counts),
                  f"counts={message_counts}")
    
    results.record("新创建的会话消息为空",
                  all(c == 0 for c in message_counts),
                  f"counts={message_counts}")
    
    # 清理
    for sid in sessions:
        try:
            delete_session(sid)
        except Exception:
            pass


def test_concurrent_operations(results):
    """测试5: 并发操作 - 同时请求多个会话消息
    
    模拟多个异步请求同时到达的情况
    """
    print("\n[测试5] 并发操作: 同时请求多个会话消息")
    
    # 创建测试会话
    sessions = []
    for i in range(5):
        try:
            sid, _ = create_session(f"{TEST_PREFIX}Concurrent{i}")
            sessions.append(sid)
        except Exception as e:
            results.record(f"创建会话{i}", False, f"失败: {e}")
            return
    
    results.record(f"创建{len(sessions)}个并发测试会话", len(sessions) == 5)
    
    # 模拟并发请求
    import concurrent.futures
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for sid in sessions:
            future = executor.submit(get_messages, sid)
            futures.append(future)
        
        results_list = []
        for future in concurrent.futures.as_completed(futures):
            try:
                msgs = future.result(timeout=10)
                results_list.append(len(msgs) if msgs is not None else -1)
            except Exception:
                results_list.append(-1)
    
    results.record("所有并发请求成功完成",
                  all(c >= 0 for c in results_list),
                  f"counts={results_list}")
    
    # 清理
    for sid in sessions:
        try:
            delete_session(sid)
        except Exception:
            pass


def test_delete_active_switch_race(results):
    """测试6: 竞态条件 - 删除会话A期间切换到会话B
    
    场景:
    1. activeSessionId = A
    2. handleDeleteSession(A) 启动 -> await api.sessions.delete(A) 等待
    3. 用户点击会话 B -> handleSelectSession(B) 启动
    4. handleSelectSession(B) 完成: activeSessionId = B, messages = B_msgs
    5. delete(A) resolve -> 检查闭包中的 activeSessionId === 'A' -> True (闭包问题!)
    6. setActiveSession(null), setMessages([]) -> B的消息被清空! (BUG)
    """
    print("\n[测试6] 竞态条件: 删除会话期间切换到其他会话")
    print("  检查: handleDeleteSession 是否使用闭包中的 activeSessionId")
    
    # 分析 handleDeleteSession 代码
    # 关键问题: if activeSessionId === id { setActiveSession(null); setMessages([]); }
    # activeSessionId 来自闭包，不是 getState()
    
    # 这个测试主要是代码分析，验证是否存在问题
    code_analyzed = True
    
    # 检查 Sidebar.tsx 第58行: if (activeSessionId === id)
    # activeSessionId 来自 useSessionStore((s) => s.activeSessionId)
    # 每次渲染都重新获取，但 handleDeleteSession 的 useCallback 依赖包含它
    # 所以在删除操作期间如果 activeSessionId 改变，闭包中的值还是旧的
    
    # 检查修复是否存在: 是否用 useSessionStore.getState().activeSessionId ?
    # 从代码看: 第58行是 if (activeSessionId === id) - 使用的是闭包值!
    # 这是潜在问题
    
    # 但实际上，在 handleDeleteSession 中:
    # 用户点击删除 -> confirm -> await delete -> 期间用户可能切换
    # 如果在 await 期间切换，activeSessionId 仍然是旧值（来自闭包）
    # 导致: 删除会话A后，即使当前activeSessionId已经变为B，仍会清空消息
    
    # 模拟这个场景
    try:
        sid_a, _ = create_session(f"{TEST_PREFIX}DelRace_A")
        sid_b, _ = create_session(f"{TEST_PREFIX}DelRace_B")
        
        results.record("创建两个测试会话", True, f"A={sid_a[:8]}..., B={sid_b[:8]}...")
        
        # 给会话A加一条消息（通过发送聊天消息）
        # 发送一条简单消息
        resp = send_chat_message("Hello", session_id=sid_a)
        results.record("给会话A发送消息", 
                      resp.status_code == 200,
                      f"status={resp.status_code}")
        
        # 场景:
        # 1. 当前激活会话 = A
        # 2. 用户删除A -> confirm -> await delete
        # 3. 同时用户点击B -> 切换到B -> setActiveSession(B) -> 获取B的消息
        # 4. delete(A) resolve -> 检查闭包 activeSessionId（仍为A）=== id(A) -> True
        # 5. setActiveSession(null), setMessages([]) -> B的消息被清空 (BUG)
        
        # 代码分析验证:
        # handleDeleteSession 第52-65行:
        #   if (activeSessionId === id) { setActiveSession(null); setMessages([]); }
        # 其中 activeSessionId 来自 useSessionStore((s) => s.activeSessionId)
        # 它在闭包中，异步操作后可能过时
        
        results.record("handleDeleteSession 存在竞态风险",
                      False,  # 标记为失败，提醒需要检查
                      "代码分析: 第58行使用闭包中的 activeSessionId，\n"
                      "          await delete() 期间如果用户切换会话，\n"
                      "          可能错误清空新会话的消息\n"
                      "          建议修复: if (useSessionStore.getState().activeSessionId === id)")
        
        # 清理
        delete_session(sid_a)
        delete_session(sid_b)
        
    except Exception as e:
        results.record("删除竞态条件测试", False, f"异常: {e}")


def test_new_session_race(results):
    """测试7: 竞态条件 - 新建会话期间切换到其他会话
    
    场景:
    1. 用户点击 New Session -> handleNewSession 启动
    2. await api.sessions.create() 等待
    3. 用户点击会话A -> handleSelectSession(A) 完成: activeSessionId=A
    4. create() resolve -> addSession(new) -> setActiveSession(new) -> setMessages([])
    5. 结果: 用户本来想看A，却被切换到新空会话 (迷惑用户)
    """
    print("\n[测试7] 竞态条件: 新建会话期间切换到其他会话")
    
    try:
        # 先创建一个会话A
        sid_a, _ = create_session(f"{TEST_PREFIX}Existing_A")
        results.record("创建已有会话A", True, f"id={sid_a[:8]}...")
        
        # 分析: handleNewSession 第41-50行:
        #   const session = await api.sessions.create();
        #   addSession(session);
        #   setActiveSession(session.id);
        #   setMessages([]);
        # 
        # 问题: 没有检查用户在await期间是否做了其他操作
        # 修复建议: await后检查用户是否还期望新会话
        #   if (useSessionStore.getState().activeSessionId === null) {
        #     setActiveSession(session.id);
        #     setMessages([]);
        #   }
        #   或: 简单标记一个"正在新建"的状态
        
        results.record("handleNewSession 竞态风险（代码分析）",
                      False,
                      "代码分析: handleNewSession await后无条件切换，\n"
                      "          用户在等待期间切换其他会话会被强制切回")
        
        delete_session(sid_a)
        
    except Exception as e:
        results.record("新建会话竞态测试", False, f"异常: {e}")


def test_send_message_race(results):
    """测试8: 竞态条件 - 发送消息期间切换/删除会话
    
    场景:
    1. 用户在会话A发送消息 -> sendMessage 启动
    2. appendMessage(user_message) -> 消息立即显示
    3. await fetch('/api/chat/stream') -> 流式响应
    4. 用户切换到会话B -> activeSessionId = B
    5. 流式响应继续: appendMessage(assistant_content) -> B的消息混入A的响应
    """
    print("\n[测试8] 竞态条件: 发送消息期间切换会话")
    
    # 分析 useChat.ts 第47-175行:
    # - 第61行: appendMessage({role: 'user', ...}) -> 立即添加
    # - 第71-76行: await fetch -> 异步请求
    # - 第89-158行: while循环处理流式响应 -> appendMessage(assistant)
    # 
    # 问题: appendMessage 没有检查当前activeSessionId是否仍为发送时的sessionId
    # 
    # 修复建议:
    #   1. 在 appendMessage assistant 之前检查:
    #      if (useSessionStore.getState().activeSessionId === currentSessionId)
    #   2. 或: 给每条消息附加sessionId，由store过滤
    
    # 实际测试: 发送消息并验证响应
    try:
        sid, _ = create_session(f"{TEST_PREFIX}MsgRace")
        
        # 发送一条简单消息
        resp = send_chat_message("你好，用中文简短回复", session_id=sid)
        results.record("发送消息并获取响应",
                      resp.status_code == 200,
                      f"status={resp.status_code}")
        
        # 读取流式响应
        has_assistant_response = False
        for line in resp.iter_lines():
            line = line.decode('utf-8') if isinstance(line, bytes) else line
            if line.startswith('data: '):
                try:
                    event = json.loads(line[6:])
                    if event.get('type') == 'complete' and event.get('content'):
                        has_assistant_response = True
                        break
                    if event.get('type') == 'session' and event.get('session_id'):
                        pass
                except json.JSONDecodeError:
                    pass
        
        results.record("AI正确响应", has_assistant_response,
                      f"got_response={has_assistant_response}")
        
        # 验证消息列表不为空
        msgs = get_messages(sid)
        results.record("发送后消息列表不为空",
                      msgs is not None and len(msgs) > 0,
                      f"count={len(msgs) if msgs else 'None'}")
        
        results.record("sendMessage 竞态风险（代码分析）",
                      False,
                      "代码分析: 流式响应期间切换会话，assistant消息\n"
                      "          可能被添加到错误的会话中\n"
                      "          建议: appendMessage前检查 activeSessionId")
        
        delete_session(sid)
        
    except Exception as e:
        results.record("消息发送竞态测试", False, f"异常: {e}")


def test_edge_cases(results):
    """测试9: 边界情况"""
    print("\n[测试9] 边界情况")
    
    # 9.1: 空消息
    try:
        resp = send_chat_message("")
        # 空消息可能被拒绝或仍处理
        results.record("发送空消息 - 后端健壮性",
                      resp.status_code in [200, 400],
                      f"status={resp.status_code}")
    except Exception as e:
        results.record("发送空消息", False, f"异常: {e}")
    
    # 9.2: 极长消息
    try:
        long_msg = "测试" * 5000  # 10000字符
        resp = send_chat_message(long_msg)
        results.record("发送长消息 (10K字符)",
                      resp.status_code == 200,
                      f"status={resp.status_code}")
        # 不等待完整响应，只检查是否不会崩溃
        try:
            for i, line in enumerate(resp.iter_lines()):
                if i > 10:  # 只读取前10行
                    break
        except Exception:
            pass
    except Exception as e:
        results.record("发送长消息", False, f"异常: {e}")
    
    # 9.3: 特殊字符消息
    try:
        special_msg = "测试 <script>alert('xss')</script> &quot; &#x27; `rm -rf`"
        resp = send_chat_message(special_msg)
        results.record("发送特殊字符消息",
                      resp.status_code == 200,
                      f"status={resp.status_code}")
        try:
            for i, line in enumerate(resp.iter_lines()):
                if i > 10:
                    break
        except Exception:
            pass
    except Exception as e:
        results.record("发送特殊字符消息", False, f"异常: {e}")
    
    # 9.4: 获取不存在会话的消息
    try:
        fake_id = str(uuid.uuid4())
        resp = requests.get(f"{BASE_URL}/api/sessions/{fake_id}/messages", timeout=5)
        results.record("获取不存在会话的消息",
                      resp.status_code in [404, 200],
                      f"status={resp.status_code}")
    except Exception as e:
        results.record("获取不存在会话的消息", False, f"异常: {e}")
    
    # 9.5: 删除不存在的会话
    try:
        fake_id = str(uuid.uuid4())
        resp = requests.delete(f"{BASE_URL}/api/sessions/{fake_id}", timeout=5)
        results.record("删除不存在的会话",
                      resp.status_code in [404, 200],
                      f"status={resp.status_code}")
    except Exception as e:
        results.record("删除不存在的会话", False, f"异常: {e}")


def test_files_search(results):
    """测试10: 文件搜索API（@mention功能）"""
    print("\n[测试10] 文件搜索API（@mention功能）")
    
    try:
        resp = requests.get(f"{BASE_URL}/api/files/search?q=test", timeout=5)
        results.record("/api/files/search 基本搜索",
                      resp.status_code == 200 and isinstance(resp.json(), list),
                      f"status={resp.status_code}, count={len(resp.json()) if resp.status_code == 200 else 'N/A'}")
    except Exception as e:
        results.record("/api/files/search 基本搜索", False, f"异常: {e}")
    
    # 空搜索词
    try:
        resp = requests.get(f"{BASE_URL}/api/files/search?q=", timeout=5)
        results.record("/api/files/search 空搜索词",
                      resp.status_code == 200,
                      f"status={resp.status_code}")
    except Exception as e:
        results.record("/api/files/search 空搜索词", False, f"异常: {e}")
    
    # 无搜索参数
    try:
        resp = requests.get(f"{BASE_URL}/api/files/search", timeout=5)
        results.record("/api/files/search 无参数",
                      resp.status_code == 200,
                      f"status={resp.status_code}")
    except Exception as e:
        results.record("/api/files/search 无参数", False, f"异常: {e}")


def main():
    print(f"{'='*60}")
    print(f"CScode 全面测试 - 启动时间: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}")
    
    # 检查服务器是否运行
    try:
        resp = requests.get(f"{BASE_URL}/api/health", timeout=3)
        if resp.status_code != 200:
            print(f"ERROR: 服务器返回 {resp.status_code}")
            sys.exit(1)
        print(f"服务器健康检查通过: {resp.json()}")
    except Exception as e:
        print(f"ERROR: 无法连接到 {BASE_URL} - {e}")
        print("请先启动后端服务器: python -m uvicorn cscode.server.app:app --port 8000")
        sys.exit(1)
    
    # 清理之前的测试数据
    cleaned = cleanup_test_sessions()
    if cleaned > 0:
        print(f"\n清理了 {cleaned} 个旧的测试会话")
    
    results = TestResults()
    
    # 运行测试
    test_api_basic(results)
    test_session_crud(results)
    test_deleted_session_message_race(results)
    test_session_switch_race(results)
    test_concurrent_operations(results)
    test_delete_active_switch_race(results)
    test_new_session_race(results)
    test_send_message_race(results)
    test_edge_cases(results)
    test_files_search(results)
    
    # 最终清理
    final_cleaned = cleanup_test_sessions()
    if final_cleaned > 0:
        print(f"\n清理了 {final_cleaned} 个测试会话")
    
    # 输出总结
    all_passed = results.summary()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
