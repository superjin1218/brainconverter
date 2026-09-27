-- Upgrade after 202609270001_membership.sql. Safe to rerun; preserves members/jobs.
-- Browser polls with the SAME request ID/body. Only a claimed running job calls AI.
begin;
alter table private.brain_jobs drop constraint if exists brain_jobs_status_check;
alter table private.brain_jobs add constraint brain_jobs_status_check
  check (status in ('queued','running','done','error'));
alter table private.brain_jobs add column if not exists running_at timestamptz;
alter table private.brain_jobs add column if not exists last_seen_at timestamptz;
update private.brain_jobs set running_at=started_at where status='running' and running_at is null;
create index if not exists brain_jobs_queue on private.brain_jobs(started_at,request_id)
  where status='queued';

create or replace function public.brain_job(p_user_id uuid, p_request_id uuid)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare j private.brain_jobs; position integer;
begin
  select * into j from private.brain_jobs where request_id=p_request_id and user_id=p_user_id;
  if not found then return jsonb_build_object('state','missing'); end if;
  if j.status='queued' and j.started_at>now()-interval '10 minutes'
    and j.last_seen_at>now()-interval '120 seconds' then
    select count(*) into position from private.brain_jobs
      where status='queued' and started_at>now()-interval '10 minutes'
        and last_seen_at>now()-interval '120 seconds'
        and (started_at,request_id)<=(j.started_at,j.request_id);
    return jsonb_build_object('state','queued','queuePosition',position);
  end if;
  if j.status='running' and j.running_at>now()-interval '120 seconds' then
    return jsonb_build_object('state','running');
  end if;
  if j.status='done' and j.result is not null and j.finished_at>now()-interval '24 hours' then
    return jsonb_build_object('state','cached','result',j.result);
  end if;
  return jsonb_build_object('state','error');
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
    if (select count(*) from private.brain_jobs where user_id=p_user_id and started_at>=month_start)>=50
      or (select count(*) from private.brain_jobs where user_id=p_user_id and started_at>=day_start)>=20
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

revoke all on function public.brain_job(uuid,uuid) from public, anon, authenticated;
revoke all on function public.brain_reserve(uuid,uuid,text) from public, anon, authenticated;
grant execute on function public.brain_job(uuid,uuid) to service_role;
grant execute on function public.brain_reserve(uuid,uuid,text) to service_role;
notify pgrst, 'reload schema';
commit;
