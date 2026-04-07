import { writable } from 'svelte/store';
import type { User, AuthStatus } from '$lib/types/auth';

export const user = writable<User | null>(null);
export const authStatus = writable<AuthStatus>('loading');
