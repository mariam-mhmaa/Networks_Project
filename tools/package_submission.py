"""Create a source/evidence ZIP without environments, builds or Git metadata."""
import argparse
import hashlib
import os
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRECTORIES = {".git", ".venv", "venv", "__pycache__", ".pytest_cache",
                    ".mypy_cache", ".ruff_cache", "node_modules", ".vscode",
                    ".build-verification", "build", "submission"}
LEGACY_LOCAL_DIRECTORIES = {"member1", "member2", "member3"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".obj", ".o", ".a", ".elf", ".map", ".bin", ".exe"}
SOURCE_CONFIGS = {"stations/production/firmware/sdkconfig",
                  "stations/production/firmware/sdkconfig.defaults"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "submission/MCT431_Milestone1.zip")
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for directory, subdirectories, filenames in os.walk(ROOT):
        subdirectories[:] = sorted(name for name in subdirectories
                                   if name not in SKIP_DIRECTORIES and not name.startswith("build-")
                                   and not (Path(directory) == ROOT and name in LEGACY_LOCAL_DIRECTORIES))
        for filename in sorted(filenames):
            path = Path(directory) / filename
            if path in {output, output.with_suffix(output.suffix + ".sha256"), ROOT / "MANIFEST.sha256"} or path.name == ".git":
                continue
            rel = path.relative_to(ROOT)
            evidence = rel.parts[0] == "Test_Cases"
            if not evidence and path.suffix.lower() in SKIP_SUFFIXES:
                continue
            # Keep deliberately collected evidence; never sweep local B Wi-Fi
            # credentials or a live database into the source package.
            if not evidence and (path.name.startswith("sdkconfig") or
                                 path.name.endswith(".local.jsonl") or ".sqlite3" in path.name):
                if rel.as_posix() not in SOURCE_CONFIGS:
                    continue
            files.append((path, rel.as_posix()))
    files.sort(key=lambda item: item[1])
    readmes = [name for _, name in files if Path(name).name.lower().startswith("readme")]
    requirements = [name for _, name in files if Path(name).name.lower().startswith("requirements")]
    if readmes != ["README.md"] or requirements != ["requirements.txt"]:
        raise SystemExit(f"Expected one root README and requirements file: {readmes}, {requirements}")
    manifest = []
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, name in files:
            data = path.read_bytes()
            archive.writestr(name, data)
            manifest.append(f"{hashlib.sha256(data).hexdigest()}  {name}")
        archive.writestr("MANIFEST.sha256", "\n".join(manifest) + "\n")
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise SystemExit("ZIP integrity check failed")
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{checksum}  {output.name}\n", encoding="utf-8")
    print(f"Created {output}: {len(files)} files; SHA256 {checksum}")


if __name__ == "__main__":
    main()
