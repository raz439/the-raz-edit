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

## Phase 1 price monitoring (manual only)

1. Apply `supabase/migrations/20261123_price_observations.sql` after the base schema. It adds append-only observations and public read access only for rows marked `verified`.
2. Add repository Actions secrets named `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. The service-role key is used only by Actions and must never be placed in frontend files or printed in logs.
3. Run **Monitor Terminal X prices** manually from the Actions tab. The workflow reads `board_content`, checks only Terminal X URLs, and records verified or failed observations without changing `board_content`.
4. The workflow is intentionally `workflow_dispatch` only. Do not add a schedule until a real product has been validated end to end.
5. The frontend reads verified rows from `price_observations`; it keeps the existing catalogue price as a labelled fallback when no verified row exists.

### Phase 1 validation

Use one current Terminal X product whose URL includes its selected `color` query parameter. Confirm that the run summary reports a verified ILS price, the Supabase row has the expected product ID and checked time, and the public board displays the verified value. A failed or ambiguous observation must not replace the previous verified row.

The workflow and migration do not deploy Netlify or publish the frontend. If the frontend changes are later approved, publish them through the existing manual Netlify/GitHub Pages process; do not enable continuous builds.

**Important:** A login form cannot provide real permissions on a static site by itself. Permission enforcement comes from database RLS and the Edge Function.

## Automatic product details from a pasted shopping link
The Admin form now offers **זיהוי פרטי המוצר**. On link paste/change it invokes the admin-only `product-lookup` Edge Function, which attempts to read public page metadata (title, shop, image) from supported fashion store domains. Stores frequently block bots, so this is best-effort, **not guaranteed**.
- Deploy `supabase/functions/product-lookup/index.ts` to Edge Functions under **product-lookup**, with legacy Verify JWT **OFF**, because this project uses a publishable key. The function enforces logged-in Admin role itself using the provided user JWT.
- If lookup fails, fill in the name, store, and image manually. Image can be replaced with a direct image URL, and a separate **תמונה חלופית** fallback is used when the primary image fails to load.
- Never put private API keys into frontend code. No product extraction bypass should be used against unsupported or blocked websites.
- Publishing product data itself only updates the Supabase database; deploying new app code is still a Netlify deployment.
