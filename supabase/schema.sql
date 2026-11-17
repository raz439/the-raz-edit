-- The Raz Edit: run once in Supabase SQL Editor
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  role text not null default 'viewer' check (role in ('admin','viewer')),
  created_at timestamptz not null default now()
);
alter table public.profiles enable row level security;
drop policy if exists "Users read own profile" on public.profiles;
create policy "Users read own profile" on public.profiles for select to authenticated
using (id = (select auth.uid()));
-- The authenticated browser cannot grant itself admin or change other profiles.
revoke insert, update, delete on public.profiles from anon, authenticated;
grant select on public.profiles to authenticated;

create or replace function public.create_viewer_profile()
returns trigger language plpgsql security definer
set search_path = '' as $$
begin
  insert into public.profiles(id, email, role)
  values (new.id, new.email, 'viewer')
  on conflict (id) do nothing;
  return new;
end;
$$;
drop trigger if exists on_auth_user_created_raz on auth.users;
create trigger on_auth_user_created_raz
after insert on auth.users for each row
execute function public.create_viewer_profile();

create table if not exists public.board_content (
  id integer primary key check(id=1),
  content jsonb not null,
  updated_at timestamptz not null default now()
);
alter table public.board_content enable row level security;
grant select on public.board_content to anon, authenticated;
grant insert, update on public.board_content to authenticated;
drop policy if exists "Public can read board" on public.board_content;
create policy "Public can read board" on public.board_content
for select to anon, authenticated using (true);
drop policy if exists "Admins can create board" on public.board_content;
create policy "Admins can create board" on public.board_content for insert to authenticated
with check (exists(select 1 from public.profiles p where p.id=(select auth.uid()) and p.role='admin'));
drop policy if exists "Admins can update board" on public.board_content;
create policy "Admins can update board" on public.board_content for update to authenticated
using (exists(select 1 from public.profiles p where p.id=(select auth.uid()) and p.role='admin'))
with check (exists(select 1 from public.profiles p where p.id=(select auth.uid()) and p.role='admin'));

-- After creating your OWN account through Supabase Auth > Users,
-- replace the UUID below and run ONE TIME in SQL Editor. Never put this command in the browser:
-- update public.profiles set role='admin' where id='YOUR-AUTH-USER-UUID';
-- Existing users created before the trigger can be seeded with:
-- insert into public.profiles(id,email,role)
-- select id,email,'viewer' from auth.users on conflict(id) do nothing;
