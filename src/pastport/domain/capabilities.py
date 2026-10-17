"""Explicit capabilities for the existing contract profile, independent of sample content."""

from pastport.domain.game import RuntimeCapabilities


def initial_capabilities() -> RuntimeCapabilities:
    return RuntimeCapabilities(
        profile="t1a-single-task",
        contract_version="0.1.0",
        task_kinds=("inspect", "caseboard"),
        condition_kinds=(
            "all",
            "any",
            "not",
            "observed_all",
            "choice_equals",
            "variable_equals",
            "has_evidence",
            "elapsed_gt",
        ),
        effect_kinds=(
            "grant_item",
            "set_variable",
            "set_relationship",
            "add_story_time",
            "unlock_scene",
            "resolve_ending",
        ),
        event_kinds=("spot_observed", "board_submitted", "option_chosen", "task_completed"),
        locales=("en", "zh"),
    )
