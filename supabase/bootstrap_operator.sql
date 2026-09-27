-- Run only after seungzookim@gmail.com has signed up and confirmed the email.
-- This is a trusted dashboard operation; the signup form never grants admin.
begin;
do $$
declare operator_id uuid;
begin
  select id into operator_id from auth.users
  where lower(email) = 'seungzookim@gmail.com' and email_confirmed_at is not null;
  if operator_id is null then
    raise exception 'confirmed operator account required';
  end if;
  update private.brain_members set role='admin', status='approved', updated_at=now()
  where user_id=operator_id;
  if not found then raise exception 'apply membership migration first'; end if;
end;
$$;
commit;
