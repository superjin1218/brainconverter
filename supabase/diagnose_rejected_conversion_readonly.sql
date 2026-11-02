-- Diagnostic for the request observed in the application journal.
-- Run in the existing project's SQL Editor. Does not call application RPCs,
-- reserve quota/budget, run migrations, or expose account/token/strategy text.
begin transaction read only;
set local statement_timeout = '10s';

with failed_request as (
  select status, finished_at, result
  from private.brain_jobs
  where result ->> 'requestId' = '7b5b42d4-3c4f-4c46-9efa-877fd60b6580'
  order by finished_at desc
  limit 1
)
select
  status as storage_status,
  finished_at,
  result ->> 'status' as conversion_status,
  result #>> '{strategyIR,schemaVersion}' as schema_version,
  result #>> '{strategyIR,status}' as ai_interpretation_status,
  result #>> '{strategyIR,reason}' as ai_interpretation_reason,
  case when jsonb_typeof(result #> '{strategyIR,metrics}') = 'array'
    then jsonb_array_length(result #> '{strategyIR,metrics}')
    else null end as metric_count,
  result -> 'warnings' as rejection_details,
  result -> 'unresolvedSettings' as unresolved_settings,
  result -> 'validation' as validation,
  result -> 'usage' as usage,
  case
    when result #>> '{strategyIR,status}' in ('ambiguous', 'unsupported')
      then 'AI interpretation rejected before compilation'
    when result #>> '{strategyIR,status}' = 'ok'
      and result #> '{strategyIR,metrics}' = '[]'::jsonb
      then 'AI returned an empty measurement plan'
    else 'Inspect rejection_details, validation and unresolved_settings'
  end as diagnostic_branch
from failed_request;

rollback;
