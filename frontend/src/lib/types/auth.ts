export interface User {
	id: string;
	display_name: string;
	email: string | null;
	avatar_url: string | null;
	is_active: boolean;
}

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';
