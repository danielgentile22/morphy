import { afterEach, describe, expect, it } from 'vitest';
import { authHeader, clearToken, getToken, setToken } from '../../src/lib/auth-token';

describe('auth-token', () => {
  afterEach(() => clearToken());

  it('starts with no token', () => {
    expect(getToken()).toBeNull();
    expect(authHeader()).toEqual({});
  });

  it('persists and reads back a token', () => {
    setToken('jwt-abc');
    expect(getToken()).toBe('jwt-abc');
  });

  it('builds a Bearer header only when a token is set', () => {
    expect(authHeader()).toEqual({});
    setToken('jwt-abc');
    expect(authHeader()).toEqual({ Authorization: 'Bearer jwt-abc' });
  });

  it('clears the token', () => {
    setToken('jwt-abc');
    clearToken();
    expect(getToken()).toBeNull();
    expect(authHeader()).toEqual({});
  });
});
