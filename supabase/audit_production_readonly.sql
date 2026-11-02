-- Run manually in this project's SQL Editor when a full live catalog audit is needed.
-- This file only reads catalogs and aggregate counts. It never invokes application RPCs.
begin transaction read only;
set local statement_timeout = '15s';

-- All five tables should exist, use RLS, and deny anon/authenticated CRUD.
select n.nspname as schema_name, c.relname as table_name,
       c.relrowsecurity as rls_enabled, c.relforcerowsecurity as force_rls,
       has_schema_privilege('anon', n.oid, 'USAGE') as anon_schema_usage,
       has_schema_privilege('authenticated', n.oid, 'USAGE') as member_schema_usage,
       has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE') as anon_any_crud,
       has_table_privilege('authenticated', c.oid, 'SELECT,INSERT,UPDATE,DELETE')
         as member_any_crud
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'private' and c.relkind = 'r' and c.relname in
  ('brain_members', 'brain_approval_audit', 'brain_jobs', 'brain_ai_budget', 'brain_ai_charges')
order by c.relname;

-- Examine every overload, including obsolete budget function signatures.
-- All anon_exec values should be false. Job/budget-reservation/readiness RPCs
-- must also have member_exec=false and server_exec=true.
select n.nspname as schema_name, p.proname as function_name,
       pg_get_function_identity_arguments(p.oid) as arguments,
       p.prosecdef as security_definer,
       p.provolatile as volatility,
       p.proconfig as function_settings,
       has_function_privilege('anon', p.oid, 'EXECUTE') as anon_exec,
       has_function_privilege('authenticated', p.oid, 'EXECUTE') as member_exec,
       has_function_privilege('service_role', p.oid, 'EXECUTE') as server_exec
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname in ('public', 'private') and p.proname like 'brain_%'
order by n.nspname, p.proname, arguments;

-- Review policy predicates; private table privileges must still be denied.
select schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
from pg_policies where schemaname = 'private' and tablename like 'brain_%'
order by tablename, policyname;

-- Membership must be created by the trigger, with database-owned defaults.
select t.tgname, t.tgenabled, pg_get_triggerdef(t.oid) as definition
from pg_trigger t join pg_class c on c.oid = t.tgrelid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'auth' and c.relname = 'users' and t.tgname = 'brain_new_member';

select a.attname, pg_get_expr(d.adbin, d.adrelid) as default_expression
from pg_attribute a join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
where a.attrelid = 'private.brain_members'::regclass and a.attname in ('status', 'role');

-- Source checks are indicators; review any false values in the function definition.
select p.proname,
       strpos(pg_get_functiondef(p.oid), 'auth.uid()') > 0 as checks_database_identity,
       strpos(pg_get_functiondef(p.oid), '''admin''') > 0 as contains_admin_check,
       strpos(pg_get_functiondef(p.oid), '''approved''') > 0 as contains_approval_check,
       strpos(pg_get_functiondef(p.oid), 'email_confirmed_at') > 0 as checks_email_confirmation
from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.proname in
  ('brain_access', 'brain_members', 'brain_members_page', 'brain_set_member_status');

-- Counts only: no email addresses, user IDs, strategy text, results, or tokens.
select status, role, count(*) as member_count
from private.brain_members group by status, role order by status, role;

rollback;
