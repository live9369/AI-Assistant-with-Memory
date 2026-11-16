-- TL-EVAL-0.1 independent evaluation database. No runtime instance tables.

PRAGMA foreign_keys=ON;

CREATE TABLE tle_run (
 contract TEXT NOT NULL CHECK(contract='TL-EVAL-0.1'),
 schema_revision INTEGER NOT NULL CHECK(schema_revision=1),
 id TEXT NOT NULL CHECK(length(id) BETWEEN 1 AND 128 AND id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 run_id TEXT NOT NULL CHECK(length(run_id) BETWEEN 1 AND 128 AND run_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 created_at TEXT NOT NULL CHECK(length(created_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at) IS created_at),
 protocol_ref TEXT NOT NULL CHECK(json_valid(protocol_ref)),
 code_digest TEXT NOT NULL CHECK(json_valid(code_digest)),
 configuration_ref TEXT NOT NULL CHECK(json_valid(configuration_ref)),
 prompt_refs TEXT NOT NULL CHECK(json_valid(prompt_refs)),
 model_ref TEXT NOT NULL CHECK(json_valid(model_ref)),
 route TEXT NOT NULL CHECK(json_valid(route)),
 materials_manifest TEXT NOT NULL CHECK(json_valid(materials_manifest)),
 review_roster TEXT NOT NULL CHECK(json_valid(review_roster)),
 price_evidence TEXT NOT NULL CHECK(json_valid(price_evidence)),
 currency TEXT NOT NULL CHECK(json_valid(currency)),
 money_limit TEXT NOT NULL CHECK(json_valid(money_limit)),
 account_limits TEXT NOT NULL CHECK(json_valid(account_limits)),
 mechanism_manifest TEXT NOT NULL CHECK(json_valid(mechanism_manifest)),
 arm_seed INTEGER NOT NULL CHECK(arm_seed=20261109),
 analysis_seed INTEGER NOT NULL CHECK(analysis_seed=20261108),
 bootstrap_samples INTEGER NOT NULL CHECK(bootstrap_samples=10000),
 concurrency_limit INTEGER NOT NULL CHECK(concurrency_limit=4),
 deadline TEXT NOT NULL CHECK(length(deadline)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',deadline) IS deadline),
 state TEXT NOT NULL CHECK(state IN ('blocked_before_start','registered','mechanism','dev','formal','stopped','completed','incomplete','failed')),
 budget_ref TEXT NOT NULL CHECK(json_valid(budget_ref)),
 PRIMARY KEY(run_id,id),
 CHECK(run_id=id)
) STRICT;

CREATE TRIGGER tle_run_identity BEFORE UPDATE ON tle_run WHEN NEW.id<>OLD.id OR NEW.run_id<>OLD.run_id OR NEW.contract<>OLD.contract OR NEW.schema_revision<>OLD.schema_revision OR NEW.created_at<>OLD.created_at BEGIN SELECT RAISE(ABORT,'immutable evaluation identity'); END;

CREATE TABLE tle_case (
 contract TEXT NOT NULL CHECK(contract='TL-EVAL-0.1'),
 schema_revision INTEGER NOT NULL CHECK(schema_revision=1),
 id TEXT NOT NULL CHECK(length(id) BETWEEN 1 AND 128 AND id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 run_id TEXT NOT NULL CHECK(length(run_id) BETWEEN 1 AND 128 AND run_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 created_at TEXT NOT NULL CHECK(length(created_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at) IS created_at),
 partition TEXT NOT NULL CHECK(partition IN ('DEV','MECH','TARGET','RETENTION')),
 category TEXT NOT NULL,
 source_cluster_id TEXT NOT NULL CHECK(length(source_cluster_id) BETWEEN 1 AND 128 AND source_cluster_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 template_family TEXT NOT NULL CHECK(json_valid(template_family)),
 learning_input_ref TEXT NOT NULL CHECK(json_valid(learning_input_ref)),
 truth_ref TEXT NOT NULL CHECK(json_valid(truth_ref)),
 base_snapshot_ref TEXT NOT NULL CHECK(json_valid(base_snapshot_ref)),
 PRIMARY KEY(run_id,id),
 FOREIGN KEY(run_id,run_id) REFERENCES tle_run(run_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(run_id,partition,id)
) STRICT;

CREATE TRIGGER tle_case_identity BEFORE UPDATE ON tle_case WHEN NEW.id<>OLD.id OR NEW.run_id<>OLD.run_id OR NEW.contract<>OLD.contract OR NEW.schema_revision<>OLD.schema_revision OR NEW.created_at<>OLD.created_at BEGIN SELECT RAISE(ABORT,'immutable evaluation identity'); END;

CREATE TABLE tle_query (
 contract TEXT NOT NULL CHECK(contract='TL-EVAL-0.1'),
 schema_revision INTEGER NOT NULL CHECK(schema_revision=1),
 id TEXT NOT NULL CHECK(length(id) BETWEEN 1 AND 128 AND id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 run_id TEXT NOT NULL CHECK(length(run_id) BETWEEN 1 AND 128 AND run_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 created_at TEXT NOT NULL CHECK(length(created_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at) IS created_at),
 case_id TEXT NOT NULL CHECK(length(case_id) BETWEEN 1 AND 128 AND case_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 query_kind TEXT NOT NULL CHECK(query_kind IN ('same_observation','new_question','boundary','retention')),
 input_ref TEXT NOT NULL CHECK(json_valid(input_ref)),
 truth_ref TEXT NOT NULL CHECK(json_valid(truth_ref)),
 k INTEGER NOT NULL CHECK(k=5),
 PRIMARY KEY(run_id,id),
 FOREIGN KEY(run_id,run_id) REFERENCES tle_run(run_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(run_id,case_id) REFERENCES tle_case(run_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(run_id,case_id,query_kind),
 UNIQUE(run_id,case_id,id)
) STRICT;

CREATE TRIGGER tle_query_identity BEFORE UPDATE ON tle_query WHEN NEW.id<>OLD.id OR NEW.run_id<>OLD.run_id OR NEW.contract<>OLD.contract OR NEW.schema_revision<>OLD.schema_revision OR NEW.created_at<>OLD.created_at BEGIN SELECT RAISE(ABORT,'immutable evaluation identity'); END;

CREATE TABLE tle_trial (
 contract TEXT NOT NULL CHECK(contract='TL-EVAL-0.1'),
 schema_revision INTEGER NOT NULL CHECK(schema_revision=1),
 id TEXT NOT NULL CHECK(length(id) BETWEEN 1 AND 128 AND id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 run_id TEXT NOT NULL CHECK(length(run_id) BETWEEN 1 AND 128 AND run_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 created_at TEXT NOT NULL CHECK(length(created_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at) IS created_at),
 logical_trial_id TEXT NOT NULL CHECK(length(logical_trial_id) BETWEEN 1 AND 128 AND logical_trial_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 case_id TEXT NOT NULL CHECK(length(case_id) BETWEEN 1 AND 128 AND case_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 arm TEXT NOT NULL CHECK(arm IN ('E','N','O')),
 repeat INTEGER NOT NULL CHECK(repeat>=1 AND repeat<=3),
 occurrence TEXT NOT NULL CHECK(occurrence IN ('original','replacement')),
 replacement_of TEXT NOT NULL CHECK(json_valid(replacement_of)),
 snapshot_ref TEXT NOT NULL CHECK(json_valid(snapshot_ref)),
 instance_ref TEXT NOT NULL CHECK(json_valid(instance_ref)),
 phase TEXT NOT NULL CHECK(phase IN ('registered','learning','querying','finished')),
 status TEXT NOT NULL CHECK(status IN ('registered','running','completed','failed','stopped','not_run','infrastructure_invalid','incomplete')),
 assigned_order INTEGER NOT NULL CHECK(assigned_order>=0),
 outcome_ref TEXT NOT NULL CHECK(json_valid(outcome_ref)),
 budget_ref TEXT NOT NULL CHECK(json_valid(budget_ref)),
 PRIMARY KEY(run_id,id),
 FOREIGN KEY(run_id,run_id) REFERENCES tle_run(run_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(run_id,case_id) REFERENCES tle_case(run_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(run_id,logical_trial_id) REFERENCES tle_trial(run_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(run_id,case_id,arm,repeat,occurrence),
 UNIQUE(run_id,logical_trial_id,id),
 CHECK((occurrence='original' AND logical_trial_id=id AND json_extract(replacement_of,'$.status')='not_applicable') OR (occurrence='replacement' AND logical_trial_id<>id AND json_extract(replacement_of,'$.status')='known' AND json_extract(replacement_of,'$.value.id')=logical_trial_id))
) STRICT;

CREATE TRIGGER tle_trial_identity BEFORE UPDATE ON tle_trial WHEN NEW.id<>OLD.id OR NEW.run_id<>OLD.run_id OR NEW.contract<>OLD.contract OR NEW.schema_revision<>OLD.schema_revision OR NEW.created_at<>OLD.created_at BEGIN SELECT RAISE(ABORT,'immutable evaluation identity'); END;

CREATE TABLE tle_attempt (
 contract TEXT NOT NULL CHECK(contract='TL-EVAL-0.1'),
 schema_revision INTEGER NOT NULL CHECK(schema_revision=1),
 id TEXT NOT NULL CHECK(length(id) BETWEEN 1 AND 128 AND id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 run_id TEXT NOT NULL CHECK(length(run_id) BETWEEN 1 AND 128 AND run_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 created_at TEXT NOT NULL CHECK(length(created_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at) IS created_at),
 trial_id TEXT NOT NULL CHECK(length(trial_id) BETWEEN 1 AND 128 AND trial_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 logical_trial_id TEXT NOT NULL CHECK(length(logical_trial_id) BETWEEN 1 AND 128 AND logical_trial_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 phase TEXT NOT NULL CHECK(phase IN ('learn','query')),
 query_id TEXT NOT NULL CHECK(json_valid(query_id)),
 request_ref TEXT NOT NULL CHECK(json_valid(request_ref)),
 reservation_ref TEXT NOT NULL CHECK(json_valid(reservation_ref)),
 actual_callback_entry TEXT NOT NULL CHECK(json_valid(actual_callback_entry)),
 receipt_ref TEXT NOT NULL CHECK(json_valid(receipt_ref)),
 outcome TEXT NOT NULL CHECK(outcome IN ('prepared','in_flight','received','failed','unknown','stopped')),
 usage_ref TEXT NOT NULL CHECK(json_valid(usage_ref)),
 PRIMARY KEY(run_id,id),
 FOREIGN KEY(run_id,run_id) REFERENCES tle_run(run_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(run_id,logical_trial_id,trial_id) REFERENCES tle_trial(run_id,logical_trial_id,id) DEFERRABLE INITIALLY DEFERRED,
 CHECK((phase='learn' AND json_extract(query_id,'$.status')='not_applicable') OR (phase='query' AND json_extract(query_id,'$.status')='known' AND json_type(query_id,'$.value')='text'))
) STRICT;

CREATE TRIGGER tle_attempt_identity BEFORE UPDATE ON tle_attempt WHEN NEW.id<>OLD.id OR NEW.run_id<>OLD.run_id OR NEW.contract<>OLD.contract OR NEW.schema_revision<>OLD.schema_revision OR NEW.created_at<>OLD.created_at BEGIN SELECT RAISE(ABORT,'immutable evaluation identity'); END;

CREATE TABLE tle_label (
 contract TEXT NOT NULL CHECK(contract='TL-EVAL-0.1'),
 schema_revision INTEGER NOT NULL CHECK(schema_revision=1),
 id TEXT NOT NULL CHECK(length(id) BETWEEN 1 AND 128 AND id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 run_id TEXT NOT NULL CHECK(length(run_id) BETWEEN 1 AND 128 AND run_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 created_at TEXT NOT NULL CHECK(length(created_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at) IS created_at),
 query_id TEXT NOT NULL CHECK(length(query_id) BETWEEN 1 AND 128 AND query_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 claim_id TEXT NOT NULL CHECK(length(claim_id) BETWEEN 1 AND 128 AND claim_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 support TEXT NOT NULL CHECK(support IN ('supported','unsupported','conflicting','unknown')),
 expected_scope TEXT NOT NULL CHECK(json_valid(expected_scope)),
 expected_slots TEXT NOT NULL CHECK(json_valid(expected_slots)),
 relevant_refs TEXT NOT NULL CHECK(json_valid(relevant_refs)),
 expected_terminal TEXT NOT NULL,
 major_error INTEGER NOT NULL CHECK(major_error IN (0,1)),
 rationale TEXT NOT NULL,
 evidence_refs TEXT NOT NULL CHECK(json_valid(evidence_refs)),
 author_id TEXT NOT NULL CHECK(length(author_id) BETWEEN 1 AND 128 AND author_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 reviewer_id TEXT NOT NULL CHECK(length(reviewer_id) BETWEEN 1 AND 128 AND reviewer_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 PRIMARY KEY(run_id,id),
 FOREIGN KEY(run_id,run_id) REFERENCES tle_run(run_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(run_id,query_id) REFERENCES tle_query(run_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(run_id,query_id,claim_id),
 CHECK(author_id<>reviewer_id)
) STRICT;

CREATE TRIGGER tle_label_identity BEFORE UPDATE ON tle_label WHEN NEW.id<>OLD.id OR NEW.run_id<>OLD.run_id OR NEW.contract<>OLD.contract OR NEW.schema_revision<>OLD.schema_revision OR NEW.created_at<>OLD.created_at BEGIN SELECT RAISE(ABORT,'immutable evaluation identity'); END;

CREATE TABLE tle_review (
 contract TEXT NOT NULL CHECK(contract='TL-EVAL-0.1'),
 schema_revision INTEGER NOT NULL CHECK(schema_revision=1),
 id TEXT NOT NULL CHECK(length(id) BETWEEN 1 AND 128 AND id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 run_id TEXT NOT NULL CHECK(length(run_id) BETWEEN 1 AND 128 AND run_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 created_at TEXT NOT NULL CHECK(length(created_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at) IS created_at),
 blind_item_id TEXT NOT NULL CHECK(length(blind_item_id) BETWEEN 1 AND 128 AND blind_item_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 reviewer_id TEXT NOT NULL CHECK(length(reviewer_id) BETWEEN 1 AND 128 AND reviewer_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 label_ref TEXT NOT NULL CHECK(json_valid(label_ref)),
 original_rating TEXT NOT NULL CHECK(original_rating IN ('pass','fail','not_evaluable')),
 reason TEXT NOT NULL,
 locator TEXT NOT NULL CHECK(json_valid(locator)),
 resolution_ref TEXT NOT NULL CHECK(json_valid(resolution_ref)),
 unblinding_risk TEXT NOT NULL CHECK(json_valid(unblinding_risk)),
 PRIMARY KEY(run_id,id),
 FOREIGN KEY(run_id,run_id) REFERENCES tle_run(run_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(run_id,blind_item_id,reviewer_id)
) STRICT;

CREATE TRIGGER tle_review_identity BEFORE UPDATE ON tle_review WHEN NEW.id<>OLD.id OR NEW.run_id<>OLD.run_id OR NEW.contract<>OLD.contract OR NEW.schema_revision<>OLD.schema_revision OR NEW.created_at<>OLD.created_at BEGIN SELECT RAISE(ABORT,'immutable evaluation identity'); END;

CREATE TABLE tle_fault (
 contract TEXT NOT NULL CHECK(contract='TL-EVAL-0.1'),
 schema_revision INTEGER NOT NULL CHECK(schema_revision=1),
 id TEXT NOT NULL CHECK(length(id) BETWEEN 1 AND 128 AND id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 run_id TEXT NOT NULL CHECK(length(run_id) BETWEEN 1 AND 128 AND run_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 created_at TEXT NOT NULL CHECK(length(created_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at) IS created_at),
 mechanism_case_id TEXT NOT NULL CHECK(length(mechanism_case_id) BETWEEN 1 AND 128 AND mechanism_case_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 decision_refs TEXT NOT NULL CHECK(json_valid(decision_refs)),
 metric_ids TEXT NOT NULL CHECK(json_valid(metric_ids)),
 fixture_ref TEXT NOT NULL CHECK(json_valid(fixture_ref)),
 injection_stage TEXT NOT NULL,
 planned_order_ref TEXT NOT NULL CHECK(json_valid(planned_order_ref)),
 actual_trace_ref TEXT NOT NULL CHECK(json_valid(actual_trace_ref)),
 expected_terminal TEXT NOT NULL,
 actual_terminal TEXT NOT NULL CHECK(json_valid(actual_terminal)),
 status TEXT NOT NULL CHECK(status IN ('planned','running','completed','not_run','failed')),
 PRIMARY KEY(run_id,id),
 FOREIGN KEY(run_id,run_id) REFERENCES tle_run(run_id,id) DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TRIGGER tle_fault_identity BEFORE UPDATE ON tle_fault WHEN NEW.id<>OLD.id OR NEW.run_id<>OLD.run_id OR NEW.contract<>OLD.contract OR NEW.schema_revision<>OLD.schema_revision OR NEW.created_at<>OLD.created_at BEGIN SELECT RAISE(ABORT,'immutable evaluation identity'); END;

CREATE TABLE tle_usage (
 contract TEXT NOT NULL CHECK(contract='TL-EVAL-0.1'),
 schema_revision INTEGER NOT NULL CHECK(schema_revision=1),
 id TEXT NOT NULL CHECK(length(id) BETWEEN 1 AND 128 AND id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 run_id TEXT NOT NULL CHECK(length(run_id) BETWEEN 1 AND 128 AND run_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 created_at TEXT NOT NULL CHECK(length(created_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at) IS created_at),
 logical_trial_id TEXT NOT NULL CHECK(length(logical_trial_id) BETWEEN 1 AND 128 AND logical_trial_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 attempt_ref TEXT NOT NULL CHECK(json_valid(attempt_ref)),
 reservation_ref TEXT NOT NULL CHECK(json_valid(reservation_ref)),
 input_tokens TEXT NOT NULL CHECK(json_valid(input_tokens)),
 output_tokens TEXT NOT NULL CHECK(json_valid(output_tokens)),
 tool_calls TEXT NOT NULL CHECK(json_valid(tool_calls)),
 elapsed_ms TEXT NOT NULL CHECK(json_valid(elapsed_ms)),
 currency_amount TEXT NOT NULL CHECK(json_valid(currency_amount)),
 evidence_refs TEXT NOT NULL CHECK(json_valid(evidence_refs)),
 PRIMARY KEY(run_id,id),
 FOREIGN KEY(run_id,run_id) REFERENCES tle_run(run_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(run_id,logical_trial_id) REFERENCES tle_trial(run_id,id) DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TRIGGER tle_usage_identity BEFORE UPDATE ON tle_usage WHEN NEW.id<>OLD.id OR NEW.run_id<>OLD.run_id OR NEW.contract<>OLD.contract OR NEW.schema_revision<>OLD.schema_revision OR NEW.created_at<>OLD.created_at BEGIN SELECT RAISE(ABORT,'immutable evaluation identity'); END;

CREATE TABLE tle_metric (
 contract TEXT NOT NULL CHECK(contract='TL-EVAL-0.1'),
 schema_revision INTEGER NOT NULL CHECK(schema_revision=1),
 id TEXT NOT NULL CHECK(length(id) BETWEEN 1 AND 128 AND id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 run_id TEXT NOT NULL CHECK(length(run_id) BETWEEN 1 AND 128 AND run_id NOT GLOB '*[^A-Za-z0-9_.:-]*'),
 created_at TEXT NOT NULL CHECK(length(created_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at) IS created_at),
 metric_id TEXT NOT NULL CHECK(metric_id IN ('TL01','TL02','TL03','TL04','TL05','TL06','TL07','TL08','TL09','TL10','TL11','TL12','TL13','TL14','TL15','TL16')),
 metric_version TEXT NOT NULL,
 partition TEXT NOT NULL CHECK(partition IN ('DEV','MECH','TARGET','RETENTION')),
 arm TEXT NOT NULL CHECK(arm IN ('E','N','O','paired')),
 case_id TEXT NOT NULL CHECK(json_valid(case_id)),
 trial_id TEXT NOT NULL CHECK(json_valid(trial_id)),
 level TEXT NOT NULL CHECK(level IN ('claim','work','query','trial','case','partition','run')),
 numerator TEXT NOT NULL CHECK(json_valid(numerator)),
 denominator TEXT NOT NULL CHECK(json_valid(denominator)),
 samples_ref TEXT NOT NULL CHECK(json_valid(samples_ref)),
 unit TEXT NOT NULL,
 coverage TEXT NOT NULL CHECK(json_valid(coverage)),
 method TEXT NOT NULL CHECK(json_valid(method)),
 source_refs TEXT NOT NULL CHECK(json_valid(source_refs)),
 status TEXT NOT NULL CHECK(status IN ('not_run','missing','not_applicable','insufficient_sample','not_evaluable','measured')),
 interval TEXT NOT NULL CHECK(json_valid(interval)),
 judgment TEXT NOT NULL CHECK(judgment IN ('pass','fail','incomplete','not_evaluable','exploratory')),
 scope TEXT NOT NULL CHECK(json_valid(scope)),
 PRIMARY KEY(run_id,id),
 FOREIGN KEY(run_id,run_id) REFERENCES tle_run(run_id,id) DEFERRABLE INITIALLY DEFERRED,
 CHECK(NOT(json_extract(numerator,'$.status')='known' AND json_extract(denominator,'$.status')='known') OR (json_type(numerator,'$.value')='integer' AND json_type(denominator,'$.value')='integer' AND json_extract(numerator,'$.value')>=0 AND json_extract(numerator,'$.value')<=json_extract(denominator,'$.value'))),
 CHECK(NOT(json_extract(denominator,'$.status')='known' AND json_extract(denominator,'$.value')=0) OR (status='not_applicable' AND judgment<>'pass'))
) STRICT;

CREATE TRIGGER tle_metric_identity BEFORE UPDATE ON tle_metric WHEN NEW.id<>OLD.id OR NEW.run_id<>OLD.run_id OR NEW.contract<>OLD.contract OR NEW.schema_revision<>OLD.schema_revision OR NEW.created_at<>OLD.created_at BEGIN SELECT RAISE(ABORT,'immutable evaluation identity'); END;

CREATE TRIGGER tle_cluster_insert BEFORE INSERT ON tle_case WHEN NEW.partition<>'MECH' AND EXISTS(SELECT 1 FROM tle_case c WHERE c.run_id=NEW.run_id AND c.id<>NEW.id AND c.source_cluster_id=NEW.source_cluster_id AND c.partition<>'MECH' AND c.partition<>NEW.partition) BEGIN SELECT RAISE(ABORT,'partition leakage'); END;

CREATE TRIGGER tle_query_partition_insert BEFORE INSERT ON tle_query WHEN EXISTS(SELECT 1 FROM tle_case c WHERE c.run_id=NEW.run_id AND c.id=NEW.case_id AND ((c.partition='RETENTION' AND NEW.query_kind<>'retention') OR (c.partition='TARGET' AND NEW.query_kind='retention'))) BEGIN SELECT RAISE(ABORT,'wrong query partition'); END;

CREATE TRIGGER tle_trial_partition_insert BEFORE INSERT ON tle_trial WHEN EXISTS(SELECT 1 FROM tle_case c WHERE c.run_id=NEW.run_id AND c.id=NEW.case_id AND ((c.partition='DEV' AND NEW.repeat<>1) OR (c.partition IN ('TARGET','RETENTION') AND NEW.arm='O'))) BEGIN SELECT RAISE(ABORT,'wrong trial allocation'); END;

CREATE TRIGGER tle_replacement_insert BEFORE INSERT ON tle_trial WHEN NEW.occurrence='replacement' AND EXISTS(SELECT 1 FROM tle_trial t WHERE t.run_id=NEW.run_id AND t.id=NEW.logical_trial_id AND (t.occurrence<>'original' OR t.case_id<>NEW.case_id OR t.arm<>NEW.arm OR t.repeat<>NEW.repeat)) BEGIN SELECT RAISE(ABORT,'replacement allocation mismatch'); END;

CREATE TRIGGER tle_attempt_query_insert BEFORE INSERT ON tle_attempt WHEN NEW.phase='query' AND NOT EXISTS(SELECT 1 FROM tle_query q JOIN tle_trial t ON t.run_id=q.run_id AND t.case_id=q.case_id WHERE t.run_id=NEW.run_id AND t.id=NEW.trial_id AND q.id=json_extract(NEW.query_id,'$.value')) BEGIN SELECT RAISE(ABORT,'query not in trial case'); END;

CREATE TRIGGER tle_usage_input_tokens_insert BEFORE INSERT ON tle_usage WHEN json_extract(NEW.input_tokens,'$.status')='known' AND (coalesce(json_type(NEW.input_tokens,'$.value'),'null') NOT IN ('integer') OR json_extract(NEW.input_tokens,'$.value')<0) BEGIN SELECT RAISE(ABORT,'invalid known usage'); END;

CREATE TRIGGER tle_usage_output_tokens_insert BEFORE INSERT ON tle_usage WHEN json_extract(NEW.output_tokens,'$.status')='known' AND (coalesce(json_type(NEW.output_tokens,'$.value'),'null') NOT IN ('integer') OR json_extract(NEW.output_tokens,'$.value')<0) BEGIN SELECT RAISE(ABORT,'invalid known usage'); END;

CREATE TRIGGER tle_usage_tool_calls_insert BEFORE INSERT ON tle_usage WHEN json_extract(NEW.tool_calls,'$.status')='known' AND (coalesce(json_type(NEW.tool_calls,'$.value'),'null') NOT IN ('integer') OR json_extract(NEW.tool_calls,'$.value')<0) BEGIN SELECT RAISE(ABORT,'invalid known usage'); END;

CREATE TRIGGER tle_usage_elapsed_ms_insert BEFORE INSERT ON tle_usage WHEN json_extract(NEW.elapsed_ms,'$.status')='known' AND (coalesce(json_type(NEW.elapsed_ms,'$.value'),'null') NOT IN ('integer','real') OR json_extract(NEW.elapsed_ms,'$.value')<0) BEGIN SELECT RAISE(ABORT,'invalid known usage'); END;

CREATE TRIGGER tle_usage_currency_amount_insert BEFORE INSERT ON tle_usage WHEN json_extract(NEW.currency_amount,'$.status')='known' AND (coalesce(json_type(NEW.currency_amount,'$.value'),'null') NOT IN ('integer','real') OR json_extract(NEW.currency_amount,'$.value')<0) BEGIN SELECT RAISE(ABORT,'invalid known usage'); END;

CREATE TRIGGER tle_cluster_update BEFORE UPDATE ON tle_case WHEN NEW.partition<>'MECH' AND EXISTS(SELECT 1 FROM tle_case c WHERE c.run_id=NEW.run_id AND c.id<>NEW.id AND c.source_cluster_id=NEW.source_cluster_id AND c.partition<>'MECH' AND c.partition<>NEW.partition) BEGIN SELECT RAISE(ABORT,'partition leakage'); END;

CREATE TRIGGER tle_query_partition_update BEFORE UPDATE ON tle_query WHEN EXISTS(SELECT 1 FROM tle_case c WHERE c.run_id=NEW.run_id AND c.id=NEW.case_id AND ((c.partition='RETENTION' AND NEW.query_kind<>'retention') OR (c.partition='TARGET' AND NEW.query_kind='retention'))) BEGIN SELECT RAISE(ABORT,'wrong query partition'); END;

CREATE TRIGGER tle_trial_partition_update BEFORE UPDATE ON tle_trial WHEN EXISTS(SELECT 1 FROM tle_case c WHERE c.run_id=NEW.run_id AND c.id=NEW.case_id AND ((c.partition='DEV' AND NEW.repeat<>1) OR (c.partition IN ('TARGET','RETENTION') AND NEW.arm='O'))) BEGIN SELECT RAISE(ABORT,'wrong trial allocation'); END;

CREATE TRIGGER tle_replacement_update BEFORE UPDATE ON tle_trial WHEN NEW.occurrence='replacement' AND EXISTS(SELECT 1 FROM tle_trial t WHERE t.run_id=NEW.run_id AND t.id=NEW.logical_trial_id AND (t.occurrence<>'original' OR t.case_id<>NEW.case_id OR t.arm<>NEW.arm OR t.repeat<>NEW.repeat)) BEGIN SELECT RAISE(ABORT,'replacement allocation mismatch'); END;

CREATE TRIGGER tle_attempt_query_update BEFORE UPDATE ON tle_attempt WHEN NEW.phase='query' AND NOT EXISTS(SELECT 1 FROM tle_query q JOIN tle_trial t ON t.run_id=q.run_id AND t.case_id=q.case_id WHERE t.run_id=NEW.run_id AND t.id=NEW.trial_id AND q.id=json_extract(NEW.query_id,'$.value')) BEGIN SELECT RAISE(ABORT,'query not in trial case'); END;

CREATE TRIGGER tle_usage_input_tokens_update BEFORE UPDATE ON tle_usage WHEN json_extract(NEW.input_tokens,'$.status')='known' AND (coalesce(json_type(NEW.input_tokens,'$.value'),'null') NOT IN ('integer') OR json_extract(NEW.input_tokens,'$.value')<0) BEGIN SELECT RAISE(ABORT,'invalid known usage'); END;

CREATE TRIGGER tle_usage_output_tokens_update BEFORE UPDATE ON tle_usage WHEN json_extract(NEW.output_tokens,'$.status')='known' AND (coalesce(json_type(NEW.output_tokens,'$.value'),'null') NOT IN ('integer') OR json_extract(NEW.output_tokens,'$.value')<0) BEGIN SELECT RAISE(ABORT,'invalid known usage'); END;

CREATE TRIGGER tle_usage_tool_calls_update BEFORE UPDATE ON tle_usage WHEN json_extract(NEW.tool_calls,'$.status')='known' AND (coalesce(json_type(NEW.tool_calls,'$.value'),'null') NOT IN ('integer') OR json_extract(NEW.tool_calls,'$.value')<0) BEGIN SELECT RAISE(ABORT,'invalid known usage'); END;

CREATE TRIGGER tle_usage_elapsed_ms_update BEFORE UPDATE ON tle_usage WHEN json_extract(NEW.elapsed_ms,'$.status')='known' AND (coalesce(json_type(NEW.elapsed_ms,'$.value'),'null') NOT IN ('integer','real') OR json_extract(NEW.elapsed_ms,'$.value')<0) BEGIN SELECT RAISE(ABORT,'invalid known usage'); END;

CREATE TRIGGER tle_usage_currency_amount_update BEFORE UPDATE ON tle_usage WHEN json_extract(NEW.currency_amount,'$.status')='known' AND (coalesce(json_type(NEW.currency_amount,'$.value'),'null') NOT IN ('integer','real') OR json_extract(NEW.currency_amount,'$.value')<0) BEGIN SELECT RAISE(ABORT,'invalid known usage'); END;

CREATE TRIGGER tle_attempt_limit BEFORE INSERT ON tle_attempt WHEN (SELECT count(*) FROM tle_attempt a WHERE a.run_id=NEW.run_id AND a.logical_trial_id=NEW.logical_trial_id)>=6 OR (NEW.phase='learn' AND (SELECT count(*) FROM tle_attempt a WHERE a.run_id=NEW.run_id AND a.trial_id=NEW.trial_id AND a.phase='learn')>=3) BEGIN SELECT RAISE(ABORT,'attempt budget exceeded'); END;

CREATE UNIQUE INDEX tle_query_once ON tle_attempt(run_id,trial_id,json_extract(query_id,'$.value')) WHERE phase='query';

CREATE UNIQUE INDEX tle_usage_event ON tle_usage(run_id,json_extract(reservation_ref,'$.id'),coalesce(json_extract(attempt_ref,'$.value.id'),'!no-attempt')); 

CREATE TRIGGER tle_run_freeze BEFORE UPDATE ON tle_run WHEN OLD.state<>'blocked_before_start' AND (NEW.protocol_ref IS NOT OLD.protocol_ref OR NEW.code_digest IS NOT OLD.code_digest OR NEW.configuration_ref IS NOT OLD.configuration_ref OR NEW.prompt_refs IS NOT OLD.prompt_refs OR NEW.model_ref IS NOT OLD.model_ref OR NEW.route IS NOT OLD.route OR NEW.materials_manifest IS NOT OLD.materials_manifest OR NEW.review_roster IS NOT OLD.review_roster OR NEW.price_evidence IS NOT OLD.price_evidence OR NEW.currency IS NOT OLD.currency OR NEW.money_limit IS NOT OLD.money_limit OR NEW.account_limits IS NOT OLD.account_limits OR NEW.mechanism_manifest IS NOT OLD.mechanism_manifest OR NEW.arm_seed IS NOT OLD.arm_seed OR NEW.analysis_seed IS NOT OLD.analysis_seed OR NEW.bootstrap_samples IS NOT OLD.bootstrap_samples OR NEW.concurrency_limit IS NOT OLD.concurrency_limit OR NEW.deadline IS NOT OLD.deadline OR NEW.budget_ref IS NOT OLD.budget_ref) BEGIN SELECT RAISE(ABORT,'run parameters frozen'); END;

CREATE TRIGGER tle_case_allocation BEFORE UPDATE ON tle_case WHEN NEW.partition IS NOT OLD.partition OR NEW.source_cluster_id IS NOT OLD.source_cluster_id BEGIN SELECT RAISE(ABORT,'allocation immutable'); END;

CREATE TRIGGER tle_query_allocation BEFORE UPDATE ON tle_query WHEN NEW.case_id IS NOT OLD.case_id OR NEW.query_kind IS NOT OLD.query_kind OR NEW.k IS NOT OLD.k BEGIN SELECT RAISE(ABORT,'allocation immutable'); END;

CREATE TRIGGER tle_trial_allocation BEFORE UPDATE ON tle_trial WHEN NEW.logical_trial_id IS NOT OLD.logical_trial_id OR NEW.case_id IS NOT OLD.case_id OR NEW.arm IS NOT OLD.arm OR NEW.repeat IS NOT OLD.repeat OR NEW.occurrence IS NOT OLD.occurrence OR NEW.replacement_of IS NOT OLD.replacement_of BEGIN SELECT RAISE(ABORT,'allocation immutable'); END;

CREATE TRIGGER tle_attempt_allocation BEFORE UPDATE ON tle_attempt WHEN NEW.trial_id IS NOT OLD.trial_id OR NEW.logical_trial_id IS NOT OLD.logical_trial_id OR NEW.phase IS NOT OLD.phase OR NEW.query_id IS NOT OLD.query_id BEGIN SELECT RAISE(ABORT,'allocation immutable'); END;

CREATE TRIGGER tle_run_no_unstart BEFORE UPDATE ON tle_run WHEN OLD.state<>'blocked_before_start' AND NEW.state='blocked_before_start' BEGIN SELECT RAISE(ABORT,'cannot unstart run'); END;
CREATE TRIGGER tle_case_children BEFORE INSERT ON tle_case WHEN EXISTS(SELECT 1 FROM tle_query q WHERE q.run_id=NEW.run_id AND q.case_id=NEW.id AND ((NEW.partition='RETENTION' AND q.query_kind<>'retention') OR (NEW.partition='TARGET' AND q.query_kind='retention'))) OR EXISTS(SELECT 1 FROM tle_trial t WHERE t.run_id=NEW.run_id AND t.case_id=NEW.id AND ((NEW.partition='DEV' AND t.repeat<>1) OR (NEW.partition IN ('TARGET','RETENTION') AND t.arm='O'))) BEGIN SELECT RAISE(ABORT,'late case allocation mismatch'); END;
CREATE TRIGGER tle_trial_replacements BEFORE INSERT ON tle_trial WHEN EXISTS(SELECT 1 FROM tle_trial t WHERE t.run_id=NEW.run_id AND t.occurrence='replacement' AND t.logical_trial_id=NEW.id AND (NEW.occurrence<>'original' OR NEW.case_id<>t.case_id OR NEW.arm<>t.arm OR NEW.repeat<>t.repeat)) BEGIN SELECT RAISE(ABORT,'late original trial mismatch'); END;
