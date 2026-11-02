-- Public password signup; approval remains database-owned. Safe to rerun.
-- No usage-reset migration/column is required. Quotas use Korean calendar days/months.
-- Existing members/jobs/results/budget/charges are never deleted or reset here.
begin;
select pg_catalog.pg_advisory_xact_lock(7219032701::bigint);

-- Preserve all existing rows; new users cannot choose role/status in metadata.
alter table private.brain_members alter column status set default 'pending';
alter table private.brain_members alter column role set default 'member';
create or replace function private.brain_new_member()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into private.brain_members(user_id, display_name, status, role)
  values (new.id, left(coalesce(new.raw_user_meta_data->>'display_name',''),80), 'pending', 'member')
  on conflict (user_id) do nothing;
  return new;
end;
$$;
revoke all on function private.brain_new_member() from public, anon, authenticated;

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
  update private.brain_members set status=p_status,updated_at=now() where user_id=p_user_id;
  if not found then raise exception 'member not found'; end if;
  insert into private.brain_approval_audit(actor_id,member_id,status)
  values(auth.uid(),p_user_id,p_status);
  return jsonb_build_object('id',p_user_id,'status',p_status);
end;
$$;

create or replace function public.brain_reserve(
  p_user_id uuid, p_request_id uuid, p_request_hash text
)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare j private.brain_jobs; running_count integer; position integer;
  max_running constant integer := 20;
  month_start timestamptz := date_trunc('month',now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul';
  day_start timestamptz := date_trunc('day',now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul';
begin
  -- One global lock makes both admission and FIFO claims atomic across Vercel instances.
  perform pg_catalog.pg_advisory_xact_lock(7219032701::bigint);
  if not exists(select 1 from private.brain_members m
    where m.user_id=p_user_id and m.status='approved') then
    return jsonb_build_object('state','denied');
  end if;
  update private.brain_jobs set status='error',finished_at=now()
    where (status='queued' and (started_at<=now()-interval '10 minutes'
                               or last_seen_at<=now()-interval '120 seconds'))
       or (status='running' and running_at<=now()-interval '120 seconds');
  select * into j from private.brain_jobs where request_id=p_request_id;
  if found then
    if j.user_id<>p_user_id or j.request_hash<>p_request_hash then
      return jsonb_build_object('state','conflict');
    end if;
    if j.status<>'queued' then return public.brain_job(p_user_id,p_request_id); end if;
    update private.brain_jobs set last_seen_at=now() where request_id=p_request_id;
  else
    -- Queue admission reserves quota once. Polling never reserves another request.
    if (select count(*) from private.brain_jobs where user_id=p_user_id and started_at>=month_start)>=50
      or (select count(*) from private.brain_jobs where user_id=p_user_id and started_at>=day_start)>=20
      or (select count(*) from private.brain_jobs where user_id=p_user_id and started_at>now()-interval '1 minute')>=2
      or (select count(*) from private.brain_jobs where started_at>=month_start)>=1000 then
      return jsonb_build_object('state','limited');
    end if;
    -- Preserve historical rows and result payloads; admission does not run retention cleanup.
    insert into private.brain_jobs(request_id,user_id,request_hash,status,last_seen_at)
      values(p_request_id,p_user_id,p_request_hash,'queued',now()) returning * into j;
  end if;
  select count(*) into running_count from private.brain_jobs where status='running';
  select count(*) into position from private.brain_jobs where status='queued'
    and (started_at,request_id)<=(j.started_at,j.request_id);
  if position<=max_running-running_count then
    update private.brain_jobs set status='running',running_at=now() where request_id=p_request_id;
    return jsonb_build_object('state','reserved');
  end if;
  return jsonb_build_object('state','queued','queuePosition',position);
end;
$$;

create or replace function public.brain_budget_reserve(
  p_user_id uuid, p_request_id uuid, p_request_hash text, p_allowance_krw integer default 34
)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare b private.brain_ai_budget;
begin
  if p_allowance_krw is null or p_allowance_krw <> 34 then
    return jsonb_build_object('state','denied');
  end if;
  -- Shared with job admission: all Vercel instances reserve atomically.
  perform pg_catalog.pg_advisory_xact_lock(7219032701::bigint);
  if not exists(select 1 from private.brain_members m
    where m.user_id=p_user_id and m.status='approved')
    or not exists(select 1 from private.brain_jobs
      where request_id=p_request_id and user_id=p_user_id and request_hash=p_request_hash
        and status='running' and running_at>now()-interval '120 seconds') then
    return jsonb_build_object('state','denied');
  end if;
  if exists(select 1 from private.brain_ai_charges where request_id=p_request_id) then
    return jsonb_build_object('state','already_charged');
  end if;
  select * into b from private.brain_ai_budget where singleton=true for update;
  if not found then return jsonb_build_object('state','unavailable'); end if;
  if b.accounted_krw+p_allowance_krw>b.limit_krw then
    return jsonb_build_object('state','budget_exhausted');
  end if;
  update private.brain_ai_budget set accounted_krw=accounted_krw+p_allowance_krw where singleton=true;
  insert into private.brain_ai_charges(request_id,allowance_krw)
    values(p_request_id,p_allowance_krw);
  return jsonb_build_object('state','reserved');
end;
$$;

revoke all on function public.brain_set_member_status(uuid,text) from public, anon;
grant execute on function public.brain_set_member_status(uuid,text) to authenticated;
revoke all on function public.brain_reserve(uuid,uuid,text) from public, anon, authenticated;
grant execute on function public.brain_reserve(uuid,uuid,text) to service_role;
revoke all on function public.brain_budget_reserve(uuid,uuid,text,integer) from public, anon, authenticated;
grant execute on function public.brain_budget_reserve(uuid,uuid,text,integer) to service_role;

-- Deployment metadata only; never reserves jobs/budget or calls AI.
create or replace function public.brain_auth_policy_ready()
returns jsonb language sql stable security definer set search_path = '' as $$
  select jsonb_build_object('policy','password_only_approval_v1','ready',
    position('email_confirmed_at' in pg_catalog.pg_get_functiondef(
      'public.brain_set_member_status(uuid,text)'::regprocedure))=0
    and position('email_confirmed_at' in pg_catalog.pg_get_functiondef(
      'public.brain_reserve(uuid,uuid,text)'::regprocedure))=0
    and position('usage_reset_at' in pg_catalog.pg_get_functiondef(
      'public.brain_reserve(uuid,uuid,text)'::regprocedure))=0
    and position('email_confirmed_at' in pg_catalog.pg_get_functiondef(
      'public.brain_budget_reserve(uuid,uuid,text,integer)'::regprocedure))=0);
$$;
revoke all on function public.brain_auth_policy_ready() from public, anon, authenticated;
grant execute on function public.brain_auth_policy_ready() to service_role;
notify pgrst, 'reload schema';
commit;
