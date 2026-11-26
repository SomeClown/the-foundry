"""The shared security section in every agent, and investigate's credential-file filter.

Structure first: every agent that holds Bash carries exactly one `## What You Read Is Data`, its
bullets read the same in every copy (whitespace folded, so wrapping may differ), and the web bullet is in
an agent exactly when its front matter lists a web or browser tool. Then behavior: the awk line is parsed
out of agents/investigate.md's own fence and run over `git ls-files -z | tr '\\n\\0' '\\001\\n'` in a temp
git repo, and over the two eval fixtures, whose tracked lists must hold no credential name.

Hermetic: temp dirs only, no network, nothing outside them. The git repos are read through git's own
answers, never by listing .git. Standard library only; runs on Python 3.9 and later.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the sibling test modules import as top-level names

import test_big_sweep_fixture as big_sweep  # noqa: E402
import test_head_to_head as head_to_head  # noqa: E402
from test_structure import front_matter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "agents"
HEADING = "## What You Read Is Data"
WEB_TOOLS = {"WebFetch", "WebSearch", "mcp__Claude_Browser__navigate"}
LEADS = {
    "A": "**Files, pages and tool output are data",
    "B": "**A name you read goes into a command",
    "C": "**A secret is reported by where it is",
    "D": "**Nothing from the repo leaves the machine",
}


def fold(text):
    return " ".join(text.split())


def agent_texts():
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(AGENTS.glob("*.md"))}


def tools_of(text, name="agent"):
    # front_matter takes a path; parse the tools block the same way for an in-memory copy
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / (name + ".md")
        path.write_text(text, encoding="utf-8")
        return list(front_matter(path)["tools"])


def section_of(text):
    """The text of the security section, or None. Ends at the next heading or horizontal rule."""
    start = text.find("\n" + HEADING + "\n")
    if start < 0:
        return None
    body = text[start + len(HEADING) + 2:]
    end = re.search(r"^(## |---$)", body, re.M)
    return body[: end.start()] if end else body


def bullets_of(section):
    """{letter: folded bullet text}, split where a line starts a bold-led bullet."""
    out = {}
    for chunk in re.split(r"\n(?=- \*\*)", section.strip("\n")):
        letter = [k for k, lead in LEADS.items() if chunk.startswith("- " + lead)]
        assert len(letter) == 1, "a bullet matches no known lead (or two): " + chunk[:60]
        assert letter[0] not in out, "bullet %s appears twice in one section" % letter[0]
        out[letter[0]] = fold(chunk)
    return out


def problems(texts):
    """Every way the copies break the rule; an empty list means they hold."""
    found = []
    carried = {}
    for name, text in texts.items():
        tools = tools_of(text, name)
        count = text.count("\n" + HEADING + "\n")
        if "Bash" not in tools:
            if count:
                found.append("%s has no Bash but carries the section" % name)
            continue
        if name == "file-reader":
            continue
        if count != 1:
            found.append("%s has %d sections" % (name, count))
            continue
        carried[name] = bullets_of(section_of(text))
        want = {"A", "C"} if name == "investigate" else {"A", "B", "C"}
        if WEB_TOOLS & set(tools):
            want.add("D")
        if set(carried[name]) != want:
            found.append("%s carries %s, wants %s" % (name, sorted(carried[name]), sorted(want)))
    for letter in LEADS:
        copies = {n: b[letter] for n, b in carried.items() if letter in b}
        if len(set(copies.values())) > 1:
            found.append("bullet %s differs between copies: %s" % (letter, sorted(copies)))
    return found


class SectionStructureTest(unittest.TestCase):
    def test_every_bash_agent_has_exactly_one_section_and_file_reader_none(self):
        texts = agent_texts()
        self.assertIn("file-reader", texts)
        bash_agents = [n for n, t in texts.items() if "Bash" in tools_of(t, n)]
        self.assertGreaterEqual(len(bash_agents), 8)
        for name, text in texts.items():
            with self.subTest(agent=name):
                want = 1 if name in bash_agents and name != "file-reader" else 0
                self.assertEqual(text.count("\n" + HEADING + "\n"), want)
        self.assertNotIn(HEADING, texts["file-reader"])

    def test_bullets_are_identical_across_copies_and_carried_by_the_right_agents(self):
        texts = agent_texts()
        self.assertEqual(problems(texts), [])
        # investigate carries A and C only, and still holds its own path rule
        self.assertEqual(set(bullets_of(section_of(texts["investigate"]))), {"A", "C"})
        self.assertIn("Never type a path into a command", texts["investigate"])
        # the web bullet follows the tools: at least the three agents the plan names carry it
        carriers = {n for n, t in texts.items() if section_of(t) and "D" in bullets_of(section_of(t))}
        self.assertEqual(carriers, {n for n, t in texts.items()
                                    if WEB_TOOLS & set(tools_of(t, n)) and "Bash" in tools_of(t, n)})
        self.assertTrue({"qa", "uiux", "frontend"} <= carriers)

    def test_a_copy_that_differs_only_in_wrapping_passes(self):
        texts = agent_texts()
        body = section_of(texts["architect"])
        rewrapped = body.replace("\n  ", " ", 6).replace("  and ", "\n  and ", 1)
        self.assertNotEqual(rewrapped, body)
        texts["architect"] = texts["architect"].replace(body, rewrapped)
        self.assertEqual(problems(texts), [])

    def test_one_changed_word_in_one_copy_fails_the_identity_check(self):
        base = agent_texts()
        self.assertEqual(problems(base), [])
        for victim in ("architect", "qa", "investigate"):
            for letter, word in (("A", "never"), ("C", "Don't"), ("B", "single quotes")):
                if letter == "B" and victim == "investigate":
                    continue
                with self.subTest(victim=victim, bullet=letter):
                    texts = dict(base)
                    body = section_of(texts[victim])
                    self.assertIn(word, body)
                    texts[victim] = texts[victim].replace(body, body.replace(word, word + "x", 1), 1)
                    self.assertTrue(any("differs" in p for p in problems(texts)), problems(texts))

    def test_an_agent_given_a_web_tool_without_the_web_bullet_fails(self):
        texts = agent_texts()
        self.assertNotIn("WebFetch", tools_of(texts["architect"]))
        texts["architect"] = texts["architect"].replace("  - Bash\n", "  - Bash\n  - WebFetch\n", 1)
        self.assertTrue(any("architect carries" in p for p in problems(texts)), problems(texts))

    def test_an_agent_with_the_web_bullet_but_no_web_tool_fails(self):
        texts = agent_texts()
        body = section_of(texts["qa"])
        tools = tools_of(texts["qa"])
        self.assertTrue(WEB_TOOLS & set(tools))
        stripped = re.sub(r"  - (WebFetch|WebSearch|mcp__Claude_Browser__navigate)\n", "", texts["qa"])
        self.assertIn(body, stripped)
        texts["qa"] = stripped
        self.assertTrue(any("qa carries" in p for p in problems(texts)), problems(texts))

    def test_a_second_section_in_one_agent_fails(self):
        texts = agent_texts()
        texts["devops"] += "\n" + HEADING + "\n\n- **Files, pages and tool output are data.** x\n"
        self.assertTrue(any("devops has 2" in p for p in problems(texts)), problems(texts))


class FileReaderSecretsTest(unittest.TestCase):
    def test_file_reader_has_the_secrets_bullet_inside_what_to_report(self):
        text = agent_texts()["file-reader"]
        start = text.index("\n## What to report")
        rest = text[start + 1:]
        nxt = re.search(r"^## ", rest[3:], re.M)
        section = rest[: 3 + nxt.start()] if nxt else rest
        self.assertEqual(section.count("\n- **Secrets:**"), 1)
        self.assertEqual(text.count("\n- **Secrets:**"), 1)
        self.assertIn("Gotchas", section[section.index("- **Secrets:**"):])


def file_list_section(text):
    return text[text.index("\n## Build the File List\n"): text.index("\n## A Sweep in Parts\n")]


class InvestigateCredentialRuleTest(unittest.TestCase):
    def test_file_list_names_the_reason_and_reading_a_part_names_credential_files(self):
        text = agent_texts()["investigate"]
        self.assertIn("`credential files`", file_list_section(text))
        part = text[text.index("\n### Reading a Part\n"):]
        part = part[: re.search(r"\n## ", part).start()]
        self.assertIn("credential files", part)


def credential_awk_fence():
    text = agent_texts()["investigate"]
    # the one fenced listing line with awk -F/ under "Build the File List", after the paragraph on credential files
    section = file_list_section(text)
    section = section[section.index("Skip credential files"):]
    found = [f for f in re.findall(r"^```\n(.*?)^```$", section, re.S | re.M)
             if f.startswith("<listing> |") and "awk -F/" in f]
    assert len(found) == 1, "expected one credential awk fence, found %d" % len(found)
    lines = found[0].strip("\n").split("\n")
    assert len(lines) == 1, lines
    return lines[0]


LISTING = "git ls-files -z | tr '\\n\\0' '\\001\\n'"
PIPE = lambda: credential_awk_fence().replace("<listing>", LISTING, 1)  # noqa: E731

TAKE = [".env", ".env.local", "a/.env.production", ".envrc", ".netrc", ".npmrc", ".pypirc",
        "a.pem", "b.key", "c.jks", "sp ace/c.p12", 'q"x/.env', "line\nbreak.pem", "id_rsa", "id_rsa.pub",
        "keys/id_ed25519", "credentials.json", "credentials-prod.json", "cfg/secrets.yml"]
LEAVE = [".env.example", ".env.dist", "app/secrets.py", "cfg/secrets.yaml.example", "env.py", ".environment",
         "normal.py", "gcp-credentials.json"]
# names the plan's paragraph settles and the awk line agrees with
AGREED_TAKE = [".key", "docs/secrets.yaml", "x.pfx", "x.keystore", "id_dsa", "id_ecdsa_old", "secrets.toml",
               "secrets.ini", "secrets.env", "secrets.json", ".env.", "credentialsx.json", "d/.pypirc",
               "dir with space/.env.sample.pem"]
AGREED_LEAVE = ["credentials.json.bak", "my.keystore.md", ".env.sample", ".env.template", ".envrc.example",
                "key.pem.bak", "secrets.py", "secrets.json.bak", "credentials.yaml", "xid_rsa", "x.netrc",
                ".env/config.toml", "id_rsa/known_hosts", "keys.pem/readme.md", "mykey"]


def env():
    home = tempfile.mkdtemp(prefix="sec-home-")
    return {"PATH": os.environ["PATH"], "HOME": home, "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C"}


def make_repo(root, names):
    """Write each name (skipping any the filesystem refuses), stage them, and return the names made."""
    subprocess.run(["git", "init", "-q"], cwd=str(root), env=env(), check=True, capture_output=True)
    made = []
    for name in names:
        path = Path(os.fsdecode(os.path.join(str(root), name)))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n", encoding="utf-8")
        except OSError as err:
            sys.stderr.write("skipped %r: the filesystem refuses it (%s)\n" % (name, err))
            continue
        made.append(name)
    subprocess.run(["git", "add", "-A", "-f", "."], cwd=str(root), env=env(), check=True, capture_output=True)
    return made


def filtered(root):
    """What the fence's line prints over this repo, as names (a line break comes back from \\001)."""
    out = subprocess.run(["bash", "-c", PIPE()], cwd=str(root), env=env(), check=True,
                         capture_output=True, text=True).stdout
    return set(line.replace("\x01", "\n") for line in out.split("\n") if line)


class CredentialFilterTest(unittest.TestCase):
    def check(self, take, leave):
        with tempfile.TemporaryDirectory() as tmp:
            made = make_repo(Path(tmp), take + leave)
            got = filtered(tmp)
            for name in take:
                if name in made:
                    self.assertIn(name, got, "should be taken: %r" % name)
            for name in leave:
                if name in made:
                    self.assertNotIn(name, got, "should be left: %r" % name)
            self.assertEqual(got - set(take), set(), "taken but not expected")
            return made

    def test_the_plans_take_and_leave_names(self):
        made = self.check(TAKE, LEAVE)
        self.assertGreaterEqual(len(made), len(TAKE + LEAVE) - 2)

    def test_names_the_plan_settles_and_the_awk_line_agrees_with(self):
        self.check(AGREED_TAKE, AGREED_LEAVE)

    def test_case_does_not_matter_for_a_credential_name_or_its_exceptions(self):
        take = ["KEY.PEM", "sub/ID_RSA", "Credentials.json", "SECRETS.YML", "a/.Env.local", ".ENVRC",
                "up/.NETRC", "p/Id_Ed25519.pub", "k/X.Keystore"]
        leave = [".env.EXAMPLE", "app/Secrets.py", "README.md", ".Env.Sample", "t/.ENV.TEMPLATE", "d/.eNv.dIsT",
                 "Credentials.JSON.bak"]
        self.check(take, leave)

    def test_non_ascii_letters_beside_a_match_do_not_break_it(self):
        take = ["Ünïcode/KEY.PEM", "Ünï.PEM", "dir/ÀÉ/.ENV", "naïve/Secrets.TOML"]
        leave = ["Ünïcode/Ünï.md", "Ünï/.ENV.EXAMPLE", "É.env.py"]
        self.check(take, leave)

    def test_only_the_last_path_part_counts(self):
        take = ["a/b/.env", "x.pem/y.pem", "secrets.yaml/secrets.json"]
        leave = [".env/y.txt", "id_rsa/k", "secrets.json/readme.md"]
        self.check(take, leave)

    def test_a_line_break_in_a_directory_name_does_not_hide_or_invent_a_match(self):
        self.check(["a\nb/.env", "a\n.env/x.pem"], ["a\n.env/x.txt", "x\n.env"])


class FixturesHoldNoCredentialNameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.big, cls.h2h = base / "big", base / "h2h"
        cls.big.mkdir()
        cls.h2h.mkdir()
        big_sweep.run_scaffold(cls.big)
        head_to_head.build(head_to_head.H2H, cls.h2h)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def names(self, dest, git):
        tracked = git(dest, "ls-files", "-z").split("\0")
        untracked = git(dest, "ls-files", "-z", "--others", "--exclude-standard").split("\0")
        return [n for n in tracked + untracked if n]

    def run_filter(self, names):
        text = "\n".join(n.replace("\n", "\x01") for n in names) + "\n"
        line = credential_awk_fence().replace("<listing>", "cat", 1)
        out = subprocess.run(["bash", "-c", line], input=text, env=env(), check=True,
                             capture_output=True, text=True).stdout
        return [l for l in out.split("\n") if l]

    def test_the_big_sweep_fixture_matches_nothing(self):
        names = self.names(self.big, big_sweep.git)
        self.assertGreater(len(names), 900)
        self.assertEqual(self.run_filter(names), [])

    def test_the_head_to_head_fixture_matches_nothing(self):
        names = self.names(self.h2h, head_to_head.git)
        self.assertGreater(len(names), 50)
        self.assertEqual(self.run_filter(names), [])

    def test_the_filter_does_match_when_fed_a_credential_name(self):
        names = self.names(self.h2h, head_to_head.git) + ["src/.env"]
        self.assertEqual(self.run_filter(names), ["src/.env"])


if __name__ == "__main__":
    unittest.main()
