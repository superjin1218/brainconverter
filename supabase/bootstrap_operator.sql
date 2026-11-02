-- Trusted SQL Editor only. Verify the operator through a separate trusted channel,
-- then SET brain.bootstrap_operator_id to that account's UUID in this session.
-- Email addresses/auto-confirm timestamps cannot establish identity.
begin;
do $$
declare operator_id uuid;
begin
  operator_id := nullif(current_setting('brain.bootstrap_operator_id',true),'')::uuid;
  if operator_id is null or not exists(select 1 from auth.users where id=operator_id) then
    raise exception 'explicit independently verified operator UUID required';
  end if;
  update private.brain_members set role='admin', status='approved', updated_at=now()
  where user_id=operator_id;
  if not found then raise exception 'apply membership migration first'; end if;
end;
$$;
commit;
