# Copyright (c) 2026 Adrian Stanea
# SPDX-License-Identifier: BSD-3-Clause
"""The docs check's shell directive requirement for doc trees and RST READMEs."""

from __future__ import annotations

import json
import unittest

from ai_hooks.checks import docs

try:
    from .helpers import RepoTestCase
except ImportError:  # discovered with `-s tests` and no `-t .`
    from helpers import RepoTestCase

SHELL_RST = "Title\n=====\n\n.. code-block:: bash\n\n   make html\n"


class InDocTreeTest(unittest.TestCase):
    def test_rst_under_doc_directories_is_in_scope(self):
        for rel in (
            "doc/a.rst",
            "docs/guide/a.rst",
            "packages/ad7xxxx/doc/a.rst",
            "targets/maxim/doc/a.rst",
            ".devcontainer/doc/a.rst",
            "doc/README.rst",
            "packages/ad7xxxx/doc/README.rst",
            "README.rst",
            "examples/demo/README.rst",
            "packages/p/README.rst",
            "targets/p/README.rst",
            ".devcontainer/README.rst",
        ):
            with self.subTest(rel=rel):
                self.assertTrue(docs.in_doc_tree(rel))

    def test_non_rst_and_non_doc_paths_are_exempt(self):
        for rel in (
            "examples/demo/README.md",
            "doc/a.md",
            "doc/a.txt",
            "lib/a.rst",
            "a.rst",
            "documentation/a.rst",
            "lib/doc.rst",
        ):
            with self.subTest(rel=rel):
                self.assertFalse(docs.in_doc_tree(rel))


class ShellDirectiveFindingsTest(unittest.TestCase):
    def test_every_terminal_language_is_flagged_for_every_code_directive(self):
        for directive in ("code-block", "code", "sourcecode"):
            for lang in sorted(docs.TERMINAL_LANGUAGES) + ["Bash", "CONSOLE"]:
                with self.subTest(directive=directive, lang=lang):
                    text = f"Intro\n\n   .. {directive}:: {lang}\n\n      ls\n"
                    findings = docs.shell_directive_findings("doc/a.rst", text)
                    self.assertEqual(len(findings), 1)
                    self.assertTrue(findings[0].startswith(f"doc/a.rst:3: `.. {directive}:: {lang}`"))
                    self.assertIn("use `.. shell::`", findings[0])

    def test_shell_directive_and_other_languages_are_accepted(self):
        text = (
            ".. shell::\n\n   $ make html\n\n"
            ".. code-block:: text\n\n   plain\n\n"
            ".. code-block:: cpp\n\n   int x;\n\n"
            ".. code:: python\n\n   x = 1\n\n"
            ".. code-block::\n\n   default\n\n"
            ".. code-block:: bashful\n\n   x\n"
        )
        self.assertEqual(docs.shell_directive_findings("doc/a.rst", text), [])

    def test_root_readme_accepts_terminal_code_blocks(self):
        self.assertEqual(docs.shell_directive_findings("README.rst", SHELL_RST), [])

    def test_nested_readme_still_requires_shell_directive(self):
        self.assertEqual(
            len(docs.shell_directive_findings("examples/demo/README.rst", SHELL_RST)),
            1,
        )


class ShellDirectiveCheckTest(RepoTestCase):
    def _stop_after_editing(self, rel, text):
        payload = {"tool_name": "Edit", "tool_input": {"file_path": self.touch_file(rel, text)}}
        self.run_hook("PostToolUse", payload)
        return self.run_hook("Stop", {})[1]

    def test_terminal_code_block_in_a_nested_doc_tree_blocks(self):
        out = self._stop_after_editing("packages/p/doc/guide.rst", SHELL_RST)
        reason = json.loads(out)["reason"]
        self.assertIn("packages/p/doc/guide.rst:4: `.. code-block:: bash`", reason)
        self.assertIn("use `.. shell::` for terminal sessions in doc trees", reason)

    def test_terminal_code_blocks_in_readmes_block(self):
        for rel in ("doc/README.rst", "examples/demo/README.rst", "packages/p/README.rst"):
            with self.subTest(rel=rel):
                reason = json.loads(self._stop_after_editing(rel, SHELL_RST))["reason"]
                self.assertIn(f"{rel}:4: `.. code-block:: bash`", reason)

    def test_root_readme_terminal_code_block_passes(self):
        self.assertEqual(self._stop_after_editing("README.rst", SHELL_RST), "")

    def test_non_doc_rst_passes(self):
        self.assertEqual(self._stop_after_editing("lib/notes.rst", SHELL_RST), "")

    def test_pre_commit_rejects_staged_terminal_code_block(self):
        self.touch_file("packages/p/README.rst", SHELL_RST)
        self.git("add", "packages/p/README.rst")
        rc, _, err = self.run_cli("git", "pre-commit")
        self.assertEqual(rc, 1)
        self.assertIn("packages/p/README.rst:4: `.. code-block:: bash`", err)

    def test_pre_commit_allows_staged_root_readme_code_block(self):
        self.touch_file("README.rst", SHELL_RST)
        self.git("add", "README.rst")
        self.assertEqual(self.run_cli("git", "pre-commit")[0], 0)

    def test_shell_directive_passes_pre_commit(self):
        self.touch_file("doc/a.rst", "Title\n=====\n\n.. shell::\n\n   $ make html\n")
        self.git("add", "doc/a.rst")
        self.assertEqual(self.run_cli("git", "pre-commit")[0], 0)


if __name__ == "__main__":
    unittest.main()
