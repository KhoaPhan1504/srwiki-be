-- 0008 enabled RLS on roles with zero policies (service-role only), copying
-- the known_logins pattern. That pattern doesn't fit here: GET/PUT /profile
-- (and other self-service profile endpoints) use user_client() — RLS-scoped
-- as the caller, not service-role — and need to read their OWN role name via
-- the roles(name) embed. Role names ("admin"/"member") aren't sensitive, so
-- allow any authenticated user to read the (tiny, static) roles table.
create policy "Authenticated users can read roles"
  on public.roles for select
  to authenticated
  using (true);
