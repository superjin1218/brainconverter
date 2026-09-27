-- Apply only after deployment approval. Existing RPC remains for older clients.
create index if not exists brain_members_page_order
  on private.brain_members(created_at desc, user_id desc);

create or replace function public.brain_members_page(
  p_status text default '', p_query text default '',
  p_before_created_at timestamptz default null, p_before_id uuid default null
)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare page jsonb; next_cursor jsonb := null;
begin
  if not exists(select 1 from private.brain_members
    where user_id=auth.uid() and status='approved' and role='admin') then
    raise insufficient_privilege;
  end if;
  if p_status is null or p_status not in ('','pending','approved','rejected','suspended')
    or p_query is null or length(p_query)>120
    or (p_before_created_at is null) <> (p_before_id is null) then
    raise exception 'invalid member page parameters';
  end if;
  select coalesce(jsonb_agg(row_to_json(rows)), '[]'::jsonb) into page from (
    select m.user_id as id, u.email, m.display_name as "displayName", m.status, m.role,
           (u.email_confirmed_at is not null) as "emailConfirmed", m.created_at as "createdAt"
    from private.brain_members m join auth.users u on u.id=m.user_id
    where (p_status='' or m.status=p_status)
      and (p_query='' or strpos(lower(m.display_name),lower(p_query))>0
           or strpos(lower(u.email),lower(p_query))>0)
      and (p_before_created_at is null
           or (m.created_at,m.user_id)<(p_before_created_at,p_before_id))
    order by m.created_at desc,m.user_id desc limit 51
  ) rows;
  if jsonb_array_length(page)>50 then
    page := page - 50;
    next_cursor := jsonb_build_object('createdAt',page->49->'createdAt','id',page->49->'id');
  end if;
  return jsonb_build_object('members',page,'nextCursor',next_cursor);
end;
$$;
revoke all on function public.brain_members_page(text,text,timestamptz,uuid) from public, anon;
grant execute on function public.brain_members_page(text,text,timestamptz,uuid) to authenticated;
