#!/usr/bin/env python3
"""EVOcoder 五轮快速测试"""
import sys, os, shutil
os.environ['PYTHONIOENCODING'] = 'utf-8'
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace', buffering=1)
sys.path.insert(0, '.')

print('='*60)
print('EVOcoder 五轮快速测试')
print('='*60)

passed = 0
failed = 0

def test(name, ok, detail=''):
    global passed, failed
    if ok:
        passed += 1
        print(f'  [PASS] {name}' + (f' - {detail}' if detail else ''))
    else:
        failed += 1
        print(f'  [FAIL] {name}' + (f' - {detail}' if detail else ''))

# === 第一轮：基础导入 ===
print('\n--- 第一轮：基础导入 ---')
try:
    from agent import EvoCoder, load_config
    test('agent导入', True)
except Exception as e:
    test('agent导入', False, str(e))
try:
    from brain.engine import Brain, TokenCache
    test('brain导入', True)
except Exception as e:
    test('brain导入', False, str(e))
try:
    from tools.registry import ToolRegistry
    from tools.builtin import register_builtins
    test('tools导入', True)
except Exception as e:
    test('tools导入', False, str(e))
try:
    from memory.store import MemoryStore
    from memory.long_term import LongTermMemory
    test('memory导入', True)
except Exception as e:
    test('memory导入', False, str(e))
try:
    from evolution.tracker import EvolutionTracker, TaskStatus
    test('tracker导入', True)
except Exception as e:
    test('tracker导入', False, str(e))
try:
    from evolution.error_memory import ErrorMemory
    test('error_memory导入', True)
except Exception as e:
    test('error_memory导入', False, str(e))
try:
    from evolution.user_prefs import UserPreferences
    test('user_prefs导入', True)
except Exception as e:
    test('user_prefs导入', False, str(e))
try:
    from evolution.strategy_memory import StrategyMemory
    test('strategy_memory导入', True)
except Exception as e:
    test('strategy_memory导入', False, str(e))
try:
    from evolution.prompt_evolver import PromptEvolver
    test('prompt_evolver导入', True)
except Exception as e:
    test('prompt_evolver导入', False, str(e))
try:
    from evolution.tool_evolver import ToolEvolver
    test('tool_evolver导入', True)
except Exception as e:
    test('tool_evolver导入', False, str(e))
try:
    from subagents.manager import SubAgentManager, AgentType
    test('subagents导入', True)
except Exception as e:
    test('subagents导入', False, str(e))
try:
    config = load_config()
    test('配置加载', True, str(list(config.keys())))
except Exception as e:
    test('配置加载', False, str(e))

# === 第二轮：工具系统 ===
print('\n--- 第二轮：工具系统 ---')
try:
    reg = ToolRegistry()
    register_builtins(reg)
    test('工具注册', True, f'{len(reg)}个工具')
except Exception as e:
    test('工具注册', False, str(e))
try:
    result = reg.execute('read_file', path='config.json')
    test('read_file', 'api' in result)
except Exception as e:
    test('read_file', False, str(e))
try:
    result = reg.execute('write_file', path='/tmp/_evo_test.txt', content='hello')
    test('write_file', 'OK' in result)
except Exception as e:
    test('write_file', False, str(e))
try:
    result = reg.execute('list_directory', path='.')
    test('list_directory', 'agent.py' in result)
except Exception as e:
    test('list_directory', False, str(e))
try:
    result = reg.execute('run_command', command='echo hello')
    test('run_command', 'hello' in result)
except Exception as e:
    test('run_command', False, str(e))
try:
    result = reg.execute('search_code', pattern='def run', path='.', glob='*.py')
    test('search_code', len(result) > 0)
except Exception as e:
    test('search_code', False, str(e))

# === 第三轮：记忆系统 ===
print('\n--- 第三轮：记忆系统 ---')
test_dir = '/tmp/_evo_test_memory'
if os.path.exists(test_dir):
    shutil.rmtree(test_dir)

try:
    store = MemoryStore(test_dir, enable_vectors=False)
    test('MemoryStore初始化', True)
except Exception as e:
    test('MemoryStore初始化', False, str(e))
try:
    store.add_conversation('user', 'hello')
    store.add_conversation('assistant', 'hi!')
    msgs = store.get_recent_conversation(n=2)
    test('会话记忆', len(msgs) == 2 and msgs[0]['role'] == 'user')
except Exception as e:
    test('会话记忆', False, str(e))
try:
    entry = store.record_experience(task='test task', category='general', outcome='success', tags=['test'])
    test('经验记录', entry['id'] is not None)
except Exception as e:
    test('经验记录', False, str(e))
try:
    similar = store.get_similar_experiences('test', top_k=1)
    test('经验检索', len(similar) > 0)
except Exception as e:
    test('经验检索', False, str(e))
try:
    stats = store.get_experience_stats()
    test('经验统计', stats['total'] > 0, f"total={stats['total']}")
except Exception as e:
    test('经验统计', False, str(e))
try:
    ltm = LongTermMemory(test_dir + '/ltm')
    user = ltm.update_user(name='TestUser', tags=['python', 'ai'])
    test('用户档案', user['name'] == 'TestUser')
except Exception as e:
    test('用户档案', False, str(e))
try:
    session = ltm.add_session(summary='test session', tags=['test'])
    test('会话记录', session['session_id'] is not None)
except Exception as e:
    test('会话记录', False, str(e))
try:
    context = ltm.get_context()
    test('上下文生成', 'TestUser' in context)
except Exception as e:
    test('上下文生成', False, str(e))
try:
    store2 = MemoryStore(test_dir, enable_vectors=False)
    similar = store2.get_similar_experiences('test', top_k=1)
    test('跨会话记忆', len(similar) > 0, 'memory preserved')
except Exception as e:
    test('跨会话记忆', False, str(e))
try:
    store.clear_conversation()
    msgs = store.get_recent_conversation()
    test('清除会话', len(msgs) == 0)
except Exception as e:
    test('清除会话', False, str(e))

# === 第四轮：进化系统 ===
print('\n--- 第四轮：进化系统 ---')
evo_dir = '/tmp/_evo_test_evolution'
if os.path.exists(evo_dir):
    shutil.rmtree(evo_dir)
os.makedirs(evo_dir, exist_ok=True)

try:
    tracker = EvolutionTracker(evo_dir + '/tracker')
    test('Tracker初始化', True)
except Exception as e:
    test('Tracker初始化', False, str(e))
try:
    task = tracker.start_task('test', 'test task')
    tracker.log_step(task.task_id, 'step1', {'detail': 'test'})
    result = tracker.end_task(task.task_id, TaskStatus.SUCCESS, result='done')
    test('任务生命周期', result.task_id == task.task_id)
except Exception as e:
    test('任务生命周期', False, str(e))
try:
    stats = tracker.summary()
    test('任务统计', stats['total_tasks'] > 0)
except Exception as e:
    test('任务统计', False, str(e))
try:
    em = ErrorMemory(evo_dir + '/errors.json')
    entry = em.record_failure(task='test', error_msg="KeyError: 'test'", attempted_solution='use .get()')
    test('ErrorMemory', entry['error_type'] == 'KeyError')
except Exception as e:
    test('ErrorMemory', False, str(e))
try:
    up = UserPreferences(evo_dir + '/prefs.json')
    signals = up.learn_from_code('def hello():\n    print("hello")')
    test('UserPreferences', True)
except Exception as e:
    test('UserPreferences', False, str(e))
try:
    sm = StrategyMemory(evo_dir + '/strategy.json')
    cat = sm.classify_task('Fix the bug in main.py')
    test('策略分类', cat == 'debug', f'category={cat}')
except Exception as e:
    test('策略分类', False, str(e))
try:
    sm.record_task_result('debug', success=True, duration=10.0)
    stats = sm.get_stats()
    test('策略统计', stats['debug']['total_tasks'] > 0)
except Exception as e:
    test('策略统计', False, str(e))
try:
    pe = PromptEvolver(persist_dir=evo_dir + '/evolver')
    test('PromptEvolver', len(pe) > 0)
except Exception as e:
    test('PromptEvolver', False, str(e))
try:
    te = ToolEvolver(evo_dir + '/tools')
    te.record_tool_call('read_file', {'path': 'test.py'}, success=True)
    te.record_tool_call('write_file', {'path': 'out.py', 'content': 'x'}, success=True)
    test('ToolEvolver', len(te.call_log) == 2)
except Exception as e:
    test('ToolEvolver', False, str(e))

# === 第五轮：Agent核心功能 ===
print('\n--- 第五轮：Agent核心功能 ---')
try:
    config = load_config()
    categories = config.get('task_categories', {})
    task_lower = 'fix the bug in main.py'
    category = 'general'
    for cat, cfg in categories.items():
        if any(w in task_lower for w in cfg.get('keywords', [])):
            category = cat
            break
    test('任务分类', category == 'debug', f'category={category}')
except Exception as e:
    test('任务分类', False, str(e))
try:
    from brain.engine import get_system_prompt
    prompt = get_system_prompt()
    test('系统提示词', 'EvoCoder' in prompt, f'{len(prompt)} chars')
except Exception as e:
    test('系统提示词', False, str(e))
try:
    tc = TokenCache()
    tc.cache_hits = 100
    tc.cache_misses = 20
    tc.total_input_tokens = 50000
    tc.total_output_tokens = 10000
    stats = tc.get_stats()
    test('TokenCache', stats['hit_rate'] > 0.8, f"hit_rate={stats['hit_rate']:.1%}")
except Exception as e:
    test('TokenCache', False, str(e))
try:
    manager = SubAgentManager(api_key='test', base_url='http://test', model='test')
    types = manager.list_types()
    test('SubAgentManager', len(types) >= 5, f'{len(types)} types')
except Exception as e:
    test('SubAgentManager', False, str(e))
try:
    from utils.platform import get_platform_prompt
    prompt = get_platform_prompt()
    test('平台检测', 'Windows' in prompt or 'Linux' in prompt or 'Darwin' in prompt)
except Exception as e:
    test('平台检测', False, str(e))

# 清理
shutil.rmtree(test_dir, ignore_errors=True)
shutil.rmtree(evo_dir, ignore_errors=True)
try:
    os.remove('/tmp/_evo_test.txt')
except:
    pass

# 总结
print()
print('='*60)
print(f'测试结果: {passed}/{passed+failed} 通过')
if failed > 0:
    print(f'失败: {failed}')
    print('❌ 测试未通过')
else:
    print('✅ 所有测试通过！可以提交')
print('='*60)
