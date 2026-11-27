-- Phase 1 price observations.
-- Apply after supabase/schema.sql in the Supabase SQL editor.
create table if not exists public.price_observations (
  id uuid primary key default gen_random_uuid(),
  product_id text not null,
  product_url text not null,
  retailer_domain text not null,
  canonical_url text,
  retailer_product_id text,
  selected_color_id text,
  price numeric(12,2),
  currency text,
  source text not null,
  verification_status text not null check (verification_status in ('verified', 'failed', 'unverified')),
  availability jsonb not null default '[]'::jsonb,
  checked_at timestamptz not null default now(),
  error_code text,
  error_message text,
  constraint price_observations_product_url_https check (product_url ~ '^https://'),
  constraint price_observations_retailer_domain_allowlist check (retailer_domain = 'terminalx.com' or retailer_domain like '%.terminalx.com'),
  constraint price_observations_price_nonnegative check (price is null or price >= 0),
  constraint price_observations_currency_format check (currency is null or currency ~ '^[A-Z]{3}$'),
  constraint price_observations_availability_array check (jsonb_typeof(availability) = 'array')
);

create index if not exists price_observations_product_checked_idx
  on public.price_observations (product_id, checked_at desc);

create index if not exists price_observations_verified_idx
  on public.price_observations (verification_status, checked_at desc);

alter table public.price_observations enable row level security;

revoke all on public.price_observations from anon, authenticated;
grant select on public.price_observations to anon, authenticated;

drop policy if exists "Public can read verified prices" on public.price_observations;
create policy "Public can read verified prices"
on public.price_observations
for select
to anon, authenticated
using (verification_status = 'verified');
