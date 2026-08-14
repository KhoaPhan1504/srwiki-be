-- register() (app/routers/auth.py) inserted profiles rows without `email`
-- until now, so any self-registered user still has a null profiles.email —
-- invisible until that row is read through a response schema that requires
-- it (e.g. AdminOut, after a self-registered member gets promoted). Same
-- backfill as migration 0008, re-run to catch rows created since.
update public.profiles p
set email = u.email
from auth.users u
where p.id = u.id and p.email is null;
