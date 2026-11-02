-- Run manually BEFORE and AFTER the migration as the trusted SQL Editor role.
-- Save both result sets. This only reads catalogs/data; no application RPC runs.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '15s';

-- Inspect actual catalog columns; absence from information_schema alone may
-- also reflect the querying role's permissions.
select c.oid::regclass as table_name, a.attname as column_name,
       pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type
from pg_catalog.pg_class c
join pg_catalog.pg_namespace n on n.oid=c.relnamespace
join pg_catalog.pg_attribute a on a.attrelid=c.oid
where n.nspname='private' and c.relname in (
  'brain_members','brain_jobs','brain_approval_audit','brain_ai_budget','brain_ai_charges'
) and a.attnum>0 and not a.attisdropped
order by c.relname,a.attnum;

-- All overloads matter: flag an obsolete three-argument budget RPC rather
-- than silently dropping it or assuming default arguments resolve ambiguity.
select p.oid::regprocedure as function_signature,
       pg_catalog.pg_get_userbyid(p.proowner) as owner,
       p.prosecdef as security_definer, p.proconfig as function_settings,
       has_function_privilege('anon',p.oid,'EXECUTE') as anon_execute,
       has_function_privilege('authenticated',p.oid,'EXECUTE') as authenticated_execute,
       has_function_privilege('service_role',p.oid,'EXECUTE') as service_role_execute,
       exists (
         select 1 from pg_catalog.aclexplode(coalesce(
           p.proacl, pg_catalog.acldefault('f',p.proowner)
         )) acl where acl.grantee=0 and acl.privilege_type='EXECUTE'
       ) as public_execute,
       pg_catalog.pg_get_functiondef(p.oid) as definition
from pg_catalog.pg_proc p
join pg_catalog.pg_namespace n on n.oid=p.pronamespace
where (n.nspname='public' and p.proname in (
  'brain_set_member_status','brain_reserve','brain_budget_reserve',
  'brain_job','brain_usage','brain_budget_status','brain_auth_policy_ready'
)) or (n.nspname='private' and p.proname='brain_new_member')
order by n.nspname,p.proname,p.oid::regprocedure::text;

-- Confirm deployed 34-KRW allowance compatibility and existing budget ceiling.
select c.conrelid::regclass as table_name, c.conname,
       pg_catalog.pg_get_constraintdef(c.oid) as definition
from pg_catalog.pg_constraint c
where c.conrelid in ('private.brain_ai_charges'::regclass,
                    'private.brain_ai_budget'::regclass)
order by c.conrelid::regclass::text,c.conname;

select singleton,limit_krw,accounted_krw from private.brain_ai_budget;

-- Check private data access remains denied to both API user roles.
select c.oid::regclass as table_name, c.relrowsecurity as rls_enabled,
       has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE') as anon_any_crud,
       has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE')
         as authenticated_any_crud
from pg_catalog.pg_class c
join pg_catalog.pg_namespace n on n.oid=c.relnamespace
where n.nspname='private' and c.relkind='r' and c.relname in (
  'brain_members','brain_jobs','brain_approval_audit','brain_ai_budget','brain_ai_charges'
)
order by c.relname;

-- Defaults/trigger must remain pending/member and must not trust signup metadata.
select a.attname,pg_catalog.pg_get_expr(d.adbin,d.adrelid) as default_expression
from pg_catalog.pg_attribute a
join pg_catalog.pg_attrdef d on d.adrelid=a.attrelid and d.adnum=a.attnum
where a.attrelid='private.brain_members'::regclass and a.attname in ('status','role');

select t.tgname,t.tgenabled,pg_catalog.pg_get_triggerdef(t.oid) as definition
from pg_catalog.pg_trigger t
where t.tgrelid='auth.users'::regclass and t.tgname='brain_new_member';

-- Fingerprint every existing row including results, without printing user data.
-- Compare before/after only during a window without concurrent application writes.
-- MD5 is an accidental-change indicator, not a backup or a security attestation.
select 'brain_members' as table_name,count(*) as row_count,
       md5(coalesce(string_agg(row_hash,'' order by row_hash),'')) as content_fingerprint
from (select md5(to_jsonb(t)::text) as row_hash from private.brain_members t) rows
union all
select 'brain_jobs',count(*),md5(coalesce(string_agg(row_hash,'' order by row_hash),''))
from (select md5(to_jsonb(t)::text) as row_hash from private.brain_jobs t) rows
union all
select 'brain_approval_audit',count(*),md5(coalesce(string_agg(row_hash,'' order by row_hash),''))
from (select md5(to_jsonb(t)::text) as row_hash from private.brain_approval_audit t) rows
union all
select 'brain_ai_budget',count(*),md5(coalesce(string_agg(row_hash,'' order by row_hash),''))
from (select md5(to_jsonb(t)::text) as row_hash from private.brain_ai_budget t) rows
union all
select 'brain_ai_charges',count(*),md5(coalesce(string_agg(row_hash,'' order by row_hash),''))
from (select md5(to_jsonb(t)::text) as row_hash from private.brain_ai_charges t) rows
order by table_name;

rollback;
