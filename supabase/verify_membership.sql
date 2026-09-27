-- Read-only deployment check. No account details, tokens, or strategy text.
select c.relname as table_name, c.relrowsecurity as rls,
  has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE') as anon_crud,
  has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE') as member_crud
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where n.nspname='private' and c.relname in
  ('brain_members','brain_jobs','brain_approval_audit')
order by c.relname;

select p.proname as function_name, p.prosecdef as security_definer,
  has_function_privilege('anon',p.oid,'EXECUTE') as anon_exec,
  has_function_privilege('authenticated',p.oid,'EXECUTE') as member_exec,
  has_function_privilege('service_role',p.oid,'EXECUTE') as server_exec
from pg_proc p join pg_namespace n on n.oid=p.pronamespace
where n.nspname='public' and p.proname like 'brain_%'
order by p.proname;

select count(*) as accounts, count(*) filter(where status='approved') as approved,
  count(*) filter(where role='admin') as operators
from private.brain_members;

-- Concurrency/queue upgrade: no jobs or AI requests are created by this check.
with definition as (
  select pg_get_functiondef('public.brain_reserve(uuid,uuid,text)'::regprocedure) as source
)
select substring(source from 'max_running constant integer := ([0-9]+)')::integer as max_running,
  strpos(source, '''queued''')>0 as queue_enabled,
  strpos(source, '>=1000')>0 and strpos(source, '>=50')>0
    and strpos(source, '>=20')>0 and strpos(source, '>=2')>0 as quotas_unchanged,
  not has_function_privilege('anon','public.brain_reserve(uuid,uuid,text)','EXECUTE')
    and not has_function_privilege('authenticated','public.brain_reserve(uuid,uuid,text)','EXECUTE')
    and has_function_privilege('service_role','public.brain_reserve(uuid,uuid,text)','EXECUTE') as server_only
from definition;
