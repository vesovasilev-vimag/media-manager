"""Update traceability only from executed JUnit results and exact source test references."""
import ast
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

root = Path(__file__).resolve().parents[2]
report = root / ".test-artifacts/backend.xml"
suite = ElementTree.parse(report).getroot()
locations = {}
for file in (root / "tests").rglob("test_*.py"):
    for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            locations[node.name] = f"{file.relative_to(root).as_posix()}:{node.lineno}"
evidence = {f"{prefix}-{index:02}": [] for prefix, count in [("T",43),("IT",17)] for index in range(1,count+1)}
results = []
for case in suite.iter("testcase"):
    name = case.attrib["name"].split("[")[0]
    state = "FAIL" if case.find("failure") is not None or case.find("error") is not None else "BLOCKED" if case.find("skipped") is not None else "PASS"
    reference = locations.get(name)
    if reference is None:
        raise ValueError("Cannot trace test source: " + name)
    row = {"test": name, "source": reference, "status": state}
    results.append(row)
    ids = ["T-"+v for v in re.findall(r"(?<!I)T(\d{2})",name)] + ["IT-"+v for v in re.findall(r"IT(\d{2})",name)]
    for identifier in ids:
        if identifier in evidence:
            evidence[identifier].append(row)
statuses = {key: "FAIL" if any(v["status"] == "FAIL" for v in values) else "PASS" if values and all(v["status"] == "PASS" for v in values) else "BLOCKED" for key,values in evidence.items()}
ledger = root / "docs/rc1-traceability.md"
lines = ledger.read_text(encoding="utf-8").splitlines()
lines = [f"**Status:** {len(results)} executed Linux tests; T/IT requirement IDs PASS={list(statuses.values()).count('PASS')}, FAIL={list(statuses.values()).count('FAIL')}, BLOCKED={list(statuses.values()).count('BLOCKED')}. External providers are emulated; PostgreSQL/filesystem/ffprobe/backup tools are real disposable fixtures. Live operational gates remain separate. [Sanitized evidence and source hashes](rc1-automated-evidence.json)." if line.startswith("**Status:**") else line for line in lines]
for index,line in enumerate(lines):
    match = re.match(r"\| ((?:IT|T)-\d{2}) \|",line)
    if not match:
        continue
    identifier = match[1]
    columns = line.split("|")
    columns[3] = " " + statuses[identifier] + " "
    refs = sorted({r["source"] for r in evidence[identifier]})
    columns[4] = " " + ("; ".join("`"+r+"`" for r in refs) if refs else "No executed automated reference") + "; Linux synthetic/ephemeral PostgreSQL. LIVE gates separate. "
    lines[index] = "|".join(columns)
ledger.write_text("\n".join(lines)+"\n",encoding="utf-8")
fingerprints = {}
for base in [root / "backend/app", root / "tests", root / "frontend/src"]:
    for file in sorted(base.rglob("*")):
        if file.suffix in {".py", ".ts", ".vue", ".css"}:
            fingerprints[file.relative_to(root).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
output = {"generated_at":datetime.now(timezone.utc).isoformat(),"environment":"Disposable Linux, synthetic media and emulated external services; not live ViMag", "junit_sha256":hashlib.sha256(report.read_bytes()).hexdigest(),"tests":results,"requirements":statuses,"source_sha256":fingerprints}
(root / "docs/rc1-automated-evidence.json").write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"tests":len(results),"requirements":{state:list(statuses.values()).count(state) for state in ["PASS","FAIL","BLOCKED"]}}))
if any(state != "PASS" for state in statuses.values()):
    raise SystemExit(1)
