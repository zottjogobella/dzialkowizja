export type UserRole = 'super_admin' | 'admin' | 'user';

export interface User {
	id: string;
	display_name: string;
	email: string | null;
	avatar_url: string | null;
	is_active: boolean;
	role: UserRole;
	organization_id: string | null;
}

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';
