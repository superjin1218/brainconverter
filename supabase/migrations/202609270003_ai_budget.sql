-- Apply after membership + concurrency_queue. Safe to rerun; never resets spending.
-- A conservative upper allowance, not an invoice: fixed Muse text request <=16KB,
-- <=1024 output tokens, $0.10/$0.20 per 1M tokens, <=$0.002/request.
-- Account at 2,000 KRW/USD => 4 KRW before each paid attempt, including failures.
-- No refunds/reset: unknown billing and month changes cannot reopen the budget.
begin;
create table if not exists private.brain_ai_budget (
  singleton boolean primary key default true check (singleton),
  limit_krw integer not null default 20000 check (limit_krw = 20000),
  accounted_krw integer not null default 0 check (accounted_krw between 0 and 20000)
);
alter table private.brain_ai_budget enable row level security;
revoke all on private.brain_ai_budget from public, anon, authenticated;

-- Deliberately no FK/cascade to jobs or users: cleanup/deletion must not refund money.
create table if not exists private.brain_ai_charges (
  request_id uuid primary key,
  allowance_krw integer not null default 4 check (allowance_krw = 4),
  created_at timestamptz not null default now()
);
alter table private.brain_ai_charges enable row level security;
revoke all on private.brain_ai_charges from public, anon, authenticated;
insert into private.brain_ai_budget(singleton,accounted_krw)
  select true,coalesce(sum(allowance_krw),0) from private.brain_ai_charges
  on conflict do nothing;

create or replace function public.brain_budget_reserve(
  p_user_id uuid, p_request_id uuid, p_request_hash text
)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare b private.brain_ai_budget;
begin
  -- Shared with job admission: all Vercel instances reserve atomically.
  perform pg_catalog.pg_advisory_xact_lock(7219032701::bigint);
  if not exists(select 1 from private.brain_members m join auth.users u on u.id=m.user_id
    where m.user_id=p_user_id and m.status='approved' and u.email_confirmed_at is not null)
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
  if b.accounted_krw+4>b.limit_krw then
    return jsonb_build_object('state','budget_exhausted');
  end if;
  update private.brain_ai_budget set accounted_krw=accounted_krw+4 where singleton=true;
  insert into private.brain_ai_charges(request_id) values(p_request_id);
  return jsonb_build_object('state','reserved');
end;
$$;
revoke all on function public.brain_budget_reserve(uuid,uuid,text) from public, anon, authenticated;
grant execute on function public.brain_budget_reserve(uuid,uuid,text) to service_role;

create or replace function public.brain_budget_status()
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare b private.brain_ai_budget;
begin
  if not exists(select 1 from private.brain_members
    where user_id=auth.uid() and status='approved' and role='admin') then
    raise insufficient_privilege;
  end if;
  select * into b from private.brain_ai_budget where singleton=true;
  if not found then raise exception 'budget unavailable'; end if;
  return jsonb_build_object('limitKrw',b.limit_krw,'accountedKrw',b.accounted_krw,
    'remainingKrw',b.limit_krw-b.accounted_krw,'stopped',b.accounted_krw+4>b.limit_krw,
    'period','cumulative','allowancePerAttemptKrw',4);
end;
$$;
revoke all on function public.brain_budget_status() from public, anon;
grant execute on function public.brain_budget_status() to authenticated;
notify pgrst, 'reload schema';
commit;
