INSERT OR IGNORE INTO projects (project_id, name, content_version)
VALUES ('pastport', 'PastPort Heritage Experience', 'bursa-muradiye-0.1.0');

INSERT OR IGNORE INTO sites (site_id, project_id, city, district, name, description, gps_state)
VALUES ('bursa-muradiye', 'pastport', 'Bursa', 'Osmangazi', 'Muradiye Külliyesi',
        'A compact heritage cluster used for the first Bursa pilot. Current map positions are schematic.', 'disabled');

INSERT OR IGNORE INTO heritage_works (work_id, site_id, work_type, name, period_text, summary)
VALUES
('muradiye-mosque', 'bursa-muradiye', 'mosque', 'Muradiye Camii', '1425–1426', 'A mosque commissioned by Sultan II Murad; use its architecture and cited inscriptions as evidence.'),
('muradiye-medrese', 'bursa-muradiye', 'madrasa', 'Muradiye Medresesi', '15th century; later restorations', 'A madrasa described with sixteen student cells, a courtyard, arcades, and an octagonal pool; later converted into a manuscript museum.'),
('muradiye-fountain', 'bursa-muradiye', 'fountain', 'Sıbyan Mektebi (Medrese) Çeşmesi', '15th century', 'The inventory identifies this as the only fountain in the complex that is a waqf work; its photographed match remains unconfirmed.'),
('muradiye-imaret', 'bursa-muradiye', 'imaret', 'İkinci Murad (Muradiye) İmareti', '1425; later restorations', 'The inventory documents a surviving imaret building, oven traces and storage jars; its present use must be rechecked.'),
('muradiye-bath', 'bursa-muradiye', 'bath', 'Muradiye Hamamı', '1426; later restorations', 'The bathhouse lies west of the madrasa and has a sequence of bathing spaces; the inventory records later reuse.'),
('tomb-murad-ii', 'bursa-muradiye', 'tomb', 'Sultan II. Murad Türbesi', '1451 onward', 'A tomb in the complex; detailed features are catalogued in the inventory volume.'),
('tomb-aladdin-ali', 'bursa-muradiye', 'tomb', 'Şehzade Alâaddin Ali Türbesi', '1442', 'A tomb in the complex, described in the inventory volume.'),
('tomb-cariyeler', 'bursa-muradiye', 'tomb', 'Cariyeler (Saraylılar) Türbesi', '', 'A tomb in the complex, described in the inventory volume.'),
('tomb-cem-sultan', 'bursa-muradiye', 'tomb', 'Cem Sultan Türbesi', '', 'A tomb in the complex, described in the inventory volume.'),
('tomb-ebe-hatun', 'bursa-muradiye', 'tomb', 'Ebe Hatun Türbesi', '', 'A tomb in the complex, described in the inventory volume.'),
('tomb-gulruh-hatun', 'bursa-muradiye', 'tomb', 'Gülruh Hatun Türbesi', '1527', 'A tomb in the complex, described in the inventory volume.'),
('tomb-gulsah-hatun', 'bursa-muradiye', 'tomb', 'Gülşah Hatun Türbesi', '', 'A tomb in the complex, described in the inventory volume.'),
('tomb-huma-hatun', 'bursa-muradiye', 'tomb', 'Hüma Hatun (Hatuniye) Türbesi', '', 'A tomb in the complex, described in the inventory volume.'),
('tomb-mukrime-hatun', 'bursa-muradiye', 'tomb', 'Mükrime Hatun Türbesi', '', 'A tomb in the complex, described in the inventory volume.'),
('tomb-sehzade-ahmet', 'bursa-muradiye', 'tomb', 'Şehzade Ahmet Türbesi', '1513', 'A tomb in the complex, described in the inventory volume.'),
('tomb-sehzade-mahmut', 'bursa-muradiye', 'tomb', 'Şehzade Mahmut Türbesi', '1506', 'A tomb in the complex, described in the inventory volume.'),
('tomb-sehzade-mustafa', 'bursa-muradiye', 'tomb', 'Şehzade Mustafa Türbesi', '1573', 'A tomb in the complex with a documented inscription, İznik tiles and reused architectural material.'),
('tomb-sirin-hatun', 'bursa-muradiye', 'tomb', 'Şirin Hatun Türbesi', '', 'A tomb in the complex, described in the inventory volume.');

INSERT OR IGNORE INTO structures (structure_id, site_id, name, structure_type, present_state, relative_position, geometry_state)
VALUES
('mosque', 'bursa-muradiye', 'Muradiye Mosque', 'mosque', 'present; detailed current survey pending', 'site anchor; schematic', 'schematic'),
('medrese', 'bursa-muradiye', 'Muradiye Madrasa', 'madrasa', 'museum use documented in 2019; recheck current status', 'west of mosque, same alignment in cited study', 'schematic'),
('imaret', 'bursa-muradiye', 'Muradiye Imaret', 'imaret', 'inventory reports restaurant use since early 2000s; recheck current use', 'about 20 m northeast of mosque', 'schematic'),
('school-fountain', 'bursa-muradiye', 'Sıbyan Mektebi (Medrese) Fountain', 'fountain', 'inventory identifies the waqf fountain; photo match pending', 'western end of the complex', 'schematic'),
('bath', 'bursa-muradiye', 'Muradiye Bath', 'bath', 'inventory records later conversion to a clothing shop in 2020; recheck current use', 'west of madrasa', 'schematic'),
('tomb-garden', 'bursa-muradiye', 'Muradiye tomb cluster', 'tomb_cluster', 'inventory covers thirteen tombs; current access details pending', 'southwest garden and surrounding cluster; schematic', 'schematic'),
('tomb-murad-ii', 'bursa-muradiye', 'Sultan II. Murad Tomb', 'tomb', 'inventory documented', 'southwest of mosque', 'schematic'),
('tomb-aladdin-ali', 'bursa-muradiye', 'Şehzade Alâaddin Ali Tomb', 'tomb', 'inventory documented', 'within tomb cluster; precise point pending', 'schematic'),
('tomb-cariyeler', 'bursa-muradiye', 'Cariyeler (Saraylılar) Tomb', 'tomb', 'inventory documented', 'within tomb cluster; precise point pending', 'schematic'),
('tomb-cem-sultan', 'bursa-muradiye', 'Cem Sultan Tomb', 'tomb', 'inventory documented', 'within tomb cluster; precise point pending', 'schematic'),
('tomb-ebe-hatun', 'bursa-muradiye', 'Ebe Hatun Tomb', 'tomb', 'inventory documented', 'within tomb cluster; precise point pending', 'schematic'),
('tomb-gulruh-hatun', 'bursa-muradiye', 'Gülruh Hatun Tomb', 'tomb', 'inventory documented', 'within tomb cluster; precise point pending', 'schematic'),
('tomb-gulsah-hatun', 'bursa-muradiye', 'Gülşah Hatun Tomb', 'tomb', 'inventory documented', 'within tomb cluster; precise point pending', 'schematic'),
('tomb-huma-hatun', 'bursa-muradiye', 'Hüma Hatun Tomb', 'tomb', 'inventory documented', 'within tomb cluster; precise point pending', 'schematic'),
('tomb-mukrime-hatun', 'bursa-muradiye', 'Mükrime Hatun Tomb', 'tomb', 'inventory documented', 'within tomb cluster; precise point pending', 'schematic'),
('tomb-sehzade-ahmet', 'bursa-muradiye', 'Şehzade Ahmet Tomb', 'tomb', 'inventory documented', 'between mosque and Sultan Murad II tomb', 'schematic'),
('tomb-sehzade-mahmut', 'bursa-muradiye', 'Şehzade Mahmut Tomb', 'tomb', 'inventory documented', 'western side of tomb cluster', 'schematic'),
('tomb-sehzade-mustafa', 'bursa-muradiye', 'Şehzade Mustafa Tomb', 'tomb', 'open to visitors per inventory; current access to recheck', 'Sedat Street, tomb cluster', 'schematic'),
('tomb-sirin-hatun', 'bursa-muradiye', 'Şirin Hatun Tomb', 'tomb', 'inventory documented', 'within tomb cluster; precise point pending', 'schematic');

INSERT OR IGNORE INTO sources (source_id, source_type, title, creator, publication_date, url, local_reference, rights_state)
VALUES
('src-vakfiye-study', 'academic_article', 'Sultan II. Murad’ın Bursa Vakfiyesi', 'Fatma Gül Altun', '2022', 'https://dergipark.org.tr/tr/pub/uluifd/article/1071329', '', 'review_required'),
('src-layout-study', 'academic_thesis', 'Bursa Muradiye Külliyesi and tombs study (site plan and architectural descriptions)', 'Ayşegül Kamacı', '2020', 'https://acikerisim.erbakan.edu.tr/bitstreams/53db0ca4-7000-4e68-a4bd-0fcc804081c8/download', '', 'review_required'),
('src-tdv', 'encyclopedia', 'Murâdiye Külliyesi', 'Doğan Yavaş / TDV İslâm Ansiklopedisi', '2020', 'https://islamansiklopedisi.org.tr/muradiye-kulliyesi--bursa', '', 'review_required'),
('src-inventory-volume', 'inventory_volume', 'Vakıf Eserleri Envanteri - II. Murad Külliyesi', 'Vakıf Katılım / inventory publication', '', '', '/Users/hanweijia/Downloads/4-II. Murat Külliyesi.pdf (printed pages 111–170)', 'review_required'),
('src-drive-photos', 'photo_archive', 'Vakıf Eserleri Envanteri - Bursa Fotoğraf Arşivi / II. Murad Külliyesi', 'Vakıf Katılım / KÖK & KOD announcement', '2025', 'https://drive.google.com/drive/folders/18rlNGjpMhGuazgqqOUkJRDNbPEBIcTbh', 'Links: https://drive.google.com/drive/folders/1HbbB-StFjGefpePbEj52DctQnnyS_HOe', 'provided_for_project'),
('src-info-note', 'competition_document', 'Foundation Heritage Inventory Project — Information Note', 'Vakıf Katılım', '2026', '', '/Users/hanweijia/Downloads/PastPort/ROOT&CODE HACKATHON - FOUNDATION HERITAGE INVENTORY PROJECT - INFORMATION NOTE.pdf', 'review_required'),
('src-terms', 'competition_document', 'ROOT&CODE Hackathon Terms and Conditions', 'Bilişim Vadisi / Vakıf Katılım', '2026', '', '/Users/hanweijia/Downloads/PastPort/ROOT&CODE Hackathon _ Terms and Conditions_ENG.pdf', 'review_required'),
('src-legacy-blueprint', 'project_design_draft', 'PastPort: Chapter Blueprint Specification (prior draft)', 'Project team', '', '', '/Users/hanweijia/Downloads/PastPort-Bursa_Chapter_Design_Document_v3 (2).pdf', 'review_required');

INSERT OR IGNORE INTO claims (claim_id, site_id, structure_id, claim_text, claim_kind, time_scope, uncertainty_note, publication_state)
VALUES
('claim-mosque-date', 'bursa-muradiye', 'mosque', 'Construction of Muradiye Mosque began in 1425 and was completed in 1426.', 'verified_fact', '1425–1426', '', 'approved'),
('claim-vakfiye-date', 'bursa-muradiye', NULL, 'The study uses an Arabic copy of the Bursa vakfiye dated 22 Shawwal 833 / 14 July 1430, alongside an Ottoman translation copy dated 1907.', 'verified_fact', '15th-century document; later translation copy', 'This dates source copies, not the fictional game incident.', 'approved'),
('claim-waqf-scale', 'bursa-muradiye', NULL, 'The study counts 58 waqf revenue sources, 89 staff and 24 duties in the vakfiye.', 'verified_fact', 'as described in the vakfiye study', 'Use as the article’s count, not as a contemporary figure.', 'approved'),
('claim-imaret-meals', 'bursa-muradiye', 'imaret', 'The vakfiye study reports two meals per day for people present at the imaret without distinction.', 'verified_fact', 'vakfiye provisions', 'A historical rule; do not imply present-day operation.', 'approved'),
('claim-katib-keeper', 'bursa-muradiye', 'imaret', 'The study describes a scribe recording incoming and outgoing goods and store personnel safeguarding supplies.', 'verified_fact', 'vakfiye staff duties', '', 'approved'),
('claim-fountain-repair', 'bursa-muradiye', 'school-fountain', 'The vakfiye study lists two architects responsible for maintaining or repairing fountains in the complex.', 'verified_fact', 'vakfiye staff duties', 'This general duty does not identify any one surviving fountain.', 'approved'),
('claim-medrese-space', 'bursa-muradiye', 'medrese', 'The inventory describes a 17 × 17 m arcaded courtyard, sixteen cells, a classroom iwan and an octagonal marble pool.', 'verified_fact', 'inventory pp. 120–122', 'Later alterations mean this historical plan must be distinguished from the present interior.', 'approved'),
('claim-medrese-change', 'bursa-muradiye', 'medrese', 'The architectural study says the courtyard was later covered and the madrasa opened as a Qur’an and Manuscripts Museum in 2019.', 'verified_fact', 'change documented by the 2020 study', 'Recheck current operation and distinguish current state from historical layout.', 'approved'),
('claim-stipend-discrepancy', 'bursa-muradiye', 'medrese', 'The vakfiye study notes a mismatch between student-stipend values in the Arabic copy and Ottoman transcription; the author considers the transcription likely erroneous.', 'verified_fact', 'comparison of document copies', 'Do not treat the figures as directly convertible or publish a single resolved amount.', 'approved'),
('claim-madrasa-fountain', 'bursa-muradiye', 'school-fountain', 'The inventory identifies the Sıbyan Mektebi (Medrese) Fountain at the western end as the complex’s only fountain considered a waqf work. It describes a pointed-arch brick niche, zigzag brick framing, two cup recesses, and a küfeki-stone basin measuring 1.30 × 0.43 m.', 'verified_fact', 'inventory pp. 123', 'A photographed fountain in the Drive archive has not yet been matched to this entry.', 'approved'),
('claim-imaret-architecture', 'bursa-muradiye', 'imaret', 'The inventory locates the imaret about 20 m northeast of the mosque and records a 13 × 40 m building with oven traces and grain and oil jars; adjacent pantry, wood store, flour store, and stables no longer survive.', 'verified_fact', 'inventory pp. 124–125', 'The inventory reports restaurant use since the early 2000s; confirm current use before publication.', 'approved'),
('claim-muradiye-tomb-count', 'bursa-muradiye', 'tomb-garden', 'The inventory volume documents thirteen tombs in the Muradiye complex, spanning 1442 to 1573.', 'verified_fact', 'inventory p. 111 and pp. 130–166', 'The volume’s count and named entries; later surveys may classify the group differently.', 'approved'),
('claim-mustafa-tomb-history', 'bursa-muradiye', 'tomb-sehzade-mustafa', 'The inventory states that Şehzade Mustafa died in 1553, was first buried elsewhere, and was transferred to this tomb when it was built in 1573; the entry transcribes the tomb-door inscription.', 'verified_fact', 'inventory p. 163', '', 'approved'),
('claim-mustafa-tomb-material', 'bursa-muradiye', 'tomb-sehzade-mustafa', 'The inventory describes an octagonal tomb with 16th-century İznik tiles, reused marble slabs and columns from Bursa Palace, and fourteen windows.', 'verified_fact', 'inventory p. 164', 'Description is from the inventory volume; verify against present-day conservation before making condition claims.', 'approved'),
('claim-mustafa-fourth-sarcophagus', 'bursa-muradiye', 'tomb-sehzade-mustafa', 'The inventory identifies three of four sarcophagi; the fourth is unknown and is only tentatively attributed to Şehzade Orhan.', 'verified_fact', 'inventory p. 164', 'The fourth attribution is explicitly uncertain and must remain unknown in gameplay answers.', 'approved'),
('claim-fictional-stock-mismatch', 'bursa-muradiye', 'imaret', 'A fictional storeroom count conflicts with a fictional entry in the player’s scenario ledger.', 'original_fiction', 'fictional scenario set around the 1430 document context', 'Invented solely for gameplay; no source reports this event.', 'approved');

INSERT OR IGNORE INTO claim_sources (claim_id, source_id, locator, support_note)
VALUES
('claim-mosque-date', 'src-tdv', 'Muradiye Külliyesi / dates', 'Cross-check with the architectural study.'),
('claim-vakfiye-date', 'src-vakfiye-study', 'Abstract and document description', 'Primary-source copy dates as described by the article.'),
('claim-waqf-scale', 'src-vakfiye-study', 'Abstract', 'Counts reported by the article.'),
('claim-imaret-meals', 'src-vakfiye-study', 'Vakfiye staff and meal provisions section', 'Historical provision, not present-day operation.'),
('claim-katib-keeper', 'src-vakfiye-study', 'Staff duties section', 'Describes scribe and store staff duties.'),
('claim-fountain-repair', 'src-vakfiye-study', 'Staff duties section', 'Two architects are listed for fountain maintenance.'),
('claim-medrese-space', 'src-layout-study', 'Muradiye Medresesi section', 'Space description and cell count.'),
('claim-medrese-change', 'src-layout-study', 'Muradiye Medresesi section', 'Use and courtyard change as documented in the 2020 study.'),
('claim-stipend-discrepancy', 'src-vakfiye-study', 'Student payments and transcription footnote', 'Preserve source disagreement in the user-facing explanation.');

INSERT OR IGNORE INTO claim_sources (claim_id, source_id, locator, support_note)
VALUES
('claim-mosque-date', 'src-inventory-volume', 'Printed pp. 111, 113', 'Entry and translation of the mosque construction inscription.'),
('claim-medrese-space', 'src-inventory-volume', 'Printed pp. 120–122', 'Includes 17 × 17 m courtyard, sixteen cells, arcade, octagonal pool and room features.'),
('claim-medrese-change', 'src-inventory-volume', 'Printed p. 122', 'Records restoration and later uses up through the inventory’s publication period.'),
('claim-madrasa-fountain', 'src-inventory-volume', 'Printed p. 123', 'Identifies the waqf fountain and describes its brick niche and basin.'),
('claim-imaret-architecture', 'src-inventory-volume', 'Printed pp. 124–125', 'Building position, dimensions, oven traces, jars, later restoration and use.'),
('claim-muradiye-tomb-count', 'src-inventory-volume', 'Printed pp. 111, 130–166', 'The overview states thirteen tombs; named entries span the listed section.'),
('claim-mustafa-tomb-history', 'src-inventory-volume', 'Printed p. 163', 'Chronology and translated tomb-door inscription.'),
('claim-mustafa-tomb-material', 'src-inventory-volume', 'Printed p. 164', 'Building form, reused material, Iznik tiles and window count.'),
('claim-mustafa-fourth-sarcophagus', 'src-inventory-volume', 'Printed p. 164', 'Fourth occupant is unknown; Orhan is only a proposed attribution.');

INSERT OR IGNORE INTO editorial_review_items (review_id, site_id, source_id, source_locator, submitted_text, review_state, reviewer_note)
VALUES
('review-legacy-1563-anchor', 'bursa-muradiye', 'src-legacy-blueprint', 'pp. 1–3', 'The previous story draft treats 1563 political conditions and Mahidevran Hatun’s poverty and merchant debts as established setting facts.', 'pending', 'Do not use as historical fact without independent primary or academic sources.'),
('review-legacy-secret-poem', 'bursa-muradiye', 'src-legacy-blueprint', 'pp. 3–4', 'The previous story draft presents a hidden poem behind an Iznik tile and its discovery during a 2020 restoration as an event.', 'fiction_only', 'No support found in the inventory volume; retain only if explicitly labeled as alternate-history fiction.'),
('review-legacy-venice-manuscript', 'bursa-muradiye', 'src-legacy-blueprint', 'p. 4', 'The previous story draft links the Muradiye story to a manuscript fragment in Venice.', 'pending', 'Requires an independently verifiable catalogue record and provenance; omit meanwhile.');

INSERT OR IGNORE INTO media_assets (asset_id, site_id, source_id, filename, media_type, observed_content, mapping_state, rights_state, alt_text, structure_id)
VALUES
('asset-aerial-oblique', 'bursa-muradiye', 'src-drive-photos', 'DJI_20241025141037_0007_D_ODAK-Edit.jpg', 'image', 'Oblique drone view showing a domed complex and surrounding urban hillside; exact building mapping needs editorial confirmation.', 'provisional', 'provided_for_project', 'Aerial view of the Muradiye complex and surrounding hillside; exact structure label pending.', NULL),
('asset-aerial-topdown', 'bursa-muradiye', 'src-drive-photos', 'DJI_20241025141257_0016_D_ODAK-Edit.jpg', 'image', 'Top-down drone view showing several roofs, paths, trees and the compact heritage cluster.', 'provisional', 'provided_for_project', 'Top-down aerial view of the heritage cluster; do not use as a measured plan.', NULL),
('asset-fountain-niche', 'bursa-muradiye', 'src-drive-photos', '20250817_140332.jpg', 'image', 'Photograph of a small brick-and-stone wall fountain niche; precise identity and location are not yet mapped.', 'unmapped', 'provided_for_project', 'A small wall fountain niche; exact location pending verification.', NULL),
('asset-courtyard-portico', 'bursa-muradiye', 'src-drive-photos', 'ERD00738 kopya-2.jpg', 'image', 'View showing a courtyard fountain structure and an arcaded portico; precise building mapping is pending.', 'provisional', 'provided_for_project', 'Courtyard water feature and arcaded portico; building label pending crosswalk.', NULL),
('asset-medrese-interior-unknown', 'bursa-muradiye', 'src-drive-photos', 'ERD00899 kopya.jpg', 'image', 'Blue-tiled interior room visible in the Drive preview; exact building and room are unverified.', 'unmapped', 'provided_for_project', 'Interior room with blue tilework; location not verified.', NULL),
('asset-masonry-detail', 'bursa-muradiye', 'src-drive-photos', 'DJI_20241025143109_0061_D_ODAK-Edit.jpeg', 'image', 'Close-up of geometric brick-and-stone masonry.', 'unmapped', 'provided_for_project', 'Geometric brick-and-stone masonry detail; location not mapped.', NULL),
('asset-tomb-exterior-candidate', 'bursa-muradiye', 'src-drive-photos', 'ERD00835 kopya.jpg', 'image', 'Exterior photograph of a domed tomb-like structure within a tree-lined setting; tomb identity pending crosswalk.', 'provisional', 'provided_for_project', 'Domed tomb-like building; exact tomb identity pending verification.', NULL);

INSERT OR IGNORE INTO chapters (chapter_id, site_id, title, period_text, premise, fiction_notice, status)
VALUES ('chapter-record-and-service', 'bursa-muradiye', 'One Record, One Service', 'around the 1430 vakfiye context',
        'A fictional clerk and a fictional madrasa student investigate how a record, a learning space and an imaret’s service fit together.',
        'Characters, ledger discrepancies, dialogue, and outcomes are fictional; they are not historical events.', 'draft');

INSERT OR IGNORE INTO game_items (item_id, chapter_id, name, description, item_kind, claim_id, fiction_notice)
VALUES
('blank-register', 'chapter-record-and-service', 'Blank record page', 'Record findings, sources, and items awaiting review.', 'document', 'claim-katib-keeper', 'This player-held item is a game prop.'),
('space-sketch', 'chapter-record-and-service', 'Site sketch', 'Help players connect madrasa spaces with the wider complex.', 'map', 'claim-medrese-space', 'This is a game prop, not a historical plan.');

INSERT OR IGNORE INTO characters (character_id, chapter_id, role_name, description, personal_goal, historical_role_claim_id, starting_item_id)
VALUES
('role-katib', 'chapter-record-and-service', 'Kâtib / Clerk', 'A fictional character in a historically documented record-keeping role.', 'Prove reliability while learning that a transparent record protects the service and its users.', 'claim-katib-keeper', 'blank-register'),
('role-talebe', 'chapter-record-and-service', 'Talebe / Student', 'A fictional student in a documented madrasa setting.', 'Make sure the institution is understood through the spaces and provisions that shape daily life.', 'claim-medrese-space', 'space-sketch');

INSERT OR IGNORE INTO scene_nodes (node_id, chapter_id, structure_id, node_order, title, node_kind, map_x, map_y, spatial_accuracy)
VALUES
('node-overview', 'chapter-record-and-service', NULL, 1, 'Complex overview', 'orientation', 50, 87, 'schematic'),
('node-mosque', 'chapter-record-and-service', 'mosque', 2, 'Mosque and site layout', 'observation', 55, 61, 'schematic'),
('node-medrese', 'chapter-record-and-service', 'medrese', 3, 'Madrasa courtyard', 'observation', 31, 59, 'schematic'),
('node-fountain', 'chapter-record-and-service', 'school-fountain', 4, 'Fountain and maintenance', 'evidence_task', 24, 51, 'schematic'),
('node-imaret', 'chapter-record-and-service', 'imaret', 5, 'Imaret and ledger desk', 'choice', 72, 55, 'schematic');

INSERT OR IGNORE INTO node_evidence (node_id, claim_id, asset_id)
VALUES
('node-overview', 'claim-vakfiye-date', 'asset-aerial-topdown'),
('node-mosque', 'claim-mosque-date', 'asset-aerial-oblique'),
('node-medrese', 'claim-medrese-space', 'asset-medrese-interior-unknown'),
('node-medrese', 'claim-stipend-discrepancy', NULL),
('node-fountain', 'claim-fountain-repair', 'asset-fountain-niche'),
('node-fountain', 'claim-madrasa-fountain', NULL),
('node-imaret', 'claim-imaret-meals', NULL),
('node-imaret', 'claim-katib-keeper', NULL),
('node-imaret', 'claim-fictional-stock-mismatch', NULL);

INSERT OR IGNORE INTO task_slots (slot_id, node_id, slot_key, task_kind, ai_enabled)
VALUES
('slot-overview-map', 'node-overview', 'map-relation', 'map_relation', 1),
('slot-medrese-observation', 'node-medrese', 'cell-and-pool', 'observation', 1),
('slot-fountain-duty', 'node-fountain', 'maintenance-role', 'matching', 1),
('slot-imaret-flow', 'node-imaret', 'service-chain', 'sorting', 1),
('slot-report-choice', 'node-imaret', 'reporting-choice', 'narrative_choice', 0);

INSERT OR IGNORE INTO task_candidates (task_id, slot_id, provider, state, version, priority, task_payload_json, approved_by)
VALUES
('task-overview-fallback', 'slot-overview-map', 'fallback', 'published', 1, 10, '{"prompt":"Use the verified site diagram to find the madrasa in relation to the mosque.","answer":"west_same_alignment","fiction_label":""}', 'content-seed'),
('task-medrese-fallback', 'slot-medrese-observation', 'fallback', 'published', 1, 10, '{"prompt":"Which description matches the madrasa in the source?","answer":"16_cells_arcade_octagonal_pool","fiction_label":""}', 'content-seed'),
('task-fountain-fallback', 'slot-fountain-duty', 'fallback', 'published', 1, 10, '{"prompt":"Which staff were responsible for fountain maintenance?","answer":"two_architects","fiction_label":"An editor must verify the photo match before it can be used as a location clue."}', 'content-seed'),
('task-imaret-fallback', 'slot-imaret-flow', 'fallback', 'published', 1, 10, '{"prompt":"Match each duty to a role: record supplies, store goods, or prepare meals.","answer":"scribe_keeper_cooks","fiction_label":"The ledger discrepancy is fictional."}', 'content-seed');

INSERT OR IGNORE INTO task_candidate_claims (task_id, claim_id)
VALUES
('task-overview-fallback', 'claim-medrese-space'),
('task-medrese-fallback', 'claim-medrese-space'),
('task-fountain-fallback', 'claim-fountain-repair'),
('task-imaret-fallback', 'claim-imaret-meals'),
('task-imaret-fallback', 'claim-katib-keeper');

UPDATE task_slots SET fallback_task_id = 'task-overview-fallback' WHERE slot_id = 'slot-overview-map';
UPDATE task_slots SET fallback_task_id = 'task-medrese-fallback' WHERE slot_id = 'slot-medrese-observation';
UPDATE task_slots SET fallback_task_id = 'task-fountain-fallback' WHERE slot_id = 'slot-fountain-duty';
UPDATE task_slots SET fallback_task_id = 'task-imaret-fallback' WHERE slot_id = 'slot-imaret-flow';

INSERT OR IGNORE INTO story_choices (choice_id, chapter_id, node_id, choice_order, prompt, options_json, effects_json)
VALUES
('choice-record-observation', 'chapter-record-and-service', 'node-medrese', 1, 'A student reports an observation that still needs checking. How will you record it?', '[{"id":"log_pending","label":"Log it as an unverified clue and note its source"},{"id":"verify_first","label":"Check the plan and source before adding it to the official record"}]', '{"log_pending":{"evidence_integrity":1,"trust_student":1,"time_budget":-1},"verify_first":{"evidence_integrity":2,"trust_student":-1,"time_budget":-1}}'),
('choice-spend-time', 'chapter-record-and-service', 'node-fountain', 2, 'Time is short. What will you check first?', '[{"id":"inspect_maintenance","label":"Check the fountain duty against the feature photo"},{"id":"reach_imaret","label":"Go to the imaret and check the meal process"}]', '{"inspect_maintenance":{"evidence_integrity":1,"time_budget":-1},"reach_imaret":{"service_continuity":1,"time_budget":0}}'),
('choice-report-mismatch', 'chapter-record-and-service', 'node-imaret', 3, 'How will you handle this fictional stock discrepancy?', '[{"id":"report_pending","label":"Flag it for review and keep service running"},{"id":"pause_verify","label":"Pause this fictional delivery until it is checked"},{"id":"quiet_correct","label":"Quietly change the record and erase the trail"}]', '{"report_pending":{"evidence_integrity":2,"service_continuity":1,"trust_student":1,"character_growth":2},"pause_verify":{"evidence_integrity":2,"service_continuity":-1,"trust_custodian":1,"character_growth":1},"quiet_correct":{"evidence_integrity":-2,"service_continuity":1,"trust_student":-1,"character_growth":-1}}');
