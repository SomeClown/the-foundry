"""Run the area commands that agents/investigate.md tells a model to run, against a small real repo.

The fence under "### Areas" holds eight comment lines, each followed by one command. The commands are
read out of the Markdown as written, their placeholders are filled in, and they run under `bash -c`
and `zsh -f -c` (never `sh`: the last one uses process substitution). Every result is compared with a
set computed in Python from the file names the repo was built from. The `find` listing and the
`sed -n` line pick, which the file quotes outside the fence, run too.

A command that gives the wrong set is a bug in the agent file's text; these tests don't bend around it.

Standard library only; git, awk, sort, uniq, sed, diff and find are the tools used. No network.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / "agents" / "investigate.md"
SHELLS = [("bash", ["bash", "-c"]), ("zsh -f", ["zsh", "-f", "-c"])]

C_TOP = "# count by top-level folder"
C_DOWN = "# count one level down inside <dir>/"
C_DIR = "# <dir>/"
C_DIRECT = "# <dir>/ (direct)"
C_ROOT = "# (root)"
C_EXCEPT = "# except <folder>/, after any piece above"
C_RANGE = "# from <first> to <last>, after any piece above"
C_ONCE = "# every file left after the whole-folder skips is in exactly one area"
COMMENTS = [C_TOP, C_DOWN, C_DIR, C_DIRECT, C_ROOT, C_EXCEPT, C_RANGE, C_ONCE]
ONCE_MESSAGE = "each file in exactly one area"


def areas_section():
    text = AGENT.read_text(encoding="utf-8")
    heading = "\n### Areas\n"
    start = text.index(heading) + len(heading)
    # only ## and ### end the section: the fence's own comment lines start with a single "# "
    match = re.search(r"^#{2,3} ", text[start:], re.M)
    end = start + match.start() if match else len(text)
    return text[start:end]


def command_fence():
    fences = [f for f in re.findall(r"^```\n(.*?)^```$", areas_section(), re.S | re.M) if C_TOP in f]
    assert len(fences) == 1, "expected exactly one command fence under ### Areas, found %d" % len(fences)
    return fences[0]


def fence_commands():
    """Map each comment line to the one command line after it."""
    lines = command_fence().rstrip("\n").split("\n")
    found = {}
    for i, line in enumerate(lines):
        if line in COMMENTS:
            assert line not in found, "comment appears twice: " + line
            assert i + 1 < len(lines) and not lines[i + 1].startswith("# "), "no command after: " + line
            found[line] = lines[i + 1]
    return found


def template(comment):
    found = fence_commands()
    if comment not in found:
        raise AssertionError("the fence has no comment line: " + comment)
    return found[comment]


def list_command():
    """What the file says <list> is: its own sentence, not a copy kept here."""
    matches = re.findall(r"`<list>` below is `(git [^`]*ls-files)`", areas_section())
    assert len(matches) == 1, matches
    return matches[0]


LIST = list_command()


def find_command():
    text = AGENT.read_text(encoding="utf-8")
    matches = re.findall(r"`(find \. \\\( .*? \| LC_ALL=C sort)`", text)
    assert len(matches) == 1, matches
    return matches[0]


def sed_template():
    matches = re.findall(r"`(<piece> \| sed -n '<n>p')`", areas_section())
    assert len(matches) == 1, matches
    return matches[0]


def fill(command, lister=LIST, **kw):
    """Fill the placeholders of one fence command. `piece` is a command string that already holds its lister."""
    for key in ("piece", "dir", "folder", "first", "last", "skipped", "n"):
        if key in kw:
            command = command.replace("<%s>" % key, str(kw[key]))
    if "areas" in kw:
        command = command.replace("<area 1>; <area 2>; <and so on>", "; ".join(kw["areas"]))
    return command.replace("<list>", lister)


def byte_key(s):
    return s.encode("utf-8")


TRACKED = sorted(
    [
        "README.md", "9", "10", "100", "Zed.txt", "_lead.txt",
        "api/a.py", "api/sub/b.py",
        "api2/c.py",
        "café/menu.txt",
        "docs/B.md", "docs/_x.md", "docs/a.md", "docs/c.md",
        "my docs/read me.md", "my docs/x.md", "my docs/old stuff/y.md",
        "src/main.py", "src/util.py", "src/naïve.py",
        "src/core/a.py", "src/core/b.py", "src/io/c.py",
        "web/index.html", "web/app.js",
        "web/vendor/a.js", "web/vendor/sub/b.js",
        "web/legacy/old.js",
        "we[ir]d*/a.txt", "we[ir]d*/b.txt", "weid/q.txt", "wexd/c.txt",
    ] + ["flat/f%02d.txt" % i for i in range(1, 41)],
    key=byte_key,
)


class AreaRepo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="area-cmds-")).resolve()
        cls.repo = cls.tmp / "repo"
        cls.repo.mkdir()
        cls.env = {
            "PATH": os.environ["PATH"],
            "HOME": str(cls.tmp),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
            # a locale that is not C: every command must set its own LC_ALL=C and not lean on this one
            "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8",
        }
        cls.git(cls.repo, "init", "-q", "-b", "main")
        for name in TRACKED:
            path = cls.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n", encoding="utf-8")
        cls.git(cls.repo, "add", "-A")
        cls.git(cls.repo, "commit", "-q", "-m", "all")

        # the same files outside git, plus the folders the find command prunes
        cls.plain = cls.tmp / "plain"
        shutil.copytree(cls.repo, cls.plain, ignore=shutil.ignore_patterns(".git"))
        for pruned in (".git/HEAD", "node_modules/n.js", "venv/v.py", ".venv/w.py",
                       "src/node_modules/deep.js", "web/venv/z.py"):
            path = cls.plain / pruned
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def git(cls, cwd, *args):
        done = subprocess.run(["git", *args], cwd=cwd, env=cls.env, capture_output=True)
        assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
        return done.stdout.decode("utf-8")

    def shells(self):
        for name, argv in SHELLS:
            if shutil.which(argv[0]):
                yield name, argv

    def run_in(self, argv, command, cwd=None):
        done = subprocess.run(argv + [command], cwd=cwd or self.repo, env=self.env, capture_output=True)
        return done.returncode, done.stdout.decode("utf-8"), done.stderr.decode("utf-8")

    def each_shell(self, command, cwd=None):
        """Yield (shell name, stdout lines) for a command that must exit 0 with an empty stderr."""
        for name, argv in self.shells():
            code, out, err = self.run_in(argv, command, cwd)
            self.assertEqual(code, 0, "%s: exit %s\n%s\n%s" % (name, code, command, err))
            self.assertEqual(err, "", "%s: stderr\n%s" % (name, command))
            yield name, out.splitlines()

    def check_paths(self, command, expected, cwd=None):
        for name, lines in self.each_shell(command, cwd):
            with self.subTest(shell=name):
                self.assertEqual(sorted(lines, key=byte_key), sorted(expected, key=byte_key), command)

    def parse_counts(self, lines):
        counts = {}
        for line in lines:
            m = re.match(r"^\s*(\d+) (.*)$", line)
            self.assertIsNotNone(m, line)
            counts[m.group(2)] = int(m.group(1))
        return counts

    # expected values, from the names the repo was built from
    @staticmethod
    def under(prefix):
        return [p for p in TRACKED if p.startswith(prefix)]

    @staticmethod
    def direct(prefix):
        return [p for p in TRACKED if p.startswith(prefix) and "/" not in p[len(prefix):]]

    @staticmethod
    def root_files():
        return [p for p in TRACKED if "/" not in p]

    @staticmethod
    def between(paths, first, last):
        a, b = byte_key(first), byte_key(last)
        return [p for p in paths if a <= byte_key(p) <= b]

    # the pieces as commands
    def dir_piece(self, d, lister=LIST):
        return fill(template(C_DIR), lister, dir=d.rstrip("/"))

    def direct_piece(self, d, lister=LIST):
        return fill(template(C_DIRECT), lister, dir=d.rstrip("/"))

    def root_piece(self, lister=LIST):
        return fill(template(C_ROOT), lister)

    def except_of(self, piece, folder):
        return fill(template(C_EXCEPT), piece=piece, folder=folder.rstrip("/"))

    def range_of(self, piece, first, last):
        return fill(template(C_RANGE), piece=piece, first=first, last=last)


class FenceShapeTest(AreaRepo):
    def test_the_fence_has_all_eight_comments_each_with_one_command(self):
        found = fence_commands()
        for comment in COMMENTS:
            self.assertIn(comment, found, "the fence has no comment line: " + comment)
        self.assertEqual(len(command_fence().rstrip("\n").split("\n")), 16)

    def test_every_command_is_one_line_and_never_asks_for_sh(self):
        for comment, command in fence_commands().items():
            self.assertNotIn("\n", command)
            self.assertFalse(command.startswith("#"), comment)

    def test_the_file_names_git_with_quotepath_off_as_the_lister(self):
        self.assertEqual(LIST, "git -c core.quotepath=off ls-files")

    def test_the_fixture_repo_lists_what_python_built(self):
        listed = self.git(self.repo, "-c", "core.quotepath=off", "ls-files").splitlines()
        self.assertEqual(listed, TRACKED)

    def test_without_quotepath_off_a_non_ascii_name_comes_back_quoted(self):
        plain = self.git(self.repo, "ls-files").splitlines()
        self.assertIn('"caf\\303\\251/menu.txt"', plain)
        self.assertNotIn("café/menu.txt", plain)


class CountTest(AreaRepo):
    def test_count_by_top_level_folder(self):
        expected = Counter(p.split("/")[0] + "/" if "/" in p else "(root)" for p in TRACKED)
        for name, lines in self.each_shell(fill(template(C_TOP))):
            with self.subTest(shell=name):
                self.assertEqual(self.parse_counts(lines), dict(expected))

    def test_count_one_level_down_inside_a_folder(self):
        for d in ("src/", "api/", "my docs/", "we[ir]d*/", "flat/", "web/"):
            expected = Counter()
            for p in self.under(d):
                rest = p[len(d):]
                i = rest.find("/")
                expected[d + rest[:i + 1] if i >= 0 else d + " (direct)"] += 1
            for name, lines in self.each_shell(fill(template(C_DOWN), dir=d.rstrip("/"))):
                with self.subTest(shell=name, dir=d):
                    self.assertEqual(self.parse_counts(lines), dict(expected))

    def test_counts_one_level_down_do_not_bleed_into_a_folder_with_the_same_start(self):
        for name, lines in self.each_shell(fill(template(C_DOWN), dir="api")):
            with self.subTest(shell=name):
                counts = self.parse_counts(lines)
                self.assertEqual(counts, {"api/ (direct)": 1, "api/sub/": 1})

    def test_a_folder_with_no_files_counts_nothing(self):
        for name, lines in self.each_shell(fill(template(C_DOWN), dir="nothing")):
            with self.subTest(shell=name):
                self.assertEqual(lines, [])


class PieceTest(AreaRepo):
    def test_a_folder_piece_is_every_file_under_it(self):
        for d in ("src/", "api/", "my docs/", "web/", "flat/", "café/"):
            self.check_paths(self.dir_piece(d), self.under(d))

    def test_a_folder_piece_does_not_take_a_folder_that_starts_with_its_name(self):
        self.check_paths(self.dir_piece("api/"), ["api/a.py", "api/sub/b.py"])
        self.check_paths(self.dir_piece("api2/"), ["api2/c.py"])
        self.check_paths(self.direct_piece("api/"), ["api/a.py"])

    def test_a_folder_name_with_a_space_works_as_a_piece_and_as_direct(self):
        self.check_paths(self.dir_piece("my docs/"),
                         ["my docs/read me.md", "my docs/x.md", "my docs/old stuff/y.md"])
        self.check_paths(self.direct_piece("my docs/"), ["my docs/read me.md", "my docs/x.md"])

    def test_brackets_and_a_star_in_a_folder_name_are_matched_literally(self):
        self.check_paths(self.dir_piece("we[ir]d*/"), ["we[ir]d*/a.txt", "we[ir]d*/b.txt"])
        self.check_paths(self.direct_piece("we[ir]d*/"), ["we[ir]d*/a.txt", "we[ir]d*/b.txt"])

    def test_a_non_ascii_folder_and_file_name_come_back_unquoted(self):
        self.check_paths(self.dir_piece("café/"), ["café/menu.txt"])
        self.check_paths(self.direct_piece("src/"), ["src/main.py", "src/util.py", "src/naïve.py"])

    def test_direct_leaves_out_the_subfolders(self):
        for d in ("src/", "web/", "docs/", "flat/"):
            self.check_paths(self.direct_piece(d), self.direct(d))

    def test_a_flat_folder_of_forty_files(self):
        self.assertEqual(len(self.under("flat/")), 40)
        self.check_paths(self.dir_piece("flat/"), self.under("flat/"))
        self.check_paths(self.direct_piece("flat/"), self.under("flat/"))

    def test_root_is_the_files_at_the_root_only(self):
        self.check_paths(self.root_piece(), self.root_files())


class ExceptTest(AreaRepo):
    def test_except_leaves_out_one_folder(self):
        self.check_paths(self.except_of(self.dir_piece("web/"), "web/vendor/"),
                         [p for p in self.under("web/") if not p.startswith("web/vendor/")])

    def test_except_chained_once_per_skipped_folder(self):
        piece = self.except_of(self.except_of(self.dir_piece("web/"), "web/vendor/"), "web/legacy/")
        self.check_paths(piece, ["web/index.html", "web/app.js"])

    def test_an_except_does_not_take_a_folder_that_starts_with_the_same_name(self):
        self.check_paths(self.except_of(LIST, "api/"), [p for p in TRACKED if not p.startswith("api/")])
        self.assertIn("api2/c.py", self.run_lines(self.except_of(LIST, "api/")))
        self.check_paths(self.except_of(LIST, "we"), TRACKED)  # "we/" is a folder that does not exist

    def run_lines(self, command):
        return [line for _, lines in self.each_shell(command) for line in lines]

    def test_except_of_a_folder_with_a_space(self):
        self.check_paths(self.except_of(self.dir_piece("my docs/"), "my docs/old stuff/"),
                         ["my docs/read me.md", "my docs/x.md"])

    def test_except_of_a_folder_with_brackets_and_a_star_is_literal(self):
        self.check_paths(self.except_of(self.dir_piece("we[ir]d*/"), "we[ir]d*/"), [])
        self.check_paths(self.except_of(LIST, "we[ir]d*/"),
                         [p for p in TRACKED if not p.startswith("we[ir]d*/")])

    def test_except_after_direct_and_after_root(self):
        self.check_paths(self.except_of(self.direct_piece("src/"), "src/core/"), self.direct("src/"))
        self.check_paths(self.except_of(self.root_piece(), "docs/"), self.root_files())


class RangeTest(AreaRepo):
    def test_root_files_named_with_digits_use_byte_order_not_number_order(self):
        # byte order: "10" < "100" < "9". A numeric comparison would match nothing for 10..9.
        piece = self.root_piece()
        self.check_paths(self.range_of(piece, "10", "9"), ["10", "100", "9"])
        self.check_paths(self.range_of(piece, "100", "9"), ["100", "9"])
        self.check_paths(self.range_of(piece, "9", "9"), ["9"])
        self.check_paths(self.range_of(piece, "10", "10"), ["10"])

    def test_a_range_ends_inclusive_and_follows_bytes_not_a_locale(self):
        # byte order in docs/: B.md < _x.md < a.md < c.md (a locale would put _x.md or B.md elsewhere)
        piece = self.dir_piece("docs/")
        self.check_paths(self.range_of(piece, "docs/B.md", "docs/_x.md"), ["docs/B.md", "docs/_x.md"])
        self.check_paths(self.range_of(piece, "docs/A", "docs/a"), ["docs/B.md", "docs/_x.md"])
        self.check_paths(self.range_of(piece, "docs/_x.md", "docs/a.md"), ["docs/_x.md", "docs/a.md"])
        self.check_paths(self.range_of(piece, "docs/a", "docs/z"), ["docs/a.md", "docs/c.md"])

    def test_a_range_over_root_puts_uppercase_before_underscore_before_lowercase(self):
        piece = self.root_piece()
        self.check_paths(self.range_of(piece, "R", "_lead.txt"), ["README.md", "Zed.txt", "_lead.txt"])
        self.check_paths(self.range_of(piece, "S", "_"), ["Zed.txt"])

    def test_a_range_whose_start_does_not_exist_and_whose_end_was_renamed(self):
        piece = self.dir_piece("src/")
        first, last = "src/aaa_gone.py", "src/zzz_renamed.py"
        self.assertNotIn(first, TRACKED)
        self.assertNotIn(last, TRACKED)
        self.check_paths(self.range_of(piece, first, last), self.between(self.under("src/"), first, last))
        self.assertEqual(self.between(self.under("src/"), first, last), self.under("src/"))
        # and a range cut inside the folder
        self.check_paths(self.range_of(piece, "src/core/b", "src/main.py"),
                         ["src/core/b.py", "src/io/c.py", "src/main.py"])

    def test_a_range_over_an_empty_stretch_matches_nothing(self):
        self.check_paths(self.range_of(self.dir_piece("src/"), "src/zz", "src/zzz"), [])
        self.check_paths(self.range_of(self.dir_piece("src/"), "src/z", "src/a"), [])

    def test_a_range_after_direct(self):
        piece = self.direct_piece("src/")
        self.check_paths(self.range_of(piece, "src/n", "src/v"), ["src/naïve.py", "src/util.py"])
        self.check_paths(self.range_of(piece, "src/a", "src/z"), self.direct("src/"))

    def test_a_range_cuts_a_flat_folder_in_two_with_nothing_lost_or_doubled(self):
        piece = self.dir_piece("flat/")
        low = self.between(self.under("flat/"), "flat/f01", "flat/f20.txt")
        high = self.between(self.under("flat/"), "flat/f21", "flat/f99")
        self.assertEqual((len(low), len(high)), (20, 20))
        self.check_paths(self.range_of(piece, "flat/f01", "flat/f20.txt"), low)
        self.check_paths(self.range_of(piece, "flat/f21", "flat/f99"), high)

    def test_a_range_after_except(self):
        piece = self.except_of(self.dir_piece("web/"), "web/vendor/")
        self.check_paths(self.range_of(piece, "web/a", "web/j"), ["web/app.js", "web/index.html"])

    def test_a_range_over_a_folder_with_a_space_and_one_with_brackets(self):
        self.check_paths(self.range_of(self.dir_piece("my docs/"), "my docs/o", "my docs/r"),
                         ["my docs/old stuff/y.md"])
        self.check_paths(self.range_of(self.dir_piece("we[ir]d*/"), "we[ir]d*/b", "we[ir]d*/c"),
                         ["we[ir]d*/b.txt"])

    def test_the_range_does_not_take_a_neighbour_folder_between_its_ends_by_accident(self):
        # api/ then api2/ sort next to each other; a range on api/ only sees api/'s own files
        self.check_paths(self.range_of(self.dir_piece("api/"), "api/", "api2/z"), self.under("api/"))


class PickLineTest(AreaRepo):
    def test_sed_prints_the_nth_path_of_a_piece(self):
        piece = self.dir_piece("src/")
        paths = self.under("src/")
        for n in (1, 3, len(paths)):
            command = sed_template().replace("<piece>", piece).replace("<n>", str(n))
            for name, lines in self.each_shell(command):
                with self.subTest(shell=name, n=n):
                    self.assertEqual(lines, [paths[n - 1]])

    def test_sed_past_the_end_prints_nothing(self):
        command = sed_template().replace("<piece>", self.dir_piece("api/")).replace("<n>", "99")
        for name, lines in self.each_shell(command):
            with self.subTest(shell=name):
                self.assertEqual(lines, [])

    def test_the_nth_path_of_a_name_with_a_space(self):
        command = sed_template().replace("<piece>", self.dir_piece("my docs/")).replace("<n>", "1")
        for name, lines in self.each_shell(command):
            with self.subTest(shell=name):
                self.assertEqual(lines, [self.under("my docs/")[0]])


class FindListingTest(AreaRepo):
    def test_the_find_command_lists_every_file_and_prunes_the_four_folders(self):
        self.check_paths(find_command(), TRACKED, cwd=self.plain)

    def test_the_fence_commands_give_the_same_answers_on_the_find_listing(self):
        lister = find_command()
        cases = [
            (fill(template(C_DIR), lister, dir="src"), self.under("src/")),
            (fill(template(C_DIRECT), lister, dir="src"), self.direct("src/")),
            (fill(template(C_DIR), lister, dir="my docs"), self.under("my docs/")),
            (fill(template(C_ROOT), lister), self.root_files()),
            (self.range_of(fill(template(C_ROOT), lister), "10", "9"), ["10", "100", "9"]),
            (self.except_of(fill(template(C_DIR), lister, dir="web"), "web/vendor/"),
             [p for p in self.under("web/") if not p.startswith("web/vendor/")]),
        ]
        for command, expected in cases:
            self.check_paths(command, expected, cwd=self.plain)

    def test_the_counts_on_the_find_listing_match_git(self):
        lister = find_command()
        expected = Counter(p.split("/")[0] + "/" if "/" in p else "(root)" for p in TRACKED)
        for name, lines in self.each_shell(fill(template(C_TOP), lister), cwd=self.plain):
            with self.subTest(shell=name):
                self.assertEqual(self.parse_counts(lines), dict(expected))


class ExactlyOnceTest(AreaRepo):
    SKIPPED = "web/vendor"

    def areas(self):
        """A whole-repo partition, one string per area, in the shapes the file describes."""
        d, dr = self.dir_piece, self.direct_piece
        web_rest = self.except_of(self.except_of(d("web/"), "web/vendor/"), "web/legacy/")
        flat = d("flat/")
        return [
            self.root_piece(),
            d("api/"),
            d("api2/"),
            d("café/"),
            d("docs/"),
            self.range_of(flat, "flat/f01", "flat/f20.txt"),
            self.range_of(flat, "flat/f21", "flat/f99"),
            d("my docs/"),
            "{ %s; %s; %s; }" % (dr("src/"), d("src/core/"), d("src/io/")),
            web_rest,
            d("web/legacy/"),
            d("we[ir]d*/"),
            d("weid/"),
            d("wexd/"),
        ]

    def once(self, areas):
        return fill(template(C_ONCE), skipped=self.SKIPPED, areas=areas)

    def run_all(self, command):
        for name, argv in self.shells():
            code, out, err = self.run_in(argv, command)
            yield name, code, out, err

    def test_a_correct_partition_prints_the_message_and_exits_0(self):
        for name, code, out, err in self.run_all(self.once(self.areas())):
            with self.subTest(shell=name):
                self.assertEqual((code, out, err), (0, ONCE_MESSAGE + "\n", ""))

    def test_the_partition_helper_really_covers_everything_but_the_skipped_folder(self):
        # guards the guard: the areas above, run by hand, are the repo minus web/vendor/
        command = "{ %s; } | LC_ALL=C sort" % "; ".join(self.areas())
        want = [p for p in TRACKED if not p.startswith("web/vendor/")]
        self.check_paths(command, want)

    def test_an_overlap_fails_with_diff_output_and_no_message(self):
        for name, code, out, err in self.run_all(self.once(self.areas() + [self.dir_piece("api/")])):
            with self.subTest(shell=name):
                self.assertNotEqual(code, 0)
                self.assertIn("> api/a.py", out)
                self.assertIn("> api/sub/b.py", out)
                self.assertNotIn(ONCE_MESSAGE, out)

    def test_an_area_listed_twice_in_a_group_is_an_overlap(self):
        doubled = "{ %s; %s; }" % (self.dir_piece("docs/"), self.direct_piece("docs/"))
        areas = [a for a in self.areas() if a != self.dir_piece("docs/")] + [doubled]
        for name, code, out, err in self.run_all(self.once(areas)):
            with self.subTest(shell=name):
                self.assertNotEqual(code, 0)
                self.assertIn("> docs/a.md", out)
                self.assertNotIn(ONCE_MESSAGE, out)

    def test_a_gap_fails_with_diff_output_and_no_message(self):
        areas = [a for a in self.areas() if a != self.dir_piece("api2/")]
        for name, code, out, err in self.run_all(self.once(areas)):
            with self.subTest(shell=name):
                self.assertNotEqual(code, 0)
                self.assertIn("< api2/c.py", out)
                self.assertNotIn(ONCE_MESSAGE, out)

    def test_a_range_that_stops_short_leaves_a_gap(self):
        flat = self.dir_piece("flat/")
        areas = [a for a in self.areas() if "f21" not in a] + [self.range_of(flat, "flat/f21", "flat/f39")]
        for name, code, out, err in self.run_all(self.once(areas)):
            with self.subTest(shell=name):
                self.assertNotEqual(code, 0)
                self.assertIn("< flat/f40.txt", out)
                self.assertNotIn(ONCE_MESSAGE, out)

    def test_an_area_that_includes_the_skipped_folder_fails(self):
        areas = [a for a in self.areas() if a != self.dir_piece("web/legacy/")]
        areas.append(self.dir_piece("web/"))
        for name, code, out, err in self.run_all(self.once(areas)):
            with self.subTest(shell=name):
                self.assertNotEqual(code, 0)
                self.assertIn("> web/vendor/a.js", out)
                self.assertNotIn(ONCE_MESSAGE, out)

    def test_a_skipped_folder_leaves_a_folder_with_a_longer_name_in_the_listing(self):
        # skipping "api" must not drop api2/: with api2/ in the areas, a drop would show as an overlap
        areas = [a for a in self.areas() if a != self.dir_piece("api/")] + [self.dir_piece("web/vendor/")]
        command = fill(template(C_ONCE), skipped="api", areas=areas)
        for name, code, out, err in self.run_all(command):
            with self.subTest(shell=name):
                self.assertEqual((code, out), (0, ONCE_MESSAGE + "\n"))


if __name__ == "__main__":
    unittest.main()
