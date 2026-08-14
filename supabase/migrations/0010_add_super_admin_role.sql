-- SuperAdmin: single, highest-privilege role that manages both Admins and
-- Members (promote/demote, full CRUD on admins). Bootstrapped exclusively
-- via INITIAL_ADMIN_EMAIL at login (see app/routers/auth.py) — never
-- created/promoted through the UI.
insert into public.roles (id, name) values
  ('00000000-0000-0000-0000-000000000003', 'super_admin');
