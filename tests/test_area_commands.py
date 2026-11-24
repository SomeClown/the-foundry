"""Run the area commands that agents/investigate.md tells a model to run, against real repos.

Paths from the repo never go into a command by typing: each one goes into a variable through a
three-line here-document (`IFS= read -r p1 <<'/END'`), and `awk` reads it from `ENVIRON`. The fence under
"### Areas" holds eight comment lines, each followed by one command; the variable block sits above it.
Both are read out of the Markdown as written (never retyped here), the placeholders are filled in with
variable names, and the whole program runs under `bash -c` and `zsh -f -c` (never `sh`: the last command
uses process substitution). Every result is compared with a set computed in Python from the `-z` listing.
The `find` listing, the `sed -n` line pick and the three `wc -l` forms run too.

Two repos: a small ordinary one, and a hostile one whose folders and files are named the way a repo
written to break the commands would name them. A command that gives the wrong set, prints a line equal to
MARKER, or leaves a file behind is a bug in the agent file's text; these tests don't bend around it.
The old form (`awk -v d='<dir>/'` with the path typed in) is kept below as a test-only literal, to show
that these tests would have caught it.

Standard library only; git, awk, tr, xargs, wc, sort, uniq, sed, diff and find are the tools used. No network.
"""
import os
import re
import shutil
import subprocess
import sys
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
VAR_FIRST = "IFS= read -r p1 <<'/END'"


def agent_text():
    return AGENT.read_text(encoding="utf-8")


def section_text(heading):
    """The body of one `##`/`###` section, raw (comment lines inside fences start with a single "# ")."""
    text = agent_text()
    marker = "\n" + heading + "\n"
    start = text.index(marker) + len(marker)
    match = re.search(r"^#{2,3} ", text[start:], re.M)
    return text[start:start + match.start()] if match else text[start:]


def areas_section():
    return section_text("### Areas")


def fences(text):
    return re.findall(r"^```\n(.*?)^```$", text, re.S | re.M)


def command_fence():
    found = [f for f in fences(areas_section()) if C_TOP in f]
    assert len(found) == 1, "expected exactly one command fence under ### Areas, found %d" % len(found)
    return found[0]


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


def var_block():
    """The three lines of the variable block: the one fence under ### Areas that starts with the read line."""
    found = [f for f in fences(areas_section()) if f.startswith(VAR_FIRST)]
    assert len(found) == 1, "expected exactly one variable block under ### Areas, found %d" % len(found)
    lines = found[0].rstrip("\n").split("\n")
    assert lines == [VAR_FIRST, "<path>", "/END"], lines
    return lines


def list_command():
    """What the file says <list> is: its own sentence, not a copy kept here."""
    flat = " ".join(areas_section().split())
    matches = re.findall(r"`<list>` below is `(git ls-files[^`]*)`", flat)
    assert len(matches) == 1, matches
    return matches[0]


LIST = list_command()


def find_command():
    matches = re.findall(r"`(find \. \\\( .*? \| LC_ALL=C sort)`", agent_text())
    assert len(matches) == 1, matches
    return matches[0]


def sed_template():
    matches = re.findall(r"`(<piece> \| sed -n '<n>p')`", areas_section())
    assert len(matches) == 1, matches
    return matches[0]


def file_list_section():
    text = agent_text()
    return text[text.index("\n## Build the File List\n"): text.index("\n## A Sweep in Parts\n")]


def wc_pipe_template():
    found = re.findall(r"`(<listing> \| tr '\\n' '\\0' \| xargs -0 wc -l --)`", file_list_section())
    assert len(found) == 1, found
    return found[0]


def wc_heredoc_template():
    """(header line, the two <path> lines' text, closing line) of the pasted-paths fence."""
    found = [f for f in fences(file_list_section()) if f.startswith("tr '\\n' '\\0' <<'/END'")]
    assert len(found) == 1, found
    lines = found[0].rstrip("\n").split("\n")
    assert lines == ["tr '\\n' '\\0' <<'/END' | xargs -0 wc -l --", "<path>", "<path>", "/END"], lines
    return lines


def block_count_header():
    flat = " ".join(section_text("### The Block").split())
    found = re.findall(r"between `(wc -l <<'/END')` and `/END`", flat)
    assert len(found) == 1, found
    return found[0]


class Prog:
    """One shell program: the variable blocks (one per path a command takes) and then the command."""

    def __init__(self):
        self.blocks = []
        self.names = {}

    def var(self, value):
        """The variable holding this path: one block per distinct path, so the same path is the same name."""
        assert "\n" not in value, "a path with a line break can't be carried in a variable block"
        if value not in self.names:
            name = "p%d" % (len(self.blocks) + 1)
            first, _mid, last = var_block()
            self.blocks.append("\n".join([first.replace("p1", name, 1), value, last]))
            self.names[value] = name
        return self.names[value]

    def script(self, command):
        return "\n".join(self.blocks + [command])


def fill(prog, command, lister=None, **kw):
    """Fill the placeholders of one fence command. `piece` is a command string that already holds its lister."""
    lister = LIST if lister is None else lister
    for key in ("dir", "folder", "first", "last", "skipped"):
        if key in kw:
            command = command.replace("<%s var>" % key, prog.var(kw[key]))
    if "piece" in kw:
        command = command.replace("<piece>", kw["piece"])
    if "n" in kw:
        command = command.replace("<n>", str(kw["n"]))
    if "areas" in kw:
        command = command.replace("<area 1>; <area 2>; <and so on>", "; ".join(kw["areas"]))
    return command.replace("<list>", lister)


def byte_key(s):
    return s.encode("utf-8")


def split_lines(paths):
    """The listing as the commands see it: `git ls-files -z | tr '\\0' '\\n'`, one awk record per line."""
    return "\n".join(paths).split("\n") if paths else []


def out_lines(out):
    lines = out.split("\n")
    assert lines[-1] == "", "output doesn't end with a line break: %r" % out[-40:]
    return lines[:-1]


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

# One path component each. The folder and file names of the hostile repo.
HOSTILE = [
    "sp ace",
    "bob's notes",
    'dq"uote',
    "a\\tb",              # a backslash followed by t, not a tab
    "tail\\",             # a trailing backslash
    "$(echo MARKER)",
    "`echo MARKER`",
    "$HOME",
    "semi;colon",
    "pi|pe",
    "and&&and",
    "a;b|c&&d",
    "-dash",
    " lead",
    "trail ",
    "br[ack]et",
    "[",
    "st*ar",
    "*",
    "café",
    "cr\rname",
    "n" * 200,
    "x'; echo MARKER; '",
    "$(touch PWNED)",
    "y'; touch PWNED; '",
]
INJECT = "x'; echo MARKER; '"

# a path with a line break, a root file named END, a folder holding a file named END, and friends
HOSTILE_EXTRA = [
    "README.md", "END", "sub/END", "-rootdash.txt", " lead-root.txt", "trail-root.txt ", "tab\there.txt",
    "docs/a.md", "docs/nl\nx.md", "docs/z.md", "files/sub/b.txt", "src/main.py", "src/core/a.py",
]


def hostile_paths():
    paths = list(HOSTILE_EXTRA)
    for h in HOSTILE:
        paths += [h + "/a.txt", h + "/sub/b.txt", "files/" + h, "nest/" + h + "/c.txt"]
    return paths


def lines_of_file(path):
    """How many lines the file holds: 1 to 3, by its name, so the `wc -l` counts differ."""
    return 1 + sum(path.encode("utf-8")) % 3


class Helpers(unittest.TestCase):
    """The shared plumbing. A subclass builds `repo`, `plain` and `tmp`, and sets `paths` (the names
    created) and `lines` (what the listing prints, split on line breaks)."""

    tmp = repo = plain = None
    paths = []
    lines = []
    skipped_names = []
    base_env = None

    @classmethod
    def make_env(cls):
        return {
            "PATH": os.environ["PATH"],
            "HOME": str(cls.tmp),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
            # a locale that is not C: every command must set its own LC_ALL=C and not lean on this one
            "LC_ALL": "en_US.UTF-8", "LANG": "en_US.UTF-8",
        }

    @classmethod
    def build(cls, paths, prune=True):
        """Create the repo and the plain copy. A name the filesystem refuses is skipped with a message."""
        cls.tmp = Path(tempfile.mkdtemp(prefix="area-cmds-")).resolve()
        cls.repo = cls.tmp / "repo"
        cls.repo.mkdir()
        cls.env = cls.make_env()
        cls.skipped_names = []
        cls.paths = []
        cls.git(cls.repo, "init", "-q", "-b", "main")
        for name in paths:
            path = cls.repo / name
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x\n" * lines_of_file(name), encoding="utf-8")
            except OSError as err:
                cls.skipped_names.append(name)
                sys.stderr.write("skipped %r: the filesystem refuses it (%s)\n" % (name, err))
                continue
            cls.paths.append(name)
        cls.git(cls.repo, "add", "-A")
        cls.git(cls.repo, "commit", "-q", "-m", "all")
        listed = cls.git_z(cls.repo)
        cls.lines = split_lines(listed)
        assert sorted(listed, key=byte_key) == sorted(cls.paths, key=byte_key), "git doesn't list what was created"

        # the same files outside git, plus the folders the find command prunes
        cls.plain = cls.tmp / "plain"
        shutil.copytree(cls.repo, cls.plain, ignore=shutil.ignore_patterns(".git"))
        if prune:
            for pruned in (".git/HEAD", "node_modules/n.js", "venv/v.py", ".venv/w.py",
                           "src/node_modules/deep.js", "web/venv/z.py"):
                path = cls.plain / pruned
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        if cls.tmp:
            shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def git(cls, cwd, *args):
        done = subprocess.run(["git", *args], cwd=cwd, env=cls.env, capture_output=True)
        assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
        return done.stdout.decode("utf-8")

    @classmethod
    def git_z(cls, cwd):
        raw = cls.git(cwd, "ls-files", "-z")
        return [p for p in raw.split("\0") if p]

    def setUp(self):
        self.prog = Prog()
        self.before = self.snapshot()

    def tearDown(self):
        self.assertEqual(self.snapshot(), self.before, "a command left something behind in the repo or its parent")

    def snapshot(self):
        """Every path under the temp folder (the repo's parent), the repo's own .git left out."""
        if not self.tmp:
            return []
        found = []
        for dirpath, dirnames, filenames in os.walk(str(self.tmp)):
            if ".git" in dirnames:
                dirnames.remove(".git")
            found.extend(os.path.join(dirpath, n) for n in dirnames + filenames)
        return sorted(found)

    def shells(self):
        for name, argv in SHELLS:
            if shutil.which(argv[0]):
                yield name, argv

    def t(self, comment, lister=None, **kw):
        return fill(self.prog, template(comment), lister, **kw)

    def run_in(self, argv, command, cwd=None, prog=None):
        script = (prog or self.prog).script(command)
        done = subprocess.run(argv + [script], cwd=cwd or self.repo, env=self.env, capture_output=True)
        return done.returncode, done.stdout.decode("utf-8"), done.stderr.decode("utf-8")

    def each_shell(self, command, cwd=None):
        """Yield (shell name, stdout lines) for a command that must exit 0 with an empty stderr and never print MARKER."""
        for name, argv in self.shells():
            code, out, err = self.run_in(argv, command, cwd)
            self.assertEqual(code, 0, "%s: exit %s\n%s\n%s" % (name, code, command, err))
            self.assertEqual(err, "", "%s: stderr\n%s" % (name, command))
            lines = out_lines(out)
            self.assertNotIn("MARKER", lines, "%s: a planted command ran\n%s" % (name, command))
            yield name, lines

    def check_paths(self, command, expected, cwd=None):
        for name, lines in self.each_shell(command, cwd):
            with self.subTest(shell=name):
                self.assertEqual(sorted(lines, key=byte_key), sorted(expected, key=byte_key), command)

    def parse_counts(self, lines):
        counts = {}
        for line in lines:
            m = re.match(r"^ *(\d+) (.*)$", line, re.S)
            self.assertIsNotNone(m, repr(line))
            counts[m.group(2)] = int(m.group(1))
        return counts

    # expected values, from the listing Python computed
    def under(self, prefix):
        return [p for p in self.lines if p.startswith(prefix)]

    def direct(self, prefix):
        return [p for p in self.lines if p.startswith(prefix) and "/" not in p[len(prefix):]]

    def root_files(self):
        return [p for p in self.lines if "/" not in p]

    def between(self, paths, first, last):
        a, b = byte_key(first), byte_key(last)
        return [p for p in paths if a <= byte_key(p) <= b]

    def expected_top(self):
        return dict(Counter(p.split("/")[0] + "/" if "/" in p else "(root)" for p in self.lines))

    def expected_down(self, d):
        expected = Counter()
        for p in self.under(d):
            rest = p[len(d):]
            i = rest.find("/")
            expected[d + rest[:i + 1] if i >= 0 else d + " (direct)"] += 1
        return dict(expected)

    # the pieces as commands (a folder is written with its trailing slash, as the variable holds it)
    def dir_piece(self, d, lister=None):
        return self.t(C_DIR, lister, dir=d)

    def direct_piece(self, d, lister=None):
        return self.t(C_DIRECT, lister, dir=d)

    def root_piece(self, lister=None):
        return self.t(C_ROOT, lister)

    def except_of(self, piece, folder):
        return self.t(C_EXCEPT, piece=piece, folder=folder)

    def range_of(self, piece, first, last):
        return self.t(C_RANGE, piece=piece, first=first, last=last)

    def once_command(self, areas, skipped, sort_listing=True):
        """The exactly-once check with one or more skipped folders: the first from the template, the rest
        chained as `except` filters on the listing side, before its sort."""
        tmpl = template(C_ONCE)
        m = re.match(r"diff <\((<list> \| x=\"\$\{<skipped var>:\?\}\" .*?) \| LC_ALL=C sort\) <\(\{ ", tmpl)
        assert m, tmpl
        listing = m.group(1)
        chained = listing.replace("<skipped var>", self.prog.var(skipped[0]))
        for folder in skipped[1:]:
            chained = self.except_of(chained.replace("<list>", LIST), folder)
        command = tmpl.replace(listing, chained)
        if not sort_listing:
            assert " | LC_ALL=C sort) <(" in command
            command = command.replace(" | LC_ALL=C sort) <(", ") <(", 1)
        return fill(self.prog, command, areas=areas)


class AreaRepo(Helpers):
    @classmethod
    def setUpClass(cls):
        cls.build(TRACKED)


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

    def test_the_variable_block_is_three_lines_with_no_indent(self):
        self.assertEqual(var_block(), [VAR_FIRST, "<path>", "/END"])

    def test_the_file_lists_with_z_and_turns_the_zero_bytes_into_line_breaks(self):
        self.assertEqual(LIST, "git ls-files -z | tr '\\0' '\\n'")

    def test_the_fixture_repo_lists_what_python_built(self):
        listed = self.git_z(self.repo)
        self.assertEqual(listed, TRACKED)
        self.assertEqual(self.run_in(["bash", "-c"], LIST)[1].split("\n")[:-1], TRACKED)

    def test_without_z_a_non_ascii_name_comes_back_quoted(self):
        plain = self.git(self.repo, "ls-files").splitlines()
        self.assertIn('"caf\\303\\251/menu.txt"', plain)
        self.assertNotIn("café/menu.txt", plain)


class CountTest(AreaRepo):
    def test_count_by_top_level_folder(self):
        for name, lines in self.each_shell(self.t(C_TOP)):
            with self.subTest(shell=name):
                self.assertEqual(self.parse_counts(lines), self.expected_top())

    def test_count_one_level_down_inside_a_folder(self):
        for d in ("src/", "api/", "my docs/", "we[ir]d*/", "flat/", "web/"):
            for name, lines in self.each_shell(self.t(C_DOWN, dir=d)):
                with self.subTest(shell=name, dir=d):
                    self.assertEqual(self.parse_counts(lines), self.expected_down(d))

    def test_counts_one_level_down_do_not_bleed_into_a_folder_with_the_same_start(self):
        for name, lines in self.each_shell(self.t(C_DOWN, dir="api/")):
            with self.subTest(shell=name):
                self.assertEqual(self.parse_counts(lines), {"api/ (direct)": 1, "api/sub/": 1})

    def test_a_folder_with_no_files_counts_nothing(self):
        for name, lines in self.each_shell(self.t(C_DOWN, dir="nothing/")):
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
        self.check_paths(self.except_of(LIST, "we/"), TRACKED)  # "we/" is a folder that does not exist

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
            (self.t(C_DIR, lister, dir="src/"), self.under("src/")),
            (self.t(C_DIRECT, lister, dir="src/"), self.direct("src/")),
            (self.t(C_DIR, lister, dir="my docs/"), self.under("my docs/")),
            (self.t(C_ROOT, lister), self.root_files()),
            (self.range_of(self.t(C_ROOT, lister), "10", "9"), ["10", "100", "9"]),
            (self.except_of(self.t(C_DIR, lister, dir="web/"), "web/vendor/"),
             [p for p in self.under("web/") if not p.startswith("web/vendor/")]),
        ]
        for command, expected in cases:
            self.check_paths(command, expected, cwd=self.plain)

    def test_the_counts_on_the_find_listing_match_git(self):
        for name, lines in self.each_shell(self.t(C_TOP, find_command()), cwd=self.plain):
            with self.subTest(shell=name):
                self.assertEqual(self.parse_counts(lines), self.expected_top())


class ExactlyOnceTest(AreaRepo):
    SKIPPED = "web/vendor/"

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
        return self.once_command(areas, [self.SKIPPED])

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
        areas = self.areas()
        self.assertEqual(areas[6], self.range_of(flat, "flat/f21", "flat/f99"))  # the second half of flat/
        areas[6] = self.range_of(flat, "flat/f21", "flat/f39")
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
        # skipping "api/" must not drop api2/: with api2/ in the areas, a drop would show as an overlap
        areas = [a for a in self.areas() if a != self.dir_piece("api/")] + [self.dir_piece("web/vendor/")]
        command = self.once_command(areas, ["api/"])
        for name, code, out, err in self.run_all(command):
            with self.subTest(shell=name):
                self.assertEqual((code, out), (0, ONCE_MESSAGE + "\n"))


# ---------------------------------------------------------------- the hostile repo


class HostileRepo(Helpers):
    """Folders and files named the way a repo written to break the commands would name them."""

    @classmethod
    def setUpClass(cls):
        cls.build(hostile_paths())

    def carriable(self, name):
        return "\n" not in name

    def hostile_dirs(self):
        """Every hostile folder name the filesystem allowed, with its trailing slash."""
        return [h + "/" for h in HOSTILE if h + "/a.txt" in self.paths]

    def test_every_hostile_name_the_filesystem_allows_was_created_and_listed_whole(self):
        refused = [n for n in hostile_paths() if n not in self.paths]
        self.assertEqual(refused, self.skipped_names)
        # at least the plain-letter hostile names must have been possible, or this run proves nothing
        for must in ("bob's notes/a.txt", "x'; echo MARKER; '/a.txt", "a\\tb/a.txt", "sp ace/a.txt", "END", "sub/END"):
            self.assertIn(must, self.paths)
        self.assertEqual(sorted(self.paths, key=byte_key), sorted(self.git_z(self.repo), key=byte_key))

    def test_the_listing_is_what_python_computes_from_the_z_listing(self):
        for name, argv in self.shells():
            with self.subTest(shell=name):
                code, out, err = self.run_in(argv, LIST)
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(out_lines(out), self.lines)

    # ---- counts

    def test_count_by_top_level_folder(self):
        for name, lines in self.each_shell(self.t(C_TOP)):
            with self.subTest(shell=name):
                self.assertEqual(self.parse_counts(lines), self.expected_top())

    def test_count_one_level_down_inside_every_hostile_folder_and_the_folders_holding_them(self):
        for d in self.hostile_dirs() + ["files/", "nest/", "docs/", "sub/"]:
            for name, lines in self.each_shell(self.t(C_DOWN, dir=d)):
                with self.subTest(shell=name, dir=d):
                    self.assertEqual(self.parse_counts(lines), self.expected_down(d))

    # ---- every piece form

    def test_a_folder_piece_and_its_direct_form_for_every_hostile_folder(self):
        for d in self.hostile_dirs():
            with self.subTest(dir=d):
                self.check_paths(self.dir_piece(d), self.under(d))
                self.check_paths(self.direct_piece(d), self.direct(d))
                self.assertEqual(len(self.under(d)), 2)
                self.assertEqual(len(self.direct(d)), 1)

    def test_a_folder_that_is_a_prefix_of_nothing_else_still_takes_only_itself(self):
        # "n"*200 and "sp ace" and friends sit beside names that start the same way
        self.check_paths(self.dir_piece("sub/"), ["sub/END"])
        self.check_paths(self.dir_piece("files/"), self.under("files/"))
        self.check_paths(self.direct_piece("files/"), [p for p in self.direct("files/")])

    def test_the_root_piece_holds_the_root_files_including_one_named_END_and_the_second_half_of_a_line_break_path(self):
        self.check_paths(self.root_piece(), self.root_files())
        self.assertIn("END", self.root_files())
        self.assertIn("x.md", self.root_files())  # docs/nl\nx.md: the second line of the listing

    def test_a_folder_holding_a_file_named_END_gives_that_file(self):
        self.check_paths(self.dir_piece("sub/"), ["sub/END"])
        self.check_paths(self.direct_piece("sub/"), ["sub/END"])

    def test_a_path_with_a_line_break_shows_as_two_lines_and_the_folder_piece_gets_the_first(self):
        self.assertIn("docs/nl", self.lines)
        self.assertIn("x.md", self.lines)
        self.check_paths(self.dir_piece("docs/"), self.under("docs/"))
        self.assertIn("docs/nl", self.under("docs/"))
        self.assertNotIn("x.md", self.under("docs/"))

    # ---- except

    def test_except_of_each_hostile_folder_after_the_whole_listing(self):
        for d in self.hostile_dirs():
            with self.subTest(dir=d):
                self.check_paths(self.except_of(LIST, d), [p for p in self.lines if not p.startswith(d)])

    def test_except_chained_twice_with_hostile_folders(self):
        dirs = self.hostile_dirs()
        pairs = [(dirs[0], dirs[1]), (dirs[3], dirs[4]), (INJECT + "/", "$(echo MARKER)/"), ("`echo MARKER`/", "$HOME/"),
                 ("-dash/", " lead/"), ("trail /", "n" * 200 + "/")]
        for a, b in pairs:
            with self.subTest(first=a[:20], second=b[:20]):
                piece = self.except_of(self.except_of(LIST, a), b)
                self.check_paths(piece, [p for p in self.lines if not p.startswith(a) and not p.startswith(b)])

    def test_except_inside_a_hostile_piece_and_after_direct_and_root(self):
        self.check_paths(self.except_of(self.dir_piece("nest/"), "nest/bob's notes/"),
                         [p for p in self.under("nest/") if not p.startswith("nest/bob's notes/")])
        self.check_paths(self.except_of(self.dir_piece("nest/"), "nest/" + INJECT + "/"),
                         [p for p in self.under("nest/") if not p.startswith("nest/" + INJECT + "/")])
        self.check_paths(self.except_of(self.direct_piece("files/"), "files/sub/"), self.direct("files/"))
        self.check_paths(self.except_of(self.root_piece(), "docs/"), self.root_files())

    # ---- ranges

    def test_ranges_that_start_and_end_on_hostile_paths(self):
        files = sorted([p for p in self.lines if p.startswith("files/") and self.carriable(p)], key=byte_key)
        self.assertGreater(len(files), 10)
        piece = self.dir_piece("files/")
        ends = [(0, len(files) - 1), (0, 0), (len(files) - 1, len(files) - 1), (1, 5), (3, 9), (5, 3)]
        ends += [(i, i + 2) for i in range(0, len(files) - 2, 4)]
        for i, j in ends:
            first, last = files[i], files[j]
            with self.subTest(first=first[:30], last=last[:30]):
                self.check_paths(self.range_of(piece, first, last), self.between(self.under("files/"), first, last))

    def test_a_range_that_ends_on_every_hostile_file_in_turn(self):
        files = sorted([p for p in self.lines if p.startswith("files/") and self.carriable(p)], key=byte_key)
        piece = self.dir_piece("files/")
        for last in files:
            with self.subTest(last=last[:30]):
                self.check_paths(self.range_of(piece, files[0], last), self.between(self.under("files/"), files[0], last))

    def test_a_range_over_the_whole_listing_ending_on_the_file_named_END_and_on_root_files(self):
        root = self.root_piece()
        for first, last in (("END", "README.md"), ("-rootdash.txt", "END"), (" lead-root.txt", "trail-root.txt "),
                            ("END", "END"), ("README.md", "x.md"), ("tab\there.txt", "trail-root.txt ")):
            with self.subTest(first=first, last=last):
                self.check_paths(self.range_of(root, first, last), self.between(self.root_files(), first, last))

    def test_a_range_after_an_except_and_after_direct_on_hostile_names(self):
        piece = self.except_of(self.dir_piece("nest/"), "nest/" + INJECT + "/")
        first, last = "nest/$(echo MARKER)/c.txt", "nest/-dash/zzz"
        self.check_paths(self.range_of(piece, first, last),
                         self.between([p for p in self.under("nest/") if not p.startswith("nest/" + INJECT + "/")], first, last))
        piece = self.direct_piece("files/")
        first, last = "files/$(echo MARKER)", "files/bob's notes"
        self.check_paths(self.range_of(piece, first, last), self.between(self.direct("files/"), first, last))

    def test_a_range_end_with_a_trailing_backslash_and_with_a_carriage_return(self):
        piece = self.dir_piece("files/")
        for last in ("files/tail\\", "files/cr\rname", "files/a\\tb"):
            if last not in self.lines:
                continue
            with self.subTest(last=last):
                self.check_paths(self.range_of(piece, "files/", last), self.between(self.under("files/"), "files/", last))

    # ---- the line-pick, the find listing

    def test_the_nth_path_of_a_hostile_piece(self):
        for d in ("files/", "nest/", INJECT + "/", "bob's notes/"):
            piece = self.dir_piece(d)
            paths = self.under(d)
            for n in (1, len(paths)):
                command = sed_template().replace("<piece>", piece).replace("<n>", str(n))
                for name, lines in self.each_shell(command):
                    with self.subTest(shell=name, dir=d, n=n):
                        self.assertEqual(lines, [paths[n - 1]])

    def test_the_find_listing_gives_the_same_set_as_git(self):
        expected = sorted(self.lines, key=byte_key)
        for name, lines in self.each_shell(find_command(), cwd=self.plain):
            with self.subTest(shell=name):
                self.assertEqual(sorted(lines, key=byte_key), expected)

    def test_every_piece_works_on_the_find_listing_for_each_hostile_folder(self):
        lister = find_command()
        for d in self.hostile_dirs():
            with self.subTest(dir=d):
                self.check_paths(self.t(C_DIR, lister, dir=d), self.under(d), cwd=self.plain)
                self.check_paths(self.t(C_DIRECT, lister, dir=d), self.direct(d), cwd=self.plain)
                self.check_paths(self.except_of(self.t(C_DIR, lister, dir="nest/"), "nest/" + d),
                                 [p for p in self.under("nest/") if not p.startswith("nest/" + d)], cwd=self.plain)

    def test_the_find_listing_counts_match_git(self):
        for name, lines in self.each_shell(self.t(C_TOP, find_command()), cwd=self.plain):
            with self.subTest(shell=name):
                self.assertEqual(self.parse_counts(lines), self.expected_top())

    def test_the_injection_folder_and_bob_s_notes_each_give_their_one_direct_file_on_the_find_listing(self):
        for d in (INJECT + "/", "bob's notes/"):
            self.check_paths(self.t(C_DIRECT, find_command(), dir=d), [d + "a.txt"], cwd=self.plain)

    # ---- the three wc -l forms

    def expected_wc(self, paths):
        return {p: lines_of_file(p) for p in paths}

    def parse_wc(self, out):
        counts, total = {}, 0
        for line in out_lines(out):
            m = re.match(r"^ *(\d+) (.*)$", line, re.S)
            self.assertIsNotNone(m, repr(line))
            if m.group(2) == "total":
                total += int(m.group(1))
            else:
                counts[m.group(2)] = int(m.group(1))
        return counts, total

    def run_wc(self, command):
        for name, argv in self.shells():
            code, out, err = self.run_in(argv, command)
            self.assertEqual((code, err), (0, ""), "%s\n%s" % (name, command))
            self.assertNotIn("MARKER", out_lines(out))
            yield name, out

    def test_wc_over_a_piped_listing_counts_every_file_of_a_hostile_folder(self):
        for d in self.hostile_dirs() + ["files/"]:
            listing = self.dir_piece(d)
            command = wc_pipe_template().replace("<listing>", listing)
            expected = self.expected_wc(self.under(d))
            for name, out in self.run_wc(command):
                with self.subTest(shell=name, dir=d):
                    counts, total = self.parse_wc(out)
                    self.assertEqual(counts, expected)
                    self.assertEqual(total, sum(expected.values()) if len(expected) > 1 else 0)

    def test_wc_over_a_pasted_here_document_counts_the_paths_given(self):
        header, _p1, _p2, end = wc_heredoc_template()
        for d in self.hostile_dirs() + ["files/"]:
            given = self.under(d)[:2]
            body = "\n".join(given[:1] + given[1:])
            # the fence holds two <path> lines; a path list of any length goes the same way
            command = "\n".join([header, body, end])
            expected = self.expected_wc(given)
            for name, out in self.run_wc(command):
                with self.subTest(shell=name, dir=d):
                    counts, _total = self.parse_wc(out)
                    self.assertEqual(counts, expected)

    def test_wc_over_a_pasted_here_document_with_every_carriable_path_at_once(self):
        header, _p1, _p2, end = wc_heredoc_template()
        given = [p for p in self.paths if self.carriable(p)]
        command = "\n".join([header] + given + [end])
        for name, out in self.run_wc(command):
            with self.subTest(shell=name):
                counts, _total = self.parse_wc(out)
                self.assertEqual(counts, self.expected_wc(given))

    def test_the_block_count_counts_area_lines_holding_hostile_paths(self):
        header = block_count_header()
        lines = []
        for d in self.hostile_dirs():
            lines.append("- %s: `%s` (%d files)" % ("area" + str(len(lines)), d, len(self.under(d))))
        lines.append("- group: `a;b|c&&d/` + `$(echo MARKER)/` (4 files)")
        lines.append("- range: `files/` from `files/$(touch PWNED)` to `files/x'; echo MARKER; '` (3 files)")
        for count in (1, 2, len(lines)):
            command = "\n".join([header] + lines[:count] + ["/END"])
            for name, out in self.run_wc(command):
                with self.subTest(shell=name, lines=count):
                    self.assertEqual(out.strip(), str(count))

    # ---- the exactly-once check

    SKIP = (INJECT + "/", "sub/")

    def partition(self):
        """Every file of the listing outside the two skipped folders, in areas of the shapes the file describes."""
        d, dr = self.dir_piece, self.direct_piece
        files = sorted([p for p in self.lines if p.startswith("files/")], key=byte_key)
        cut = len(files) // 2
        hostile = [h for h in self.hostile_dirs() if h != INJECT + "/"]
        singles, group = hostile[3:], hostile[:3]
        areas = [
            self.root_piece(),
            "{ %s; %s; %s; }" % (d("docs/"), dr("src/"), d("src/core/")),
            d("nest/"),
            self.range_of(d("files/"), files[0], files[cut]),
            self.range_of(d("files/"), files[cut + 1], files[-1]),
            "{ %s; }" % "; ".join(d(g) if i % 2 == 0 else dr(g) + "; " + d(g + "sub/") for i, g in enumerate(group)),
        ]
        areas += [d(h) for h in singles]
        return areas

    def once(self, areas, skipped=None, sort_listing=True):
        return self.once_command(areas, list(skipped or self.SKIP), sort_listing)

    def run_all(self, command):
        for name, argv in self.shells():
            code, out, err = self.run_in(argv, command)
            yield name, code, out, err

    def test_the_partition_helper_really_covers_everything_but_the_two_skipped_folders(self):
        command = "{ %s; } | LC_ALL=C sort" % "; ".join(self.partition())
        want = [p for p in self.lines if not any(p.startswith(s) for s in self.SKIP)]
        self.check_paths(command, want)

    def test_a_full_partition_with_two_skipped_folders_one_hostile_and_a_multi_piece_area_passes(self):
        self.assertIn("{ ", "".join(self.partition()))
        for name, code, out, err in self.run_all(self.once(self.partition())):
            with self.subTest(shell=name):
                self.assertEqual((code, out, err), (0, ONCE_MESSAGE + "\n", ""))

    def test_the_check_fails_on_an_overlap(self):
        areas = self.partition() + [self.dir_piece("bob's notes/")]
        for name, code, out, err in self.run_all(self.once(areas)):
            with self.subTest(shell=name):
                self.assertNotEqual(code, 0)
                self.assertIn("> bob's notes/a.txt", out)
                self.assertNotIn(ONCE_MESSAGE, out)

    def test_the_check_fails_on_a_gap(self):
        areas = self.partition()[:-1]
        left_out = [h for h in self.hostile_dirs() if h != INJECT + "/"][-1]
        for name, code, out, err in self.run_all(self.once(areas)):
            with self.subTest(shell=name):
                self.assertNotEqual(code, 0)
                self.assertIn("< " + left_out + "a.txt", out)
                self.assertNotIn(ONCE_MESSAGE, out)

    def test_an_area_that_takes_a_skipped_hostile_folder_fails(self):
        areas = self.partition() + [self.dir_piece(INJECT + "/")]
        for name, code, out, err in self.run_all(self.once(areas)):
            with self.subTest(shell=name):
                self.assertNotEqual(code, 0)
                self.assertIn("> " + INJECT + "/a.txt", out)

    def test_without_the_sort_on_the_listing_side_a_line_break_path_makes_the_check_fail(self):
        # the mutation: the same command with its listing-side sort cut out
        mutated = self.once(self.partition(), sort_listing=False)
        for name, code, out, err in self.run_all(mutated):
            with self.subTest(shell=name):
                self.assertNotEqual(code, 0, "the check passes without the sort; the line-break path no longer bites")
                self.assertNotIn(ONCE_MESSAGE, out)
                self.assertIn("x.md", out)

    def test_the_sorted_check_passes_where_the_unsorted_one_fails(self):
        for name, code, out, err in self.run_all(self.once(self.partition(), sort_listing=True)):
            with self.subTest(shell=name):
                self.assertEqual((code, out), (0, ONCE_MESSAGE + "\n"))

    # ---- the guards: an unset or empty variable stops the command

    def guarded(self):
        """Every fence command that takes a path in a variable, built with its variables, and the names it uses."""
        cases = {}
        cases["down"] = self.t(C_DOWN, dir="files/")
        cases["dir"] = self.t(C_DIR, dir="files/")
        cases["direct"] = self.t(C_DIRECT, dir="files/")
        cases["except"] = self.t(C_EXCEPT, piece=LIST, folder="files/")
        cases["range"] = self.t(C_RANGE, piece=LIST, first="files/a", last="files/z")
        return cases

    def variants(self, command):
        """The command with every variable unset, and with every variable set to an empty line."""
        unset = Prog()
        empty = Prog()
        # the same names, each set from an empty line
        empty.blocks = [block.split("\n")[0] + "\n\n/END" for block in self.prog.blocks]
        return [("unset", unset), ("empty", empty)]

    def test_an_unset_or_empty_variable_stops_each_command_with_a_message_and_no_paths(self):
        for label, command in self.guarded().items():
            if label == "down":
                continue
            for kind, prog in self.variants(command):
                for name, argv in self.shells():
                    with self.subTest(command=label, variable=kind, shell=name):
                        code, out, err = self.run_in(argv, command, prog=prog)
                        self.assertNotEqual(code, 0)
                        self.assertEqual(out, "", "paths were printed with the variable " + kind)
                        self.assertRegex(err, r"not set|null")

    def test_an_unset_or_empty_variable_stops_the_count_one_level_down_with_a_message_and_no_counts(self):
        command = self.guarded()["down"]
        for kind, prog in self.variants(command):
            for name, argv in self.shells():
                with self.subTest(variable=kind, shell=name):
                    code, out, err = self.run_in(argv, command, prog=prog)
                    self.assertEqual(out, "")
                    self.assertRegex(err, r"not set|null")

    def test_the_count_one_level_down_exits_non_zero_when_its_variable_is_unset_or_empty(self):
        # the command ends in `| uniq -c`, so the pipeline's status is uniq's, not the failed awk's
        command = self.guarded()["down"]
        for kind, prog in self.variants(command):
            for name, argv in self.shells():
                with self.subTest(variable=kind, shell=name):
                    code, out, err = self.run_in(argv, command, prog=prog)
                    self.assertNotEqual(code, 0, "exit 0 with stderr %r" % err)

    def test_the_fixed_count_line_gives_the_right_counts_for_every_hostile_folder_and_lists_nothing_when_unset(self):
        for d in self.hostile_dirs() + ["files/", "nest/"]:
            for name, lines in self.each_shell(self.t(C_DOWN, dir=d)):
                with self.subTest(shell=name, dir=d):
                    self.assertEqual(self.parse_counts(lines), self.expected_down(d))
        command = self.t(C_DOWN, dir="files/")
        self.assertTrue(command.startswith(': "${'), command)
        for kind, prog in self.variants(command):
            for name, argv in self.shells():
                with self.subTest(variable=kind, shell=name):
                    code, out, err = self.run_in(argv, command, prog=prog)
                    self.assertEqual(out, "")  # nothing listed at all, not even an empty-looking count
                    self.assertNotEqual(code, 0)
                    self.assertRegex(err, r"not set|null")

    def test_an_unset_or_empty_skipped_variable_stops_the_exactly_once_check(self):
        command = self.once(self.partition())
        for kind, prog in self.variants(command):
            for name, argv in self.shells():
                with self.subTest(variable=kind, shell=name):
                    code, out, err = self.run_in(argv, command, prog=prog)
                    self.assertNotEqual(code, 0)
                    self.assertNotIn(ONCE_MESSAGE, out)
                    self.assertRegex(err, r"not set|null")

    def test_an_empty_variable_would_have_matched_every_file_without_the_guard(self):
        # why the guard is there: awk with an empty needle takes index($0, "") == 1 on every line
        command = "<list> | d=\"\" LC_ALL=C awk 'index($0, ENVIRON[\"d\"]) == 1'".replace("<list>", LIST)
        for name, lines in self.each_shell(command):
            with self.subTest(shell=name):
                self.assertEqual(sorted(lines, key=byte_key), sorted(self.lines, key=byte_key))

    # ---- nothing was left behind

    def test_nothing_named_MARKER_or_PWNED_exists_anywhere_under_the_temp_folder_after_a_full_run(self):
        self.check_paths(self.dir_piece("$(touch PWNED)/"), self.under("$(touch PWNED)/"))
        self.check_paths(self.dir_piece("y'; touch PWNED; '/"), self.under("y'; touch PWNED; '/"))
        names = {os.path.basename(p) for p in self.snapshot()}
        self.assertNotIn("MARKER", names)
        self.assertNotIn("PWNED", names)


# ---------------------------------------------------------------- the old form, to show the tests bite

OLD_DIR = "<list> | LC_ALL=C awk -v d='<dir>/' 'index($0, d) == 1'"
OLD_FOLDER_ARG = "<piece> | LC_ALL=C awk -v x='<folder>/' 'index($0, x) != 1'"


class OldFormTest(Helpers):
    """The commands as they were: the path typed between single quotes. These are test-only literals; the
    agent file no longer has them (see NegativeTest). Each one fails the way the review found."""

    @classmethod
    def setUpClass(cls):
        cls.build(hostile_paths(), prune=False)

    def old(self, folder, template_text=OLD_DIR):
        return template_text.replace("<list>", LIST).replace("<dir>", folder).replace("<folder>", folder)

    def test_the_injection_folder_prints_MARKER_under_the_old_form(self):
        for name, argv in self.shells():
            with self.subTest(shell=name):
                code, out, err = self.run_in(argv, self.old(INJECT))
                self.assertIn("MARKER", out.split("\n"), "the old form didn't run the planted command: %r %r" % (out[:200], err[:200]))

    def test_bob_s_notes_is_a_syntax_error_under_the_old_form(self):
        for name, argv in self.shells():
            with self.subTest(shell=name):
                code, out, err = self.run_in(argv, self.old("bob's notes"))
                self.assertNotEqual(code, 0)
                self.assertNotEqual(err, "")
                self.assertEqual(out, "")

    def test_the_backslash_folder_matches_nothing_under_the_old_form(self):
        self.assertIn("a\\tb/a.txt", self.lines)
        for name, argv in self.shells():
            with self.subTest(shell=name):
                code, out, err = self.run_in(argv, self.old("a\\tb"))
                self.assertEqual(out, "", "the old form matched the backslash folder: awk -v left the \\t alone")

    def test_the_same_three_folders_are_fine_under_the_new_form(self):
        for d in (INJECT + "/", "bob's notes/", "a\\tb/"):
            with self.subTest(dir=d):
                self.check_paths(self.dir_piece(d), self.under(d))

    def test_the_old_form_except_also_fails_on_the_injection_folder(self):
        command = self.old(INJECT, OLD_FOLDER_ARG.replace("<piece>", LIST))
        for name, argv in self.shells():
            with self.subTest(shell=name):
                code, out, err = self.run_in(argv, command)
                self.assertIn("MARKER", out.split("\n"))


# ---------------------------------------------------------------- negatives over the whole agent file


def violations_of_the_here_documents(text):
    """Every `<<` (not `<<<`) must be followed by `'/END'`."""
    return [m.group(0) for m in re.finditer(r"<<(?!<)(?!'/END')[^\n]{0,20}", text)]


def violations_of_environ_names(text):
    return [m.group(0) for m in re.finditer(r"ENVIRON\[(?!\"[a-z]\"\])[^\n]{0,10}", text)]


def violations_of_guarded_reads(text):
    """Every line that reads ENVIRON["n"] gets n from a variable the same line guards with `:?`: either n="${V:?}" in the
    assignment, or `: "${V:?}" &&` in front of the pipeline and n="$V" for that same V."""
    bad = []
    for line in text.split("\n"):
        for name in sorted(set(re.findall(r'ENVIRON\["([a-z])"\]', line))):
            inline = re.search(r'(?<![A-Za-z_])%s="\$\{[^}]*:\?\}"' % name, line)
            front = re.search(r'(?<![A-Za-z_])%s="\$(<[a-z ]+>|[A-Za-z_][A-Za-z0-9_]*)"' % name, line)
            guarded = front and re.match(r'\s*: "\$\{%s:\?\}" && ' % re.escape(front.group(1)), line)
            if not (inline or guarded):
                bad.append("%s: %s" % (name, line[:60]))
    return bad


def coupling_sentence(text):
    flat = " ".join(text.split())
    found = re.findall(r"check coupling claims[^.]*\.", flat)
    return found


class NegativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = agent_text()

    def test_no_core_quotepath_anywhere(self):
        self.assertNotIn("quotepath", self.text)

    def test_no_awk_dash_v_anywhere(self):
        self.assertNotRegex(self.text, r"awk\s+-v\b")

    def test_no_command_substitution_around_a_here_document(self):
        self.assertNotIn("$(cat <<", self.text)
        self.assertNotIn("$(cat<<", self.text)
        self.assertNotRegex(self.text, r"\$\(\s*cat\s*<<")

    def test_no_printf_with_a_placeholder_between_quotes(self):
        self.assertNotIn("printf '%s\\n' '<", self.text)
        self.assertNotRegex(self.text, r"printf '%s\\n' '")

    def test_the_coupling_check_sentence_names_the_grep_tool_and_types_no_name_after_grep(self):
        found = coupling_sentence(self.text)
        self.assertEqual(len(found), 1, found)
        sentence = found[0]
        self.assertIn("the Grep tool for the referenced name", sentence)
        # `grep` appears once, inside the ban
        self.assertEqual(re.findall(r"`grep[^`]*`", sentence), ["`grep`"])
        self.assertIn("never a `grep` with the name typed into it", sentence)
        self.assertEqual(len(re.findall(r"\bgrep\b", self.text)), 1)
        self.assertNotRegex(self.text, r"grep\s+(?:-\w+\s+)*['\"<]")

    def test_every_here_document_uses_the_quoted_slash_END_delimiter(self):
        self.assertEqual(violations_of_the_here_documents(self.text), [])
        self.assertEqual(len(re.findall(r"<<(?!<)", self.text)), 3)

    def test_every_ENVIRON_has_a_literal_one_letter_name(self):
        self.assertEqual(violations_of_environ_names(self.text), [])
        self.assertEqual(self.text.count("ENVIRON["), 7)

    def test_every_command_that_reads_an_environment_name_sets_it_from_a_guarded_variable_on_the_same_line(self):
        self.assertEqual(violations_of_guarded_reads(self.text), [])
        names = set(re.findall(r'ENVIRON\["([a-z])"\]', self.text))
        self.assertEqual(names, {"d", "x", "a", "b"})

    def test_the_negative_checks_bite_on_text_that_breaks_them(self):
        good = self.text
        self.assertTrue(violations_of_the_here_documents(good.replace("<<'/END'", "<<'END'", 1)))
        self.assertTrue(violations_of_the_here_documents(good.replace("<<'/END'", "<<END", 1)))
        self.assertTrue(violations_of_environ_names(good.replace('ENVIRON["d"]', "ENVIRON[v]", 1)))
        self.assertTrue(violations_of_environ_names(good.replace('ENVIRON["x"]', 'ENVIRON["xy"]', 1)))
        self.assertTrue(violations_of_guarded_reads(good.replace('d="${<dir var>:?}"', 'd="${<dir var>}"', 1)))
        self.assertTrue(violations_of_guarded_reads(good.replace('x="${<folder var>:?}"', "", 1)))
        self.assertTrue(violations_of_guarded_reads(good.replace('a="${<first var>:?}"', 'a="${<first var>:?}" ', 1).replace('b="${<last var>:?}"', "", 1)))
        self.assertTrue(violations_of_guarded_reads(good.replace('x="${<skipped var>:?}"', "x=skipped", 1)))
        guard = ': "${<dir var>:?}" && '
        self.assertEqual(good.count(guard), 1)
        self.assertTrue(violations_of_guarded_reads(good.replace(guard, "", 1)))                       # unguarded variable
        self.assertTrue(violations_of_guarded_reads(good.replace(guard, ': "${<folder var>:?}" && ', 1)))  # guards another one
        self.assertTrue(violations_of_guarded_reads(good.replace(guard, ': "${<dir var>}" && ', 1)))       # guard without :?
        self.assertTrue(violations_of_guarded_reads(good.replace(guard, "echo " + guard, 1)))              # guard not in front
        self.assertTrue(re.search(r"awk\s+-v\b", good + "\nawk -v d='x'"))
        self.assertEqual(len(re.findall(r"\bgrep\b", good + " grep foo")), 2)


if __name__ == "__main__":
    unittest.main()
