import { derived, writable, type Readable } from 'svelte/store';
import { user } from './auth';

/**
 * Set of field keys hidden from the current user. Stays empty for
 * admin/super_admin (server returns an empty list for them).
 *
 * Components should call ``isHidden(key)`` rather than reading this set
 * directly so the call sites stay one-liners.
 */
export const restrictions: Readable<Set<string>> = derived(user, ($user) => {
	return new Set($user?.restricted_keys ?? []);
});

/**
 * Layout overrides exposed by the server load function. Frontend code
 * uses this only when the user store hasn't been hydrated yet (e.g. on
 * the very first render of the root layout).
 */
const initialRestrictions = writable<Set<string>>(new Set());

export function hydrateInitialRestrictions(keys: string[] | null | undefined) {
	initialRestrictions.set(new Set(keys ?? []));
}

/** Returns ``true`` if ``key`` is currently hidden for the active user. */
export function isHiddenSync(currentUser: { restricted_keys?: string[] } | null, key: string): boolean {
	if (!currentUser?.restricted_keys) return false;
	return currentUser.restricted_keys.includes(key);
}
