-- OpenAI GPT-5.4 mini reserves 34 KRW per attempt at 2,000 KRW/USD.
-- Historical charges (4 KRW) and all cumulative spending remain unchanged.
-- New reservations and status use only the current OpenAI allowance.
begin;
alter table private.brain_ai_charges
  drop constraint if exists brain_ai_charges_allowance_krw_check;
alter table private.brain_ai_charges
  add constraint brain_ai_charges_allowance_krw_check check (allowance_krw in (4,34));
drop function if exists public.brain_budget_reserve(uuid,uuid,text);
drop function if exists public.brain_budget_status();

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
  if b.accounted_krw+p_allowance_krw>b.limit_krw then
    return jsonb_build_object('state','budget_exhausted');
  end if;
  update private.brain_ai_budget set accounted_krw=accounted_krw+p_allowance_krw where singleton=true;
  insert into private.brain_ai_charges(request_id,allowance_krw)
    values(p_request_id,p_allowance_krw);
  return jsonb_build_object('state','reserved');
end;
$$;
revoke all on function public.brain_budget_reserve(uuid,uuid,text,integer) from public, anon, authenticated;
grant execute on function public.brain_budget_reserve(uuid,uuid,text,integer) to service_role;

create or replace function public.brain_budget_status(p_allowance_krw integer default 34)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare b private.brain_ai_budget;
begin
  if not exists(select 1 from private.brain_members
    where user_id=auth.uid() and status='approved' and role='admin') then
    raise insufficient_privilege;
  end if;
  if p_allowance_krw is null or p_allowance_krw <> 34 then
    raise exception 'invalid allowance';
  end if;
  select * into b from private.brain_ai_budget where singleton=true;
  if not found then raise exception 'budget unavailable'; end if;
  return jsonb_build_object('limitKrw',b.limit_krw,'accountedKrw',b.accounted_krw,
    'remainingKrw',b.limit_krw-b.accounted_krw,'stopped',b.accounted_krw+p_allowance_krw>b.limit_krw,
    'period','cumulative','allowancePerAttemptKrw',p_allowance_krw);
end;
$$;
revoke all on function public.brain_budget_status(integer) from public, anon;
grant execute on function public.brain_budget_status(integer) to authenticated;

-- Deployment preflight: service-only metadata query, no reservation or AI call.
create or replace function public.brain_openai_budget_ready()
returns jsonb language sql stable security definer set search_path = '' as $$
  select jsonb_build_object('migration','202609280004','allowanceKrw',34,
    'limitKrw',limit_krw,'ready',true)
  from private.brain_ai_budget where singleton=true;
$$;
revoke all on function public.brain_openai_budget_ready() from public, anon, authenticated;
grant execute on function public.brain_openai_budget_ready() to service_role;

notify pgrst, 'reload schema';
commit;
