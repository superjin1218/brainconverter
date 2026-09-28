-- User-requested, one-time reset. Keep historical jobs/charges and archive the
-- previous budget counter. Reapplying this migration never resets again.
begin;
select pg_catalog.pg_advisory_xact_lock(7219032701::bigint);

create table if not exists private.brain_accounting_reset (
  singleton boolean primary key default true check (singleton),
  started_at timestamptz not null default clock_timestamp(),
  archived_accounted_krw integer not null,
  archived_charge_count bigint not null
);
alter table private.brain_accounting_reset enable row level security;
revoke all on private.brain_accounting_reset from public, anon, authenticated;
alter table private.brain_members add column if not exists usage_reset_at timestamptz;
alter table private.brain_ai_charges
  add column if not exists input_tokens bigint check (input_tokens >= 0),
  add column if not exists output_tokens bigint check (output_tokens >= 0),
  add column if not exists cost_microusd bigint check (cost_microusd >= 0);
alter table private.brain_ai_charges alter column allowance_krw set default 34;
alter table private.brain_ai_charges alter column created_at set default clock_timestamp();

do $$
begin
  if not exists(select 1 from private.brain_accounting_reset) then
    if exists(select 1 from private.brain_jobs where
      (status='running' and running_at>now()-interval '120 seconds') or
      (status='queued' and last_seen_at>now()-interval '120 seconds')) then
      raise exception 'Wait for active conversions before resetting accounting';
    end if;
    insert into private.brain_accounting_reset(singleton,archived_accounted_krw,archived_charge_count)
      select true,accounted_krw,(select count(*) from private.brain_ai_charges)
      from private.brain_ai_budget where singleton=true;
    if not found then raise exception 'budget unavailable'; end if;
    update private.brain_ai_budget set accounted_krw=0 where singleton=true;
    update private.brain_members set usage_reset_at=(
      select started_at from private.brain_accounting_reset where singleton=true
    ) where role='admin' and status='approved';
  end if;
end;
$$;

-- Persist usage beside the non-expiring reservation ledger. Job results are
-- cleaned after 24h and must not be the source of cumulative cost reporting.
create or replace function public.brain_finish(
  p_user_id uuid, p_request_id uuid, p_result jsonb, p_failed boolean
)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare saved boolean;
begin
  update private.brain_jobs set status=case when p_failed then 'error' else 'done' end,
    result=case when p_failed then null else p_result end,finished_at=now()
    where request_id=p_request_id and user_id=p_user_id and status='running';
  saved := found;
  if saved and not p_failed and p_result->>'provider'='openai'
    and (p_result#>>'{usage,inputTokens}')::bigint>0
    and (p_result#>>'{usage,outputTokens}')::bigint>=0
    and (p_result#>>'{usage,costMicrousd}')::bigint>=0 then
    update private.brain_ai_charges
      set input_tokens=(p_result#>>'{usage,inputTokens}')::bigint,
          output_tokens=(p_result#>>'{usage,outputTokens}')::bigint,
          cost_microusd=(p_result#>>'{usage,costMicrousd}')::bigint
      where request_id=p_request_id and allowance_krw=34;
  end if;
  return jsonb_build_object('saved',saved);
end;
$$;
revoke all on function public.brain_finish(uuid,uuid,jsonb,boolean) from public, anon, authenticated;
grant execute on function public.brain_finish(uuid,uuid,jsonb,boolean) to service_role;

create or replace function public.brain_budget_status(p_allowance_krw integer default 34)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare b private.brain_ai_budget; since timestamptz; totals jsonb;
begin
  if not exists(select 1 from private.brain_members
    where user_id=auth.uid() and status='approved' and role='admin') then
    raise insufficient_privilege;
  end if;
  if p_allowance_krw is null or p_allowance_krw<>34 then raise exception 'invalid allowance'; end if;
  select * into b from private.brain_ai_budget where singleton=true;
  if not found then raise exception 'budget unavailable'; end if;
  select started_at into strict since from private.brain_accounting_reset where singleton=true;
  select jsonb_build_object(
    'attempts',count(*),'usageRecordedAttempts',count(cost_microusd),
    'unconfirmedAttempts',count(*) filter (where cost_microusd is null),
    'inputTokens',coalesce(sum(input_tokens),0),'outputTokens',coalesce(sum(output_tokens),0),
    'estimatedCostMicrousd',coalesce(sum(cost_microusd),0)) into totals
    from private.brain_ai_charges where created_at>=since and allowance_krw=34;
  return totals || jsonb_build_object(
    'limitKrw',b.limit_krw,'accountedKrw',b.accounted_krw,
    'remainingKrw',b.limit_krw-b.accounted_krw,'stopped',b.accounted_krw+34>b.limit_krw,
    'period','since_reset','since',since,'allowancePerAttemptKrw',34);
end;
$$;
revoke all on function public.brain_budget_status(integer) from public, anon;
grant execute on function public.brain_budget_status(integer) to authenticated;

create or replace function public.brain_usage()
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare monthly integer; daily integer; since timestamptz;
  month_start timestamptz := date_trunc('month',now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul';
  day_start timestamptz := date_trunc('day',now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul';
begin
  select usage_reset_at into since from private.brain_members
    where user_id=auth.uid() and status='approved';
  if not found then raise insufficient_privilege; end if;
  select count(*) into monthly from private.brain_jobs
    where user_id=auth.uid() and started_at>=greatest(month_start,since);
  select count(*) into daily from private.brain_jobs
    where user_id=auth.uid() and started_at>=greatest(day_start,since);
  return jsonb_build_object('monthlyLimit',50,'monthlyRemaining',greatest(0,50-monthly),
                           'dailyLimit',20,'dailyUsed',daily,'since',since);
end;
$$;
revoke all on function public.brain_usage() from public, anon;
grant execute on function public.brain_usage() to authenticated;

-- The admission function below uses the same reset boundary as the display.
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
  if not exists(select 1 from private.brain_members m join auth.users u on u.id=m.user_id
    where m.user_id=p_user_id and m.status='approved' and u.email_confirmed_at is not null) then
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
    if (select count(*) from private.brain_jobs where user_id=p_user_id and started_at>=greatest(month_start,
        (select usage_reset_at from private.brain_members where user_id=p_user_id)))>=50
      or (select count(*) from private.brain_jobs where user_id=p_user_id and started_at>=greatest(day_start,
        (select usage_reset_at from private.brain_members where user_id=p_user_id)))>=20
      or (select count(*) from private.brain_jobs where user_id=p_user_id and started_at>now()-interval '1 minute')>=2
      or (select count(*) from private.brain_jobs where started_at>=month_start)>=1000 then
      return jsonb_build_object('state','limited');
    end if;
    update private.brain_jobs set result=null where result is not null and finished_at<now()-interval '24 hours';
    delete from private.brain_jobs where started_at<now()-interval '35 days';
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

revoke all on function public.brain_reserve(uuid,uuid,text) from public, anon, authenticated;
grant execute on function public.brain_reserve(uuid,uuid,text) to service_role;

create or replace function public.brain_openai_budget_ready()
returns jsonb language sql stable security definer set search_path = '' as $$
  select jsonb_build_object('migration','202609280005','allowanceKrw',34,
    'limitKrw',limit_krw,'ready',exists(select 1 from private.brain_accounting_reset))
  from private.brain_ai_budget where singleton=true;
$$;
revoke all on function public.brain_openai_budget_ready() from public, anon, authenticated;
grant execute on function public.brain_openai_budget_ready() to service_role;
notify pgrst, 'reload schema';
commit;
