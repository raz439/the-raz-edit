# Shopping Board – Admin & Users (work in progress)

This branch **is not deployed**. The published Netlify site and production branch remain unchanged.

## Target architecture
- Supabase Auth: email/password sign-in and emailed viewer invitations.
- Supabase Postgres: one JSON document for products, categories, and subcategories.
- Row Level Security: everyone can read the board; only approved admins can write it.
- Edge Function: invite viewers from the Admin interface, with a server-side secret. Never place a secret or service-role key in the browser.
- Updates to products / categories / subcategories do **not** create Netlify deploys after backend setup.

## One-time setup (owner)
1. Create a Supabase project at https://supabase.com/dashboard.
2. Run `supabase/schema.sql` in its SQL Editor.
3. Set up email Auth. Create your own first account in **Authentication → Users** and copy its UUID.
4. Run `update public.profiles set role='admin' where id='YOUR-UUID';` in SQL Editor (after profile creation). Do this only for yourself.
5. Fill in `supabase-config.js` with **Project URL** and **publishable/anon key** from Supabase project settings; these two are public identifiers. Never use a service-role / secret key there.
6. Deploy `supabase/functions/invite-user/index.ts` as function `invite-user`. Configure its **server-side** secret `SUPABASE_SERVICE_ROLE_KEY` and expected URL / anon key. Keep JWT verification enabled and ensure the function checks the caller's profile role.
7. Test login, initial import of the existing 30 products, adding category / product and user invitation on the staging branch before merging into `main`.
8. Merge and trigger ONE production deployment only after testing.

**Important:** A login form cannot provide real permissions on a static site by itself. Permission enforcement comes from database RLS and the Edge Function.
