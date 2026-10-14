PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    content_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sites (
    site_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    city TEXT NOT NULL,
    district TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    gps_state TEXT NOT NULL DEFAULT 'disabled'
        CHECK (gps_state IN ('disabled', 'planned', 'enabled')),
    CHECK ((latitude IS NULL AND longitude IS NULL) OR
           (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180))
);

CREATE TABLE IF NOT EXISTS heritage_works (
    work_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    work_type TEXT NOT NULL,
    name TEXT NOT NULL,
    period_text TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL,
    discovery_state TEXT NOT NULL DEFAULT 'published'
        CHECK (discovery_state IN ('draft', 'published', 'retired'))
);

CREATE TABLE IF NOT EXISTS structures (
    structure_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    parent_structure_id TEXT REFERENCES structures(structure_id),
    name TEXT NOT NULL,
    structure_type TEXT NOT NULL,
    present_state TEXT NOT NULL DEFAULT 'unverified',
    relative_position TEXT NOT NULL DEFAULT '',
    geometry_state TEXT NOT NULL DEFAULT 'schematic'
        CHECK (geometry_state IN ('schematic', 'measured', 'reconstructed'))
);

CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    title TEXT NOT NULL,
    creator TEXT NOT NULL DEFAULT '',
    publication_date TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    local_reference TEXT NOT NULL DEFAULT '',
    access_date TEXT NOT NULL DEFAULT '2026-10-14',
    rights_state TEXT NOT NULL DEFAULT 'review_required'
        CHECK (rights_state IN ('provided_for_project', 'open_license', 'permission_required', 'review_required'))
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    structure_id TEXT REFERENCES structures(structure_id),
    claim_text TEXT NOT NULL,
    claim_kind TEXT NOT NULL
        CHECK (claim_kind IN ('verified_fact', 'evidence_based_reconstruction', 'original_fiction', 'unverified')),
    time_scope TEXT NOT NULL DEFAULT '',
    uncertainty_note TEXT NOT NULL DEFAULT '',
    publication_state TEXT NOT NULL DEFAULT 'approved'
        CHECK (publication_state IN ('draft', 'review', 'approved', 'rejected'))
);

CREATE TABLE IF NOT EXISTS claim_sources (
    claim_id TEXT NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    locator TEXT NOT NULL DEFAULT '',
    support_note TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (claim_id, source_id, locator)
);

CREATE TABLE IF NOT EXISTS editorial_review_items (
    review_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    source_locator TEXT NOT NULL DEFAULT '',
    submitted_text TEXT NOT NULL,
    review_state TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_state IN ('pending', 'verified', 'rejected', 'fiction_only')),
    reviewer_note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS media_assets (
    asset_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    source_file_id TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL,
    observed_content TEXT NOT NULL DEFAULT '',
    mapping_state TEXT NOT NULL DEFAULT 'unmapped'
        CHECK (mapping_state IN ('unmapped', 'provisional', 'verified')),
    rights_state TEXT NOT NULL DEFAULT 'review_required'
        CHECK (rights_state IN ('provided_for_project', 'open_license', 'permission_required', 'review_required')),
    alt_text TEXT NOT NULL DEFAULT '',
    structure_id TEXT REFERENCES structures(structure_id),
    UNIQUE (source_id, filename)
);

CREATE TABLE IF NOT EXISTS chapters (
    chapter_id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES sites(site_id),
    title TEXT NOT NULL,
    period_text TEXT NOT NULL,
    premise TEXT NOT NULL,
    fiction_notice TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'review', 'published', 'retired'))
);

CREATE TABLE IF NOT EXISTS game_items (
    item_id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(chapter_id),
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    item_kind TEXT NOT NULL,
    claim_id TEXT REFERENCES claims(claim_id),
    fiction_notice TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS characters (
    character_id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(chapter_id),
    role_name TEXT NOT NULL,
    description TEXT NOT NULL,
    personal_goal TEXT NOT NULL,
    historical_role_claim_id TEXT REFERENCES claims(claim_id),
    starting_item_id TEXT NOT NULL REFERENCES game_items(item_id)
);

CREATE TABLE IF NOT EXISTS scene_nodes (
    node_id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(chapter_id),
    structure_id TEXT REFERENCES structures(structure_id),
    node_order INTEGER NOT NULL,
    title TEXT NOT NULL,
    node_kind TEXT NOT NULL,
    map_x REAL NOT NULL CHECK (map_x BETWEEN 0 AND 100),
    map_y REAL NOT NULL CHECK (map_y BETWEEN 0 AND 100),
    spatial_accuracy TEXT NOT NULL DEFAULT 'schematic'
        CHECK (spatial_accuracy IN ('schematic', 'measured', 'reconstructed')),
    gps_latitude REAL,
    gps_longitude REAL,
    gps_radius_m REAL,
    model_asset_id TEXT,
    UNIQUE (chapter_id, node_order),
    CHECK ((gps_latitude IS NULL AND gps_longitude IS NULL) OR
           (gps_latitude BETWEEN -90 AND 90 AND gps_longitude BETWEEN -180 AND 180))
);

CREATE TABLE IF NOT EXISTS node_evidence (
    node_id TEXT NOT NULL REFERENCES scene_nodes(node_id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    asset_id TEXT REFERENCES media_assets(asset_id),
    PRIMARY KEY (node_id, claim_id, asset_id)
);

CREATE TABLE IF NOT EXISTS task_slots (
    slot_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES scene_nodes(node_id),
    slot_key TEXT NOT NULL,
    task_kind TEXT NOT NULL,
    ai_enabled INTEGER NOT NULL DEFAULT 1 CHECK (ai_enabled IN (0, 1)),
    fallback_task_id TEXT REFERENCES task_candidates(task_id),
    UNIQUE (node_id, slot_key)
);

CREATE TABLE IF NOT EXISTS task_candidates (
    task_id TEXT PRIMARY KEY,
    slot_id TEXT NOT NULL REFERENCES task_slots(slot_id),
    provider TEXT NOT NULL CHECK (provider IN ('manual', 'ai', 'fallback')),
    state TEXT NOT NULL DEFAULT 'draft'
        CHECK (state IN ('draft', 'review', 'published', 'rejected', 'retired')),
    version INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 0,
    validation_state TEXT NOT NULL DEFAULT 'unchecked'
        CHECK (validation_state IN ('unchecked', 'passed', 'failed')),
    task_payload_json TEXT NOT NULL,
    approved_by TEXT NOT NULL DEFAULT '',
    UNIQUE (slot_id, version)
);

CREATE TABLE IF NOT EXISTS task_candidate_claims (
    task_id TEXT NOT NULL REFERENCES task_candidates(task_id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    PRIMARY KEY (task_id, claim_id)
);

CREATE TABLE IF NOT EXISTS task_candidate_assets (
    task_id TEXT NOT NULL REFERENCES task_candidates(task_id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES media_assets(asset_id),
    PRIMARY KEY (task_id, asset_id)
);

CREATE TABLE IF NOT EXISTS story_choices (
    choice_id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(chapter_id),
    node_id TEXT NOT NULL REFERENCES scene_nodes(node_id),
    choice_order INTEGER NOT NULL,
    prompt TEXT NOT NULL,
    options_json TEXT NOT NULL,
    effects_json TEXT NOT NULL,
    fiction_notice TEXT NOT NULL DEFAULT 'This choice is an original fictional scenario.'
);

CREATE TABLE IF NOT EXISTS game_sessions (
    session_id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(chapter_id),
    character_id TEXT NOT NULL REFERENCES characters(character_id),
    state_json TEXT NOT NULL,
    content_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_items (
    session_id TEXT NOT NULL REFERENCES game_sessions(session_id) ON DELETE CASCADE,
    item_id TEXT NOT NULL REFERENCES game_items(item_id),
    acquired_at TEXT NOT NULL,
    item_state_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (session_id, item_id)
);

CREATE TABLE IF NOT EXISTS session_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES game_sessions(session_id) ON DELETE CASCADE,
    node_id TEXT REFERENCES scene_nodes(node_id),
    event_type TEXT NOT NULL,
    event_payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback_events (
    feedback_id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(chapter_id),
    session_id TEXT REFERENCES game_sessions(session_id),
    feedback_kind TEXT NOT NULL,
    feedback_payload_json TEXT NOT NULL,
    consent_state TEXT NOT NULL DEFAULT 'anonymous'
        CHECK (consent_state IN ('anonymous', 'consented', 'withdrawn')),
    created_at TEXT NOT NULL
);

-- Published editorial tasks always outrank AI and fallback candidates.
CREATE VIEW IF NOT EXISTS effective_tasks AS
SELECT task_id, slot_id, provider, version, priority, task_payload_json
FROM (
    SELECT candidate.*,
           ROW_NUMBER() OVER (
               PARTITION BY slot_id
               ORDER BY CASE provider WHEN 'manual' THEN 3 WHEN 'ai' THEN 2 ELSE 1 END DESC,
                        priority DESC, version DESC, task_id ASC
           ) AS candidate_rank
    FROM task_candidates AS candidate
    WHERE state = 'published'
      AND (
          provider <> 'ai'
          OR (
              validation_state = 'passed'
              AND EXISTS (
                  SELECT 1 FROM task_candidate_claims AS link
                  WHERE link.task_id = candidate.task_id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM task_candidate_claims AS link
                  JOIN claims AS claim ON claim.claim_id = link.claim_id
                  JOIN task_slots AS slot ON slot.slot_id = candidate.slot_id
                  WHERE link.task_id = candidate.task_id
                    AND (
                        claim.publication_state <> 'approved'
                        OR claim.claim_kind = 'unverified'
                        OR NOT EXISTS (
                            SELECT 1 FROM node_evidence AS evidence
                            WHERE evidence.node_id = slot.node_id
                              AND evidence.claim_id = claim.claim_id
                        )
                    )
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM task_candidate_assets AS link
                  JOIN media_assets AS asset ON asset.asset_id = link.asset_id
                  JOIN task_slots AS slot ON slot.slot_id = candidate.slot_id
                  WHERE link.task_id = candidate.task_id
                    AND (
                        asset.mapping_state <> 'verified'
                        OR NOT EXISTS (
                            SELECT 1 FROM node_evidence AS evidence
                            WHERE evidence.node_id = slot.node_id
                              AND evidence.asset_id = asset.asset_id
                        )
                    )
              )
          )
      )
)
WHERE candidate_rank = 1;

-- Local publication photographs are derivatives; the 93 Drive originals remain intact.
CREATE TABLE IF NOT EXISTS media_derivatives (
    derivative_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    local_path TEXT NOT NULL,
    pdf_page INTEGER NOT NULL CHECK (pdf_page > 0),
    printed_page TEXT NOT NULL,
    image_index INTEGER NOT NULL CHECK (image_index >= 0),
    caption TEXT NOT NULL,
    structure_id TEXT REFERENCES structures(structure_id),
    review_state TEXT NOT NULL CHECK (review_state IN ('pending', 'verified'))
);
CREATE TABLE IF NOT EXISTS narrative_versions (
    chapter_id TEXT NOT NULL REFERENCES chapters(chapter_id),
    version TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    PRIMARY KEY (chapter_id, version)
);
CREATE TABLE IF NOT EXISTS scene_photos (
    node_id TEXT NOT NULL REFERENCES scene_nodes(node_id),
    derivative_id TEXT NOT NULL REFERENCES media_derivatives(derivative_id),
    PRIMARY KEY (node_id, derivative_id)
);
