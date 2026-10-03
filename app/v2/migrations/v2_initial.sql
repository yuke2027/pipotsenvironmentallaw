
CREATE TABLE v2_channels (
	name VARCHAR(120) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	config JSON NOT NULL, 
	credential_ref VARCHAR(120), 
	enabled BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE v2_cities (
	code VARCHAR(30) NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	timezone VARCHAR(40) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code)
)

;

CREATE TABLE v2_laws (
	title VARCHAR(240) NOT NULL, 
	region VARCHAR(80) NOT NULL, 
	effective_from DATE NOT NULL, 
	effective_to DATE, 
	source_url TEXT NOT NULL, 
	summary TEXT NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (title)
)

;

CREATE TABLE v2_source_attempts (
	local_date DATE NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	message TEXT, 
	job_id VARCHAR(36), 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE v2_source_files (
	source_key VARCHAR(200) NOT NULL, 
	local_date DATE NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	origin VARCHAR(20) NOT NULL, 
	url TEXT, 
	sha256 VARCHAR(64) NOT NULL, 
	storage_key TEXT NOT NULL, 
	is_current BOOLEAN NOT NULL, 
	row_count INTEGER NOT NULL, 
	invalid_count INTEGER NOT NULL, 
	attribution TEXT NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (source_key, sha256)
)

;

CREATE TABLE v2_standards (
	code VARCHAR(80) NOT NULL, 
	pollutant VARCHAR(16) NOT NULL, 
	basis VARCHAR(24) NOT NULL, 
	grade VARCHAR(16) NOT NULL, 
	region VARCHAR(80) NOT NULL, 
	limit_value FLOAT NOT NULL, 
	unit VARCHAR(20) NOT NULL, 
	min_points INTEGER NOT NULL, 
	effective_from DATE NOT NULL, 
	effective_to DATE, 
	source_url TEXT NOT NULL, 
	article TEXT NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code, pollutant, basis, grade, effective_from)
)

;

CREATE TABLE v2_users (
	username VARCHAR(80) NOT NULL, 
	display_name VARCHAR(80) NOT NULL, 
	password_hash TEXT NOT NULL, 
	role VARCHAR(32) NOT NULL, 
	active BOOLEAN NOT NULL, 
	must_change_password BOOLEAN NOT NULL, 
	failed_logins INTEGER NOT NULL, 
	locked_until TIMESTAMP WITH TIME ZONE, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (username)
)

;

CREATE TABLE v2_audits (
	actor_id VARCHAR(36), 
	action VARCHAR(80) NOT NULL, 
	object_type VARCHAR(80) NOT NULL, 
	object_id VARCHAR(64), 
	detail JSON NOT NULL, 
	request_id VARCHAR(64), 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_id) REFERENCES v2_users (id)
)

;

CREATE TABLE v2_enterprises (
	name VARCHAR(200) NOT NULL, 
	credit_code VARCHAR(18), 
	industry VARCHAR(100) NOT NULL, 
	address TEXT NOT NULL, 
	contact VARCHAR(200) NOT NULL, 
	version INTEGER NOT NULL, 
	created_by VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (credit_code), 
	FOREIGN KEY(created_by) REFERENCES v2_users (id)
)

;

CREATE TABLE v2_jobs (
	kind VARCHAR(40) NOT NULL, 
	owner_id VARCHAR(36), 
	parameters JSON NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	progress INTEGER NOT NULL, 
	progress_stage VARCHAR(80), 
	progress_message VARCHAR(240), 
	result JSON NOT NULL, 
	error TEXT, 
	attempts INTEGER NOT NULL, 
	target_key VARCHAR(160) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	heartbeat_at TIMESTAMP WITH TIME ZONE, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_id) REFERENCES v2_users (id)
)

;

CREATE TABLE v2_notifications (
	user_id VARCHAR(36) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	body TEXT NOT NULL, 
	href VARCHAR(240) NOT NULL, 
	dedupe_key VARCHAR(200) NOT NULL, 
	read_at TIMESTAMP WITH TIME ZONE, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (user_id, dedupe_key), 
	FOREIGN KEY(user_id) REFERENCES v2_users (id)
)

;

CREATE TABLE v2_sessions (
	user_id VARCHAR(36) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	csrf_hash VARCHAR(64) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	revoked BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES v2_users (id), 
	UNIQUE (token_hash)
)

;

CREATE TABLE v2_stations (
	city_id VARCHAR(36) NOT NULL, 
	code VARCHAR(100) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	latitude FLOAT, 
	longitude FLOAT, 
	active BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (city_id, code), 
	FOREIGN KEY(city_id) REFERENCES v2_cities (id)
)

;

CREATE TABLE v2_aqi_results (
	station_id VARCHAR(36) NOT NULL, 
	local_date DATE NOT NULL, 
	value INTEGER, 
	components JSON NOT NULL, 
	complete BOOLEAN NOT NULL, 
	version VARCHAR(32) NOT NULL, 
	snapshot_hash VARCHAR(64) NOT NULL, 
	is_current BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (station_id, local_date, snapshot_hash, version), 
	FOREIGN KEY(station_id) REFERENCES v2_stations (id)
)

;

CREATE TABLE v2_deliveries (
	notification_id VARCHAR(36) NOT NULL, 
	channel_id VARCHAR(36) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	attempts INTEGER NOT NULL, 
	error TEXT, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (notification_id, channel_id), 
	FOREIGN KEY(notification_id) REFERENCES v2_notifications (id), 
	FOREIGN KEY(channel_id) REFERENCES v2_channels (id)
)

;

CREATE TABLE v2_enterprise_records (
	enterprise_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	details JSON NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(enterprise_id) REFERENCES v2_enterprises (id)
)

;

CREATE TABLE v2_evaluations (
	station_id VARCHAR(36) NOT NULL, 
	local_date DATE NOT NULL, 
	pollutant VARCHAR(16) NOT NULL, 
	basis VARCHAR(24) NOT NULL, 
	standard_id VARCHAR(36) NOT NULL, 
	standard_snapshot JSON NOT NULL, 
	snapshot_hash VARCHAR(64) NOT NULL, 
	valid_points INTEGER NOT NULL, 
	value FLOAT, 
	exceed_ratio FLOAT, 
	status VARCHAR(24) NOT NULL, 
	is_current BOOLEAN NOT NULL, 
	job_id VARCHAR(36), 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (station_id, local_date, pollutant, basis, snapshot_hash, standard_id), 
	FOREIGN KEY(station_id) REFERENCES v2_stations (id), 
	FOREIGN KEY(standard_id) REFERENCES v2_standards (id)
)

;

CREATE TABLE v2_models (
	task VARCHAR(24) NOT NULL, 
	algorithm VARCHAR(40) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	storage_key TEXT NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	manifest JSON NOT NULL, 
	metrics JSON NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(job_id) REFERENCES v2_jobs (id)
)

;

CREATE TABLE v2_observations (
	source_file_id VARCHAR(36) NOT NULL, 
	station_id VARCHAR(36) NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	local_date DATE NOT NULL, 
	pollutant VARCHAR(16) NOT NULL, 
	basis VARCHAR(24) NOT NULL, 
	value FLOAT, 
	unit VARCHAR(20) NOT NULL, 
	quality VARCHAR(20) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (source_file_id, station_id, observed_at, pollutant, basis), 
	FOREIGN KEY(source_file_id) REFERENCES v2_source_files (id), 
	FOREIGN KEY(station_id) REFERENCES v2_stations (id)
)

;

CREATE TABLE v2_outbox (
	job_id VARCHAR(36) NOT NULL, 
	sent_at TIMESTAMP WITH TIME ZONE, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (job_id), 
	FOREIGN KEY(job_id) REFERENCES v2_jobs (id)
)

;

CREATE TABLE v2_station_aliases (
	station_id VARCHAR(36) NOT NULL, 
	provider VARCHAR(50) NOT NULL, 
	external_name VARCHAR(100) NOT NULL, 
	valid_from DATE NOT NULL, 
	valid_to DATE, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (provider, external_name, valid_from), 
	FOREIGN KEY(station_id) REFERENCES v2_stations (id)
)

;

CREATE TABLE v2_derived_values (
	station_id VARCHAR(36) NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	pollutant VARCHAR(16) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	value FLOAT NOT NULL, 
	lower FLOAT, 
	upper FLOAT, 
	model_id VARCHAR(36), 
	job_id VARCHAR(36) NOT NULL, 
	data_cutoff TIMESTAMP WITH TIME ZONE NOT NULL, 
	snapshot_hash VARCHAR(64) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (job_id, station_id, observed_at, pollutant, kind), 
	FOREIGN KEY(station_id) REFERENCES v2_stations (id), 
	FOREIGN KEY(model_id) REFERENCES v2_models (id), 
	FOREIGN KEY(job_id) REFERENCES v2_jobs (id)
)

;

CREATE TABLE v2_leads (
	title VARCHAR(200) NOT NULL, 
	description TEXT NOT NULL, 
	station_id VARCHAR(36), 
	enterprise_id VARCHAR(36), 
	evaluation_id VARCHAR(36), 
	status VARCHAR(24) NOT NULL, 
	priority VARCHAR(20) NOT NULL, 
	created_by VARCHAR(36), 
	reason TEXT, 
	claimed_by VARCHAR(36), 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(station_id) REFERENCES v2_stations (id), 
	FOREIGN KEY(enterprise_id) REFERENCES v2_enterprises (id), 
	UNIQUE (evaluation_id), 
	FOREIGN KEY(evaluation_id) REFERENCES v2_evaluations (id), 
	FOREIGN KEY(created_by) REFERENCES v2_users (id), 
	FOREIGN KEY(claimed_by) REFERENCES v2_users (id)
)

;

CREATE TABLE v2_model_activations (
	task VARCHAR(24) NOT NULL, 
	model_id VARCHAR(36) NOT NULL, 
	previous_id VARCHAR(36), 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (task), 
	FOREIGN KEY(model_id) REFERENCES v2_models (id), 
	FOREIGN KEY(previous_id) REFERENCES v2_models (id)
)

;

CREATE TABLE v2_inspections (
	title VARCHAR(200) NOT NULL, 
	lead_id VARCHAR(36), 
	enterprise_id VARCHAR(36), 
	assignee_id VARCHAR(36) NOT NULL, 
	collaborators JSON NOT NULL, 
	created_by VARCHAR(36) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	due_date DATE, 
	facts TEXT NOT NULL, 
	legal_references JSON NOT NULL, 
	version INTEGER NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (lead_id), 
	FOREIGN KEY(lead_id) REFERENCES v2_leads (id), 
	FOREIGN KEY(enterprise_id) REFERENCES v2_enterprises (id), 
	FOREIGN KEY(assignee_id) REFERENCES v2_users (id), 
	FOREIGN KEY(created_by) REFERENCES v2_users (id)
)

;

CREATE TABLE v2_attachments (
	inspection_id VARCHAR(36), 
	enterprise_id VARCHAR(36), 
	owner_id VARCHAR(36) NOT NULL, 
	original_name VARCHAR(240) NOT NULL, 
	mime VARCHAR(100) NOT NULL, 
	size INTEGER NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	storage_key TEXT NOT NULL, 
	replaces_id VARCHAR(36), 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(inspection_id) REFERENCES v2_inspections (id), 
	FOREIGN KEY(enterprise_id) REFERENCES v2_enterprises (id), 
	FOREIGN KEY(owner_id) REFERENCES v2_users (id), 
	FOREIGN KEY(replaces_id) REFERENCES v2_attachments (id)
)

;

CREATE TABLE v2_rectifications (
	inspection_id VARCHAR(36) NOT NULL, 
	requirement TEXT NOT NULL, 
	due_date DATE NOT NULL, 
	response TEXT NOT NULL, 
	review_note TEXT NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(inspection_id) REFERENCES v2_inspections (id)
)

;

CREATE TABLE v2_workflow_events (
	inspection_id VARCHAR(36) NOT NULL, 
	actor_id VARCHAR(36) NOT NULL, 
	action VARCHAR(40) NOT NULL, 
	from_status VARCHAR(32) NOT NULL, 
	to_status VARCHAR(32) NOT NULL, 
	note TEXT NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(inspection_id) REFERENCES v2_inspections (id), 
	FOREIGN KEY(actor_id) REFERENCES v2_users (id)
)

;
CREATE INDEX ix_v2_source_attempts_local_date ON v2_source_attempts (local_date);
CREATE INDEX ix_v2_source_current_date ON v2_source_files (is_current, local_date);
CREATE INDEX ix_v2_source_files_source_key ON v2_source_files (source_key);
CREATE INDEX ix_v2_audits_action ON v2_audits (action);
CREATE INDEX ix_v2_enterprises_name ON v2_enterprises (name);
CREATE INDEX ix_v2_jobs_kind ON v2_jobs (kind);
CREATE INDEX ix_v2_jobs_status ON v2_jobs (status);
CREATE INDEX ix_v2_notifications_user_id ON v2_notifications (user_id);
CREATE INDEX ix_v2_sessions_expires_at ON v2_sessions (expires_at);
CREATE INDEX ix_v2_sessions_user_id ON v2_sessions (user_id);
CREATE INDEX ix_v2_stations_city_id ON v2_stations (city_id);
CREATE INDEX ix_v2_aqi_results_local_date ON v2_aqi_results (local_date);
CREATE INDEX ix_v2_enterprise_records_enterprise_id ON v2_enterprise_records (enterprise_id);
CREATE INDEX ix_v2_evaluations_local_date ON v2_evaluations (local_date);
CREATE INDEX ix_v2_evaluations_station_id ON v2_evaluations (station_id);
CREATE INDEX ix_v2_obs_date_basis_pollutant ON v2_observations (local_date, basis, pollutant, station_id);
CREATE INDEX ix_v2_obs_station_pollutant_time ON v2_observations (station_id, pollutant, observed_at);
CREATE INDEX ix_v2_obs_time_pollutant ON v2_observations (observed_at, pollutant);
CREATE INDEX ix_v2_observations_local_date ON v2_observations (local_date);
CREATE INDEX ix_v2_observations_source_file_id ON v2_observations (source_file_id);
CREATE INDEX ix_v2_derived_values_observed_at ON v2_derived_values (observed_at);
CREATE INDEX ix_v2_derived_values_station_id ON v2_derived_values (station_id);
CREATE INDEX ix_v2_inspections_assignee_id ON v2_inspections (assignee_id);
CREATE INDEX ix_v2_inspections_status ON v2_inspections (status);
CREATE INDEX ix_v2_attachments_enterprise_id ON v2_attachments (enterprise_id);
CREATE INDEX ix_v2_attachments_inspection_id ON v2_attachments (inspection_id);
CREATE INDEX ix_v2_rectifications_inspection_id ON v2_rectifications (inspection_id);
CREATE INDEX ix_v2_workflow_events_inspection_id ON v2_workflow_events (inspection_id);
