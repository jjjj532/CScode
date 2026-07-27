/**
 * Tests for useOnlineStatus hook
 */
import { renderHook, act } from '@testing-library/react';
import { useOnlineStatus } from '../src/hooks/useOnlineStatus';

describe('useOnlineStatus', () => {
  beforeEach(() => {
    // Default: assume online
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: true,
    });
  });

  test('returns a boolean', () => {
    const { result } = renderHook(() => useOnlineStatus());
    expect(typeof result.current).toBe('boolean');
  });

  test('returns true when navigator.onLine is true', () => {
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: true,
    });
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(true);
  });

  test('returns false when navigator.onLine is false', () => {
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: false,
    });
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(false);
  });

  test('reacts to offline event', () => {
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(true);

    act(() => {
      window.dispatchEvent(new Event('offline'));
    });

    expect(result.current).toBe(false);
  });

  test('reacts to online event', () => {
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      value: false,
    });
    const { result } = renderHook(() => useOnlineStatus());
    expect(result.current).toBe(false);

    act(() => {
      window.dispatchEvent(new Event('online'));
    });

    expect(result.current).toBe(true);
  });

  test('cleans up event listeners on unmount', () => {
    const removeSpyOnline = jest.spyOn(window, 'removeEventListener');
    const { unmount } = renderHook(() => useOnlineStatus());

    unmount();

    expect(removeSpyOnline).toHaveBeenCalledWith('online', expect.any(Function));
    expect(removeSpyOnline).toHaveBeenCalledWith('offline', expect.any(Function));
  });
});
