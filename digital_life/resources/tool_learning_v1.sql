-- TL-LOOP-0.1 additive DDL; no migration/version change. Requires genuine schema3.

PRAGMA foreign_keys=ON;
CREATE UNIQUE INDEX tl_budget_activity_key ON activity_budget_accounts(instance_id,activity_id,id);
CREATE UNIQUE INDEX tl_revision_owner_key ON object_revision_registry(instance_id,object_id,id);

CREATE TABLE tl_command (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 operation TEXT NOT NULL CHECK(operation IN ('admit_observation','assess_observation','decide_proposal','claim_representation','publish_representation','recall','apply_invalidation','acknowledge_propagation','resume_work','record_effect')),
 idempotency_key TEXT NOT NULL,
 fingerprint TEXT NOT NULL CHECK(length(fingerprint)=64 AND fingerprint NOT GLOB '*[^0-9a-f]*'),
 principal_artifact_id TEXT NOT NULL,
 work_id TEXT,
 result_artifact_id TEXT,
 state TEXT NOT NULL CHECK (state IN ('pending','committed','failed')),
 row_revision INTEGER NOT NULL CHECK(row_revision>=0),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,principal_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,result_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,work_id) REFERENCES tl_work(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,operation,idempotency_key),
 CHECK(state<>'committed' OR result_artifact_id IS NOT NULL)
) STRICT;

CREATE TRIGGER tl_command_register AFTER INSERT ON tl_command BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_command'); END;

CREATE TRIGGER tl_command_update_guard BEFORE UPDATE ON tl_command WHEN (NEW.id IS NOT OLD.id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.schema_revision IS NOT OLD.schema_revision OR NEW.operation IS NOT OLD.operation OR NEW.idempotency_key IS NOT OLD.idempotency_key OR NEW.fingerprint IS NOT OLD.fingerprint OR NEW.principal_artifact_id IS NOT OLD.principal_artifact_id OR NEW.row_revision<>OLD.row_revision+1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_command_delete_guard BEFORE DELETE ON tl_command WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_work (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 learning_activity_id TEXT NOT NULL,
 source_activity_id TEXT NOT NULL,
 source_artifact_id TEXT NOT NULL,
 purpose TEXT NOT NULL CHECK (purpose IN ('learn','accept','represent','recall_experience','recall_episode','verify_source','evaluate','history_audit','propagate','erase','recover')),
 processing_identity TEXT NOT NULL CHECK(length(processing_identity)=64 AND processing_identity NOT GLOB '*[^0-9a-f]*'),
 state TEXT NOT NULL CHECK (state IN ('admitted','processing','awaiting_decision','handoff_pending','waiting','blocked','failed','stopped','completed','no_change','rejected')),
 phase TEXT NOT NULL CHECK (phase IN ('admit','assess','decide','represent','complete')),
 review_round INTEGER NOT NULL CHECK(review_round>=0),
 conditions_artifact_id TEXT NOT NULL,
 control_artifact_id TEXT NOT NULL,
 method_artifact_id TEXT NOT NULL,
 deadline TEXT NOT NULL CHECK(length(deadline)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',deadline) IS deadline),
 budget_account_id TEXT NOT NULL,
 row_revision INTEGER NOT NULL CHECK(row_revision>=0),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,source_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,conditions_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,control_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,method_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,learning_activity_id) REFERENCES activities(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,source_activity_id) REFERENCES activities(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,learning_activity_id,budget_account_id) REFERENCES activity_budget_accounts(instance_id,activity_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,learning_activity_id),
 UNIQUE(instance_id,budget_account_id),
 UNIQUE(instance_id,processing_identity),
 CHECK(state NOT IN ('completed','no_change','rejected') OR phase='complete')
) STRICT;

CREATE TRIGGER tl_work_register AFTER INSERT ON tl_work BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_work'); END;

CREATE TRIGGER tl_work_update_guard BEFORE UPDATE ON tl_work WHEN (NEW.id IS NOT OLD.id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.schema_revision IS NOT OLD.schema_revision OR NEW.learning_activity_id IS NOT OLD.learning_activity_id OR NEW.source_activity_id IS NOT OLD.source_activity_id OR NEW.source_artifact_id IS NOT OLD.source_artifact_id OR NEW.purpose IS NOT OLD.purpose OR NEW.processing_identity IS NOT OLD.processing_identity OR NEW.budget_account_id IS NOT OLD.budget_account_id OR NEW.deadline IS NOT OLD.deadline OR NEW.row_revision<>OLD.row_revision+1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_work_delete_guard BEFORE DELETE ON tl_work WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_product (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 work_id TEXT NOT NULL,
 product_type TEXT NOT NULL CHECK (product_type IN ('ObservationExtract','ComparisonAssessment','UpdateProposal','EffectAssessment')),
 payload_artifact_id TEXT NOT NULL,
 processing_identity TEXT NOT NULL CHECK(length(processing_identity)=64 AND processing_identity NOT GLOB '*[^0-9a-f]*'),
 supersedes_id TEXT,
 source_fingerprint TEXT NOT NULL CHECK(length(source_fingerprint)=64 AND source_fingerprint NOT GLOB '*[^0-9a-f]*'),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,payload_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,work_id) REFERENCES tl_work(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,supersedes_id) REFERENCES tl_product(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,work_id,product_type,processing_identity)
) STRICT;

CREATE TRIGGER tl_product_register AFTER INSERT ON tl_product BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_product'); END;

CREATE TRIGGER tl_product_update_guard BEFORE UPDATE ON tl_product WHEN (1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_product_delete_guard BEFORE DELETE ON tl_product WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_content (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 content_kind TEXT NOT NULL CHECK (content_kind IN ('source_report','world_claim','method_claim','causal_claim')),
 head_revision_id TEXT,
 row_revision INTEGER NOT NULL CHECK(row_revision>=0),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,id,head_revision_id) REFERENCES tl_content_revision(instance_id,content_id,id) DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TRIGGER tl_content_register AFTER INSERT ON tl_content BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_content'); END;

CREATE TRIGGER tl_content_update_guard BEFORE UPDATE ON tl_content WHEN (NEW.id IS NOT OLD.id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.schema_revision IS NOT OLD.schema_revision OR NEW.content_kind IS NOT OLD.content_kind OR NEW.row_revision<>OLD.row_revision+1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_content_delete_guard BEFORE DELETE ON tl_content WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_content_revision (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 content_id TEXT NOT NULL,
 revision_no INTEGER NOT NULL CHECK(revision_no>=1),
 decision_id TEXT NOT NULL,
 product_id TEXT NOT NULL,
 payload_artifact_id TEXT NOT NULL,
 status TEXT NOT NULL CHECK (status IN ('candidate','accepted')),
 previous_revision_id TEXT,
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_revision_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,payload_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,content_id) REFERENCES tl_content(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,decision_id) REFERENCES tl_decision(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,product_id) REFERENCES tl_product(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,content_id,revision_no),
 UNIQUE(instance_id,content_id,id),
 FOREIGN KEY(instance_id,content_id,previous_revision_id) REFERENCES tl_content_revision(instance_id,content_id,id) DEFERRABLE INITIALLY DEFERRED,
 CHECK(previous_revision_id IS NULL OR previous_revision_id<>id)
) STRICT;

CREATE TRIGGER tl_content_revision_register AFTER INSERT ON tl_content_revision BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_content_revision'); END;

CREATE TRIGGER tl_content_revision_update_guard BEFORE UPDATE ON tl_content_revision WHEN (1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_content_revision_delete_guard BEFORE DELETE ON tl_content_revision WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_decision (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 work_id TEXT NOT NULL,
 proposal_id TEXT NOT NULL,
 review_round INTEGER NOT NULL CHECK(review_round>=0),
 decision_artifact_id TEXT NOT NULL,
 operation TEXT NOT NULL CHECK (operation IN ('accept','candidate','defer','reject','conflict','reuse')),
 content_revision_id TEXT,
 policy_ref_id TEXT NOT NULL,
 created_at TEXT NOT NULL CHECK(length(created_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',created_at) IS created_at),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,decision_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,work_id) REFERENCES tl_work(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,proposal_id) REFERENCES tl_product(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,content_revision_id) REFERENCES tl_content_revision(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,policy_ref_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,proposal_id,review_round),
 CHECK(operation NOT IN ('defer','reject') OR content_revision_id IS NULL)
) STRICT;

CREATE TRIGGER tl_decision_register AFTER INSERT ON tl_decision BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_decision'); END;

CREATE TRIGGER tl_decision_update_guard BEFORE UPDATE ON tl_decision WHEN (1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_decision_delete_guard BEFORE DELETE ON tl_decision WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_group (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 group_key TEXT NOT NULL,
 members_artifact_id TEXT NOT NULL,
 state TEXT NOT NULL CHECK (state IN ('pending','ready','obsolete')),
 row_revision INTEGER NOT NULL CHECK(row_revision>=0),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,members_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,group_key)
) STRICT;

CREATE TRIGGER tl_group_register AFTER INSERT ON tl_group BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_group'); END;

CREATE TRIGGER tl_group_update_guard BEFORE UPDATE ON tl_group WHEN (NEW.id IS NOT OLD.id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.schema_revision IS NOT OLD.schema_revision OR NEW.group_key IS NOT OLD.group_key OR NEW.members_artifact_id IS NOT OLD.members_artifact_id OR NEW.row_revision<>OLD.row_revision+1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_group_delete_guard BEFORE DELETE ON tl_group WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_handoff (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 work_id TEXT NOT NULL,
 content_revision_id TEXT NOT NULL,
 decision_id TEXT NOT NULL,
 group_id TEXT,
 format_version TEXT NOT NULL CHECK (format_version IN ('TL-TEXT-1')),
 input_fingerprint TEXT NOT NULL CHECK(length(input_fingerprint)=64 AND input_fingerprint NOT GLOB '*[^0-9a-f]*'),
 state TEXT NOT NULL CHECK (state IN ('pending','leased','published','retryable','blocked','permanent_failure','obsolete')),
 lease_worker_id TEXT,
 lease_generation INTEGER NOT NULL CHECK(lease_generation>=0),
 lease_expires_at TEXT CHECK(lease_expires_at IS NULL OR (length(lease_expires_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',lease_expires_at) IS lease_expires_at)),
 attempts INTEGER NOT NULL CHECK(attempts>=0),
 deadline TEXT NOT NULL CHECK(length(deadline)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',deadline) IS deadline),
 budget_account_id TEXT NOT NULL,
 representation_id TEXT,
 receipt_artifact_id TEXT,
 row_revision INTEGER NOT NULL CHECK(row_revision>=0),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,receipt_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,work_id) REFERENCES tl_work(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,content_revision_id) REFERENCES tl_content_revision(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,decision_id) REFERENCES tl_decision(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,group_id) REFERENCES tl_group(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,lease_worker_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,budget_account_id) REFERENCES activity_budget_accounts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,representation_id) REFERENCES tl_representation(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,content_revision_id,format_version,input_fingerprint),
 CHECK((state='leased' AND lease_worker_id IS NOT NULL AND lease_expires_at IS NOT NULL) OR (state<>'leased' AND lease_worker_id IS NULL AND lease_expires_at IS NULL)),
 CHECK(state<>'published' OR (representation_id IS NOT NULL AND receipt_artifact_id IS NOT NULL))
) STRICT;

CREATE TRIGGER tl_handoff_register AFTER INSERT ON tl_handoff BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_handoff'); END;

CREATE TRIGGER tl_handoff_update_guard BEFORE UPDATE ON tl_handoff WHEN (NEW.id IS NOT OLD.id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.schema_revision IS NOT OLD.schema_revision OR NEW.work_id IS NOT OLD.work_id OR NEW.content_revision_id IS NOT OLD.content_revision_id OR NEW.decision_id IS NOT OLD.decision_id OR NEW.group_id IS NOT OLD.group_id OR NEW.format_version IS NOT OLD.format_version OR NEW.input_fingerprint IS NOT OLD.input_fingerprint OR NEW.deadline IS NOT OLD.deadline OR NEW.budget_account_id IS NOT OLD.budget_account_id OR NEW.row_revision<>OLD.row_revision+1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_handoff_delete_guard BEFORE DELETE ON tl_handoff WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_representation (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 series_id TEXT NOT NULL,
 content_revision_id TEXT NOT NULL,
 decision_id TEXT NOT NULL,
 format_version TEXT NOT NULL CHECK (format_version IN ('TL-TEXT-1')),
 representation_no INTEGER NOT NULL CHECK(representation_no>=1),
 payload_artifact_id TEXT NOT NULL,
 body_artifact_id TEXT NOT NULL,
 body_digest TEXT NOT NULL CHECK(length(body_digest)=64 AND body_digest NOT GLOB '*[^0-9a-f]*'),
 group_id TEXT,
 state TEXT NOT NULL CHECK (state IN ('ready','superseded','withdrawn')),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_revision_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,payload_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,body_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,series_id) REFERENCES tl_representation_head(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,content_revision_id) REFERENCES tl_content_revision(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,decision_id) REFERENCES tl_decision(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,group_id) REFERENCES tl_group(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,series_id,representation_no),
 UNIQUE(instance_id,series_id,id,content_revision_id,format_version)
) STRICT;

CREATE TRIGGER tl_representation_register AFTER INSERT ON tl_representation BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_representation'); END;

CREATE TRIGGER tl_representation_update_guard BEFORE UPDATE ON tl_representation WHEN (NEW.id IS NOT OLD.id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.schema_revision IS NOT OLD.schema_revision OR NEW.series_id IS NOT OLD.series_id OR NEW.content_revision_id IS NOT OLD.content_revision_id OR NEW.decision_id IS NOT OLD.decision_id OR NEW.format_version IS NOT OLD.format_version OR NEW.representation_no IS NOT OLD.representation_no OR NEW.payload_artifact_id IS NOT OLD.payload_artifact_id OR NEW.body_artifact_id IS NOT OLD.body_artifact_id OR NEW.body_digest IS NOT OLD.body_digest OR NEW.group_id IS NOT OLD.group_id OR NOT(NEW.state=OLD.state OR (OLD.state='ready' AND NEW.state IN ('superseded','withdrawn')))) BEGIN SELECT RAISE(ABORT,'immutable representation payload/state'); END;

CREATE TRIGGER tl_representation_delete_guard BEFORE DELETE ON tl_representation WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_representation_head (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 content_id TEXT NOT NULL,
 format_version TEXT NOT NULL CHECK(format_version='TL-TEXT-1'),
 representation_id TEXT NOT NULL,
 expected_content_revision_id TEXT NOT NULL,
 row_revision INTEGER NOT NULL CHECK(row_revision>=0),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,content_id) REFERENCES tl_content(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,content_id,format_version),
 FOREIGN KEY(instance_id,id,representation_id,expected_content_revision_id,format_version) REFERENCES tl_representation(instance_id,series_id,id,content_revision_id,format_version) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,content_id,expected_content_revision_id) REFERENCES tl_content_revision(instance_id,content_id,id) DEFERRABLE INITIALLY DEFERRED
) STRICT;

CREATE TRIGGER tl_representation_head_register AFTER INSERT ON tl_representation_head BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_representation_head'); END;

CREATE TRIGGER tl_representation_head_update_guard BEFORE UPDATE ON tl_representation_head WHEN (NEW.id IS NOT OLD.id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.schema_revision IS NOT OLD.schema_revision OR NEW.content_id IS NOT OLD.content_id OR NEW.format_version IS NOT OLD.format_version OR NEW.row_revision<>OLD.row_revision+1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_representation_head_delete_guard BEFORE DELETE ON tl_representation_head WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_dependency (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 consumer_ref_id TEXT NOT NULL,
 source_ref_id TEXT NOT NULL,
 source_revision_id TEXT,
 relation TEXT NOT NULL CHECK (relation IN ('support','derive','read','delete','representation','group')),
 purpose TEXT NOT NULL CHECK (purpose IN ('learn','accept','represent','recall_experience','recall_episode','verify_source','evaluate','history_audit','propagate','erase','recover')),
 expected_epoch INTEGER NOT NULL CHECK(expected_epoch>=0),
 field_path TEXT NOT NULL,
 metadata_artifact_id TEXT NOT NULL,
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,metadata_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,consumer_ref_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,source_ref_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,source_ref_id,source_revision_id) REFERENCES object_revision_registry(instance_id,object_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,consumer_ref_id,source_ref_id,relation,purpose,field_path,expected_epoch)
) STRICT;

CREATE TRIGGER tl_dependency_register AFTER INSERT ON tl_dependency BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_dependency'); END;

CREATE TRIGGER tl_dependency_update_guard BEFORE UPDATE ON tl_dependency WHEN (1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_dependency_delete_guard BEFORE DELETE ON tl_dependency WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_source_epoch (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 source_ref_id TEXT NOT NULL,
 scope_key TEXT NOT NULL CHECK(length(scope_key)=64 AND scope_key NOT GLOB '*[^0-9a-f]*'),
 scope_artifact_id TEXT NOT NULL,
 epoch INTEGER NOT NULL CHECK(epoch>=0),
 row_revision INTEGER NOT NULL CHECK(row_revision>=0),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,scope_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,source_ref_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,source_ref_id,scope_key)
) STRICT;

CREATE TRIGGER tl_source_epoch_register AFTER INSERT ON tl_source_epoch BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_source_epoch'); END;

CREATE TRIGGER tl_source_epoch_update_guard BEFORE UPDATE ON tl_source_epoch WHEN (NEW.id IS NOT OLD.id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.schema_revision IS NOT OLD.schema_revision OR NEW.source_ref_id IS NOT OLD.source_ref_id OR NEW.scope_key IS NOT OLD.scope_key OR NEW.scope_artifact_id IS NOT OLD.scope_artifact_id OR NEW.row_revision<>OLD.row_revision+1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_source_epoch_delete_guard BEFORE DELETE ON tl_source_epoch WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_change (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 change_key TEXT NOT NULL,
 fingerprint TEXT NOT NULL CHECK(length(fingerprint)=64 AND fingerprint NOT GLOB '*[^0-9a-f]*'),
 payload_artifact_id TEXT NOT NULL,
 kind TEXT NOT NULL CHECK (kind IN ('correct','revoke','erase','conflict','unavailable')),
 source_ref_id TEXT NOT NULL,
 expected_epoch INTEGER NOT NULL CHECK(expected_epoch>=0),
 result_epoch INTEGER NOT NULL CHECK(result_epoch>=0),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,payload_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,source_ref_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,change_key),
 CHECK(result_epoch=expected_epoch+1)
) STRICT;

CREATE TRIGGER tl_change_register AFTER INSERT ON tl_change BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_change'); END;

CREATE TRIGGER tl_change_update_guard BEFORE UPDATE ON tl_change WHEN (1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_change_delete_guard BEFORE DELETE ON tl_change WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_barrier (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 change_id TEXT NOT NULL,
 source_ref_id TEXT NOT NULL,
 source_epoch INTEGER NOT NULL CHECK(source_epoch>=0),
 kind TEXT NOT NULL CHECK (kind IN ('correct','revoke','erase','conflict','unavailable')),
 scope_artifact_id TEXT NOT NULL,
 authorization_ref_id TEXT NOT NULL,
 state TEXT NOT NULL CHECK (state IN ('active','resolved')),
 resolution_artifact_id TEXT,
 row_revision INTEGER NOT NULL CHECK(row_revision>=0),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,scope_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,resolution_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,change_id) REFERENCES tl_change(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,source_ref_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,authorization_ref_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,change_id),
 CHECK(state<>'resolved' OR resolution_artifact_id IS NOT NULL)
) STRICT;

CREATE TRIGGER tl_barrier_register AFTER INSERT ON tl_barrier BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_barrier'); END;

CREATE TRIGGER tl_barrier_update_guard BEFORE UPDATE ON tl_barrier WHEN (NEW.id IS NOT OLD.id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.schema_revision IS NOT OLD.schema_revision OR NEW.change_id IS NOT OLD.change_id OR NEW.source_ref_id IS NOT OLD.source_ref_id OR NEW.source_epoch IS NOT OLD.source_epoch OR NEW.kind IS NOT OLD.kind OR NEW.scope_artifact_id IS NOT OLD.scope_artifact_id OR NEW.authorization_ref_id IS NOT OLD.authorization_ref_id OR NEW.row_revision<>OLD.row_revision+1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_barrier_delete_guard BEFORE DELETE ON tl_barrier WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_propagation (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 barrier_id TEXT NOT NULL,
 domain TEXT NOT NULL CHECK (domain IN ('M01','M03','M04','M12','M13','M14','M17','coordinator','evaluator')),
 targets_artifact_id TEXT NOT NULL,
 coverage_artifact_id TEXT NOT NULL,
 state TEXT NOT NULL CHECK (state IN ('pending','processing','blocked','verified','failed')),
 generation INTEGER NOT NULL CHECK(generation>=0),
 verification_artifact_id TEXT,
 deadline TEXT NOT NULL CHECK(length(deadline)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',deadline) IS deadline),
 budget_account_id TEXT NOT NULL,
 row_revision INTEGER NOT NULL CHECK(row_revision>=0),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,targets_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,coverage_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,verification_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,barrier_id) REFERENCES tl_barrier(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,budget_account_id) REFERENCES activity_budget_accounts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,barrier_id,domain,generation),
 CHECK(state<>'verified' OR verification_artifact_id IS NOT NULL)
) STRICT;

CREATE TRIGGER tl_propagation_register AFTER INSERT ON tl_propagation BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_propagation'); END;

CREATE TRIGGER tl_propagation_update_guard BEFORE UPDATE ON tl_propagation WHEN (NEW.id IS NOT OLD.id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.schema_revision IS NOT OLD.schema_revision OR NEW.barrier_id IS NOT OLD.barrier_id OR NEW.domain IS NOT OLD.domain OR NEW.generation IS NOT OLD.generation OR NEW.targets_artifact_id IS NOT OLD.targets_artifact_id OR NEW.deadline IS NOT OLD.deadline OR NEW.budget_account_id IS NOT OLD.budget_account_id OR NEW.row_revision<>OLD.row_revision+1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_propagation_delete_guard BEFORE DELETE ON tl_propagation WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_erasure_target (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 barrier_id TEXT NOT NULL,
 plan_ref_id TEXT NOT NULL,
 target_ref_id TEXT NOT NULL,
 location_kind TEXT NOT NULL CHECK (location_kind IN ('database','blob','index','cache','managed_backup','remote')),
 state TEXT NOT NULL CHECK (state IN ('pending','removed','verified','blocked','unknown')),
 verification_artifact_id TEXT,
 row_revision INTEGER NOT NULL CHECK(row_revision>=0),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,verification_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,barrier_id) REFERENCES tl_barrier(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,plan_ref_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,target_ref_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,barrier_id,target_ref_id,location_kind),
 CHECK(state<>'verified' OR verification_artifact_id IS NOT NULL)
) STRICT;

CREATE TRIGGER tl_erasure_target_register AFTER INSERT ON tl_erasure_target BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_erasure_target'); END;

CREATE TRIGGER tl_erasure_target_update_guard BEFORE UPDATE ON tl_erasure_target WHEN (NEW.id IS NOT OLD.id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.schema_revision IS NOT OLD.schema_revision OR NEW.barrier_id IS NOT OLD.barrier_id OR NEW.plan_ref_id IS NOT OLD.plan_ref_id OR NEW.target_ref_id IS NOT OLD.target_ref_id OR NEW.location_kind IS NOT OLD.location_kind OR NEW.row_revision<>OLD.row_revision+1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_erasure_target_delete_guard BEFORE DELETE ON tl_erasure_target WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_input_dependency (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 request_ref_id TEXT NOT NULL,
 source_ref_id TEXT NOT NULL,
 source_epoch INTEGER NOT NULL CHECK(source_epoch>=0),
 source_revision_ref_id TEXT,
 field_path TEXT NOT NULL,
 purpose TEXT NOT NULL CHECK (purpose IN ('learn','accept','represent','recall_experience','recall_episode','verify_source','evaluate','history_audit','propagate','erase','recover')),
 recipient_ref_id TEXT NOT NULL,
 body_digest TEXT CHECK(length(body_digest)=64 AND body_digest NOT GLOB '*[^0-9a-f]*'),
 retention_state TEXT NOT NULL CHECK (retention_state IN ('allowed','blocked','erase_pending','erased')),
 row_revision INTEGER NOT NULL CHECK(row_revision>=0),
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,request_ref_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,source_ref_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,source_ref_id,source_revision_ref_id) REFERENCES object_revision_registry(instance_id,object_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,recipient_ref_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,request_ref_id,source_ref_id,field_path,purpose,recipient_ref_id),
 CHECK(retention_state<>'erased' OR body_digest IS NULL)
) STRICT;

CREATE TRIGGER tl_input_dependency_register AFTER INSERT ON tl_input_dependency BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_input_dependency'); END;

CREATE TRIGGER tl_input_dependency_update_guard BEFORE UPDATE ON tl_input_dependency WHEN (NEW.id IS NOT OLD.id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.schema_revision IS NOT OLD.schema_revision OR NEW.request_ref_id IS NOT OLD.request_ref_id OR NEW.source_ref_id IS NOT OLD.source_ref_id OR NEW.source_epoch IS NOT OLD.source_epoch OR NEW.source_revision_ref_id IS NOT OLD.source_revision_ref_id OR NEW.field_path IS NOT OLD.field_path OR NEW.purpose IS NOT OLD.purpose OR NEW.recipient_ref_id IS NOT OLD.recipient_ref_id OR NEW.row_revision<>OLD.row_revision+1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_input_dependency_delete_guard BEFORE DELETE ON tl_input_dependency WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_effect (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 work_id TEXT NOT NULL,
 product_id TEXT NOT NULL,
 measurement_ref_id TEXT,
 metric_contract TEXT NOT NULL,
 state TEXT NOT NULL CHECK (state IN ('not_measured','incomplete','measured','invalidated','not_applicable')),
 payload_artifact_id TEXT NOT NULL,
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,payload_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,work_id) REFERENCES tl_work(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,product_id) REFERENCES tl_product(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,measurement_ref_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,product_id),
 CHECK(state<>'measured' OR measurement_ref_id IS NOT NULL)
) STRICT;

CREATE TRIGGER tl_effect_register AFTER INSERT ON tl_effect BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_effect'); END;

CREATE TRIGGER tl_effect_update_guard BEFORE UPDATE ON tl_effect WHEN (NEW.id IS NOT OLD.id OR NEW.instance_id IS NOT OLD.instance_id OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.schema_revision IS NOT OLD.schema_revision OR NEW.work_id IS NOT OLD.work_id OR NEW.product_id IS NOT OLD.product_id OR NEW.measurement_ref_id IS NOT OLD.measurement_ref_id OR NEW.metric_contract IS NOT OLD.metric_contract OR NEW.payload_artifact_id IS NOT OLD.payload_artifact_id OR (OLD.state='invalidated' AND NEW.state<>'invalidated')) BEGIN SELECT RAISE(ABORT,'immutable effect payload or invalidated assessment'); END;

CREATE TRIGGER tl_effect_delete_guard BEFORE DELETE ON tl_effect WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TABLE tl_recall_item (
 id TEXT PRIMARY KEY NOT NULL CHECK(length(id)=32 AND id NOT GLOB '*[^0-9a-f]*'),
 instance_id TEXT NOT NULL,
 recorded_at TEXT NOT NULL DEFAULT(strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(length(recorded_at)=24 AND strftime('%Y-%m-%dT%H:%M:%fZ',recorded_at) IS recorded_at),
 schema_revision INTEGER NOT NULL DEFAULT 1 CHECK(schema_revision=1),
 retrieval_run_id TEXT NOT NULL,
 rank INTEGER NOT NULL CHECK(rank>=0),
 kind TEXT NOT NULL CHECK (kind IN ('episode','accepted_content','source_evidence','candidate','history','shadow_statistic')),
 target_ref_id TEXT NOT NULL,
 payload_artifact_id TEXT NOT NULL,
 origin_result_id TEXT,
 control_artifact_id TEXT NOT NULL,
 UNIQUE(instance_id,id),
 FOREIGN KEY(instance_id,id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id) REFERENCES identity_instances(id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,payload_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,control_artifact_id) REFERENCES artifacts(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,retrieval_run_id) REFERENCES memory_retrieval_runs(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,target_ref_id) REFERENCES object_registry(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(instance_id,origin_result_id) REFERENCES memory_retrieval_results(instance_id,id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(instance_id,retrieval_run_id,rank),
 UNIQUE(instance_id,retrieval_run_id,target_ref_id)
) STRICT;

CREATE TRIGGER tl_recall_item_register AFTER INSERT ON tl_recall_item BEGIN INSERT INTO object_registry(id,instance_id,kind) VALUES(NEW.id,NEW.instance_id,'tl_recall_item'); END;

CREATE TRIGGER tl_recall_item_update_guard BEFORE UPDATE ON tl_recall_item WHEN (1) BEGIN SELECT RAISE(ABORT,'immutable payload or invalid row_revision'); END;

CREATE TRIGGER tl_recall_item_delete_guard BEFORE DELETE ON tl_recall_item WHEN NOT EXISTS(SELECT 1 FROM deletion_effects e JOIN deletion_requests r ON r.instance_id=e.instance_id AND r.id=e.request_id JOIN tl_erasure_target t ON t.instance_id=r.instance_id AND t.plan_ref_id=r.id AND t.target_ref_id=OLD.id AND t.location_kind='database' JOIN tl_barrier b ON b.instance_id=t.instance_id AND b.id=t.barrier_id AND b.kind='erase' WHERE e.instance_id=OLD.instance_id AND e.object_ref=OLD.id AND e.operation='purge' AND r.state='cleaning') BEGIN SELECT RAISE(ABORT,'authorized deletion required'); END;

CREATE TRIGGER tl_content_revision_version AFTER INSERT ON tl_content_revision BEGIN INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind) VALUES(NEW.id,NEW.instance_id,NEW.content_id,NEW.revision_no,'tl_content_revision'); END;

CREATE TRIGGER tl_representation_version AFTER INSERT ON tl_representation BEGIN INSERT INTO object_revision_registry(id,instance_id,object_id,revision_no,kind) VALUES(NEW.id,NEW.instance_id,NEW.series_id,NEW.representation_no,'tl_representation'); END;

CREATE INDEX tl_command_work_id ON tl_command(instance_id,work_id);

CREATE INDEX tl_work_state_deadline ON tl_work(instance_id,state,deadline);

CREATE INDEX tl_content_content_kind ON tl_content(instance_id,content_kind);

CREATE INDEX tl_content_revision_decision_id ON tl_content_revision(instance_id,decision_id);

CREATE INDEX tl_content_revision_product_id ON tl_content_revision(instance_id,product_id);

CREATE INDEX tl_group_state ON tl_group(instance_id,state);

CREATE INDEX tl_handoff_state_lease_expires_at_deadline ON tl_handoff(instance_id,state,lease_expires_at,deadline);

CREATE INDEX tl_dependency_source_ref_id_relation ON tl_dependency(instance_id,source_ref_id,relation);

CREATE INDEX tl_dependency_consumer_ref_id ON tl_dependency(instance_id,consumer_ref_id);

CREATE INDEX tl_barrier_source_ref_id_state_source_epoch ON tl_barrier(instance_id,source_ref_id,state,source_epoch);

CREATE INDEX tl_propagation_state_deadline ON tl_propagation(instance_id,state,deadline);

CREATE INDEX tl_input_dependency_source_ref_id_retention_state ON tl_input_dependency(instance_id,source_ref_id,retention_state);

CREATE INDEX tl_recall_item_target_ref_id ON tl_recall_item(instance_id,target_ref_id);

CREATE INDEX tl_recall_item_retrieval_run_id ON tl_recall_item(instance_id,retrieval_run_id);

CREATE TRIGGER tl_decision_product BEFORE INSERT ON tl_decision WHEN EXISTS(SELECT 1 FROM tl_product p WHERE p.instance_id=NEW.instance_id AND p.id=NEW.proposal_id AND (p.product_type<>'UpdateProposal' OR p.work_id<>NEW.work_id)) BEGIN SELECT RAISE(ABORT,'wrong product type/work'); END;

CREATE TRIGGER tl_decision_product_reverse BEFORE INSERT ON tl_product WHEN EXISTS(SELECT 1 FROM tl_decision x WHERE x.instance_id=NEW.instance_id AND x.proposal_id=NEW.id AND (NEW.product_type<>'UpdateProposal' OR x.work_id<>NEW.work_id)) BEGIN SELECT RAISE(ABORT,'wrong product type/work'); END;

CREATE TRIGGER tl_effect_product BEFORE INSERT ON tl_effect WHEN EXISTS(SELECT 1 FROM tl_product p WHERE p.instance_id=NEW.instance_id AND p.id=NEW.product_id AND (p.product_type<>'EffectAssessment' OR p.work_id<>NEW.work_id)) BEGIN SELECT RAISE(ABORT,'wrong product type/work'); END;

CREATE TRIGGER tl_effect_product_reverse BEFORE INSERT ON tl_product WHEN EXISTS(SELECT 1 FROM tl_effect x WHERE x.instance_id=NEW.instance_id AND x.product_id=NEW.id AND (NEW.product_type<>'EffectAssessment' OR x.work_id<>NEW.work_id)) BEGIN SELECT RAISE(ABORT,'wrong product type/work'); END;

CREATE TRIGGER tl_c1_revision BEFORE INSERT ON tl_content_revision WHEN EXISTS(SELECT 1 FROM tl_decision d WHERE d.instance_id=NEW.instance_id AND d.id=NEW.decision_id AND (d.proposal_id<>NEW.product_id OR d.content_revision_id IS NOT NEW.id OR (NEW.status='accepted' AND d.operation<>'accept') OR (NEW.status='candidate' AND d.operation<>'candidate'))) BEGIN SELECT RAISE(ABORT,'decision revision mismatch'); END;

CREATE TRIGGER tl_c1_decision BEFORE INSERT ON tl_decision WHEN EXISTS(SELECT 1 FROM tl_content_revision r WHERE NEW.instance_id=r.instance_id AND NEW.id=r.decision_id AND (NEW.proposal_id<>r.product_id OR NEW.content_revision_id IS NOT r.id OR (r.status='accepted' AND NEW.operation<>'accept') OR (r.status='candidate' AND NEW.operation<>'candidate'))) BEGIN SELECT RAISE(ABORT,'decision revision mismatch'); END;

CREATE TRIGGER tl_series_representation BEFORE INSERT ON tl_representation WHEN EXISTS(SELECT 1 FROM tl_representation_head h JOIN tl_content_revision r ON r.instance_id=NEW.instance_id AND r.id=NEW.content_revision_id WHERE h.instance_id=NEW.instance_id AND h.id=NEW.series_id AND (h.content_id<>r.content_id OR h.format_version<>NEW.format_version)) BEGIN SELECT RAISE(ABORT,'representation series mismatch'); END;

CREATE TRIGGER tl_series_head BEFORE INSERT ON tl_representation_head WHEN EXISTS(SELECT 1 FROM tl_representation p JOIN tl_content_revision r ON r.instance_id=p.instance_id AND r.id=p.content_revision_id WHERE p.instance_id=NEW.instance_id AND p.series_id=NEW.id AND (NEW.content_id<>r.content_id OR NEW.format_version<>p.format_version)) BEGIN SELECT RAISE(ABORT,'representation series mismatch'); END;

CREATE TRIGGER tl_dependency_revision_owner BEFORE INSERT ON tl_dependency WHEN EXISTS(SELECT 1 FROM object_revision_registry r WHERE r.instance_id=NEW.instance_id AND r.id=NEW.source_revision_id AND r.object_id<>NEW.source_ref_id) BEGIN SELECT RAISE(ABORT,'source revision mismatch'); END;

CREATE TRIGGER tl_input_dependency_revision_owner BEFORE INSERT ON tl_input_dependency WHEN EXISTS(SELECT 1 FROM object_revision_registry r WHERE r.instance_id=NEW.instance_id AND r.id=NEW.source_revision_ref_id AND r.object_id<>NEW.source_ref_id) BEGIN SELECT RAISE(ABORT,'source revision mismatch'); END;

CREATE TRIGGER tl_recall_kind BEFORE INSERT ON tl_recall_item WHEN EXISTS(SELECT 1 FROM object_registry r WHERE r.instance_id=NEW.instance_id AND r.id=NEW.target_ref_id AND r.kind NOT IN ('memory_revisions','tl_representation')) BEGIN SELECT RAISE(ABORT,'invalid recall target kind'); END;

CREATE TRIGGER tl_work_transition BEFORE UPDATE ON tl_work WHEN NEW.state<>OLD.state AND NOT((OLD.state='admitted' AND NEW.state IN ('processing','waiting','blocked','stopped')) OR (OLD.state='processing' AND NEW.state IN ('awaiting_decision','completed','no_change','waiting','blocked','failed','stopped')) OR (OLD.state='awaiting_decision' AND NEW.state IN ('handoff_pending','completed','no_change','waiting','blocked','rejected','stopped')) OR (OLD.state='handoff_pending' AND NEW.state IN ('completed','waiting','blocked','failed','stopped')) OR (OLD.state='waiting' AND NEW.state IN ('processing','handoff_pending')) OR (OLD.state='blocked' AND NEW.state IN ('processing','handoff_pending')) OR (OLD.state='failed' AND NEW.state IN ('processing','handoff_pending')) OR (OLD.state='stopped' AND NEW.state IN ('processing','handoff_pending'))) BEGIN SELECT RAISE(ABORT,'illegal state transition'); END;

CREATE TRIGGER tl_handoff_transition BEFORE UPDATE ON tl_handoff WHEN NEW.state<>OLD.state AND NOT((OLD.state='pending' AND NEW.state IN ('leased','blocked','obsolete')) OR (OLD.state='leased' AND NEW.state IN ('published','retryable','blocked','permanent_failure','obsolete')) OR (OLD.state='retryable' AND NEW.state IN ('leased','blocked','obsolete')) OR (OLD.state='blocked' AND NEW.state IN ('pending','obsolete'))) BEGIN SELECT RAISE(ABORT,'illegal state transition'); END;

CREATE TRIGGER tl_group_transition BEFORE UPDATE ON tl_group WHEN NEW.state<>OLD.state AND NOT((OLD.state='pending' AND NEW.state IN ('ready','obsolete')) OR (OLD.state='ready' AND NEW.state IN ('obsolete'))) BEGIN SELECT RAISE(ABORT,'illegal state transition'); END;

CREATE TRIGGER tl_barrier_transition BEFORE UPDATE ON tl_barrier WHEN NEW.state<>OLD.state AND NOT((OLD.state='active' AND NEW.state IN ('resolved'))) BEGIN SELECT RAISE(ABORT,'illegal state transition'); END;

CREATE TRIGGER tl_propagation_transition BEFORE UPDATE ON tl_propagation WHEN NEW.state<>OLD.state AND NOT((OLD.state='pending' AND NEW.state IN ('processing','blocked')) OR (OLD.state='processing' AND NEW.state IN ('verified','blocked','failed')) OR (OLD.state='failed' AND NEW.state IN ('processing')) OR (OLD.state='blocked' AND NEW.state IN ('processing'))) BEGIN SELECT RAISE(ABORT,'illegal state transition'); END;


CREATE TRIGGER tl_work_budget_insert BEFORE INSERT ON tl_work WHEN EXISTS(SELECT 1 FROM activity_budget_accounts b WHERE b.instance_id=NEW.instance_id AND b.id=NEW.budget_account_id AND b.activity_id<>NEW.learning_activity_id) BEGIN SELECT RAISE(ABORT,'work budget activity mismatch'); END;

CREATE TRIGGER tl_handoff_pair_insert BEFORE INSERT ON tl_handoff WHEN EXISTS(SELECT 1 FROM tl_content_revision r JOIN tl_decision d ON d.instance_id=r.instance_id AND d.id=NEW.decision_id WHERE r.instance_id=NEW.instance_id AND r.id=NEW.content_revision_id AND (r.decision_id<>d.id OR d.work_id<>NEW.work_id OR d.operation<>'accept' OR r.status<>'accepted')) OR EXISTS(SELECT 1 FROM tl_work w WHERE w.instance_id=NEW.instance_id AND w.id=NEW.work_id AND w.budget_account_id<>NEW.budget_account_id) BEGIN SELECT RAISE(ABORT,'handoff decision/work mismatch'); END;

CREATE TRIGGER tl_handoff_rep_insert BEFORE INSERT ON tl_handoff WHEN EXISTS(SELECT 1 FROM tl_representation p WHERE p.instance_id=NEW.instance_id AND p.id=NEW.representation_id AND (p.content_revision_id<>NEW.content_revision_id OR p.decision_id<>NEW.decision_id OR p.group_id IS NOT NEW.group_id OR p.format_version<>NEW.format_version)) BEGIN SELECT RAISE(ABORT,'handoff representation mismatch'); END;

CREATE TRIGGER tl_barrier_change_insert BEFORE INSERT ON tl_barrier WHEN EXISTS(SELECT 1 FROM tl_change c WHERE c.instance_id=NEW.instance_id AND c.id=NEW.change_id AND (c.source_ref_id<>NEW.source_ref_id OR c.result_epoch<>NEW.source_epoch OR c.kind<>NEW.kind)) BEGIN SELECT RAISE(ABORT,'barrier change mismatch'); END;

CREATE TRIGGER tl_input_revision_insert BEFORE INSERT ON tl_input_dependency WHEN EXISTS(SELECT 1 FROM object_revision_registry r WHERE r.instance_id=NEW.instance_id AND r.id=NEW.source_revision_ref_id AND r.object_id<>NEW.source_ref_id) BEGIN SELECT RAISE(ABORT,'input source revision mismatch'); END;

CREATE TRIGGER tl_epoch_monotonic_insert BEFORE INSERT ON tl_source_epoch WHEN NEW.epoch<0 BEGIN SELECT RAISE(ABORT,'source epoch must increment'); END;

CREATE TRIGGER tl_previous_order_insert BEFORE INSERT ON tl_content_revision WHEN EXISTS(SELECT 1 FROM tl_content_revision p WHERE p.instance_id=NEW.instance_id AND p.id=NEW.previous_revision_id AND p.revision_no>=NEW.revision_no) BEGIN SELECT RAISE(ABORT,'previous revision ordering'); END;

CREATE TRIGGER tl_representation_decision_insert BEFORE INSERT ON tl_representation WHEN EXISTS(SELECT 1 FROM tl_content_revision r WHERE r.instance_id=NEW.instance_id AND r.id=NEW.content_revision_id AND (r.decision_id<>NEW.decision_id OR r.status<>'accepted')) BEGIN SELECT RAISE(ABORT,'representation revision decision mismatch'); END;

CREATE TRIGGER tl_head_owner_insert BEFORE INSERT ON tl_representation_head WHEN EXISTS(SELECT 1 FROM tl_representation p JOIN tl_content_revision r ON r.instance_id=p.instance_id AND r.id=p.content_revision_id WHERE p.instance_id=NEW.instance_id AND p.series_id=NEW.id AND (r.content_id<>NEW.content_id OR p.format_version<>NEW.format_version)) BEGIN SELECT RAISE(ABORT,'head series ownership mismatch'); END;

CREATE TRIGGER tl_work_budget_update BEFORE UPDATE ON tl_work WHEN EXISTS(SELECT 1 FROM activity_budget_accounts b WHERE b.instance_id=NEW.instance_id AND b.id=NEW.budget_account_id AND b.activity_id<>NEW.learning_activity_id) BEGIN SELECT RAISE(ABORT,'work budget activity mismatch'); END;

CREATE TRIGGER tl_handoff_pair_update BEFORE UPDATE ON tl_handoff WHEN EXISTS(SELECT 1 FROM tl_content_revision r JOIN tl_decision d ON d.instance_id=r.instance_id AND d.id=NEW.decision_id WHERE r.instance_id=NEW.instance_id AND r.id=NEW.content_revision_id AND (r.decision_id<>d.id OR d.work_id<>NEW.work_id OR d.operation<>'accept' OR r.status<>'accepted')) OR EXISTS(SELECT 1 FROM tl_work w WHERE w.instance_id=NEW.instance_id AND w.id=NEW.work_id AND w.budget_account_id<>NEW.budget_account_id) BEGIN SELECT RAISE(ABORT,'handoff decision/work mismatch'); END;

CREATE TRIGGER tl_handoff_rep_update BEFORE UPDATE ON tl_handoff WHEN EXISTS(SELECT 1 FROM tl_representation p WHERE p.instance_id=NEW.instance_id AND p.id=NEW.representation_id AND (p.content_revision_id<>NEW.content_revision_id OR p.decision_id<>NEW.decision_id OR p.group_id IS NOT NEW.group_id OR p.format_version<>NEW.format_version)) BEGIN SELECT RAISE(ABORT,'handoff representation mismatch'); END;

CREATE TRIGGER tl_barrier_change_update BEFORE UPDATE ON tl_barrier WHEN EXISTS(SELECT 1 FROM tl_change c WHERE c.instance_id=NEW.instance_id AND c.id=NEW.change_id AND (c.source_ref_id<>NEW.source_ref_id OR c.result_epoch<>NEW.source_epoch OR c.kind<>NEW.kind)) BEGIN SELECT RAISE(ABORT,'barrier change mismatch'); END;

CREATE TRIGGER tl_input_revision_update BEFORE UPDATE ON tl_input_dependency WHEN EXISTS(SELECT 1 FROM object_revision_registry r WHERE r.instance_id=NEW.instance_id AND r.id=NEW.source_revision_ref_id AND r.object_id<>NEW.source_ref_id) BEGIN SELECT RAISE(ABORT,'input source revision mismatch'); END;

CREATE TRIGGER tl_epoch_monotonic_update BEFORE UPDATE ON tl_source_epoch WHEN NEW.epoch<>OLD.epoch+1 BEGIN SELECT RAISE(ABORT,'source epoch must increment'); END;

CREATE TRIGGER tl_previous_order_update BEFORE UPDATE ON tl_content_revision WHEN EXISTS(SELECT 1 FROM tl_content_revision p WHERE p.instance_id=NEW.instance_id AND p.id=NEW.previous_revision_id AND p.revision_no>=NEW.revision_no) BEGIN SELECT RAISE(ABORT,'previous revision ordering'); END;

CREATE TRIGGER tl_representation_decision_update BEFORE UPDATE ON tl_representation WHEN EXISTS(SELECT 1 FROM tl_content_revision r WHERE r.instance_id=NEW.instance_id AND r.id=NEW.content_revision_id AND (r.decision_id<>NEW.decision_id OR r.status<>'accepted')) BEGIN SELECT RAISE(ABORT,'representation revision decision mismatch'); END;

CREATE TRIGGER tl_head_owner_update BEFORE UPDATE ON tl_representation_head WHEN EXISTS(SELECT 1 FROM tl_representation p JOIN tl_content_revision r ON r.instance_id=p.instance_id AND r.id=p.content_revision_id WHERE p.instance_id=NEW.instance_id AND p.series_id=NEW.id AND (r.content_id<>NEW.content_id OR p.format_version<>NEW.format_version)) BEGIN SELECT RAISE(ABORT,'head series ownership mismatch'); END;

CREATE TRIGGER tl_registry_recall_reverse BEFORE INSERT ON object_registry WHEN NEW.kind NOT IN ('memory_revisions','tl_representation') AND EXISTS(SELECT 1 FROM tl_recall_item i WHERE i.instance_id=NEW.instance_id AND i.target_ref_id=NEW.id) BEGIN SELECT RAISE(ABORT,'invalid recall target kind'); END;
CREATE TRIGGER tl_revision_series_reverse BEFORE INSERT ON tl_content_revision WHEN EXISTS(SELECT 1 FROM tl_representation p JOIN tl_representation_head h ON h.instance_id=p.instance_id AND h.id=p.series_id WHERE p.instance_id=NEW.instance_id AND p.content_revision_id=NEW.id AND (h.content_id<>NEW.content_id OR h.format_version<>p.format_version OR p.decision_id<>NEW.decision_id OR NEW.status<>'accepted')) BEGIN SELECT RAISE(ABORT,'late revision representation mismatch'); END;
CREATE TRIGGER tl_previous_reverse BEFORE INSERT ON tl_content_revision WHEN EXISTS(SELECT 1 FROM tl_content_revision r WHERE r.instance_id=NEW.instance_id AND r.previous_revision_id=NEW.id AND r.revision_no<=NEW.revision_no) BEGIN SELECT RAISE(ABORT,'late previous revision ordering'); END;
CREATE TRIGGER tl_handoff_decision_reverse BEFORE INSERT ON tl_decision WHEN EXISTS(SELECT 1 FROM tl_handoff h WHERE h.instance_id=NEW.instance_id AND h.decision_id=NEW.id AND (h.work_id<>NEW.work_id OR h.content_revision_id IS NOT NEW.content_revision_id OR NEW.operation<>'accept')) BEGIN SELECT RAISE(ABORT,'late handoff decision mismatch'); END;
CREATE TRIGGER tl_handoff_revision_reverse BEFORE INSERT ON tl_content_revision WHEN EXISTS(SELECT 1 FROM tl_handoff h WHERE h.instance_id=NEW.instance_id AND h.content_revision_id=NEW.id AND (h.decision_id<>NEW.decision_id OR NEW.status<>'accepted')) BEGIN SELECT RAISE(ABORT,'late handoff revision mismatch'); END;
CREATE TRIGGER tl_handoff_rep_reverse BEFORE INSERT ON tl_representation WHEN EXISTS(SELECT 1 FROM tl_handoff h WHERE h.instance_id=NEW.instance_id AND h.representation_id=NEW.id AND (h.content_revision_id<>NEW.content_revision_id OR h.decision_id<>NEW.decision_id OR h.group_id IS NOT NEW.group_id OR h.format_version<>NEW.format_version)) BEGIN SELECT RAISE(ABORT,'late handoff representation mismatch'); END;
CREATE TRIGGER tl_barrier_change_reverse BEFORE INSERT ON tl_change WHEN EXISTS(SELECT 1 FROM tl_barrier b WHERE b.instance_id=NEW.instance_id AND b.change_id=NEW.id AND (b.source_ref_id<>NEW.source_ref_id OR b.source_epoch<>NEW.result_epoch OR b.kind<>NEW.kind)) BEGIN SELECT RAISE(ABORT,'late barrier change mismatch'); END;

CREATE TRIGGER tl_work_handoff_reverse BEFORE INSERT ON tl_work WHEN EXISTS(SELECT 1 FROM tl_handoff h WHERE h.instance_id=NEW.instance_id AND h.work_id=NEW.id AND h.budget_account_id<>NEW.budget_account_id) BEGIN SELECT RAISE(ABORT,'late work budget mismatch'); END;

CREATE TRIGGER tl_command_initial_revision BEFORE INSERT ON tl_command WHEN NEW.row_revision<>0 BEGIN SELECT RAISE(ABORT,'initial row_revision must be zero'); END;

CREATE TRIGGER tl_work_initial_revision BEFORE INSERT ON tl_work WHEN NEW.row_revision<>0 BEGIN SELECT RAISE(ABORT,'initial row_revision must be zero'); END;

CREATE TRIGGER tl_content_initial_revision BEFORE INSERT ON tl_content WHEN NEW.row_revision<>0 BEGIN SELECT RAISE(ABORT,'initial row_revision must be zero'); END;

CREATE TRIGGER tl_group_initial_revision BEFORE INSERT ON tl_group WHEN NEW.row_revision<>0 BEGIN SELECT RAISE(ABORT,'initial row_revision must be zero'); END;

CREATE TRIGGER tl_handoff_initial_revision BEFORE INSERT ON tl_handoff WHEN NEW.row_revision<>0 BEGIN SELECT RAISE(ABORT,'initial row_revision must be zero'); END;

CREATE TRIGGER tl_representation_head_initial_revision BEFORE INSERT ON tl_representation_head WHEN NEW.row_revision<>0 BEGIN SELECT RAISE(ABORT,'initial row_revision must be zero'); END;

CREATE TRIGGER tl_source_epoch_initial_revision BEFORE INSERT ON tl_source_epoch WHEN NEW.row_revision<>0 BEGIN SELECT RAISE(ABORT,'initial row_revision must be zero'); END;

CREATE TRIGGER tl_barrier_initial_revision BEFORE INSERT ON tl_barrier WHEN NEW.row_revision<>0 BEGIN SELECT RAISE(ABORT,'initial row_revision must be zero'); END;

CREATE TRIGGER tl_propagation_initial_revision BEFORE INSERT ON tl_propagation WHEN NEW.row_revision<>0 BEGIN SELECT RAISE(ABORT,'initial row_revision must be zero'); END;

CREATE TRIGGER tl_erasure_target_initial_revision BEFORE INSERT ON tl_erasure_target WHEN NEW.row_revision<>0 BEGIN SELECT RAISE(ABORT,'initial row_revision must be zero'); END;

CREATE TRIGGER tl_input_dependency_initial_revision BEFORE INSERT ON tl_input_dependency WHEN NEW.row_revision<>0 BEGIN SELECT RAISE(ABORT,'initial row_revision must be zero'); END;

CREATE TRIGGER tl_work_initial_round BEFORE INSERT ON tl_work WHEN NEW.review_round<>0 BEGIN SELECT RAISE(ABORT,'initial review round must be zero'); END;

-- Every accept/candidate owns its newly created revision; only reuse may name an older one.
CREATE TRIGGER tl_decision_owned_target BEFORE INSERT ON tl_decision WHEN NEW.operation IN ('accept','candidate') AND (NEW.content_revision_id IS NULL OR EXISTS(SELECT 1 FROM tl_content_revision r WHERE r.instance_id=NEW.instance_id AND r.id=NEW.content_revision_id AND (r.decision_id<>NEW.id OR r.product_id<>NEW.proposal_id OR r.status<>CASE NEW.operation WHEN 'accept' THEN 'accepted' ELSE 'candidate' END))) BEGIN SELECT RAISE(ABORT,'decision does not own target revision'); END;
CREATE TRIGGER tl_revision_owned_target_reverse BEFORE INSERT ON tl_content_revision WHEN EXISTS(SELECT 1 FROM tl_decision d WHERE d.instance_id=NEW.instance_id AND d.content_revision_id=NEW.id AND d.operation IN ('accept','candidate') AND (NEW.decision_id<>d.id OR NEW.product_id<>d.proposal_id OR NEW.status<>CASE d.operation WHEN 'accept' THEN 'accepted' ELSE 'candidate' END)) BEGIN SELECT RAISE(ABORT,'late revision decision ownership'); END;
CREATE TRIGGER tl_revision_representation_reverse BEFORE INSERT ON tl_content_revision WHEN EXISTS(SELECT 1 FROM tl_representation p WHERE p.instance_id=NEW.instance_id AND p.content_revision_id=NEW.id AND (p.decision_id<>NEW.decision_id OR NEW.status<>'accepted')) BEGIN SELECT RAISE(ABORT,'late representation revision ownership'); END;
