#!/usr/bin/env bash
# Builds the big-sweep fixture: a fictional toll-road operator ("tollway") with a CLI called twctl.
# 990 tracked files, one of them a flat folder of 610 rules, sized so a whole-repo read can't fit
# in one report. Self-contained on purpose: everything is generated from the Python below, with a
# fixed seed, so two builds are byte-identical.
#
#   scaffold.sh                  build the full fixture in the current directory
#   scaffold.sh --subset N       build a reduced repo of exactly N files a reader would read: the five
#                                root text files plus the first N-5 eligible paths in byte order, with
#                                no lock file, binaries, vendored folder or untracked files
#   scaffold.sh --emit-key PATH  write the answer key to PATH and build nothing
#
# The key never goes into the workspace; sync_big_sweep.py asks for it with --emit-key.
SUBSET="450"
set -euo pipefail

IFS= read -r -d '' GEN <<'PYEOF' || true
import json
import os
import random
import re
import sys

SEED = 20261123
AREAS = ["accounts", "billing", "plazas", "trips"]

NOUNS = ("toll lane booth gantry plaza transponder tag receipt invoice ledger account balance deposit refund fine waiver "
         "permit vehicle plate axle class trip exit entry ramp span bridge tunnel camera sensor loop queue shift cashier "
         "vault audit rate tier peak holiday discount carpool commuter fleet trailer weight height speed incident closure "
         "detour cone patrol tow lien notice dispute statement payment batch export import sync").split()
VERBS = ("hold release reassign void approve escalate reconcile recalc archive flag split merge export preview refresh "
         "retry cancel confirm defer expedite audit notify quote verify tag lock unlock reopen assign rebook "
         "reprice trace purge redact sweep rollup stage freeze thaw").split()
PUBLIC_COUNTS = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 2, 3, 5]
PW = "zone weight rate window limit tier band offset margin factor bucket span share floor cap".split()
SEGS = ["gateway", "rules", "zones", "web", "jobs"]

GOTCHAS = [
    ("_HOLD_DAYS", "90", "Keep the 90-day hold: settlement files arrive late (see {ref}); shortening it double-charges."),
    ("_RETRY_CEILING", "4", "Four attempts is the ceiling, since the gateway locks the account on the fifth ({ref})."),
    ("_ROUND_TO", "3", "Round to three places: the clearing house rejects totals that differ by a cent, per {ref}."),
    ("_BATCH_LIMIT", "250", "Past 250 rows the plaza feed silently truncates. {ref} has the details."),
    ("_CUTOFF_HOUR", "17", "Cutoff is 17:00 plaza time, not UTC; mixing them double-billed a morning rush ({ref})."),
    ("_GRACE_SECONDS", "14", "Grace is 14 seconds, not 15: the gantry clock runs a second fast ({ref})."),
    ("_MAX_AXLES", "9", "The class table stops making sense beyond nine axles; see {ref}."),
    ("_SCAN_DEDUP_SECONDS", "7", "Seven seconds of dedup absorbs the double read from old transponders, {ref}."),
    ("_DEFAULT_CLASS", '"C2"', "Any default class but C2 mis-charges motorcycles at the tunnel; rolled back once already under {ref}."),
    ("_PAGE_SIZE", "50", "Fifty per page: the partner portal times out on larger ones ({ref})."),
    ("_STALE_AFTER_HOURS", "36", "Weekend feeds lag a day and a half, so stale means 36 hours, not 24. Shipped as {ref}."),
    ("_WEIGHT_TOLERANCE", "0.02", "Two percent matches the scale vendor's spec sheet ({ref})."),
    ("_LOCK_TIMEOUT", "12", "Twelve seconds, no more: a longer lock stalls the nightly close behind it ({ref})."),
    ("_MIN_REFUND_CENTS", "150", "Under 150 cents the refund costs more to send than it returns. Context in {ref}."),
    ("_PEAK_FACTOR", "1.35", "The congestion data gives 1.35; a flat rate undercharges ({ref})."),
    ("_QUOTE_TTL_MINUTES", "45", "Quotes live 45 minutes because the transponder vendor re-prices on the hour, see {ref}."),
]

# One regex per reference shape; every match anywhere in the tree must be a planted token.
CODE_SHAPES = {
    "tracker key": r"\bTWY-\d{4}\b",
    "ticket number": r"ticket \d{4}\b",
    "change number": r"\bCHG\d{7}\b",
    "issue number": r"#\d{5}\b",
    "runbook section": r"runbook section \d+\.\d+",
}

SENTENCES = [
    "The {d} area keeps its own models and views, and talks to the other areas through services.",
    "Every {n} record carries a reference, a status, and an amount.",
    "Operators work from the command line first; the web views serve the partner portal.",
    "Changes to the {d} area go through review by its owner before they ship.",
    "Nothing in the {d} area reads another area's tables directly.",
    "Nightly jobs for the {d} area run after the plaza files land.",
    "The glossary is the shared vocabulary; use it in comments and in commit messages.",
    "Money is handled in the core money module, never as bare floats in a view.",
    "A {n} that looks wrong in production is raised with the area's owner, not patched in place.",
    "Dates are stored in UTC and shown in the plaza's local time.",
    "Retries go through the shared retry helper so the backoff stays consistent.",
    "Tests live next to nothing: they sit in the tests folder and import the area they cover.",
]
CHANGES = [
    "Tightened the {n} check in the {d} area.",
    "Moved the {n} lookup behind the shared cache.",
    "Fixed a rounding slip in the {n} total.",
    "Added a nightly report on {n} activity.",
    "Dropped the old {n} export now that the partner portal reads the API.",
    "Made the {n} view faster for large plazas.",
]
AREA_LINES = [
    "api", "cli", "docs", "jobs", "rules", "scripts", "tests", "web", "zones",
]


def plural(word):
    return word + ("es" if word.endswith(("s", "x", "ch", "sh")) else "s")


def helper(rng, size, used):
    """A private helper of exactly `size` lines: a data table or a small function."""
    assert size >= 6, size
    while True:
        name = "_%s_%s_%d" % (rng.choice(PW), rng.choice(PW), rng.randint(1, 99))
        if name not in used:
            used.add(name)
            break
    if rng.random() < 0.4:
        out = ["", "", name.upper() + "_TABLE = {"]
        for i in range(size - 4):
            out.append('    "%s_%d": %s,' % (rng.choice(PW), i, rng.randint(1, 900)))
        out.append("}")
    else:
        out = ["", "", "def %s(value, factor=%s):" % (name, round(rng.random() * 3 + 0.5, 2))]
        for i in range(size - 4):
            if i == 0:
                out.append("    t0 = value * factor")
            else:
                out.append("    t%d = t%d * %s + %d" % (i, i - 1, rng.randint(2, 9), rng.randint(1, 40)))
        out.append("    return t%d" % (size - 5))
    assert len(out) == size
    return out


def fill(rng, lines, upto, used):
    assert len(lines) <= upto, (len(lines), upto)
    while len(lines) < upto:
        gap = upto - len(lines)
        size = gap if gap <= 24 else rng.randint(8, 24)
        if 0 < gap - size < 6:
            size = gap
        lines.extend(helper(rng, size, used))
    assert len(lines) == upto


def pad_normal(rng, lines, used, low=30, high=120):
    target = max(len(lines), rng.randint(low, high))
    if 0 < target - len(lines) < 6:
        target = len(lines) + 6
    assert target <= 120, (target, lines[:2])
    fill(rng, lines, target, used)
    return lines


class World:
    def __init__(self):
        self.rng = random.Random(SEED)
        self.tokens = []
        self.routes = []
        self.commands = []
        self.codes = []
        self.facts = []
        self.decoys = []
        self.plants = {}
        self.files = {}
        self.untracked = {}
        self.vendor = []
        self.gotcha_n = 0
        self.ordinary = {}
        self.publics = {}

    # ---- tokens -----------------------------------------------------------

    def fresh(self, token):
        return all(token not in t and t not in token for t in self.tokens)

    def new_route(self, seg):
        rng = self.rng
        while True:
            noun = rng.choice(NOUNS)
            verb = rng.choice(VERBS)
            token = "/v3/%s/%s/%s" % (seg, plural(noun), verb)
            if self.fresh(token):
                self.tokens.append(token)
                self.routes.append(token)
                return {"kind": "route", "token": token, "noun": noun, "verb": verb, "seg": seg}

    def new_command(self):
        rng = self.rng
        while True:
            noun = rng.choice(NOUNS)
            verb = rng.choice(VERBS)
            token = "twctl %s-%s" % (verb, noun)
            if self.fresh(token):
                self.tokens.append(token)
                self.commands.append(token)
                return {"kind": "command", "token": token, "noun": noun, "verb": verb}

    def new_gotcha(self):
        rng = self.rng
        shape = self.gotcha_n % 5
        while True:
            if shape == 0:
                ref = "TWY-%04d" % rng.randint(1000, 9999)
            elif shape == 1:
                ref = "ticket %04d" % rng.randint(1000, 9999)
            elif shape == 2:
                ref = "CHG%07d" % rng.randint(1000000, 9999999)
            elif shape == 3:
                ref = "#%05d" % rng.randint(10000, 99999)
            else:
                ref = "runbook section %d.%d" % (rng.randint(1, 9), rng.randint(1, 9))
            if self.fresh(ref):
                break
        self.tokens.append(ref)
        self.codes.append(ref)
        name, value, text = GOTCHAS[self.gotcha_n % len(GOTCHAS)]
        self.gotcha_n += 1
        return {"kind": "gotcha", "token": ref, "name": name, "value": value, "text": text.format(ref=ref)}

    def new(self, kind, seg=None):
        if kind == "route":
            return self.new_route(seg)
        if kind == "command":
            return self.new_command()
        return self.new_gotcha()

    def plant(self, path, kind, seg=None):
        spec = self.new(kind, seg)
        self.plants.setdefault(path, []).append(spec)
        self.facts.append(dict(spec, path=path))

    def decoy(self, path, kind, why, seg=None):
        spec = self.new(kind, seg)
        self.plants.setdefault(path, []).append(spec)
        self.decoys.append({"why": why, "path": path, "token": spec["token"]})

    # ---- layout -----------------------------------------------------------

    def layout(self):
        rng = self.rng
        py = []
        py += ["api/__init__.py", "api/app.py", "api/auth.py", "api/errors.py"]
        api_words = {}
        for d in AREAS:
            words = rng.sample(NOUNS, 39)
            api_words[d] = words
            py.append("api/%s/__init__.py" % d)
            py += ["api/%s/%s.py" % (d, w) for w in words]
        cli_words = rng.sample(NOUNS, 34)
        py += ["cli/__init__.py", "cli/main.py"] + ["cli/cmd_%s.py" % w for w in cli_words]
        py += ["jobs/__init__.py", "jobs/runner.py", "jobs/schedule.py", "jobs/retry.py"]
        night = rng.sample(NOUNS, 24)
        py += ["jobs/nightly/%s_close.py" % w for w in night]
        word_of = {}
        for i in range(1, 611):
            word_of[i] = rng.choice(NOUNS)
            py.append("rules/r%04d_%s.py" % (i, word_of[i]))
        py += ["scripts/%s.py" % s for s in "bootstrap seed_data export_ledger rotate_logs check_gantry backfill dump_schema smoke".split()]
        test_words = rng.sample(NOUNS, 36)
        py += ["tests/test_%s.py" % w for w in test_words]
        py += ["web/__init__.py", "web/app.py", "web/forms.py", "web/session.py", "web/static.py", "web/templates.py"]
        view_words = rng.sample(NOUNS, 20)
        py += ["web/views/%s.py" % w for w in view_words]
        vendor_words = rng.sample(NOUNS, 40)
        self.vendor = ["web/vendor/%slib.py" % w for w in vendor_words]
        py += self.vendor
        py += ["zones/z%02d_%s.py" % (i, rng.choice(NOUNS)) for i in range(1, 21)]
        py += ["main.py"]
        self.py = py
        self.docs = ["docs/%s.md" % n for n in
                     "architecture operations glossary onboarding tolling-rules zones billing-cycle incident-review releases testing style faq".split()]
        self.root_text = ["CHANGELOG.md", "Makefile", "README.md", "pyproject.toml"]
        self.assets = ["web/assets/%s.bin" % n for n in ("sprite", "font", "route-map", "badge-sheet")]

        # planted facts
        self.plant("main.py", "gotcha")
        self.plant("api/app.py", "route", "gateway")
        for d in AREAS:
            a, b = rng.sample(["api/%s/%s.py" % (d, w) for w in api_words[d]], 2)
            self.plant(a, "route", d)
            self.plant(b, "gotcha")
        for path in sorted(rng.sample(["cli/cmd_%s.py" % w for w in cli_words], 2)):
            self.plant(path, "command")
        self.plant("jobs/runner.py", "command")
        self.plant(rng.choice(["jobs/nightly/%s_close.py" % w for w in night]), "gotcha")
        for k, rank in enumerate([int(round(i * 609 / 11.0)) + 1 for i in range(12)]):
            self.plant("rules/r%04d_%s.py" % (rank, word_of[rank]), ["gotcha", "route", "command"][k % 3], "rules")
        self.plant("scripts/export_ledger.py", "command")
        self.plant(rng.choice(["tests/test_%s.py" % w for w in test_words]), "gotcha")
        self.plant(rng.choice(["web/views/%s.py" % w for w in view_words]), "route", "web")
        self.plant("web/session.py", "gotcha")
        zone_files = sorted(p for p in py if p.startswith("zones/"))
        self.plant(zone_files[3], "route", "zones")
        self.plant(zone_files[10], "command")
        self.plant(zone_files[19], "gotcha")

        # decoys
        self.decoy(self.vendor[7], "route", "vendored", "legacy")
        self.decoy(self.vendor[29], "gotcha", "vendored")
        self.decoy("rules/r9999_draft.py", "route", "untracked", "drafts")
        self.decoy("notes/scratch.md", "gotcha", "untracked")
        self.decoy("zones/zz_todo.txt", "command", "untracked")

        self.inventory()

    def spread(self, pool, total, cap, kind, segs):
        """Hand `total` ordinary routes or commands to files drawn from `pool`, unevenly, at most `cap` to a file."""
        rng = self.rng
        given = {}
        for _i in range(total):
            while True:
                path = rng.choice(pool)
                if given.get(path, 0) < cap:
                    break
            given[path] = given.get(path, 0) + 1
            self.ordinary.setdefault(path, []).append(self.new(kind, segs(path)))

    def inventory(self):
        """Ordinary public inventory: routes in api/ and web/views/, commands in cli/, scripts/ and jobs/, plain public functions in every code folder."""
        rng = self.rng
        api = [p for p in self.py if p.startswith("api/") and not p.endswith("__init__.py")]
        views = [p for p in self.py if p.startswith("web/views/")]
        self.spread(api, 90, 4, "route", lambda p: p.split("/")[1] if p.count("/") == 2 else "gateway")
        self.spread(views, 39, 3, "route", lambda p: "web")
        cmds = [p for p in self.py if p.startswith(("cli/cmd_", "scripts/"))] * 3
        cmds += [p for p in self.py if p.startswith("jobs/") and not p.endswith("__init__.py")]
        self.spread(cmds, 193, 8, "command", lambda p: None)
        late_rules = [p for p in self.py if p.startswith("rules/r") and int(p[7:11]) > 310]
        self.spread(late_rules, 60, 2, "route", lambda p: "rules")
        self.spread(late_rules, 90, 2, "command", lambda p: None)
        for path in self.py:
            if not path.startswith("web/vendor/"):
                self.publics[path] = rng.choice(PUBLIC_COUNTS)

    def public_block(self, rng, used):
        while True:
            name = "%s_%s" % (rng.choice(VERBS), rng.choice(NOUNS))
            if name not in used:
                used.add(name)
                break
        out = ["", "", "def %s(record, limit=%d):" % (name, rng.randint(2, 99)),
               '    """Return the %s figure for one %s."""' % (rng.choice(NOUNS), rng.choice(NOUNS)), "    t0 = record * limit"]
        for i in range(1, rng.randint(2, 5)):
            out.append("    t%d = t%d * %d + %d" % (i, i - 1, rng.randint(2, 9), rng.randint(1, 40)))
        out.append("    return t%d" % (len(out) - 5))
        return out

    # ---- rendering --------------------------------------------------------

    def block(self, spec):
        kind = spec["kind"]
        if kind == "route":
            return ["", "", '@route("%s")' % spec["token"], "def %s_%s(request):" % (spec["verb"], spec["noun"]),
                    '    return {"route": "%s", "ok": True}' % spec["seg"]]
        if kind == "command":
            return ["", "", '@command("%s")' % spec["token"], "def %s_%s(args):" % (spec["verb"], spec["noun"]), "    return 0"]
        return ["", "", "# " + spec["text"], spec["name"] + " = " + spec["value"]]

    def render_py(self, path):
        rng = self.rng
        stem = path.rsplit("/", 1)[-1][:-3]
        title = stem.replace("_", " ")
        lines = ['"""%s: %s"""' % (title.capitalize(), rng.choice(SENTENCES).format(d=rng.choice(AREAS), n=rng.choice(NOUNS))), ""]
        specs = self.plants.get(path, [])
        ordinary = self.ordinary.get(path, [])
        kinds = set(s["kind"] for s in specs + ordinary)
        if "route" in kinds:
            lines.append("from tollway.web import route")
        if "command" in kinds:
            lines.append("from tollway.cli import command")
        if kinds:
            lines.append("")
        used = set("%s_%s" % (s["verb"], s["noun"]) for s in specs + ordinary if s["kind"] != "gotcha")
        blocks = [self.block(s) for s in specs + ordinary]
        room = 100 - len(lines) - sum(len(b) for b in blocks)
        for _i in range(self.publics.get(path, 0)):
            block = self.public_block(rng, used)
            if len(block) <= room:
                room -= len(block)
                blocks.append(block)
        rng.shuffle(blocks)
        pre = rng.choice([0, 0, 6, 12, 20, 30])
        if pre and pre <= room:
            fill(rng, lines, len(lines) + pre, set())
        for block in blocks:
            lines.extend(block)
        return pad_normal(rng, lines, set())

    def render_vendor(self, path):
        rng = self.rng
        name = path.rsplit("/", 1)[-1][:-3]
        lines = ["# Vendored copy of %s 1.%d.%d. Do not edit; update by re-vendoring." % (name, rng.randint(0, 9), rng.randint(0, 9))]
        for spec in self.plants.get(path, []):
            lines.extend(self.block(spec))
        fill(rng, lines, max(len(lines), 1) + 6 * rng.randint(6, 12), set())
        return lines

    def render_md(self, path):
        rng = self.rng
        name = path[5:-3]
        lines = ["# " + name.replace("-", " ").capitalize(), ""]
        while len(lines) < 32:
            d = rng.choice(AREAS + ["rules", "zones", "jobs"])
            lines.append("## " + d.capitalize())
            lines.append("")
            for _j in range(rng.randint(4, 6)):
                lines.append(rng.choice(SENTENCES).format(d=d, n=rng.choice(NOUNS)))
            lines.append("")
        return lines

    def render_readme(self):
        lines = ["# tollway", "", "A small toll-road operations service: accounts, billing, plazas, trips, and the rule engine behind the rates.",
                 "", "The command line is `twctl`; ask it for `--help` to see what it can do. HTTP routes live under `/v3/`.", "", "## Layout", ""]
        notes = {"api": "the HTTP application and its four areas", "cli": "the command line, one module per command",
                 "docs": "architecture, operations, and the glossary", "jobs": "the scheduler and the nightly close jobs",
                 "rules": "one module per rating rule, numbered", "scripts": "one-off operator scripts",
                 "tests": "unittest modules, one per concept", "web": "the partner portal: views, forms, and vendored assets",
                 "zones": "the rate zones and their boundaries"}
        for d in AREA_LINES:
            lines.append("- `%s/`: %s" % (d, notes[d]))
        lines += ["", "## Working on it", "",
                  "Python 3.9 or newer. Install with pip, run the tests with unittest, and keep each area's code inside its own folder.",
                  "The vendored folder under the web area is third-party code: don't edit it. The lock file is rebuilt by the tooling.",
                  "Read the glossary before naming anything new.", "",
                  "## Conventions", "", "Each area owns its models, views, services, and commands, and nothing else.",
                  "Shared behavior goes in the core modules, not into a second copy inside an area.",
                  "Tests import the area they cover and never reach into another one.",
                  "Rating rules are numbered; a new rule takes the next free number and never renumbers an old one.",
                  "Zone files are numbered the same way and are read in order."]
        return lines

    def render_changelog(self):
        rng = self.rng
        lines = ["# Changelog", ""]
        for minor in range(9, -1, -1):
            lines += ["## 3.%d.0" % minor, ""]
            for _j in range(3):
                lines.append("- " + rng.choice(CHANGES).format(d=rng.choice(AREAS), n=rng.choice(NOUNS)))
            lines.append("")
        return lines

    def render_makefile(self):
        lines = [".PHONY: test lint run " + " ".join("check-" + d for d in AREA_LINES), "",
                 "test:", "\tpython3 -m unittest discover -s tests", "", "lint:", "\tpython3 -m compileall -q .", "",
                 "run:", "\tpython3 main.py", ""]
        for d in AREA_LINES:
            lines += ["check-%s:" % d, "\tpython3 -m compileall -q %s" % d, ""]
        return lines

    def render_pyproject(self):
        rng = self.rng
        lines = ["[project]", 'name = "tollway"', 'version = "3.9.0"', 'description = "Toll-road operations service and command line"',
                 'requires-python = ">=3.9"', "dependencies = [", '    "flask>=3.0",', '    "click>=8.1",', "]", "",
                 "[project.scripts]", 'twctl = "cli.main:main"', "", "[tool.ruff]", "line-length = 100", "",
                 "[tool.tollway.zones]", "# multipliers per rate zone, read by the rules"]
        for i in range(20):
            lines.append("%s_%d = %s" % (rng.choice(PW), i, round(rng.random() * 2 + 0.5, 2)))
        return lines

    def render_lock(self):
        rng = self.rng
        lock = []
        for pkg in "flask click werkzeug jinja2 itsdangerous markupsafe blinker colorama".split():
            lock += ["[[package]]", 'name = "%s"' % pkg, 'version = "%d.%d.%d"' % (rng.randint(1, 4), rng.randint(0, 9), rng.randint(0, 9)),
                     'hash = "%032x"' % rng.getrandbits(128), ""]
        return lock

    def render_all(self):
        rng = self.rng
        for path in self.py:
            if path in self.vendor:
                self.files[path] = self.render_vendor(path)
            else:
                self.files[path] = self.render_py(path)
        for path in self.docs:
            self.files[path] = self.render_md(path)
        self.files["README.md"] = self.render_readme()
        self.files["CHANGELOG.md"] = self.render_changelog()
        self.files["Makefile"] = self.render_makefile()
        self.files["pyproject.toml"] = self.render_pyproject()
        self.files["poetry.lock"] = self.render_lock()
        # untracked: decoys only
        for path in ("rules/r9999_draft.py", "notes/scratch.md", "zones/zz_todo.txt"):
            specs = self.plants[path]
            tok = specs[0]["token"]
            if path.endswith(".py"):
                lines = ['"""Draft rule, not committed yet."""', "", "from tollway.web import route"] + self.block(specs[0])
            elif path.endswith(".md"):
                lines = ["# Scratch", "", "Ask ops about the settlement spreadsheet.", self.block(specs[0])[2][2:], "Check whether the plazas still use the old transponders."]
            else:
                lines = ["TODO: wire up %s once the zone table is final." % tok, "Check the zone boundaries against the survey."]
            self.untracked[path] = lines

    def binaries(self):
        rng = self.rng
        out = {}
        for i, path in enumerate(self.assets):
            out[path] = b"\x00TWB%d" % (i + 1) + bytes(rng.randrange(256) for _ in range(384 + 128 * i))
        return out


def eligible(path):
    return not (path == "poetry.lock" or path.startswith("web/vendor/") or path.endswith(".bin"))


def build():
    w = World()
    w.layout()
    w.render_all()
    blobs = {}
    for path, lines in w.files.items():
        blobs[path] = ("\n".join(lines) + "\n").encode("utf-8")
    blobs.update(w.binaries())
    untracked = {path: ("\n".join(lines) + "\n").encode("utf-8") for path, lines in w.untracked.items()}
    # checks that would make a paid run worthless
    assert len(blobs) == 990, len(blobs)
    assert len([p for p in blobs if not p.startswith("web/vendor/")]) == 950
    assert len([p for p in blobs if eligible(p)]) == 945
    assert len(w.facts) == 33 and len(w.decoys) == 5
    for path, blob in blobs.items():
        if path.endswith(".bin"):
            continue
        text = blob.decode("utf-8")
        n = text.count("\n")
        assert 30 <= n <= 120, (path, n)
        assert not re.search(r"^[ \t]*pa" + r"ss([ \t]|$)", text, re.M), path
        if path.endswith(".py"):
            compile(text, path, "exec")
    for path, blob in untracked.items():
        text = blob.decode("utf-8")
        assert not re.search(r"^[ \t]*pa" + r"ss([ \t]|$)", text, re.M), path
        if path.endswith(".py"):
            compile(text, path, "exec")
    everything = "\n".join(b.decode("utf-8", "replace") for b in list(blobs.values()) + list(untracked.values()))
    for tok in w.tokens:
        assert everything.count(tok) == 1, (tok, everything.count(tok))
    for m in re.findall(r"/v3/[a-z][a-z0-9/_-]*", everything):
        assert m in w.routes, m
    for m in re.findall(r"twctl [a-z][a-z0-9-]*", everything):
        assert m in w.commands, m
    for shape, pattern in CODE_SHAPES.items():
        found = re.findall(pattern, everything)
        assert 0 < len(found), shape
        assert all(m in w.codes for m in found), (shape, found)
    facts = []
    for i, f in enumerate(sorted(w.facts, key=lambda x: x["path"]), 1):
        where = [j + 1 for j, text in enumerate(w.files[f["path"]]) if f["token"] in text]
        assert len(where) == 1, (f["token"], where)
        assert eligible(f["path"]), f["path"]
        facts.append({"id": "f%02d" % i, "kind": f["kind"], "path": f["path"], "line": where[0], "token": f["token"]})
    decoys = []
    for i, d in enumerate(sorted(w.decoys, key=lambda x: x["path"]), 1):
        assert (d["path"] in untracked) == (d["why"] == "untracked"), d
        assert (d["path"].startswith("web/vendor/")) == (d["why"] == "vendored"), d
        decoys.append({"id": "d%d" % i, "why": d["why"], "path": d["path"], "token": d["token"]})
    key = {
        "facts": facts,
        "decoys": decoys,
        "layout": {
            "tracked": len(blobs),
            "after_whole_folder_skips": len([p for p in blobs if not p.startswith("web/vendor/")]),
            "skipped_whole": {"web/vendor/": len([p for p in blobs if p.startswith("web/vendor/")])},
            "file_skips": {"lock": 1, "binary": len([p for p in blobs if p.endswith(".bin")])},
            "untracked": sorted(untracked),
        },
    }
    return blobs, untracked, key


def main(argv):
    blobs, untracked, key = build()
    if argv[:1] == ["emit-key"]:
        with open(argv[1], "w", encoding="utf-8") as fh:
            fh.write(json.dumps(key, indent=1) + "\n")
        return 0
    subset = argv[1] if argv[:1] == ["build"] and len(argv) > 1 else ""
    if subset:
        n = int(subset)
        root = ["CHANGELOG.md", "Makefile", "README.md", "main.py", "pyproject.toml"]
        rest = sorted(p for p in blobs if "/" in p and eligible(p))
        assert 5 <= n <= 5 + len(rest), n
        keep = set(root + rest[:n - 5])
        blobs = {p: b for p, b in blobs.items() if p in keep}
        untracked = {}
        assert len(blobs) == n, (len(blobs), n)
    for group in (blobs, untracked):
        for path, blob in group.items():
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(blob)
    return 0


sys.exit(main(sys.argv[1:]))
PYEOF

if [ "${1:-}" = "--emit-key" ]; then
  [ -n "${2:-}" ] || { echo "usage: scaffold.sh --emit-key PATH" >&2; exit 2; }
  python3 -c "$GEN" emit-key "$2"
  exit 0
fi
if [ "${1:-}" = "--subset" ]; then
  case "${2:-}" in
    ''|*[!0-9]*) echo "usage: scaffold.sh --subset N" >&2; exit 2 ;;
  esac
  SUBSET="$2"
fi

real_git=""
for candidate in "$(xcrun --find git 2>/dev/null || true)" /Library/Developer/CommandLineTools/usr/bin/git "$(command -v git)"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then real_git="$candidate"; break; fi
done
[ -n "$real_git" ] || { echo "no git found" >&2; exit 1; }
if [ -n "$(ls -A)" ]; then
  echo "scaffold.sh: $(pwd) isn't empty; run it in an empty folder" >&2
  exit 1
fi
if "$real_git" rev-parse --verify -q HEAD >/dev/null 2>&1; then
  echo "scaffold.sh: $(pwd) is inside a git repo that has commits; run it in an empty folder outside any repo" >&2
  exit 1
fi
mkdir -p bin
printf '#!/bin/sh\nexec "%s" "$@"\n' "$real_git" > bin/git
chmod +x bin/git
# maintenance.auto=false: otherwise git starts a detached repack that keeps writing into .git after this script returns
G="./bin/git -c maintenance.auto=false -c user.name=Owner -c user.email=owner@example.com -c commit.gpgsign=false"

python3 -c "$GEN" build "$SUBSET"
$G init -q -b main
mkdir -p .git/info
printf 'bin/\nparts/\n' >> .git/info/exclude
$G add -A -- . ':!notes' ':!rules/r9999_draft.py' ':!zones/zz_todo.txt'
GIT_AUTHOR_DATE="2026-11-23T09:00:00 +0000" GIT_COMMITTER_DATE="2026-11-23T09:00:00 +0000" $G commit -qm "tollway 3.9.0"
