"""Run the retro commands in skills/run-plan/SKILL.md and skills/debug/SKILL.md as written.

Each skill carries a command that resolves the retro file's path and one that appends to it. They are
read out of the Markdown, the example entry is swapped for the test's own, and they run under bash and
`zsh -f` in a scratch directory. HOME is a scratch directory and FOUNDRY_RETRO_FILE points into it, so
nothing here can reach a real `~/.foundry` or `~/.claude`. No environment is inherited except PATH.

Standard library only; no network.
"""
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = {"run-plan": ROOT / "skills" / "run-plan" / "SKILL.md", "debug": ROOT / "skills" / "debug" / "SKILL.md"}
SHELLS = [("bash", ["bash", "-c"]), ("zsh -f", ["zsh", "-f", "-c"])]


MARKER = "FOUNDRY_RETRO_END"


def blocks(skill):
    """Every fenced block, with opening fences of any language, as text ending in a newline."""
    found, current = [], None
    for line in SKILLS[skill].read_text(encoding="utf-8").splitlines(keepends=True):
        if line.startswith("```"):
            if current is None:
                current = []
            else:
                found.append("".join(current))
                current = None
        elif current is not None:
            current.append(line)
    return found


def resolve_command(skill):
    found = [b for b in blocks(skill) if "printf '%s\\n' \"$F\"" in b]
    assert len(found) == 1, found
    return found[0].strip("\n")


def append_command(skill):
    found = [b for b in blocks(skill) if "<<'FOUNDRY_RETRO_END'" in b]
    assert len(found) == 1, found
    return found[0]


def with_entry(skill, entry):
    """The append command with the example between the markers swapped for `entry` (which starts
    with the blank line the skill puts first)."""
    command = append_command(skill)
    head, _, rest = command.partition("<<'FOUNDRY_RETRO_END'\n")
    _, _, tail = rest.rpartition("\n" + MARKER + "\n")
    return head + "<<'FOUNDRY_RETRO_END'\n" + entry + "\n" + MARKER + "\n" + tail


def skeleton(skill):
    """The append command with the entry removed, to compare the two skills' commands."""
    return with_entry(skill, "ENTRY")


ENTRY = "\n## 2026-11-23 | proj | run-plan plan.md\n- implement [missed]: left a caller; should have searched (qa pass, finding 2)"


class RetroCommandCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="retro-cmds-")).resolve()
        self.addCleanup(self.cleanup)
        self.home = self.tmp / "home"
        self.cwd = self.tmp / "cwd"
        self.home.mkdir()
        self.cwd.mkdir()

    def cleanup(self):
        for path in self.tmp.rglob("*"):
            try:
                path.chmod(0o755)
            except OSError:
                continue
        shutil.rmtree(self.tmp, ignore_errors=True)

    def env(self, retro=None):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home)}
        if retro is not None:
            env["FOUNDRY_RETRO_FILE"] = str(retro)
        return env

    def run_cmd(self, argv, command, retro=None, cwd=None):
        return subprocess.run(argv + [command], cwd=cwd or self.cwd, env=self.env(retro), capture_output=True, text=True)

    def shells(self):
        for name, argv in SHELLS:
            if shutil.which(argv[0]):
                yield name, argv


class ResolveCommandTest(RetroCommandCase):
    def test_unset_variable_resolves_to_the_default_under_home(self):
        for skill in SKILLS:
            for name, argv in self.shells():
                with self.subTest(skill=skill, shell=name):
                    done = self.run_cmd(argv, resolve_command(skill))
                    self.assertEqual(done.returncode, 0, done.stderr)
                    self.assertEqual(done.stdout, f"{self.home}/.foundry/retro.md\n")
                    self.assertFalse((self.home / ".foundry").exists(), "resolving must not create anything")

    def test_an_empty_variable_also_resolves_to_the_default(self):
        for skill in SKILLS:
            with self.subTest(skill=skill):
                env = self.env("")
                done = subprocess.run(["bash", "-c", resolve_command(skill)], cwd=self.cwd, env=env, capture_output=True, text=True)
                self.assertEqual(done.stdout, f"{self.home}/.foundry/retro.md\n")

    def test_an_absolute_path_with_spaces_comes_back_whole(self):
        path = self.tmp / "a folder" / "my retro.md"
        for skill in SKILLS:
            for name, argv in self.shells():
                with self.subTest(skill=skill, shell=name):
                    done = self.run_cmd(argv, resolve_command(skill), retro=path)
                    self.assertEqual(done.stdout, f"{path}\n")

    def test_a_relative_path_is_made_absolute_against_the_working_directory(self):
        for skill in SKILLS:
            for name, argv in self.shells():
                with self.subTest(skill=skill, shell=name):
                    done = self.run_cmd(argv, resolve_command(skill), retro="rel dir/r.md")
                    self.assertEqual(done.stdout, f"{self.cwd}/rel dir/r.md\n")


class AppendCommandTest(RetroCommandCase):
    def append(self, skill, argv, retro, entry=ENTRY, cwd=None):
        return self.run_cmd(argv, with_entry(skill, entry), retro=retro, cwd=cwd)

    def test_the_first_write_creates_the_folder_and_the_file(self):
        for skill in SKILLS:
            for name, argv in self.shells():
                with self.subTest(skill=skill, shell=name):
                    path = self.tmp / f"new {skill} {name[:3]}" / "deeper folder" / "retro.md"
                    done = self.append(skill, argv, path)
                    self.assertIn("retro exit=0", done.stdout, done)
                    self.assertEqual(path.read_text(encoding="utf-8"), ENTRY + "\n")

    def test_the_default_path_is_created_under_home(self):
        for skill in SKILLS:
            with self.subTest(skill=skill):
                shutil.rmtree(self.home / ".foundry", ignore_errors=True)
                done = subprocess.run(["bash", "-c", with_entry(skill, ENTRY)], cwd=self.cwd, env=self.env(),
                                      capture_output=True, text=True)
                self.assertIn("retro exit=0", done.stdout)
                self.assertEqual((self.home / ".foundry" / "retro.md").read_text(encoding="utf-8"), ENTRY + "\n")

    def test_a_second_append_keeps_the_first_block_byte_for_byte(self):
        second = "\n## 2026-11-24 | other | debug slug\n- debug [user]: skipped the pin; the user asked for it (step 5)"
        for skill in SKILLS:
            for name, argv in self.shells():
                with self.subTest(skill=skill, shell=name):
                    path = self.tmp / f"two {skill} {name[:3]}.md"
                    self.append(skill, argv, path)
                    first = path.read_bytes()
                    done = self.append(skill, argv, path, entry=second)
                    self.assertIn("retro exit=0", done.stdout)
                    self.assertEqual(path.read_bytes(), first + (second + "\n").encode())

    def test_a_relative_path_writes_under_the_working_directory(self):
        for skill in SKILLS:
            for name, argv in self.shells():
                with self.subTest(skill=skill, shell=name):
                    done = self.append(skill, argv, f"rel {skill} {name[:3]}/r.md")
                    self.assertIn("retro exit=0", done.stdout, done)
                    self.assertEqual((self.cwd / f"rel {skill} {name[:3]}" / "r.md").read_text(encoding="utf-8"), ENTRY + "\n")

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can write anywhere")
    def test_an_unwritable_folder_says_so_through_the_retro_exit_line(self):
        locked = self.tmp / "locked"
        locked.mkdir()
        locked.chmod(0o555)
        for skill in SKILLS:
            for name, argv in self.shells():
                with self.subTest(skill=skill, shell=name):
                    path = locked / "sub" / "retro.md"
                    done = self.append(skill, argv, path)
                    self.assertRegex(done.stdout, r"retro exit=[1-9]", done)
                    self.assertFalse(path.exists())

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can write anywhere")
    def test_a_read_only_file_says_so_and_stays_unchanged(self):
        path = self.tmp / "ro.md"
        path.write_text("old\n", encoding="utf-8")
        path.chmod(0o444)
        for skill in SKILLS:
            for name, argv in self.shells():
                with self.subTest(skill=skill, shell=name):
                    done = self.append(skill, argv, path)
                    self.assertRegex(done.stdout, r"retro exit=[1-9]", done)
                    self.assertEqual(path.read_text(encoding="utf-8"), "old\n")

    def test_special_characters_land_unchanged(self):
        # The heredoc marker is quoted: no expansion of backticks, $, quotes or backslashes.
        line = r"""- implement [missed]: ran `rm -rf x`, $HOME, $(date), "dq", 'sq', back\slash, \n, ${FOO:-bar}, !! (qa pass, finding 3)"""
        entry = "\n## 2026-11-23 | proj | run-plan plan.md\n" + line
        for skill in SKILLS:
            for name, argv in self.shells():
                with self.subTest(skill=skill, shell=name):
                    path = self.tmp / f"special {skill} {name[:3]}.md"
                    done = self.append(skill, argv, path, entry=entry)
                    self.assertIn("retro exit=0", done.stdout, done)
                    self.assertEqual(path.read_text(encoding="utf-8"), entry + "\n")

    def test_a_line_that_is_exactly_RETRO_and_commands_after_it_land_as_text(self):
        # The old marker was RETRO: a line that was exactly that cut the entry and ran the rest as shell.
        # The marker is now FOUNDRY_RETRO_END, so these are just text, and nothing runs.
        entry = "\n## 2026-11-23 | proj | run-plan plan.md\n- implement [missed]: a\nRETRO\ntouch ran-as-shell\n$(touch ran-as-subst)\n- implement [missed]: b"
        for skill in SKILLS:
            for name, argv in self.shells():
                with self.subTest(skill=skill, shell=name):
                    path = self.tmp / f"retro-line {skill} {name[:3]}.md"
                    done = self.append(skill, argv, path, entry=entry)
                    self.assertIn("retro exit=0", done.stdout, done)
                    self.assertEqual(path.read_text(encoding="utf-8"), entry + "\n")
                    self.assertFalse((self.cwd / "ran-as-shell").exists())
                    self.assertFalse((self.cwd / "ran-as-subst").exists())

    def test_a_line_that_is_exactly_the_new_marker_still_cuts_the_entry_which_the_text_forbids(self):
        # Pinned as it stands, not fixed: the skill says no line may be the marker, and a line that is
        # exactly FOUNDRY_RETRO_END ends the heredoc, so what follows runs as shell.
        entry = f"\n## 2026-11-23 | proj | run-plan plan.md\n- implement [missed]: a\n{MARKER}\ntouch ran-as-shell\n- implement [missed]: b"
        for skill in SKILLS:
            for name, argv in self.shells():
                with self.subTest(skill=skill, shell=name):
                    path = self.tmp / f"marker-line {skill} {name[:3]}.md"
                    marker = self.cwd / "ran-as-shell"
                    marker.unlink(missing_ok=True)
                    self.append(skill, argv, path, entry=entry)
                    self.assertEqual(path.read_text(encoding="utf-8"),
                                     "\n## 2026-11-23 | proj | run-plan plan.md\n- implement [missed]: a\n")
                    self.assertTrue(marker.exists())

    def test_a_line_that_only_contains_or_pads_the_marker_stays_in_the_entry(self):
        # Only a line that is exactly the marker ends it: containing it, a prefix, a suffix, leading or
        # trailing spaces, a tab, and the lowercase word are all text.
        lines = [f"- implement [missed]: mentions {MARKER} in a sentence", f"{MARKER}x", f"x{MARKER}",
                 f" {MARKER}", f"{MARKER} ", f"\t{MARKER}", f"{MARKER}\t", MARKER.lower(), f"## {MARKER}"]
        entry = "\n## 2026-11-23 | proj | run-plan plan.md\n" + "\ntouch not-run\n".join(lines)
        for skill in SKILLS:
            for name, argv in self.shells():
                with self.subTest(skill=skill, shell=name):
                    path = self.tmp / f"padded {skill} {name[:3]}.md"
                    done = self.append(skill, argv, path, entry=entry)
                    self.assertIn("retro exit=0", done.stdout, done)
                    self.assertEqual(path.read_text(encoding="utf-8"), entry + "\n")
                    self.assertFalse((self.cwd / "not-run").exists())

    def test_two_appends_racing_both_land_whole(self):
        block_a = "\n## 2026-11-23 | a | run-plan a.md\n" + "\n".join(f"- implement [missed]: A{i} " + "a" * 60 for i in range(12))
        block_b = "\n## 2026-11-23 | b | debug b\n" + "\n".join(f"- debug [user]: B{i} " + "b" * 60 for i in range(12))
        for skill in SKILLS:
            for name, argv in self.shells():
                with self.subTest(skill=skill, shell=name):
                    for trial in range(15):
                        path = self.tmp / f"race {skill} {name[:3]} {trial}.md"
                        results = []
                        go = threading.Event()

                        def worker(entry):
                            go.wait()
                            results.append(self.append(skill, argv, path, entry=entry))

                        threads = [threading.Thread(target=worker, args=(e,)) for e in (block_a, block_b)]
                        for t in threads:
                            t.start()
                        go.set()
                        for t in threads:
                            t.join()
                        self.assertTrue(all("retro exit=0" in r.stdout for r in results), results)
                        content = path.read_text(encoding="utf-8")
                        self.assertIn(content, (block_a + "\n" + block_b + "\n", block_b + "\n" + block_a + "\n"))


PROJECT_CMD = 'basename "$(git rev-parse --show-toplevel)"'


class ProjectNameTest(RetroCommandCase):
    """The heading's project name: the repo's top folder, whichever folder the session is in."""

    def git(self, *args, cwd):
        env = dict(self.env(), GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
        return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True)

    def test_both_skills_name_the_same_project_command(self):
        for skill in SKILLS:
            text = " ".join(SKILLS[skill].read_text(encoding="utf-8").split())
            with self.subTest(skill=skill):
                self.assertIn("`" + PROJECT_CMD + "`", text)

    def test_the_top_folder_and_a_subfolder_give_the_same_name(self):
        repo = self.tmp / "my project"
        (repo / "src" / "deep").mkdir(parents=True)
        self.git("init", "-q", cwd=repo)
        for name, argv in self.shells():
            for where in (repo, repo / "src", repo / "src" / "deep"):
                with self.subTest(shell=name, cwd=str(where.relative_to(self.tmp))):
                    done = self.run_cmd(argv, PROJECT_CMD, cwd=where)
                    self.assertEqual(done.stdout, "my project\n", done)

    def test_a_worktree_gives_the_worktrees_folder_name_not_the_repos(self):
        repo = self.tmp / "main-repo"
        repo.mkdir()
        self.git("init", "-q", "-b", "main", cwd=repo)
        (repo / "a").write_text("x", encoding="utf-8")
        self.git("add", "a", cwd=repo)
        self.git("-c", "user.name=t", "-c", "user.email=t@e.x", "commit", "-q", "-m", "c", cwd=repo)
        wt = self.tmp / "feat-worktree"
        self.git("worktree", "add", "-q", str(wt), "-b", "feat", cwd=repo)
        done = self.run_cmd(["bash", "-c"], PROJECT_CMD, cwd=wt)
        self.assertEqual(done.stdout, "feat-worktree\n")

    def test_outside_a_repo_the_command_prints_nothing_useful_so_the_fallback_is_needed(self):
        # What the command does outside a git repo: git says fatal, basename gets an empty argument and
        # prints an empty line or fails. The text's fallback ("the working folder's name") covers it, but
        # gives no command: a session has to know to use the cwd's name.
        bare = self.tmp / "not a repo"
        bare.mkdir()
        for name, argv in self.shells():
            with self.subTest(shell=name):
                done = self.run_cmd(argv, PROJECT_CMD, cwd=bare)
                self.assertIn("not a git repository", done.stderr)
                self.assertNotIn("not a repo", done.stdout)
                self.assertIn(done.stdout, ("\n", ""))
                fallback = self.run_cmd(argv, 'basename "$PWD"', cwd=bare)
                self.assertEqual(fallback.stdout, "not a repo\n")

    def test_each_skill_gives_a_fallback_for_outside_a_repo(self):
        for skill in SKILLS:
            text = " ".join(SKILLS[skill].read_text(encoding="utf-8").split())
            with self.subTest(skill=skill):
                self.assertIn("outside a git repo, the working folder's name", text)


class SameCommandTest(unittest.TestCase):
    def test_both_skills_carry_the_same_resolve_command(self):
        self.assertEqual(resolve_command("run-plan"), resolve_command("debug"))

    def test_both_skills_carry_the_same_append_command_apart_from_the_entry(self):
        self.assertEqual(skeleton("run-plan"), skeleton("debug"))

    def test_the_append_command_is_resolved_on_its_own_and_reports_its_exit(self):
        for skill in SKILLS:
            command = append_command(skill)
            with self.subTest(skill=skill):
                self.assertIn('F="${FOUNDRY_RETRO_FILE:-$HOME/.foundry/retro.md}"', command)
                self.assertIn('mkdir -p "$(dirname "$F")" && cat >> "$F" <<\'FOUNDRY_RETRO_END\'', command)
                self.assertTrue(command.rstrip().endswith('echo "retro exit=$?"'))
                self.assertNotIn(">>>", command)
                self.assertNotRegex(command, r"(?m)^[^<\n]*[^>]> \"?\$F")  # a single > would rewrite the file


if __name__ == "__main__":
    unittest.main()
