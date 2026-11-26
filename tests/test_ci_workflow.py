"""The GitHub Actions workflow (.github/workflows/ci.yml) keeps the promises the plan makes about it.

Standard library only, no YAML parser: each check is a function of the file's text that returns a list
of problems (empty means good). The real workflow must pass every check, and each check has mutation
tests: a broken copy of the text, made by one edit, that the check must reject. A mutation test also
proves the edit took, so a drifted fixture string can't turn a check into a silent pass.

Whole-line comments are ignored by every check, so a comment that names a forbidden thing is fine and
the same thing as a key is not. Nothing here reads outside the repo, and nothing runs the workflow.
Runs on Python 3.9 and later.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"

EVAL = "ev" + "al"  # built from pieces, so no file spells out the plugin subcommand it forbids

EXPECTED_TOP_KEYS = ["name", "on", "permissions", "concurrency", "defaults", "jobs"]
FORBIDDEN = [
    r"pull_request_target", r"workflow_run", r"\bsecrets\b", r"github\.event\.", r"GITHUB_TOKEN",
    r"claude\s+-p\b", r"claude\s+--print\b", r"plugin\s+" + EVAL, r"toJSON\(\s*github", r"github\.head_ref",
]
USES = re.compile(r"^\s*(?:-\s+)?uses:\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)@([0-9a-f]{40})(?:\s+#.*)?$")


def code_lines(text):
    return [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def block_after(lines, header_re, min_indent=0):
    """The lines indented deeper than the first line matching header_re (and the header's index)."""
    for i, line in enumerate(lines):
        if re.match(header_re, line):
            base = indent_of(line)
            body = []
            for nxt in lines[i + 1:]:
                if indent_of(nxt) <= base:
                    break
                body.append(nxt)
            return i, body
    return None, []


def jobs_of(text):
    """{job name: its lines}, taking the jobs: block's children at indent 2."""
    _, body = block_after(code_lines(text), r"^jobs:\s*$")
    jobs, current = {}, None
    for line in body:
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m:
            current = jobs.setdefault(m.group(1), [])
        elif current is not None:
            current.append(line)
    return jobs


def steps_of(job_lines):
    steps = []
    for line in job_lines:
        if re.match(r"^      - ", line):
            steps.append([line])
        elif steps:
            steps[-1].append(line)
    return steps


def run_scope_lines(lines):
    """Lines that belong to a run: key (its own line and the deeper lines after it)."""
    out, base = [], None
    for line in lines:
        if base is not None and indent_of(line) > base:
            out.append(line)
            continue
        base = None
        m = re.match(r"^(\s*)(?:-\s+)?run:", line)
        if m:
            base = len(m.group(1))
            out.append(line)
    return out


# ---- the checks: text -> list of problems -------------------------------------------------------

def check_no_tabs(text):
    return ["tab on line %d" % (i + 1) for i, l in enumerate(text.splitlines()) if "\t" in l]


def check_top_level_keys(text):
    keys = [m.group(1) for l in code_lines(text) for m in [re.match(r"^([A-Za-z_][\w-]*):", l)] if m]
    return [] if keys == EXPECTED_TOP_KEYS else ["top-level keys are %s" % keys]


def check_permissions(text):
    lines = code_lines(text)
    problems = []
    all_permissions = [l for l in lines if re.match(r"^\s*(?:-\s+)?permissions\s*:", l)]
    if len(all_permissions) != 1:
        problems.append("%d permissions: lines, want exactly one" % len(all_permissions))
    i, body = block_after(lines, r"^permissions:")
    if i is None or lines[i].rstrip() != "permissions:":
        problems.append("no top-level permissions: block")
    elif body != ["  contents: read"]:
        problems.append("permissions block is %s" % body)
    for l in lines:
        if re.search(r":\s*[\"']?(write|write-all|read-all)\b", l):
            problems.append("a write or read-all permission: %s" % l.strip())
    return problems


def check_on_block(text):
    lines = code_lines(text)
    i, body = block_after(lines, r"^on:")
    if i is None or lines[i].rstrip() != "on:":
        return ["no on: block"]
    kids = [(m.group(1), m.group(2).strip()) for l in body for m in [re.match(r"^  ([\w-]+):(.*)$", l)] if m]
    problems = []
    if [k for k, _ in kids] != ["push", "pull_request"]:
        problems.append("on: children are %s" % [k for k, _ in kids])
    deeper = {}
    current = None
    for l in body:
        m = re.match(r"^  ([\w-]+):", l)
        if m:
            current = m.group(1)
            deeper[current] = []
        elif current:
            deeper[current].append(l)
    if deeper.get("push") != ["    branches: [main]"]:
        problems.append("push block is %s" % deeper.get("push"))
    if deeper.get("pull_request") != []:
        problems.append("pull_request block is %s" % deeper.get("pull_request"))
    if any(rest for _, rest in kids):
        problems.append("an on: child has an inline value: %s" % kids)
    return problems


def check_forbidden_words(text):
    problems = []
    for line in code_lines(text):
        for pattern in FORBIDDEN:
            if re.search(pattern, line):
                problems.append("%s: %s" % (pattern, line.strip()))
    return problems


def check_no_expressions_in_run_blocks(text):
    return ["expression in a run block: %s" % l.strip() for l in run_scope_lines(code_lines(text)) if "${{" in l]


def check_every_action_is_pinned_to_a_full_commit(text):
    uses = [l for l in code_lines(text) if re.match(r"^\s*(?:-\s+)?uses:", l)]
    problems = ["not pinned to 40 hex: %s" % l.strip() for l in uses if not USES.match(l)]
    if len(uses) < 3:
        problems.append("only %d uses: lines" % len(uses))
    return problems


def check_checkouts_keep_no_credentials(text):
    problems, seen = [], 0
    for name, job in jobs_of(text).items():
        for step in steps_of(job):
            if any("uses: actions/checkout@" in l for l in step):
                seen += 1
                if "          persist-credentials: false" not in step:
                    problems.append("job %s: a checkout without persist-credentials: false" % name)
                if any(re.search(r"persist-credentials:\s+(?!false\b)\S", l) for l in step):
                    problems.append("job %s: persist-credentials set to something else" % name)
    if seen == 0:
        problems.append("no checkout step")
    return problems


def check_tests_job_fetches_the_whole_history(text):
    job = jobs_of(text).get("tests")
    if job is None:
        return ["no tests job"]
    checkouts = [s for s in steps_of(job) if any("uses: actions/checkout@" in l for l in s)]
    if len(checkouts) != 1:
        return ["tests job has %d checkout steps" % len(checkouts)]
    return [] if "          fetch-depth: 0" in checkouts[0] else ["checkout in tests job lacks fetch-depth: 0"]


def check_every_job_has_a_timeout_and_a_macos_runner(text):
    jobs = jobs_of(text)
    problems = [] if jobs else ["no jobs"]
    for name, job in jobs.items():
        if not any(re.fullmatch(r"    timeout-minutes: [1-9]\d*", l) for l in job):
            problems.append("job %s has no timeout-minutes" % name)
        if not any(re.fullmatch(r"    runs-on: macos-[\w.-]+", l) for l in job):
            problems.append("job %s does not run on macos-" % name)
    return problems


def check_the_gate_commands_are_all_run(text):
    body = "\n".join(code_lines(text))
    return ["missing %s" % want for want in ("tests/run_tests.py", "/usr/bin/python3", "unittest discover -s tests")
            if want not in body]


def check_the_cli_install_is_pinned(text):
    for step in (s for job in jobs_of(text).values() for s in steps_of(job)):
        if step[0].strip() == "- name: Install the Claude Code CLI":
            body = "\n".join(step)
            if re.search(r"@anthropic-ai/claude-code@\d+\.\d+\.\d+(?![\w.-])", body):
                return []
            return ["the install step names no exact version"]
    return ["no step named exactly 'Install the Claude Code CLI'"]


def contributing_validate_lines():
    lines = [l.strip() for l in CONTRIBUTING.read_text(encoding="utf-8").splitlines()]
    return [l for l in lines if l.startswith("claude plugin validate") and "$" not in l]


def check_the_validate_commands_match_contributing(text):
    want = contributing_validate_lines()
    have = {re.sub(r"\s*\|\|\s*status=1$", "", l.strip()) for l in code_lines(text)}
    problems = ["CONTRIBUTING lists %d validate lines, want 3" % len(want)] if len(want) != 3 else []
    problems += ["workflow lacks the line: %s" % w for w in want if w not in have]
    return problems


CHECKS = {
    "no tabs": check_no_tabs,
    "top-level keys": check_top_level_keys,
    "permissions": check_permissions,
    "on block": check_on_block,
    "forbidden words": check_forbidden_words,
    "no expressions in run blocks": check_no_expressions_in_run_blocks,
    "pinned actions": check_every_action_is_pinned_to_a_full_commit,
    "no credentials kept": check_checkouts_keep_no_credentials,
    "whole history": check_tests_job_fetches_the_whole_history,
    "timeouts and runners": check_every_job_has_a_timeout_and_a_macos_runner,
    "gate commands": check_the_gate_commands_are_all_run,
    "pinned cli install": check_the_cli_install_is_pinned,
    "validate lines": check_the_validate_commands_match_contributing,
}


def replace_once(text, old, new):
    assert text.count(old) == 1, "mutation target %r found %d times" % (old, text.count(old))
    return text.replace(old, new)


class RealWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_the_workflow_file_exists_and_is_not_trivially_small(self):
        self.assertGreater(len(self.text.splitlines()), 100)

    def test_every_check_passes_on_the_real_workflow(self):
        for name, check in CHECKS.items():
            with self.subTest(check=name):
                self.assertEqual(check(self.text), [])

    def test_the_jobs_are_the_two_the_plan_names(self):
        self.assertEqual(sorted(jobs_of(self.text)), ["tests", "validate"])

    def test_every_workflow_file_in_the_folder_is_this_one(self):
        self.assertEqual(sorted(p.name for p in WORKFLOW.parent.iterdir()), ["ci.yml"])


class MutationTest(unittest.TestCase):
    """Each broken copy must be rejected by the check it targets."""

    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def rejects(self, check_name, mutated):
        self.assertNotEqual(mutated, self.text)
        self.assertNotEqual(CHECKS[check_name](mutated), [], "%s accepted the broken copy" % check_name)

    def accepts(self, check_name, mutated):
        self.assertNotEqual(mutated, self.text)
        self.assertEqual(CHECKS[check_name](mutated), [])

    # no tabs
    def test_a_tab_is_rejected(self):
        self.rejects("no tabs", replace_once(self.text, "\n    timeout-minutes: 30", "\n\ttimeout-minutes: 30"))

    # top-level keys
    def test_an_extra_top_level_key_is_rejected(self):
        self.rejects("top-level keys", replace_once(self.text, "\ndefaults:\n", '\nenv:\n  X: "1"\ndefaults:\n'))

    def test_a_missing_top_level_key_is_rejected(self):
        self.rejects("top-level keys", replace_once(self.text, "defaults:\n  run:\n    shell: bash\n\n", ""))

    # permissions
    def test_a_write_permission_is_rejected(self):
        self.rejects("permissions", replace_once(self.text, "  contents: read\n", "  contents: write\n"))

    def test_a_broader_permission_block_is_rejected(self):
        self.rejects("permissions", replace_once(self.text, "  contents: read\n", "  contents: read\n  id-token: write\n"))

    def test_a_second_read_only_permission_child_is_rejected(self):
        self.rejects("permissions", replace_once(self.text, "  contents: read\n", "  contents: read\n  issues: read\n"))

    def test_write_all_is_rejected(self):
        self.rejects("permissions", replace_once(self.text, "permissions:\n  contents: read\n", "permissions: write-all\n"))

    def test_a_missing_permissions_block_is_rejected(self):
        self.rejects("permissions", replace_once(self.text, "permissions:\n  contents: read\n\n", ""))

    def test_a_second_permissions_block_inside_a_job_is_rejected_even_when_it_is_read_only(self):
        lines = self.text.splitlines(keepends=True)
        at = [i for i, l in enumerate(lines) if l.startswith("    timeout-minutes: 15")]
        self.assertEqual(len(at), 1)
        lines.insert(at[0], "    permissions:\n      contents: read\n")
        self.rejects("permissions", "".join(lines))

    def test_a_job_level_write_permission_is_rejected(self):
        lines = self.text.splitlines(keepends=True)
        at = [i for i, l in enumerate(lines) if l.startswith("    timeout-minutes: 30")]
        lines.insert(at[0], "    permissions:\n      contents: write\n")
        self.rejects("permissions", "".join(lines))

    # the on: block
    def test_pull_request_target_as_a_key_is_rejected_by_the_on_block_and_the_forbidden_words(self):
        mutated = replace_once(self.text, "\n  pull_request:\n", "\n  pull_request_target:\n")
        self.rejects("on block", mutated)
        self.rejects("forbidden words", mutated)

    def test_pull_request_target_in_the_flow_form_is_rejected(self):
        mutated = replace_once(self.text, "on:\n  push:\n    branches: [main]\n  pull_request:\n", "on: [push, pull_request_target]\n")
        self.rejects("on block", mutated)
        self.rejects("forbidden words", mutated)

    def test_pull_request_target_in_a_whole_line_comment_is_not_a_problem(self):
        mutated = replace_once(self.text, "name: CI\n", "name: CI\n# never use pull_request_target here\n")
        self.accepts("forbidden words", mutated)
        self.accepts("on block", mutated)

    def test_a_third_trigger_is_rejected(self):
        self.rejects("on block", replace_once(self.text, "  pull_request:\n", "  pull_request:\n  workflow_dispatch:\n"))

    def test_a_schedule_trigger_is_rejected(self):
        self.rejects("on block", replace_once(self.text, "  pull_request:\n", "  pull_request:\n  schedule:\n    - cron: '0 0 * * *'\n"))

    def test_more_branches_are_rejected(self):
        self.rejects("on block", replace_once(self.text, "branches: [main]", "branches: [main, dev]"))

    def test_a_types_filter_on_pull_request_is_rejected(self):
        self.rejects("on block", replace_once(self.text, "  pull_request:\n", "  pull_request:\n    types: [opened]\n"))

    def test_a_workflow_run_trigger_is_rejected(self):
        mutated = replace_once(self.text, "  pull_request:\n", "  pull_request:\n  workflow_run:\n    workflows: [x]\n")
        self.rejects("on block", mutated)
        self.rejects("forbidden words", mutated)

    # forbidden words
    def test_a_secret_is_rejected(self):
        self.rejects("forbidden words", replace_once(self.text, '      HOW: ${{ matrix.how }}\n', '      HOW: ${{ matrix.how }}\n      TOKEN: ${{ secrets.TOKEN }}\n'))

    def test_a_secret_by_index_is_rejected(self):
        self.rejects("forbidden words", replace_once(self.text, '      HOW: ${{ matrix.how }}\n', "      TOKEN: ${{ secrets['T'] }}\n      HOW: ${{ matrix.how }}\n"))

    def test_the_github_token_is_rejected(self):
        self.rejects("forbidden words", replace_once(self.text, '      HOW: ${{ matrix.how }}\n', '      HOW: ${{ matrix.how }}\n      T: $GITHUB_TOKEN\n'))

    def test_a_model_session_is_rejected(self):
        self.rejects("forbidden words", replace_once(self.text, "          claude --version\n", '          claude --version\n          claude -p "hi"\n'))

    def test_the_plugin_eval_subcommand_is_rejected(self):
        self.rejects("forbidden words", replace_once(self.text, "          claude --version\n", "          claude plugin " + EVAL + " .\n"))

    def test_a_github_event_value_echoed_in_a_run_line_is_rejected(self):
        mutated = replace_once(self.text, "          claude --version\n", '          echo "${{ github.event.pull_request.title }}"\n          claude --version\n')
        self.rejects("forbidden words", mutated)
        self.rejects("no expressions in run blocks", mutated)

    def test_a_branch_name_echoed_in_a_run_line_is_rejected(self):
        mutated = replace_once(self.text, "          claude --version\n", '          echo "${{ github.head_ref }}"\n          claude --version\n')
        self.rejects("forbidden words", mutated)
        self.rejects("no expressions in run blocks", mutated)

    def test_the_whole_github_context_dumped_is_rejected(self):
        mutated = replace_once(self.text, "          claude --version\n", "          echo '${{ toJSON(github) }}'\n          claude --version\n")
        self.rejects("forbidden words", mutated)
        self.rejects("no expressions in run blocks", mutated)

    def test_a_hash_inside_a_quoted_echo_does_not_hide_the_expression(self):
        mutated = replace_once(self.text, "          claude --version\n", '          echo "# ${{ github.event.issue.body }}"\n          claude --version\n')
        self.rejects("forbidden words", mutated)

    def test_an_expression_in_a_one_line_run_is_rejected_by_the_run_block_check(self):
        mutated = replace_once(self.text, "      - name: Validate the plugin\n", '      - name: Echo\n        run: echo "${{ matrix.label }}"\n      - name: Validate the plugin\n')
        self.rejects("no expressions in run blocks", mutated)

    # pinned actions
    def test_an_action_pinned_to_a_tag_is_rejected(self):
        self.rejects("pinned actions", replace_once(self.text, "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1", "actions/setup-node@v4"))

    def test_an_action_pinned_to_a_branch_is_rejected(self):
        self.rejects("pinned actions", replace_once(self.text, "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1", "actions/setup-node@main"))

    def test_an_action_pinned_to_a_short_hash_is_rejected(self):
        self.rejects("pinned actions", replace_once(self.text, "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1", "actions/setup-node@949feb2"))

    def test_a_hash_one_character_short_or_long_is_rejected(self):
        full = "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1"
        self.rejects("pinned actions", replace_once(self.text, full, full[:-1]))
        self.rejects("pinned actions", replace_once(self.text, full, full + "a"))

    def test_a_hash_with_a_non_hex_character_is_rejected(self):
        self.rejects("pinned actions", replace_once(self.text, "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1", "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15cz"))

    def test_an_unpinned_extra_action_is_rejected(self):
        self.rejects("pinned actions", replace_once(self.text, "      - name: Validate the plugin\n", "      - uses: some/action@v1\n      - name: Validate the plugin\n"))

    def test_a_local_or_docker_action_is_rejected(self):
        self.rejects("pinned actions", replace_once(self.text, "      - name: Validate the plugin\n", "      - uses: ./local-action\n      - name: Validate the plugin\n"))
        self.rejects("pinned actions", replace_once(self.text, "      - name: Validate the plugin\n", "      - uses: docker://alpine:3\n      - name: Validate the plugin\n"))

    def test_a_trailing_version_comment_after_the_hash_is_fine(self):
        self.accepts("pinned actions", replace_once(self.text, "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0", "actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1"))

    # checkout credentials and history
    def test_a_checkout_without_persist_credentials_false_is_rejected(self):
        self.rejects("no credentials kept", replace_once(self.text, "        with:\n          persist-credentials: false\n", ""))

    def test_persist_credentials_true_is_rejected(self):
        self.rejects("no credentials kept", replace_once(self.text, "        with:\n          persist-credentials: false\n", "        with:\n          persist-credentials: true\n"))

    def test_persist_credentials_moved_to_a_different_step_is_rejected(self):
        mutated = replace_once(self.text, "        with:\n          persist-credentials: false\n", "")
        mutated = replace_once(mutated, "      - name: Set up Node for the CLI\n", "      - name: Set up Node for the CLI\n        with:\n          persist-credentials: false\n")
        self.rejects("no credentials kept", mutated)

    def test_a_missing_fetch_depth_is_rejected(self):
        self.rejects("whole history", replace_once(self.text, "          fetch-depth: 0\n", ""))

    def test_a_shallow_fetch_depth_is_rejected(self):
        self.rejects("whole history", replace_once(self.text, "fetch-depth: 0", "fetch-depth: 1"))

    # timeouts and runners
    def test_a_job_without_a_timeout_is_rejected(self):
        self.rejects("timeouts and runners", replace_once(self.text, "    timeout-minutes: 15\n", ""))

    def test_a_zero_timeout_is_rejected(self):
        self.rejects("timeouts and runners", replace_once(self.text, "timeout-minutes: 15", "timeout-minutes: 0"))

    def test_a_linux_runner_is_rejected(self):
        self.rejects("timeouts and runners", replace_once(self.text, "runs-on: macos-15\n    timeout-minutes: 15", "runs-on: ubuntu-latest\n    timeout-minutes: 15"))

    def test_a_self_hosted_runner_is_rejected(self):
        self.rejects("timeouts and runners", replace_once(self.text, "runs-on: macos-15\n    timeout-minutes: 30", "runs-on: self-hosted\n    timeout-minutes: 30"))

    # the commands
    def test_dropping_the_runner_command_is_rejected(self):
        self.rejects("gate commands", replace_once(self.text, '"$PY" tests/run_tests.py', '"$PY" -m unittest discover -s tests -q'))

    def test_dropping_the_single_process_discover_is_rejected(self):
        self.rejects("gate commands", replace_once(self.text, '"$PY" -m unittest discover -s tests -q', '"$PY" tests/run_tests.py'))

    def test_dropping_the_stock_python_is_rejected(self):
        self.rejects("gate commands", self.text.replace("/usr/bin/python3", "python3"))

    def test_the_commands_named_only_in_a_comment_do_not_count(self):
        mutated = replace_once(self.text, '"$PY" tests/run_tests.py', "echo skipped").replace("name: CI\n", "name: CI\n# tests/run_tests.py\n", 1)
        self.rejects("gate commands", mutated)

    # the CLI install
    def test_an_install_step_with_a_different_name_is_rejected(self):
        self.rejects("pinned cli install", replace_once(self.text, "name: Install the Claude Code CLI", "name: Install the CLI"))

    def test_an_install_step_with_a_slightly_different_name_is_rejected(self):
        self.rejects("pinned cli install", replace_once(self.text, "name: Install the Claude Code CLI", "name: Install the Claude Code CLI now"))

    def test_an_unpinned_install_is_rejected(self):
        self.rejects("pinned cli install", replace_once(self.text, "claude-code@2.1.318", "claude-code"))

    def test_a_latest_install_is_rejected(self):
        self.rejects("pinned cli install", replace_once(self.text, "claude-code@2.1.318", "claude-code@latest"))

    def test_a_range_install_is_rejected(self):
        self.rejects("pinned cli install", replace_once(self.text, "claude-code@2.1.318", "claude-code@^2.1.0"))
        self.rejects("pinned cli install", replace_once(self.text, "claude-code@2.1.318", "claude-code@2"))

    def test_a_partial_version_with_a_tail_is_rejected(self):
        self.rejects("pinned cli install", replace_once(self.text, "claude-code@2.1.318", "claude-code@2.1.318-beta.1"))

    # the validate lines
    def test_dropping_each_validate_line_is_rejected(self):
        for old in ("          claude plugin validate --strict . || status=1\n",
                    "          claude plugin validate --strict .claude-plugin/plugin.json || status=1\n",
                    "          claude plugin validate --profile directory . || status=1\n"):
            with self.subTest(dropped=old.strip()):
                self.rejects("validate lines", replace_once(self.text, old, ""))

    def test_a_validate_line_that_only_starts_like_the_real_one_is_rejected(self):
        self.rejects("validate lines", replace_once(self.text, "claude plugin validate --profile directory . || status=1", "claude plugin validate --profile directory .. || status=1"))

    def test_a_validate_line_that_only_appears_in_a_comment_is_rejected(self):
        mutated = replace_once(self.text, "          claude plugin validate --profile directory . || status=1\n", "          # claude plugin validate --profile directory .\n")
        self.rejects("validate lines", mutated)


class ContributingLinesTest(unittest.TestCase):
    def test_the_process_block_holds_the_three_validate_lines_the_workflow_must_match(self):
        self.assertEqual(contributing_validate_lines(), [
            "claude plugin validate --strict .",
            "claude plugin validate --strict .claude-plugin/plugin.json",
            "claude plugin validate --profile directory .",
        ])


if __name__ == "__main__":
    unittest.main()
