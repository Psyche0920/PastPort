PRAGMA foreign_keys=ON;
CREATE TABLE documents(id TEXT PRIMARY KEY,original_path TEXT NOT NULL,sha256 TEXT NOT NULL,page_count INTEGER NOT NULL,rights_state TEXT NOT NULL);
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE source_pages(pdf_page INTEGER PRIMARY KEY,printed_page INTEGER NOT NULL,raw_text TEXT NOT NULL,normalized_text TEXT NOT NULL,text_sha256 TEXT NOT NULL,extraction_method TEXT NOT NULL);
CREATE TABLE buildings(id TEXT PRIMARY KEY,title TEXT NOT NULL,evidence TEXT NOT NULL);
CREATE TABLE modern_objects(id INTEGER PRIMARY KEY,name TEXT NOT NULL,category TEXT NOT NULL,note TEXT NOT NULL,parent_id INTEGER REFERENCES modern_objects(id) DEFERRABLE INITIALLY DEFERRED);
CREATE TABLE photos(id INTEGER PRIMARY KEY,filename TEXT NOT NULL,media_path TEXT NOT NULL,original_path TEXT NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,sha256 TEXT NOT NULL);
CREATE TABLE observations(id INTEGER PRIMARY KEY,photo_id INTEGER NOT NULL REFERENCES photos(id),object_id INTEGER NOT NULL REFERENCES modern_objects(id),x0 REAL NOT NULL,y0 REAL NOT NULL,x1 REAL NOT NULL,y1 REAL NOT NULL,identity_state TEXT NOT NULL,note TEXT NOT NULL,identity_basis TEXT NOT NULL,CHECK(x0>=0 AND y0>=0 AND x1<=1 AND y1<=1 AND x1>x0 AND y1>y0));
CREATE TABLE historical_objects(id TEXT PRIMARY KEY,building_id TEXT NOT NULL REFERENCES buildings(id),parent_ref TEXT,title_zh TEXT NOT NULL,title_en TEXT NOT NULL,image_page INTEGER NOT NULL REFERENCES source_pages(pdf_page),image_box TEXT NOT NULL,media_path TEXT NOT NULL,text_scope TEXT NOT NULL,scope_warning TEXT NOT NULL);
CREATE TABLE passages(id INTEGER PRIMARY KEY,pdf_page INTEGER NOT NULL REFERENCES source_pages(pdf_page),start_offset INTEGER NOT NULL,end_offset INTEGER NOT NULL,exact_text TEXT NOT NULL,prefix TEXT NOT NULL,suffix TEXT NOT NULL,UNIQUE(pdf_page,start_offset,end_offset));
CREATE TABLE text_associations(historical_id TEXT PRIMARY KEY REFERENCES historical_objects(id),passage_id INTEGER NOT NULL REFERENCES passages(id),translation_zh TEXT NOT NULL,coverage TEXT NOT NULL,limitation TEXT NOT NULL,method TEXT NOT NULL,review_state TEXT NOT NULL);
CREATE TABLE pairings(modern_id INTEGER PRIMARY KEY REFERENCES modern_objects(id),historical_id TEXT REFERENCES historical_objects(id),proposal_state TEXT NOT NULL,rationale TEXT NOT NULL,method TEXT NOT NULL,visual_score REAL,semantic_score REAL,image_review TEXT NOT NULL,text_review TEXT NOT NULL,version INTEGER NOT NULL);
CREATE TABLE review_events(id INTEGER PRIMARY KEY,modern_id INTEGER NOT NULL REFERENCES pairings(modern_id),image_verdict TEXT NOT NULL CHECK(image_verdict IN ('unreviewed','suitable','unsuitable','uncertain')),text_verdict TEXT NOT NULL CHECK(text_verdict IN ('unreviewed','direct','context_only','unsuitable','uncertain')),note TEXT NOT NULL,reviewer TEXT NOT NULL,created_at TEXT NOT NULL,previous_version INTEGER NOT NULL);
CREATE TABLE design_references(title TEXT PRIMARY KEY,url TEXT NOT NULL,basis TEXT NOT NULL);
CREATE INDEX observations_object ON observations(object_id);

CREATE TABLE media_assets(path TEXT PRIMARY KEY,sha256 TEXT NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL);

CREATE TABLE assistant_semantic_audit(historical_id TEXT PRIMARY KEY REFERENCES historical_objects(id),verdict TEXT NOT NULL,recommended_display_zh TEXT NOT NULL,limitation TEXT NOT NULL,reviewer TEXT NOT NULL,basis TEXT NOT NULL);
