import os
import re
import json
import csv
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

API_ENDPOINT_PATTERNS = [
    ("GET", r'@GetMapping\("([^"]+)"\)'),
    ("POST", r'@PostMapping\("([^"]+)"\)'),
    ("PUT", r'@PutMapping\("([^"]+)"\)'),
    ("DELETE", r'@DeleteMapping\("([^"]+)"\)'),
    ("ANY", r'@RequestMapping\("([^"]+)"\)'),
    ("ANY", r'@Path\("([^"]+)"\)'),
    ("DELETE", r'@DELETE\b'),
    ("GET", r'app\.get\(\s*["\']([^"\']+)["\']'),
    ("POST", r'app\.post\(\s*["\']([^"\']+)["\']'),
    ("PUT", r'app\.put\(\s*["\']([^"\']+)["\']'),
    ("DELETE", r'app\.delete\(\s*["\']([^"\']+)["\']'),
    ("GET", r'router\.get\(\s*["\']([^"\']+)["\']'),
    ("POST", r'router\.post\(\s*["\']([^"\']+)["\']'),
    ("PUT", r'router\.put\(\s*["\']([^"\']+)["\']'),
    ("DELETE", r'router\.delete\(\s*["\']([^"\']+)["\']')
]

CALL_PATTERNS = [
    r'axios\.(get|post|put|delete|request|create)\(',
    r'fetch\(',
    r'requests\.(get|post|put|delete|head|options)\(',
    r'RestTemplate\.(getForObject|getForEntity|postForObject|postForEntity|exchange)\(',
    r'httpClient\.(send|execute)\(',
    r'WebClient\..*?\.(get|post|put|delete)\(',
    r'Grpc.*stub', r'\.newBlockingStub\(', r'insecure_channel\(',
    r'http\.Get\(', r'http\.Post\(',
    r'curl_init\(', r'file_get_contents\(', r'\bcurl\b', r'\bwget\b',
    r'Invoke-WebRequest',
    r'http[s]?://[^\s"\']+',
    r'["\'`](/api/[^"\']+)["\'`]',
]

UNWANTED_SCOPES = {"test", "provided", "system", "import"}
NS = {'mvn': 'http://maven.apache.org/POM/4.0.0'}
EXCLUDE_DIRS = ["node_modules", "frontend", "client", "web", "ui", "dist", "build", "__mocks__", "test"]
DEPENDENCY_FILES = ["pom.xml", "package.json", "requirements.txt", "setup.py", "build.gradle", "go.mod", "composer.json"]

def is_excluded_path(path):
    return any(excl in path for excl in EXCLUDE_DIRS)

def get_modules_from_pom(pom_path):
    try:
        tree = ET.parse(pom_path)
        root = tree.getroot()
        return [m.text.strip() for m in root.findall(".//mvn:modules/mvn:module", NS) if m.text]
    except Exception:
        return []

def count_dependencies(path):
    deps = set()
    for root, _, files in os.walk(path):
        if is_excluded_path(root):
            continue
        for file in files:
            if not file or not isinstance(file, str):
                continue
            try:
                full_path = os.path.join(root, file)
            except Exception:
                continue
            if file == "pom.xml":
                try:
                    tree = ET.parse(full_path)
                    root = tree.getroot()
                    for dep_node in root.findall(".//mvn:dependencies/mvn:dependency", NS):
                        scope = dep_node.find("mvn:scope", NS)
                        if scope is not None and scope.text.strip() in UNWANTED_SCOPES:
                            continue
                        gid = dep_node.find("mvn:groupId", NS)
                        aid = dep_node.find("mvn:artifactId", NS)
                        ver = dep_node.find("mvn:version", NS)
                        if gid is not None and aid is not None:
                            coord = f"{gid.text.strip()}:{aid.text.strip()}:{ver.text.strip() if ver is not None else '<inherited>'}"
                            deps.add(coord)
                except Exception:
                    continue
            elif file == "package.json":
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        deps.update(data.get("dependencies", {}).keys())
                except Exception:
                    continue
            elif file == "requirements.txt":
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip() and not line.startswith("#"):
                                deps.add(line.strip().split("==")[0])
                except Exception:
                    continue
            elif file == "build.gradle":
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        matches = re.findall(r'(?:implementation|api|compile)\s+["\']([^"\']+)["\']', content)
                        deps.update(matches)
                except Exception:
                    continue
            elif file == "go.mod":
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.startswith("require"):
                                parts = line.split()
                                if len(parts) > 1:
                                    deps.add(parts[1])
                except Exception:
                    continue
    return deps

def count_endpoints(path):
    unique = set()
    for root, _, files in os.walk(path):
        if is_excluded_path(root):
            continue
        for file in files:
            if file.endswith((".py", ".js", ".ts", ".java", ".kt", ".php", ".go")):
                try:
                    content = open(os.path.join(root, file), encoding='utf-8', errors='ignore').read()
                    for method, pattern in API_ENDPOINT_PATTERNS:
                        for match in re.findall(pattern, content, re.IGNORECASE):
                            unique.add((method, "/" + match.strip("/")))
                except Exception:
                    continue
    return len(unique), sorted([f"{m} {p}" for m, p in unique])

def count_inter_service_calls(path):
    matches = set()
    for root, _, files in os.walk(path):
        if is_excluded_path(root):
            continue
        for file in files:
            if file.endswith((".py", ".js", ".ts", ".java", ".kt")):
                try:
                    content = open(os.path.join(root, file), encoding='utf-8', errors='ignore').read()
                    for pattern in CALL_PATTERNS:
                        for match in re.finditer(pattern, content):
                            matches.add(match.group(0).strip())
                except Exception:
                    continue
    return len(matches), sorted(matches)

def get_commits(repo_path, frequency, periods):
    now = datetime.utcnow()
    delta = timedelta(weeks=1 if frequency == "weekly" else 30)
    start_date = (now - timedelta(days=now.weekday())) - delta * periods if frequency == "weekly" else now - delta * periods
    commits = []
    for branch in ["main", "master", "develop"]:
        try:
            subprocess.check_output(["git", "-C", repo_path, "rev-parse", "--verify", branch], text=True)
            break
        except subprocess.CalledProcessError:
            continue
    else:
        return []
    for i in range(periods + 1):
        date = (start_date + i * delta).strftime('%Y-%m-%d')
        try:
            commit = subprocess.check_output(["git", "-C", repo_path, "rev-list", "-1", "--before", date, branch], text=True).strip()
            if commit:
                commits.append((commit, date))
        except subprocess.CalledProcessError:
            pass
    return commits

def analyze_service(repo_path, csv_writer, date):
    root_pom = os.path.join(repo_path, "pom.xml")
    modules = get_modules_from_pom(root_pom) if os.path.exists(root_pom) else []
    paths = [os.path.join(repo_path, m) for m in modules] if modules else [repo_path]

    total_eps, total_calls = 0, 0
    all_eps, all_calls, all_deps = set(), set(), set()

    for path in paths:
        ep_count, eps = count_endpoints(path)
        call_count, calls = count_inter_service_calls(path)
        deps = count_dependencies(path)

        total_eps += ep_count
        total_calls += call_count
        all_eps.update(eps)
        all_calls.update(calls)
        all_deps.update(deps)

    print(f"\nSnapshot at {date}:")
    print(f"  Endpoints: {total_eps}")
    for ep in sorted(all_eps):
        print(f"    - {ep}")
    print(f"  Inter-Service Communications: {len(all_calls)}")
    for c in sorted(all_calls):
        print(f"    - {c}")
    print(f"  Dependencies: {len(all_deps)}")
    for d in sorted(all_deps):
        print(f"    - {d}")

    csv_writer.writerow([
        os.path.basename(repo_path),
        date,
        total_eps,
        len(all_deps),
        len(all_calls),
        '"' + ';'.join(sorted(all_deps)) + '"',
        '"' + ';'.join(sorted(all_eps)) + '"',
        '"' + ';'.join(sorted(all_calls)) + '"'
    ])

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('repo_path')
    parser.add_argument('output')
    parser.add_argument('--frequency', choices=['weekly', 'monthly'], default='monthly')
    parser.add_argument('--periods', type=int, default=24)
    args = parser.parse_args()

    original_head = subprocess.check_output(["git", "-C", args.repo_path, "rev-parse", "HEAD"], text=True).strip()

    with open(args.output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Service", "Date", "Endpoints", "Dependencies", "InterServiceCommunications",
                         "DependencyList", "EndpointList", "InterServiceCommunicationsList"])
        for commit, date in get_commits(args.repo_path, args.frequency, args.periods):
            subprocess.run(["git", "-C", args.repo_path, "checkout", "-q", commit], check=True)
            analyze_service(args.repo_path, writer, date)

    subprocess.run(["git", "-C", args.repo_path, "checkout", "-q", original_head], check=True)

    print(f"\nAnalysis complete.")
