import { act, renderHook, waitFor } from '@testing-library/react';
import { useSync } from '../src/hooks/useSync';
import type { SyncEvent } from '../src/hooks/useSync';

// Mock global fetch
const mockFetch = jest.fn();
global.fetch = mockFetch as jest.Mock;

function mockSyncEventsResponse(events: SyncEvent[]) {
  return { ok: true, json: () => Promise.resolve(events) } as Response;
}

function mockSyncPushResponse(pushed: number) {
  return { ok: true, json: () => Promise.resolve({ pushed }) } as Response;
}

describe('useSync hook', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  test('initial state is idle with no events', () => {
    const { result } = renderHook(() => useSync());
    expect(result.current.status).toBe('idle');
    expect(result.current.events).toEqual([]);
    expect(result.current.lastSyncedAt).toBeNull();
  });

  test('refresh fetches events and transitions to complete', async () => {
    const events: SyncEvent[] = [{ id: 1, aggregate_id: 'agg-1', seq: 1, type: 'session.created', created_at: 1000 }];
    mockFetch.mockResolvedValueOnce(mockSyncEventsResponse(events));

    const { result } = renderHook(() => useSync());
    await act(async () => {
      await result.current.refresh();
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/sync/events', expect.any(Object));
    expect(result.current.status).toBe('complete');
    expect(result.current.events).toEqual(events);
    expect(result.current.lastSyncedAt).not.toBeNull();
  });

  test('push posts and refreshes events on completion', async () => {
    mockFetch
      .mockResolvedValueOnce(mockSyncPushResponse(3))
      .mockResolvedValueOnce(mockSyncEventsResponse([]));

    const { result } = renderHook(() => useSync());
    await act(async () => {
      await result.current.push();
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/sync/push', expect.objectContaining({ method: 'POST' }));
    // push 后自动 refresh → 两次 fetch
    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(result.current.status).toBe('complete');
  });

  test('status is syncing while request is in flight', async () => {
    let resolveFetch!: (value: Response) => void;
    mockFetch.mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveFetch = resolve; }));

    const { result } = renderHook(() => useSync());
    let pushPromise: Promise<void>;
    act(() => {
      pushPromise = result.current.refresh();
    });
    expect(result.current.status).toBe('syncing');

    await act(async () => {
      resolveFetch(mockSyncEventsResponse([]));
      await pushPromise;
    });
    expect(result.current.status).toBe('complete');
  });

  test('serialization: repeated refresh while busy is ignored (single fetch)', async () => {
    let resolveFetch!: (value: Response) => void;
    mockFetch.mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveFetch = resolve; }));

    const { result } = renderHook(() => useSync());
    let firstPromise: Promise<void>;
    act(() => {
      firstPromise = result.current.refresh();
    });
    // busy 期间再次调用 → 忽略
    await act(async () => {
      await result.current.refresh();
    });
    expect(mockFetch).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveFetch(mockSyncEventsResponse([]));
      await firstPromise;
    });
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  test('error state keeps last successful sync time', async () => {
    mockFetch
      .mockResolvedValueOnce(mockSyncEventsResponse([]))  // first refresh succeeds
      .mockRejectedValueOnce(new Error('network down'));   // second refresh fails

    const { result } = renderHook(() => useSync());
    await act(async () => {
      await result.current.refresh();
    });
    const lastSynced = result.current.lastSyncedAt;
    expect(result.current.status).toBe('complete');

    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.status).toBe('error');
    expect(result.current.lastSyncedAt).toBe(lastSynced);
  });

  test('push serialization: rapid double push produces single push request', async () => {
    mockFetch
      .mockResolvedValueOnce(mockSyncPushResponse(1))
      .mockResolvedValueOnce(mockSyncEventsResponse([]));

    const { result } = renderHook(() => useSync());
    await act(async () => {
      await Promise.all([result.current.push(), result.current.push()]);
    });

    const pushCalls = mockFetch.mock.calls.filter((c) => c[0] === '/api/sync/push');
    expect(pushCalls).toHaveLength(1);
  });
});
