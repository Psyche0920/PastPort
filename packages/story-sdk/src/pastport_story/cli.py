"""Standalone installed command reusing shared CLI and canonical Skills."""

from pastport.adapters.runtime_resources import skill_root
from pastport.story_cli import main as core_main


def main() -> None:
    core_main(default_skill_directory=skill_root())
