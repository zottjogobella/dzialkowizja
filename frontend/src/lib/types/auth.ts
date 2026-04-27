export type UserRole = 'super_admin' | 'admin' | 'handlowiec' | 'prawnik';

export interface User {
	id: string;
	display_name: string;
	email: string | null;
	avatar_url: string | null;
	is_active: boolean;
	role: UserRole;
	organization_id: string | null;
	/** Field keys hidden for this user. Empty for admin/super_admin. */
	restricted_keys: string[];
}

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';
