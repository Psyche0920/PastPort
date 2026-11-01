// Generated from src/pastport/data/gameplay-capabilities.json; do not hand edit.
export const gameplayCatalog = {
  "schema_version": "gameplay-capabilities/1.0.0",
  "host_profile": "pastport.demo.activities/1",
  "profiles": [
    {
      "capability_id": "source-reading:1",
      "plugin_id": "pastport.activity.dialogue",
      "kind": "dialogue",
      "version": "1.0.0",
      "max_items": 128,
      "board_width": null,
      "board_height": null,
      "minimum_pieces": null,
      "maximum_pieces": null,
      "maximum_piece_dimension": null,
      "rotation_allowed": false,
      "source_choice_required": false,
      "solver_node_limit": null,
      "failure_policy": "retry_without_story_progress",
      "exit_policy": "preserve_progress"
    },
    {
      "capability_id": "source-gated-coverage:1",
      "plugin_id": "pastport.activity.tiling",
      "kind": "tiling",
      "version": "1.0.0",
      "max_items": 4,
      "board_width": 4,
      "board_height": 4,
      "minimum_pieces": 1,
      "maximum_pieces": 16,
      "maximum_piece_dimension": 4,
      "rotation_allowed": true,
      "source_choice_required": true,
      "solver_node_limit": 50000,
      "failure_policy": "retry_without_story_progress",
      "exit_policy": "preserve_progress"
    }
  ]
};
export const gameplayCatalogSha256 = 'a51821064c1ae3ca523acd3acf746bcc254b102323de3a8fb81a5d5c194daf7c';
