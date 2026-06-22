/**
 * Types Tests
 * 测试类型定义
 */
import { Message, Session, Config, ToolCall } from '../src/types';

describe('Message type', () => {
  test('creates valid user message', () => {
    const message: Message = {
      id: '1',
      role: 'user',
      content: 'Hello',
      createdAt: new Date().toISOString(),
    };

    expect(message.id).toBe('1');
    expect(message.role).toBe('user');
    expect(message.content).toBe('Hello');
  });

  test('creates valid assistant message', () => {
    const message: Message = {
      id: '2',
      role: 'assistant',
      content: 'Hi there!',
      createdAt: new Date().toISOString(),
    };

    expect(message.role).toBe('assistant');
  });

  test('message can have tool calls', () => {
    const toolCall: ToolCall = {
      id: 'tool_1',
      name: 'websearch',
      arguments: { query: 'test' },
    };

    const message: Message = {
      id: '3',
      role: 'assistant',
      content: 'Let me search for that',
      toolCalls: [toolCall],
      createdAt: new Date().toISOString(),
    };

    expect(message.toolCalls).toBeDefined();
    expect(message.toolCalls).toHaveLength(1);
    expect(message.toolCalls![0].name).toBe('websearch');
  });

  test('message can have tool call id', () => {
    const message: Message = {
      id: '4',
      role: 'tool',
      content: 'Search result: ...',
      toolCallId: 'call_123',
      name: 'websearch',
      createdAt: new Date().toISOString(),
    };

    expect(message.role).toBe('tool');
    expect(message.toolCallId).toBe('call_123');
    expect(message.name).toBe('websearch');
  });
});

describe('Session type', () => {
  test('creates valid session', () => {
    const session: Session = {
      id: 'session_1',
      title: 'My Session',
      provider: 'openai',
      model: 'gpt-4',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    expect(session.id).toBe('session_1');
    expect(session.title).toBe('My Session');
    expect(session.provider).toBe('openai');
  });
});

describe('Config type', () => {
  test('creates valid config', () => {
    const config: Config = {
      provider: 'openai',
      model: 'gpt-4',
      apiKey: 'sk-test',
      temperature: 0.7,
      maxTokens: 2000,
      stream: true,
    };

    expect(config.provider).toBe('openai');
    expect(config.model).toBe('gpt-4');
    expect(config.apiKey).toBe('sk-test');
    expect(config.temperature).toBe(0.7);
    expect(config.stream).toBe(true);
  });

  test('config has optional fields', () => {
    const config: Partial<Config> = {
      provider: 'anthropic',
      model: 'claude-3',
    };

    expect(config.provider).toBe('anthropic');
    expect(config.model).toBe('claude-3');
  });
});

describe('ToolCall type', () => {
  test('creates valid tool call', () => {
    const toolCall: ToolCall = {
      id: 'tool_1',
      name: 'read',
      arguments: { path: '/path/to/file' },
    };

    expect(toolCall.id).toBe('tool_1');
    expect(toolCall.name).toBe('read');
    expect(toolCall.arguments).toEqual({ path: '/path/to/file' });
  });
});
