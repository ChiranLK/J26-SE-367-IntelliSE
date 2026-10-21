"""Stdlib regression checks: python3 -m unittest discover -s scripts -p test_startup_checks.py"""
from pathlib import Path
import tempfile
import unittest

from startup_checks import absolute_path


class StartupPaths(unittest.TestCase):
    def test_interpreter_symlink_keeps_virtual_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            executable = base / "base-python"
            executable.touch()
            interpreter = base / ".venv/bin/python"
            interpreter.parent.mkdir(parents=True)
            interpreter.symlink_to(executable)
            self.assertEqual(absolute_path(base, Path(".venv/bin/python")), interpreter)
            self.assertNotEqual(absolute_path(base, interpreter), interpreter.resolve())

    def test_relative_model_paths_are_backend_relative(self):
        self.assertEqual(absolute_path(Path("/example/backend"), Path("research/models")), Path("/example/backend/research/models"))
