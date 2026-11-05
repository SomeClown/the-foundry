#!/usr/bin/env bash
# Builds the head-to-head fixture: a fictional freight service with a CLI called fxctl.
# Self-contained on purpose: everything is generated from the Python below, with a
# fixed seed, so two builds are byte-identical.
#
#   scaffold.sh                  build the fixture in the current directory
#   scaffold.sh --emit-key PATH  write the answer key to PATH and build nothing
#
# The key never goes into the workspace; sync_case.py asks for it with --emit-key.
set -euo pipefail

IFS= read -r -d '' GEN <<'PYEOF' || true
import json
import os
import random
import re
import sys

TQ = '"' * 3
SEED = 20261105

DOMAINS = {
    "billing": "invoice ledger tariff surcharge credit dispute remittance statement accrual rebate payer charge penalty deposit voucher levy".split(),
    "carriers": "carrier lane contract bid manifest handoff pickup rateshop tender quote haul backhaul liner bondsman slot permit".split(),
    "customs": "declaration broker duty hscode inspection clearance entry origin waiver quota seizure embargo drawback consul lien filing".split(),
    "dispatch": "driver shift assignment roster callout window yard gate appointment handover escort relay standby checkin turnaround board".split(),
    "fleet": "truck trailer frame gps fueling tire odometer service warranty plate recall garage mileage hoist lease axle".split(),
    "routing": "route stop leg detour corridor toll geofence waypoint bridge ferry ramp pathway grid zone hub".split(),
    "settlement": "settlement netting clearing payout holdback escrow reserve chargeback writeoff subledger recon cutoff batch float drawdown".split(),
    "tracking": "shipment event scan milestone beacon eta exception proof delivery signature photo geotag ping state trail".split(),
    "warehouse": "bin aisle pallet dock putaway picklist count wave tote rack cage label inventory staging carton".split(),
}
BIG = {"billing": 1100, "carriers": 1250, "customs": 1400, "settlement": 1640, "tracking": 1900, "warehouse": 2400}

VERBS = ("hold release reassign void approve escalate reconcile recalc archive flag split merge export preview refresh "
         "retry cancel confirm defer expedite audit notify quote sync verify tag lock unlock reopen assign rebook "
         "reprice trace purge redact sweep rollup stage freeze thaw").split()
PW = "zone weight rate window limit tier band offset margin factor bucket span share floor cap".split()
CORE_STEMS = "config db errors logging_setup money dates ids retry units http".split()
SKIP_PATHS = [
    "poetry.lock",
    "vendor/tinyjson/__init__.py", "vendor/tinyjson/decoder.py", "vendor/tinyjson/encoder.py",
    "generated/manifest_pb2.py", "generated/carrier_client.py",
    "data/rates_2026.csv", "fixtures/manifest_sample.json", "fixtures/zones.json",
    "assets/label-template.bin", "assets/sort-belt.bin",
]

GOTCHAS = [
    ("_HOLD_DAYS", "90", "Keep the 90-day hold: settlement files arrive late (see PDX-7712); shortening it double-charges.", "PDX-7712"),
    ("_RETRY_CEILING", "4", "Four attempts is the ceiling, since the gateway locks the account on the fifth (LOG-2290).", "LOG-2290"),
    ("_ROUND_TO", "3", "Round to three places: customs rejects totals that differ by a cent, per OPS-5412.", "OPS-5412"),
    ("_BATCH_LIMIT", "250", "Past 250 rows the broker endpoint silently truncates. FRT-3180 has the details.", "FRT-3180"),
    ("_CUTOFF_HOUR", "17", "Cutoff is 17:00 depot time, not UTC; mixing them double-dispatched a morning load (ticket 4127).", "ticket 4127"),
    ("_GRACE_MINUTES", "14", "Grace is 14 minutes, not 15: the telematics clock runs a minute fast (ticket 6093).", "ticket 6093"),
    ("_MAX_LEGS", "9", "The planner stops converging beyond nine legs; see ticket 7716.", "ticket 7716"),
    ("_SCAN_DEDUP_SECONDS", "7", "Seven seconds of dedup absorbs the double scan from old handhelds, ticket 5841.", "ticket 5841"),
    ("_TAX_FALLBACK_REGION", '"NA-EAST"', "Any default region but NA-EAST mis-taxes border crossings; rolled back once already under CHG0041872.", "CHG0041872"),
    ("_PAGE_SIZE", "50", "Fifty per page: the partner portal times out on larger ones (change CHG0052107).", "CHG0052107"),
    ("_STALE_AFTER_HOURS", "36", "Weekend feeds lag a day and a half, so stale means 36 hours, not 24. Shipped as CHG0047730.", "CHG0047730"),
    ("_WEIGHT_TOLERANCE", "0.02", "Two percent matches the scale vendor's spec sheet (CHG0060915).", "CHG0060915"),
    ("_LOCK_TIMEOUT", "12", "Twelve seconds, no more: a longer lock stalls the nightly sweep behind it (#88213).", "#88213"),
    ("_MIN_PALLET_KG", "18", "Under 18 kg this ships as parcel, since pallet rates lose money there. Context in #90417.", "#90417"),
    ("_DETOUR_FACTOR", "1.35", "The toll-road data gives 1.35; a straight-line figure undercharges (#77305).", "#77305"),
    ("_QUOTE_TTL_MINUTES", "45", "Quotes live 45 minutes because the carrier re-prices on the hour, see #81644.", "#81644"),
    ("_DOCK_BUFFER", "20", "Leave 20 minutes at the dock; Monday trucks arrive early and block the gate (runbook section 6.3).", "runbook section 6.3"),
    ("_EPOCH_OFFSET", "3600", "The feed stamps local time with no zone, and this undoes it (see runbook section 2.8).", "runbook section 2.8"),
    ("_BOND_CAP", "75000", "Bonds above 75,000 need a second signature, so this is a hard cap (runbook section 9.1).", "runbook section 9.1"),
    ("_SPLIT_SHARE", "0.4", "The partner contract fixes forty percent for the first leg (runbook section 4.5).", "runbook section 4.5"),
    ("_EXPORT_WINDOW_DAYS", "5", "Five-day window: the portal drops older requests, as we learned in the Tacoma cutover.", "the Tacoma cutover"),
    ("_RECALL_LOOKBACK", "120", "Look back 120 days; maker notices trickle in for months. We found out during the Reno freeze.", "the Reno freeze"),
    ("_SIGNATURE_BYTES", "4096", "Signatures over 4096 bytes crash the label printer firmware, as the Boise reprint showed.", "the Boise reprint"),
    ("_FUEL_INDEX_LAG", "2", "Use the fuel index from two weeks back; the current one is revised later, which bit us in the Laredo surcharge mixup.", "the Laredo surcharge mixup"),
    ("_PING_INTERVAL", "30", "Thirty-second pings: faster polling got us throttled by the beacon vendor (vendor case 5530281).", "vendor case 5530281"),
    ("_SWEEP_ORDER", '"oldest-first"', "Sweep oldest-first or the escrow balance goes negative mid-run, per bank case 6104472.", "bank case 6104472"),
    ("_ZONE_FALLBACK", "7", "Zone 7 is the catch-all, so unknown postcodes land there instead of raising (carrier case 4471093).", "carrier case 4471093"),
    ("_CHARGEBACK_DAYS", "45", "The card network allows 45 days for chargebacks (portal case 3382650).", "portal case 3382650"),
]

# One regex per reference shape that has one; the named events have none.
CODE_SHAPES = {
    "tracker key": r"\b[A-Z]{3}-\d{4}\b",
    "ticket number": r"ticket \d+",
    "change number": r"\bCHG\d+\b",
    "issue number": r"#\d{5}",
    "runbook section": r"runbook section \d+\.\d+",
    "case number": r"\b[a-z]+ case \d{7}\b",
}

SENTENCES = [
    "The {d} area keeps its own models and views, and talks to the other areas through services.",
    "Every {n} record carries a reference, a status, and an amount.",
    "Operators work from the command line first; the web views serve the partner portal.",
    "Changes to the {d} area go through review by its owner before they ship.",
    "Nothing in the {d} area reads another area's tables directly.",
    "Nightly jobs for the {d} area run after the carrier files land.",
    "The glossary is the shared vocabulary; use it in comments and in commit messages.",
    "Money is handled in the core money module, never as bare floats in a view.",
    "A {n} that looks wrong in production is raised with the area's owner, not patched in place.",
    "Dates are stored in UTC and shown in the depot's local time.",
    "Retries go through the shared retry helper so the backoff stays consistent.",
    "Tests live next to nothing: they sit in the tests folder and import the area they cover.",
]


def plural(word):
    return word + ("es" if word.endswith(("s", "x", "ch", "sh")) else "s")


def camel(word):
    return "".join(p.capitalize() for p in word.split("_"))


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


def pad_normal(rng, lines, used, low=34, high=140):
    target = max(len(lines), rng.randint(low, high))
    if 0 < target - len(lines) < 6:
        target = len(lines) + 6
    assert target <= 150, (target, lines[:2])
    fill(rng, lines, target, used)
    return lines


def gotcha_block(entry):
    name, value, text, _token = entry
    return ["", "", "# " + text, name + " = " + value]


class World:
    def __init__(self):
        self.rng = random.Random(SEED)
        self.specs = {}
        self.facts = {}
        self.routes = []
        self.commands = []
        self.codes = []
        self.decoys = []
        self.codepool = []
        self.files = {}

    def add(self, path, role, **kw):
        assert path not in self.specs, path
        spec = {"path": path, "role": role, "plant": []}
        spec.update(kw)
        self.specs[path] = spec

    # ---- registries -------------------------------------------------------

    def new_route(self, d, n, taken):
        """A fresh route for a file's noun: (path, function name, verb)."""
        rng = self.rng
        while True:
            verb = rng.choice(VERBS)
            if verb in taken:
                continue
            taken.add(verb)
            path = "/v2/%s/%s/%s" % (d, plural(n), verb)
            self.routes.append(path)
            return path, "%s_%s" % (verb, n), verb

    def new_command(self, n, taken):
        rng = self.rng
        while True:
            verb = rng.choice(VERBS)
            if verb in taken:
                continue
            taken.add(verb)
            name = "%s-%s" % (verb, n)
            self.commands.append("fxctl " + name)
            return name, "%s_%s" % (verb, n), verb

    # ---- role generators --------------------------------------------------

    def handler(self, fn, c, verb, n, decorator=None):
        out = []
        if decorator:
            out.append(decorator)
        out.append("def %s():" % fn)
        out.append("    %s%s the %s.%s" % (TQ, verb.capitalize(), n, TQ))
        out.append('    record = %s(ref=request.args.get("ref", ""))' % c)
        out.append('    return jsonify({"ref": record.ref, "action": "%s"})' % verb)
        return out

    def gen_view(self, spec):
        rng = self.rng
        d, n, mn = spec["domain"], spec["noun"], spec["model"]
        c = camel(mn)
        style = spec["style"]
        taken, used = set(), set()
        routes = []
        for _ in range(rng.randint(2, 3)):
            routes.append(self.new_route(d, n, taken) + (None,))
        for fid in spec["plant"]:
            if self.facts[fid]["kind"] == "route":
                r = self.new_route(d, n, taken)
                self.facts[fid]["token"] = r[0]
                routes.append(r + (fid,))
        rng.shuffle(routes)
        lines = [TQ + camel(n) + " views for the " + d + " area." + TQ, "", "from flask import %sjsonify, request" % ("Blueprint, " if style == 0 else ""),
                 "", "from %s.%s import %s" % (d, mn, c)]
        if style == 0:
            lines += ["", 'bp = Blueprint("%s_%s", __name__)' % (d, n)]
        for path, fn, verb, _fid in routes:
            methods = '["GET"]' if verb in ("preview", "export", "trace", "audit", "quote", "verify") else '["POST"]'
            lines += ["", ""]
            deco = ('@bp.route("%s", methods=%s)' % (path, methods)) if style == 0 else None
            lines += self.handler(fn, c, verb, n, deco)
            used.add(fn)
        if style == 1:
            lines += ["", "", "def register(app):"]
            for path, fn, verb, _fid in routes:
                methods = '["GET"]' if verb in ("preview", "export", "trace", "audit", "quote", "verify") else '["POST"]'
                lines.append('    app.add_url_rule("%s", view_func=%s, methods=%s)' % (path, fn, methods))
        elif style == 2:
            lines += ["", "", "ROUTE_TABLE = ["]
            for path, fn, verb, _fid in routes:
                methods = '["GET"]' if verb in ("preview", "export", "trace", "audit", "quote", "verify") else '["POST"]'
                lines.append('    ("%s", %s, %s),' % (path, fn, methods))
            lines += ["]", "", "", "def register(app):", "    for path, view, methods in ROUTE_TABLE:",
                      "        app.add_url_rule(path, view_func=view, methods=methods)"]
        if spec.get("decoy"):
            host_path, fn, verb = spec["decoy"]
            lines += ["", "", "# Retired with the carrier portal rewrite; kept so the old path isn't reused.",
                      '# @bp.route("%s", methods=["POST"])' % host_path,
                      "# def %s():" % fn,
                      '#     return jsonify({"ref": ""})']
        return self.finish(spec, lines, used)

    def gen_cmd(self, spec):
        rng = self.rng
        d, n = spec.get("domain"), spec.get("noun")
        taken, used = set(), set()
        cmds = []
        if spec.get("fixed"):
            for name, fn, doc in spec["fixed"]:
                self.commands.append("fxctl " + name)
                cmds.append((name, fn, doc, None))
        else:
            for _ in range(rng.randint(1, 2)):
                name, fn, verb = self.new_command(n, taken)
                cmds.append((name, fn, None, verb))
            for fid in spec["plant"]:
                if self.facts[fid]["kind"] == "command":
                    name, fn, verb = self.new_command(n, taken)
                    self.facts[fid]["token"] = "fxctl " + name
                    cmds.append((name, fn, None, verb))
            rng.shuffle(cmds)
        lines = [TQ + camel(n or "cli") + " commands for the " + (d or "cli") + " area." + TQ, "", "import click", "", "from cli.app import cli"]
        if spec.get("model"):
            lines.append("from %s.%s import %s" % (d, spec["model"], camel(spec["model"])))
        for i, (name, fn, doc, verb) in enumerate(cmds):
            if doc is None:
                form = i % 3
                doc = [
                    "%s %s records; try fxctl %s --dry-run first." % (verb.capitalize(), n, name),
                    "%s the %s queue. Run fxctl %s from the depot shell." % (verb.capitalize(), n, name),
                    "%s %s records (fxctl %s)." % (verb.capitalize(), n, name),
                ][form]
            else:
                doc = doc
            lines += ["", ""]
            lines.append('@cli.command(name="%s")' % name if i % 3 == 2 else '@cli.command("%s")' % name)
            lines.append('@click.option("--dry-run", is_flag=True)')
            lines.append("def %s(dry_run):" % fn)
            lines.append("    " + TQ + doc + TQ)
            lines.append('    click.echo("%s" + (" (dry run)" if dry_run else ""))' % fn.replace("_", " "))
            used.add(fn)
        return self.finish(spec, lines, used)

    def gen_model(self, spec):
        d, n = spec["domain"], spec["noun"]
        c = camel(n)
        lines = [TQ + c + " records for the " + d + " area." + TQ, "", "from dataclasses import dataclass", "", "", "@dataclass",
                 "class %s:" % c, "    " + TQ + "A " + n.replace("_", " ") + " in the " + d + " area." + TQ, "",
                 "    ref: str", '    status: str = "open"', "    amount: float = 0.0", "",
                 "    def to_dict(self):", '        return {"ref": self.ref, "status": self.status, "amount": self.amount}']
        return self.finish(spec, lines, set())

    def gen_service(self, spec):
        d, n, mn = spec["domain"], spec["noun"], spec["model"]
        c = camel(mn)
        lines = [TQ + camel(n) + " service for the " + d + " area." + TQ, "", "from %s.%s import %s" % (d, mn, c), "",
                 '_DEFAULT_STATUS = "open"', "", "",
                 "def summarize_%s(records):" % n, "    " + TQ + "Count " + n + " records by status." + TQ, "    counts = {}",
                 "    for record in records:", "        counts[record.status] = counts.get(record.status, 0) + 1",
                 "    return counts", "", "",
                 "def open_%s(ref):" % n, "    " + TQ + "Start a new " + n + " record." + TQ,
                 "    return %s(ref=ref, status=_DEFAULT_STATUS)" % c]
        return self.finish(spec, lines, set())

    def gen_util(self, spec):
        n = spec["noun"]
        lines = [TQ + camel(n) + " helpers for the " + spec["domain"] + " area." + TQ, "", "",
                 "def normalize_%s(value):" % n, "    " + TQ + "Trim and lower-case a " + n + " reference." + TQ,
                 "    return str(value).strip().lower()"]
        return self.finish(spec, lines, set())

    def gen_test(self, spec):
        d, mn = spec["domain"], spec["model"]
        c = camel(mn)
        lines = [TQ + "Tests for the " + mn + " records in the " + d + " area." + TQ, "", "import unittest", "",
                 "from %s.%s import %s" % (d, mn, c), "", "",
                 "class %sTest(unittest.TestCase):" % c,
                 "    def test_defaults(self):", '        record = %s(ref="r-1")' % c,
                 '        self.assertEqual(record.status, "open")', "",
                 "    def test_to_dict(self):", '        record = %s(ref="r-2", amount=3.5)' % c,
                 '        self.assertEqual(record.to_dict()["amount"], 3.5)']
        return self.finish(spec, lines, set(), 34, 90)

    def gen_http(self, spec):
        views = sorted(p for p, s in self.specs.items() if s["role"] == "view")
        lines = [TQ + "Builds the web app and loads every views module." + TQ, "", "import importlib", "", "from flask import Flask", "",
                 "VIEW_MODULES = ["]
        lines += ['    "%s",' % p[:-3].replace("/", ".") for p in views]
        lines += ["]", "", "", "def create_app():", "    app = Flask(__name__)", "    for name in VIEW_MODULES:",
                  "        module = importlib.import_module(name)", '        if hasattr(module, "register"):', "            module.register(app)",
                  '        elif hasattr(module, "bp"):', "            app.register_blueprint(module.bp)", "    return app"]
        return self.finish(spec, lines, set())

    def gen_cli_main(self, spec):
        cmds = sorted(p for p, s in self.specs.items() if s["role"] in ("cmd", "cli_cmd"))
        lines = [TQ + "Entry point: imports every commands module so the group sees them." + TQ, "", "import importlib", "",
                 "from cli.app import cli", "", "COMMAND_MODULES = ["]
        lines += ['    "%s",' % p[:-3].replace("/", ".") for p in cmds]
        lines += ["]", "", "", "def main():", "    for name in COMMAND_MODULES:", "        importlib.import_module(name)",
                  "    cli()"]
        return self.finish(spec, lines, set())

    def gen_cli_app(self, spec):
        lines = [TQ + "The click group every commands module attaches to." + TQ, "", "import click", "", "",
                 '@click.group(name="fxctl")', "def cli():", "    " + TQ + "Freight operations tools." + TQ]
        return self.finish(spec, lines, set())

    def gen_generic(self, spec):
        stem = spec["noun"]
        c = camel(stem)
        lines = [TQ + c + " support for the whole service." + TQ, "", "",
                 "class %s:" % c, "    " + TQ + "Shared " + stem.replace("_", " ") + " behavior." + TQ, "",
                 "    def __init__(self, label=%s):" % json.dumps(stem), "        self.label = label", "",
                 "    def describe(self):", '        return "%s:" + self.label' % stem]
        return self.finish(spec, lines, set())

    def finish(self, spec, lines, used, low=34, high=140):
        rng = self.rng
        for fid in spec["plant"]:
            fact = self.facts[fid]
            if fact["kind"] == "gotcha":
                lines.extend(gotcha_block(fact["entry"]))
        return pad_normal(rng, lines, used, low, high)

    def gen_big(self, spec):
        rng = self.rng
        d, n, n_lines = spec["domain"], spec["noun"], spec["lines"]
        c = camel(n)
        used = set()
        lines = [TQ + "Legacy " + n + " operations for the " + d + " area, kept in one module." + TQ, "", "import click", "",
                 "from flask import Blueprint, jsonify, request", "", "from cli.app import cli", "", 'bp = Blueprint("%s_legacy", __name__)' % d]
        lo, hi = int(0.35 * n_lines) + 10, int(0.65 * n_lines) - 10
        forced = spec.get("forced")
        while True:
            spots = sorted(rng.sample(range(lo, hi), 4 - (1 if forced else 0)) + ([forced] if forced else []))
            if all(b - a >= 70 for a, b in zip(spots, spots[1:])):
                break
        order = list(spec["plant"])
        rng.shuffle(order)
        # the forced spot belongs to the route
        if forced:
            order.remove(spec["route_fid"])
            order.insert(spots.index(forced), spec["route_fid"])
        taken, ctaken = set(), set()
        for spot, fid in zip(spots, order):
            fact = self.facts[fid]
            if fact["kind"] == "route":
                path, fn, verb = self.new_route(d, n, taken)
                fact["token"] = path
                if spec["style"] == 0:
                    block = ["", ""] + self.handler(fn, c, verb, n, '@bp.route("%s", methods=["POST"])' % path)
                else:
                    block = ["", ""] + self.handler(fn, c, verb, n) + ["", 'bp.add_url_rule("%s", view_func=%s, methods=["POST"])' % (path, fn)]
            elif fact["kind"] == "command":
                name, fn, verb = self.new_command(n, ctaken)
                fact["token"] = "fxctl " + name
                block = ["", "", '@cli.command("%s")' % name, "def %s():" % fn,
                         "    " + TQ + verb.capitalize() + " the " + n + " backlog with fxctl " + name + "." + TQ,
                         '    click.echo("%s")' % fn.replace("_", " ")]
            else:
                block = gotcha_block(fact["entry"])
            at = next(i for i, text in enumerate(block) if fact["token"] in text)
            fill(rng, lines, spot - 1 - at, used)
            lines.extend(block)
            assert fact["token"] in lines[spot - 1], (fid, spot)
        fill(rng, lines, n_lines, used)
        return lines

    # ---- the whole tree -----------------------------------------------------

    def layout(self):
        rng = self.rng
        for d in sorted(DOMAINS):
            nouns = DOMAINS[d]
            model = nouns[7]
            for i, n in enumerate(nouns[0:4]):
                self.add("%s/views_%s.py" % (d, n), "view", domain=d, noun=n, model=model, style=(i + len(d)) % 3)
            for n in nouns[4:7]:
                self.add("%s/cmd_%s.py" % (d, n), "cmd", domain=d, noun=n, model=model)
            for n in nouns[7:11]:
                self.add("%s/%s.py" % (d, n), "model", domain=d, noun=n)
            for i, n in enumerate(nouns[11:15]):
                if i == 0 and d in BIG:
                    self.add("%s/%s_service.py" % (d, n), "big", domain=d, noun=n, lines=BIG[d], style=len(d) % 2)
                else:
                    self.add("%s/%s_service.py" % (d, n), "service", domain=d, noun=n, model=model)
            if len(nouns) == 16:
                self.add("%s/util_%s.py" % (d, nouns[15]), "util", domain=d, noun=nouns[15])
            self.add("tests/test_%s.py" % d, "test", domain=d, model=model)
        for stem in CORE_STEMS:
            if stem == "http":
                self.add("core/http.py", "http")
            else:
                self.add("core/%s.py" % stem, "generic", noun=stem)
        for stem in ("money", "dates", "ids", "units", "retry"):
            self.add("tests/test_core_%s.py" % stem, "test", domain="core", model=stem)
        self.add("cli/app.py", "cli_app")
        self.add("cli/main.py", "cli_main")
        for stem in ("output", "options", "prompts"):
            self.add("cli/%s.py" % stem, "generic", noun="cli_" + stem)
        self.add("cli/cmd_health.py", "cli_cmd", fixed=[("health", "health", "Check the service and its database; fxctl health exits non-zero when either is down.")])
        self.add("cli/cmd_version.py", "cli_cmd", fixed=[("version", "version", "Print the build version; fxctl version is what support asks for first.")])
        self.add("cli/cmd_config.py", "cli_cmd", fixed=[("show-config", "show_config", "Print the settings in effect; fxctl show-config hides secrets.")])
        for name in ("architecture", "operations", "glossary", "onboarding", "runbook", "removed-endpoints"):
            self.add("docs/%s.md" % name, "doc")
        self.add("README.md", "readme")
        self.add("pyproject.toml", "pyproject")

    def plan_facts(self):
        rng = self.rng
        tracked = sorted(list(self.specs) + SKIP_PATHS)
        eligible = sorted(self.specs)

        def in_band(path):
            r1 = tracked.index(path) / (len(tracked) - 1)
            r2 = eligible.index(path) / (len(eligible) - 1)
            return 0.38 <= r1 <= 0.62 and 0.38 <= r2 <= 0.62

        band = [p for p in sorted(self.specs) if in_band(p)]
        views = [p for p in band if self.specs[p]["role"] == "view"]
        cmds = [p for p in band if self.specs[p]["role"] == "cmd"]
        assert len(views) >= 6 and len(cmds) >= 6, (len(views), len(cmds))
        route_files = rng.sample(views, 6)
        cmd_files = rng.sample(cmds, 6)
        taken = set(route_files) | set(cmd_files)
        rest = [p for p in band if p not in taken and self.specs[p]["role"] in ("view", "cmd", "model", "service", "util", "generic")]
        assert len(rest) >= 12, len(rest)
        gotcha_files = rng.sample(rest, 12)
        order = list(GOTCHAS)
        rng.shuffle(order)
        pairs = list(order)
        self.codes = [entry[3] for entry in order]

        def plant(fid, kind, placement, path, entry=None, token=None):
            self.facts[fid] = {"id": fid, "kind": kind, "placement": placement, "path": path, "token": token, "entry": entry}
            self.specs[path]["plant"].append(fid)

        k = 0
        for path in route_files:
            k += 1
            plant("mid-%02d" % k, "route", "repo-middle", path)
        for path in cmd_files:
            k += 1
            plant("mid-%02d" % k, "command", "repo-middle", path)
        for path in gotcha_files:
            k += 1
            entry = pairs.pop(0)
            plant("mid-%02d" % k, "gotcha", "repo-middle", path, entry, entry[3])
        k = 0
        for d in sorted(BIG, key=lambda x: BIG[x]):
            path = [p for p, s in self.specs.items() if s["role"] == "big" and s["domain"] == d][0]
            spec = self.specs[path]
            for kind in ("route", "command", "gotcha", "gotcha"):
                k += 1
                fid = "big-%02d" % k
                if kind == "gotcha":
                    entry = pairs.pop(0)
                    plant(fid, kind, "big-file-middle", path, entry, entry[3])
                else:
                    plant(fid, kind, "big-file-middle", path)
                    if kind == "route":
                        spec["route_fid"] = fid
            if BIG[d] == 1640:
                spec["forced"] = rng.randint(758, 792)
        # the remaining gotchas are real but unplanted
        extras = [p for p in sorted(self.specs) if self.specs[p]["role"] in ("view", "cmd", "model", "service", "util", "generic")
                  and not self.specs[p]["plant"]]
        for path in rng.sample(extras, len(pairs)):
            entry = pairs.pop(0)
            k += 1
            plant("extra-%02d" % k, "gotcha", "unplanted", path, entry, entry[3])
        assert not pairs
        # decoys: three commented-out routes in view files, three documented as removed
        free_views = [p for p in sorted(self.specs) if self.specs[p]["role"] == "view" and not self.specs[p]["plant"]]
        for path in rng.sample(free_views, 3):
            s = self.specs[path]
            verb = rng.choice(VERBS)
            host_path = "/v2/%s/%s/legacy-%s" % (s["domain"], plural(s["noun"]), verb)
            s["decoy"] = (host_path, "legacy_%s_%s" % (verb, s["noun"]), verb)
            self.decoys.append({"kind": "commented-out", "path": path, "token": host_path})

    def render_all(self):
        rng = self.rng
        removed = []
        for _ in range(3):
            d = rng.choice(sorted(DOMAINS))
            n = rng.choice(DOMAINS[d][0:4])
            verb = rng.choice(VERBS)
            removed.append("/v2/%s/%s/legacy-%s" % (d, plural(n), verb))
        for tok in removed:
            self.decoys.append({"kind": "documented-removed", "path": "docs/removed-endpoints.md", "token": tok})
        for path in sorted(self.specs):
            spec = self.specs[path]
            role = spec["role"]
            if role == "doc":
                lines = self.gen_doc(spec, removed)
            elif role == "readme":
                lines = self.gen_readme()
            elif role == "pyproject":
                lines = self.gen_pyproject()
            elif role == "cli_cmd":
                lines = self.gen_cmd(dict(spec, domain=None, noun="cli"))
            else:
                lines = getattr(self, {"view": "gen_view", "cmd": "gen_cmd", "model": "gen_model", "service": "gen_service",
                                       "util": "gen_util", "test": "gen_test", "http": "gen_http", "cli_main": "gen_cli_main",
                                       "cli_app": "gen_cli_app", "generic": "gen_generic", "big": "gen_big"}[role])(spec)
            self.files[path] = lines
        self.skipped()

    def gen_doc(self, spec, removed):
        rng = self.rng
        name = spec["path"][5:-3]
        lines = ["# " + name.replace("-", " ").capitalize(), ""]
        if name == "removed-endpoints":
            lines += ["These endpoints were taken out and must not come back under the same path.", ""]
            for tok, why in zip(removed, ("the partner portal stopped calling it", "replaced by the batch endpoint", "the carrier retired the feed")):
                lines.append("- `%s`: removed in 4.0; %s." % (tok, why))
            lines.append("")
        while len(lines) < 32:
            d = rng.choice(sorted(DOMAINS))
            lines.append("## " + d.capitalize())
            lines.append("")
            for _j in range(rng.randint(4, 6)):
                lines.append(rng.choice(SENTENCES).format(d=d, n=rng.choice(DOMAINS[d])))
            lines.append("")
        return lines

    def gen_readme(self):
        lines = ["# freight-ops", "", "A small freight operations service: shipments, billing, carriers, customs, and the depot floor.",
                 "", "The command line is `fxctl`; ask it for `--help` to see what it can do.", "", "## Layout", ""]
        for d in sorted(DOMAINS):
            lines.append("- `%s/`: models, views, services, and commands for the %s area" % (d, d))
        lines += ["- `core/`: money, dates, ids, retries, and the shared settings", "- `cli/`: the click group and its entry point",
                  "- `docs/`: architecture, operations, and the glossary", "- `tests/`: unittest modules, one per area", "",
                  "## Working on it", "", "Python 3.10 or newer. Install with pip, run the tests with unittest, and keep each area's code inside its own folder.",
                  "The vendored folder is third-party code: don't edit it. The generated folder is rebuilt by the tooling.",
                  "Read the glossary before naming anything new.", "",
                  "## Conventions", "", "Each area owns its models, views, services, and commands, and nothing else.",
                  "Shared behavior goes in core, not into a second copy inside an area.", "Tests import the area they cover and never reach into another one."]
        return lines

    def gen_pyproject(self):
        rng = self.rng
        lines = ["[project]", 'name = "freight-ops"', 'version = "4.2.0"', 'description = "Freight operations service and command line"',
                 'requires-python = ">=3.10"', "dependencies = [", '    "flask>=3.0",', '    "click>=8.1",', "]", "",
                 "[project.scripts]", 'fxctl = "cli.main:main"', "", "[tool.ruff]", "line-length = 100", "",
                 "[tool.freight.zones]", "# multipliers per rate zone, read by the routing area"]
        for i in range(20):
            lines.append("%s_%d = %s" % (rng.choice(PW), i, round(rng.random() * 2 + 0.5, 2)))
        return lines

    def skipped(self):
        rng = self.rng
        lock = []
        for pkg in "flask click werkzeug jinja2 itsdangerous markupsafe blinker colorama".split():
            lock += ["[[package]]", 'name = "%s"' % pkg, 'version = "%d.%d.%d"' % (rng.randint(1, 4), rng.randint(0, 9), rng.randint(0, 9)),
                     'hash = "%032x"' % rng.getrandbits(128), ""]
        self.files["poetry.lock"] = lock
        for path, what in (("vendor/tinyjson/__init__.py", "tinyjson 0.4.1"), ("vendor/tinyjson/decoder.py", "tinyjson 0.4.1"),
                           ("vendor/tinyjson/encoder.py", "tinyjson 0.4.1")):
            lines = ["# Vendored copy of %s. Do not edit; update by re-vendoring." % what]
            fill(rng, lines, 1 + 6 * rng.randint(6, 12), set())
            self.files[path] = lines
        for path in ("generated/manifest_pb2.py", "generated/carrier_client.py"):
            lines = ["# Generated by fxgen from carrier.proto. DO NOT EDIT."]
            fill(rng, lines, 1 + 6 * rng.randint(10, 18), set())
            self.files[path] = lines
        rows = ["zone,band,rate_per_kg,fuel_pct"]
        for i in range(120):
            rows.append("z%d,b%d,%s,%s" % (rng.randint(1, 9), rng.randint(1, 5), round(rng.random() * 4 + 0.3, 2), round(rng.random() * 18, 1)))
        self.files["data/rates_2026.csv"] = rows
        manifest = {"shipments": [{"ref": "SHP%04d" % i, "weight": rng.randint(10, 900), "zone": rng.randint(1, 9)} for i in range(40)]}
        self.files["fixtures/manifest_sample.json"] = json.dumps(manifest, indent=2).split("\n")
        zones = {"zones": [{"id": i, "multiplier": round(rng.random() * 2 + 0.5, 2)} for i in range(20)]}
        self.files["fixtures/zones.json"] = json.dumps(zones, indent=2).split("\n")

    def binaries(self):
        rng = self.rng
        out = {}
        for path, head, size in (("assets/label-template.bin", b"\x00FXB1", 512), ("assets/sort-belt.bin", b"\x00FXB2", 768)):
            out[path] = head + bytes(rng.randrange(256) for _ in range(size))
        return out


def build():
    w = World()
    w.layout()
    w.plan_facts()
    w.render_all()
    blobs = {}
    for path, lines in w.files.items():
        blobs[path] = ("\n".join(lines) + "\n").encode("utf-8")
    blobs.update(w.binaries())
    untracked = {"notes/untracked-scratch.md": ("# Scratch\n\nAsk ops about the tariff spreadsheet.\nCheck whether the depot still uses the old handhelds.\n").encode("utf-8")}
    # checks that would make a paid run worthless
    assert len(w.specs) == 180, len(w.specs)
    for path, blob in blobs.items():
        text = blob.decode("utf-8", "replace")
        assert not re.search(r"^[ \t]*pa" + r"ss([ \t]|$)", text, re.M), path
        if path.endswith(".py"):
            compile(text, path, "exec")
    everything = "\n".join(b.decode("utf-8", "replace") for b in list(blobs.values()) + list(untracked.values()))
    for tok in w.routes + w.commands + w.codes + [x["token"] for x in w.decoys]:
        assert everything.count(tok) == 1, (tok, everything.count(tok))
    assert len(set(w.routes)) == len(w.routes)
    for a in w.routes + [x["token"] for x in w.decoys]:
        for b in w.routes + [x["token"] for x in w.decoys]:
            assert a == b or a not in b, (a, b)
    for a in w.commands:
        for b in w.commands:
            assert a == b or a not in b, (a, b)
    for m in re.findall(r"fxctl [a-z][a-z0-9-]*", everything):
        assert m in w.commands, m
    for shape, pattern in CODE_SHAPES.items():
        found = re.findall(pattern, everything)
        assert 0 < len(found) <= 4, (shape, found)
        assert all(m in w.codes for m in found), (shape, found)
    facts = []
    for fid in sorted(w.facts):
        f = w.facts[fid]
        if f["placement"] == "unplanted":
            continue
        where = [i + 1 for i, text in enumerate(w.files[f["path"]]) if f["token"] in text]
        assert len(where) == 1, (fid, where)
        facts.append({"id": fid, "kind": f["kind"], "placement": f["placement"], "path": f["path"], "line": where[0], "token": f["token"]})
    assert len(facts) == 48
    decoys = []
    for i, dec in enumerate(w.decoys, 1):
        where = [j + 1 for j, text in enumerate(w.files[dec["path"]]) if dec["token"] in text]
        assert len(where) == 1, dec
        decoys.append({"id": "decoy-%02d" % i, "kind": dec["kind"], "path": dec["path"], "line": where[0], "token": dec["token"]})
    key = {"facts": facts, "decoys": decoys, "routes": sorted(w.routes), "commands": sorted(w.commands), "codes": sorted(w.codes), "code_shapes": CODE_SHAPES}
    return blobs, untracked, key


def main(argv):
    blobs, untracked, key = build()
    if argv[:1] == ["emit-key"]:
        with open(argv[1], "w", encoding="utf-8") as fh:
            fh.write(json.dumps(key, indent=1) + "\n")
        return 0
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

real_git=""
for candidate in "$(xcrun --find git 2>/dev/null || true)" /Library/Developer/CommandLineTools/usr/bin/git "$(command -v git)"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then real_git="$candidate"; break; fi
done
[ -n "$real_git" ] || { echo "no git found" >&2; exit 1; }
mkdir -p bin
printf '#!/bin/sh\nexec "%s" "$@"\n' "$real_git" > bin/git
chmod +x bin/git
G="./bin/git -c user.name=Owner -c user.email=owner@example.com -c commit.gpgsign=false"

python3 -c "$GEN" build
$G init -q -b main
mkdir -p .git/info
printf 'bin/\n' >> .git/info/exclude
$G add -A -- . ':!notes'
GIT_AUTHOR_DATE="2026-11-05T09:00:00 +0000" GIT_COMMITTER_DATE="2026-11-05T09:00:00 +0000" $G commit -qm "freight-ops 4.2.0"
