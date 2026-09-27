-- Run once (or rerun safely) in the Q-Lab project's Supabase SQL Editor.
-- Private tables are never exposed to browser CRUD. Approval is database-owned.
begin;
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table if not exists private.brain_members (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default '',
  status text not null default 'pending' check (status in ('pending','approved','rejected','suspended')),
  role text not null default 'member' check (role in ('member','admin')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table private.brain_members enable row level security;
revoke all on private.brain_members from public, anon, authenticated;

create table if not exists private.brain_approval_audit (
  id bigint generated always as identity primary key,
  actor_id uuid not null,
  member_id uuid not null,
  status text not null,
  created_at timestamptz not null default now()
);
alter table private.brain_approval_audit enable row level security;
revoke all on private.brain_approval_audit from public, anon, authenticated;

create table if not exists private.brain_jobs (
  request_id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  request_hash text not null check (length(request_hash) = 64),
  status text not null default 'running' check (status in ('running','done','error')),
  result jsonb,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);
create index if not exists brain_jobs_user_time on private.brain_jobs(user_id, started_at);
create index if not exists brain_jobs_time on private.brain_jobs(started_at);
alter table private.brain_jobs enable row level security;
revoke all on private.brain_jobs from public, anon, authenticated;

create or replace function private.brain_new_member()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into private.brain_members(user_id, display_name)
  values (new.id, left(coalesce(new.raw_user_meta_data->>'display_name',''),80))
  on conflict (user_id) do nothing;
  return new;
end;
$$;
revoke all on function private.brain_new_member() from public, anon, authenticated;
drop trigger if exists brain_new_member on auth.users;
create trigger brain_new_member after insert on auth.users
for each row execute function private.brain_new_member();
insert into private.brain_members(user_id, display_name)
select id, left(coalesce(raw_user_meta_data->>'display_name',''),80) from auth.users
on conflict (user_id) do nothing;

create or replace function public.brain_access()
returns jsonb language sql stable security definer set search_path = '' as $$
  select coalesce((select jsonb_build_object(
    'status',m.status,'role',m.role,'displayName',m.display_name
  ) from private.brain_members m where m.user_id = auth.uid()),
  jsonb_build_object('status','pending','role','member','displayName',''));
$$;
revoke all on function public.brain_access() from public, anon;
grant execute on function public.brain_access() to authenticated;

create or replace function public.brain_members()
returns jsonb language plpgsql stable security definer set search_path = '' as $$
begin
  if not exists(select 1 from private.brain_members
    where user_id=auth.uid() and status='approved' and role='admin') then
    raise insufficient_privilege;
  end if;
  return coalesce((select jsonb_agg(row_to_json(rows)) from (
    select m.user_id as id, u.email, m.display_name as "displayName", m.status, m.role,
           (u.email_confirmed_at is not null) as "emailConfirmed",
           m.created_at as "createdAt"
    from private.brain_members m join auth.users u on u.id=m.user_id
    order by (m.status='pending') desc, m.created_at desc limit 200
  ) rows),'[]'::jsonb);
end;
$$;
revoke all on function public.brain_members() from public, anon;
grant execute on function public.brain_members() to authenticated;

create or replace function public.brain_set_member_status(p_user_id uuid, p_status text)
returns jsonb language plpgsql security definer set search_path = '' as $$
begin
  if not exists(select 1 from private.brain_members
    where user_id=auth.uid() and status='approved' and role='admin') then
    raise insufficient_privilege;
  end if;
  if p_status not in ('approved','rejected','suspended') then
    raise exception 'invalid status';
  end if;
  if p_user_id=auth.uid() or exists(select 1 from private.brain_members
    where user_id=p_user_id and role='admin') then
    raise exception 'admin accounts require dashboard management';
  end if;
  if p_status='approved' and not exists(select 1 from auth.users
    where id=p_user_id and email_confirmed_at is not null) then
    raise exception 'email confirmation required';
  end if;
  update private.brain_members set status=p_status,updated_at=now() where user_id=p_user_id;
  if not found then raise exception 'member not found'; end if;
  insert into private.brain_approval_audit(actor_id,member_id,status)
  values(auth.uid(),p_user_id,p_status);
  return jsonb_build_object('id',p_user_id,'status',p_status);
end;
$$;
revoke all on function public.brain_set_member_status(uuid,text) from public, anon;
grant execute on function public.brain_set_member_status(uuid,text) to authenticated;

-- These three job functions are for the verified backend only, never end users.
create or replace function public.brain_job(p_user_id uuid, p_request_id uuid)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare j private.brain_jobs;
begin
  select * into j from private.brain_jobs where request_id=p_request_id and user_id=p_user_id;
  if not found then return jsonb_build_object('state','missing'); end if;
  if j.status='running' and j.started_at > now()-interval '120 seconds' then
    return jsonb_build_object('state','running');
  end if;
  if j.status='done' and j.result is not null and j.finished_at > now()-interval '24 hours' then
    return jsonb_build_object('state','cached','result',j.result);
  end if;
  return jsonb_build_object('state','error');
end;
$$;
revoke all on function public.brain_job(uuid,uuid) from public, anon, authenticated;
grant execute on function public.brain_job(uuid,uuid) to service_role;

create or replace function public.brain_reserve(
  p_user_id uuid, p_request_id uuid, p_request_hash text
)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare j private.brain_jobs;
  month_start timestamptz := date_trunc('month',now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul';
  day_start timestamptz := date_trunc('day',now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul';
begin
  perform pg_catalog.pg_advisory_xact_lock(7219032701::bigint);
  if not exists(select 1 from private.brain_members m join auth.users u on u.id=m.user_id
    where m.user_id=p_user_id and m.status='approved' and u.email_confirmed_at is not null) then
    return jsonb_build_object('state','denied');
  end if;
  select * into j from private.brain_jobs where request_id=p_request_id;
  if found then
    if j.user_id<>p_user_id or j.request_hash<>p_request_hash then
      return jsonb_build_object('state','conflict');
    end if;
    return public.brain_job(p_user_id,p_request_id);
  end if;
  if (select count(*) from private.brain_jobs where user_id=p_user_id and started_at>=month_start)>=50
    or (select count(*) from private.brain_jobs where user_id=p_user_id and started_at>=day_start)>=20
    or (select count(*) from private.brain_jobs where user_id=p_user_id and started_at>now()-interval '1 minute')>=2
    or (select count(*) from private.brain_jobs where started_at>=month_start)>=1000
    or (select count(*) from private.brain_jobs where status='running' and started_at>now()-interval '120 seconds')>=2 then
    return jsonb_build_object('state','limited');
  end if;
  -- Expire results; keep only request metadata needed for monthly counters.
  update private.brain_jobs set result=null where result is not null and finished_at<now()-interval '24 hours';
  delete from private.brain_jobs where started_at<now()-interval '35 days';
  insert into private.brain_jobs(request_id,user_id,request_hash)
  values(p_request_id,p_user_id,p_request_hash);
  return jsonb_build_object('state','reserved');
end;
$$;
revoke all on function public.brain_reserve(uuid,uuid,text) from public, anon, authenticated;
grant execute on function public.brain_reserve(uuid,uuid,text) to service_role;

create or replace function public.brain_finish(
  p_user_id uuid,p_request_id uuid,p_result jsonb,p_failed boolean
)
returns jsonb language plpgsql security definer set search_path = '' as $$
begin
  update private.brain_jobs set status=case when p_failed then 'error' else 'done' end,
    result=case when p_failed then null else p_result end,finished_at=now()
  where request_id=p_request_id and user_id=p_user_id and status='running';
  return jsonb_build_object('saved',found);
end;
$$;
revoke all on function public.brain_finish(uuid,uuid,jsonb,boolean) from public, anon, authenticated;
grant execute on function public.brain_finish(uuid,uuid,jsonb,boolean) to service_role;

create or replace function public.brain_usage()
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare monthly integer; daily integer;
  month_start timestamptz := date_trunc('month',now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul';
  day_start timestamptz := date_trunc('day',now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul';
begin
  if not exists(select 1 from private.brain_members where user_id=auth.uid() and status='approved') then
    raise insufficient_privilege;
  end if;
  select count(*) into monthly from private.brain_jobs where user_id=auth.uid() and started_at>=month_start;
  select count(*) into daily from private.brain_jobs where user_id=auth.uid() and started_at>=day_start;
  return jsonb_build_object('monthlyLimit',50,'monthlyRemaining',greatest(0,50-monthly),
                           'dailyLimit',20,'dailyUsed',daily);
end;
$$;
revoke all on function public.brain_usage() from public, anon;
grant execute on function public.brain_usage() to authenticated;
notify pgrst, 'reload schema';
commit;
