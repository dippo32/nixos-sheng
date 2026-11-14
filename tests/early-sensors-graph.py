#!/usr/bin/env python3
"""Check a synthetic charger/sensor graph using Nix-evaluated unit fields.

This deliberately does not claim to model the whole NixOS transaction or
hardware. Run real rendered-unit/boot checks separately.
"""
import collections
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def unit_fields(value):
    result = {}
    for key in ("after", "before", "wants", "requires", "conflicts"):
        field = value.get(key, [])
        if not isinstance(field, list) or not all(isinstance(x, str) and x for x in field):
            raise ValueError(f"{key} must be a list of unit names")
        result[key] = list(dict.fromkeys(field))
    result["defaultDependencies"] = value.get("defaultDependencies")
    if not isinstance(result["defaultDependencies"], bool):
        raise ValueError("defaultDependencies must be boolean")
    return result


def add_unique(target, field, values):
    for value in values:
        if value not in target[field]:
            target[field].append(value)


def reachable(edges, start, end):
    todo, seen = [start], set()
    while todo:
        node = todo.pop()
        if node == end:
            return True
        if node not in seen:
            seen.add(node)
            todo.extend(edges[node] - seen)
    return False


def main(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    names = {"registry": "sheng-sensors-data.service",
             "rpc": "adsprpcd-sensorspd.service",
             "charger": "xiaomi-charger-mode.service"}
    units = {names[k]: unit_fields(data[k]) for k in names}
    registry, rpc, charger = (units[names[k]] for k in ("registry", "rpc", "charger"))
    mount = data["registry"].get("requiresMountsFor")
    if mount != "/var/lib/qcom":
        raise ValueError("registry must wait for its persistent directory")
    if registry["defaultDependencies"] or rpc["defaultDependencies"]:
        raise ValueError("sensor services must not inherit After=basic.target")
    if charger["defaultDependencies"]:
        raise ValueError("charger baseline must run without default dependencies")

    # Parts supplied by the package units and the existing firmware module,
    # which are not necessarily present in Nix's selected service fields.
    add_unique(registry, "before", [names["rpc"]])
    add_unique(rpc, "requires", [names["registry"]])
    add_unique(rpc, "after", [names["registry"]])
    add_unique(rpc, "before", ["iio-sensor-proxy.service"])
    add_unique(charger, "after", ["local-fs.target", "systemd-udev-trigger.service",
                                  "systemd-modules-load.service", "plymouth-start.service"])
    add_unique(charger, "wants", ["local-fs.target", "systemd-udev-trigger.service",
                                  "systemd-modules-load.service"])
    add_unique(charger, "before", ["basic.target", "display-manager.service", "shutdown.target"])

    if names["rpc"] not in charger["wants"]:
        raise ValueError("charger must request the early daemon")
    if names["rpc"] in charger["requires"] or names["registry"] in charger["requires"]:
        raise ValueError("charger must not require sensors to succeed")
    for unit in (registry, rpc):
        if "basic.target" in unit["after"] or "sysinit.target" in unit["after"]:
            raise ValueError("early service cannot wait for late boot targets")
        if "shutdown.target" not in unit["before"] or "shutdown.target" not in unit["conflicts"]:
            raise ValueError("early service must stop for shutdown")

    # Minimal baseline dependencies representing boot milestones and IIO.
    empty = lambda: {"after": [], "before": [], "wants": [], "requires": [],
                     "conflicts": [], "defaultDependencies": False}
    for name in ("local-fs.target", "sysinit.target", "basic.target", "shutdown.target",
                 "systemd-udev-trigger.service", "systemd-modules-load.service",
                 "systemd-journald.socket", "plymouth-start.service",
                 "iio-sensor-proxy.service", "display-manager.service"):
        units[name] = empty()
    units["sysinit.target"]["after"] = ["local-fs.target", "systemd-udev-trigger.service",
                                         "systemd-modules-load.service"]
    units["basic.target"]["after"] = ["sysinit.target"]
    units["iio-sensor-proxy.service"]["after"] = ["basic.target", names["rpc"]]

    edges = collections.defaultdict(set)
    indegree = {name: 0 for name in units}
    for name, unit in units.items():
        for previous in unit["after"]:
            edges[previous].add(name)
        for later in unit["before"]:
            edges[name].add(later)
    # Include unknown dependency nodes as graph leaves, not real unit models.
    for source, dests in list(edges.items()):
        indegree.setdefault(source, 0)
        for dest in dests:
            indegree[dest] = indegree.get(dest, 0) + 1
    queue = collections.deque(node for node, degree in indegree.items() if degree == 0)
    count = 0
    while queue:
        node = queue.popleft()
        count += 1
        for dest in edges[node]:
            indegree[dest] -= 1
            if indegree[dest] == 0:
                queue.append(dest)
    if count != len(indegree):
        raise ValueError("synthetic ordering graph contains a cycle")
    if not reachable(edges, names["registry"], names["rpc"]):
        raise ValueError("registry is not ordered before sensor daemon")
    if not reachable(edges, names["rpc"], "basic.target"):
        raise ValueError("sensor daemon is not ordered before basic.target")
    if reachable(edges, names["rpc"], names["charger"]) or reachable(edges, names["registry"], names["charger"]):
        raise ValueError("sensor startup must not delay the charger screen")
    print("Synthetic ordering is acyclic; charger requests sensors without requiring or waiting for them.")

    analyzer = shutil.which("systemd-analyze")
    if not analyzer:
        print("systemd-analyze unavailable; synthetic graph checks passed, unit verification skipped.")
        return
    with tempfile.TemporaryDirectory(prefix="sheng-early-sensors-") as tmp:
        root = Path(tmp)
        for name, unit in units.items():
            lines = ["[Unit]", "Description=Synthetic validation fixture", "DefaultDependencies=no"]
            for field, directive in (("after", "After"), ("before", "Before"),
                                     ("wants", "Wants"), ("requires", "Requires"),
                                     ("conflicts", "Conflicts")):
                if unit[field]:
                    lines.append(f"{directive}={' '.join(unit[field])}")
            if name == names["registry"]:
                lines.append("RequiresMountsFor=/var/lib/qcom")
            if name == names["rpc"]:
                lines += ["ConditionPathExists=|/dev/fastrpc-adsp",
                          "ConditionPathExists=|/dev/fastrpc-adsp-secure"]
            if name == names["charger"]:
                lines += ["ConditionKernelCommandLine=|androidboot.mode=charger",
                          "ConditionPathExists=|/proc/device-tree/chosen/sheng,charger-mode"]
            if name.endswith(".service"):
                service_type = "exec" if name == names["rpc"] else "oneshot"
                lines += ["", "[Service]", f"Type={service_type}", "ExecStart=/bin/true"]
            elif name.endswith(".socket"):
                lines += ["", "[Socket]", "ListenStream=/run/sheng-test-journald.sock",
                          "Service=sheng-test-journal.service"]
            (root / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        (root / "sheng-test-journal.service").write_text(
            "[Unit]\nDefaultDependencies=no\n[Service]\nExecStart=/bin/true\n", encoding="utf-8")
        (root / "-.mount").write_text(
            "[Unit]\nDefaultDependencies=no\n[Mount]\nWhat=/dev/root\nWhere=/\nType=ext4\n", encoding="utf-8")
        env = os.environ.copy()
        env["SYSTEMD_UNIT_PATH"] = str(root)
        command = [analyzer, "verify", "--man=no", *(str(root / names[k]) for k in names)]
        result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=40)
        if result.returncode or "ordering cycle" in result.stderr.lower():
            raise RuntimeError("systemd-analyze rejected synthetic fixture:\n" + result.stderr)
    print("systemd-analyze verified the synthetic fixture; actual generated graph and hardware remain unverified.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: early-sensors-graph.py EVALUATED-UNITS.json")
    main(sys.argv[1])
