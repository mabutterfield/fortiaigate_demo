#!/usr/bin/env python3
"""Build or verify a versioned Ubuntu NVIDIA APT package cache bundle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def identity():
    info = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            info[k] = v.strip('"')
    return {'os_id': info.get('ID'), 'os_version': info.get('VERSION_ID'),
            'arch': subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()}


def fields(path):
    out = subprocess.check_output(['dpkg-deb', '-f', str(path), 'Package', 'Version', 'Architecture'], text=True)
    values = dict(line.split(': ', 1) for line in out.splitlines() if ': ' in line)
    if set(values) != {'Package', 'Version', 'Architecture'}:
        raise ValueError('Unable to identify deb: ' + path.name)
    return values


def required(suffix):
    return ['nvidia-driver-' + suffix, 'nvidia-utils-' + suffix,
            'nvidia-dkms-' + suffix, 'nvidia-compute-utils-' + suffix.removesuffix('-open')]


def build(args):
    if args.output.exists():
        raise ValueError('Output already exists')
    packages = []
    for file in sorted(args.packages.glob('*.deb')):
        f = fields(file)
        packages.append({'file': file.name, 'package': f['Package'], 'version': f['Version'],
                         'arch': f['Architecture'], 'sha256': digest(file)})
    by_name = {entry['package']: entry for entry in packages}
    if len(by_name) != len(packages):
        raise ValueError('Package cache contains multiple versions of a package; select one version per package')
    missing = [name for name in required(args.driver_suffix) if name not in by_name]
    if missing:
        raise ValueError('Required driver packages missing from completed cache: ' + ', '.join(missing))
    versions = {by_name[name]['version'] for name in required(args.driver_suffix)}
    if len(versions) != 1:
        raise ValueError('NVIDIA package versions do not match')
    meta = {'format': 1, **identity(), 'driver_suffix': args.driver_suffix,
            'driver_version': versions.pop(), 'packages': packages}
    try:
        with args.output.open('xb') as raw:
            with tarfile.open(fileobj=raw, mode='w') as archive:
                blob = json.dumps(meta, sort_keys=True, indent=2).encode()
                info = tarfile.TarInfo('manifest.json')
                info.size = len(blob)
                import io
                archive.addfile(info, io.BytesIO(blob))
                for entry in packages:
                    archive.add(args.packages / entry['file'], arcname='packages/' + entry['file'], recursive=False)
    except Exception:
        args.output.unlink(missing_ok=True)
        raise
    print(json.dumps({'path': str(args.output), 'sha256': digest(args.output),
                      'driver_version': meta['driver_version'], 'packages': len(packages)}))


def prepare(args):
    if not re.fullmatch(r'[a-fA-F0-9]{64}', args.sha256):
        raise ValueError('Expected a 64-character SHA-256')
    if digest(args.archive) != args.sha256.lower():
        raise ValueError('Archive checksum does not match configured SHA-256')
    args.root.mkdir(parents=True, exist_ok=True, mode=0o755)
    final = args.root / args.sha256.lower()
    with tempfile.TemporaryDirectory(prefix='.nvidia-cache-', dir=args.root) as tmp:
        temp = Path(tmp)
        temp.chmod(0o755)
        with tarfile.open(args.archive, 'r:*') as archive:
            members = archive.getmembers()
            if any(not m.isfile() or not (m.name == 'manifest.json' or
                   (m.name.startswith('packages/') and '/' not in m.name[len('packages/'):]
                    and m.name.endswith('.deb'))) for m in members):
                raise ValueError('Archive contains unexpected paths or file types')
            if len({m.name for m in members}) != len(members):
                raise ValueError('Archive contains duplicate paths')
            manifest_file = archive.extractfile('manifest.json')
            if manifest_file is None:
                raise ValueError('Missing manifest')
            meta = json.load(manifest_file)
            if meta.get('format') != 1 or any(meta.get(k) != v for k, v in identity().items()):
                raise ValueError('Bundle OS or architecture does not match this host')
            if meta.get('driver_suffix') != args.driver_suffix:
                raise ValueError('Bundle driver branch does not match requested branch')
            entries = meta['packages']
            expected = {'manifest.json'} | {'packages/' + e['file'] for e in entries}
            if expected != {m.name for m in members} or len(expected) != len(entries) + 1:
                raise ValueError('Manifest and archive members do not match')
            versions = {}
            blocks = []
            for entry in entries:
                filename = entry['file']
                if Path(filename).name != filename:
                    raise ValueError('Invalid package filename')
                out = temp / filename
                inp = archive.extractfile('packages/' + filename)
                if inp is None:
                    raise ValueError('Missing package: ' + filename)
                with out.open('xb') as stream:
                    shutil.copyfileobj(inp, stream)
                out.chmod(0o644)
                if digest(out) != entry['sha256']:
                    raise ValueError('Package checksum mismatch: ' + filename)
                f = fields(out)
                if (f['Package'], f['Version'], f['Architecture']) != (entry['package'], entry['version'], entry['arch']):
                    raise ValueError('Package metadata mismatch: ' + filename)
                if f['Package'] in versions:
                    raise ValueError('Multiple versions of package: ' + f['Package'])
                versions[f['Package']] = f['Version']
                control = subprocess.check_output(['dpkg-deb', '-f', str(out)], text=True).rstrip()
                blocks.append(control + '\nFilename: ' + filename + '\nSize: ' + str(out.stat().st_size) + '\nSHA256: ' + entry['sha256'] + '\n')
            wanted = required(args.driver_suffix)
            if any(versions.get(name) != meta['driver_version'] for name in wanted):
                raise ValueError('Required NVIDIA versions are missing or inconsistent')
            (temp / 'Packages').write_text('\n'.join(blocks))
            (temp / 'Packages').chmod(0o644)
        if final.exists():
            shutil.rmtree(final)
        os.rename(temp, final)
        print(json.dumps({'repository': str(final), 'driver_version': meta['driver_version'],
                          'packages': [name + '=' + versions[name] for name in wanted]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build')
    b.add_argument('--packages', type=Path, required=True)
    b.add_argument('--driver-suffix', required=True)
    b.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--sha256', required=True)
    p.add_argument('--driver-suffix', required=True)
    p.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    (build if args.command == 'build' else prepare)(args)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        print('NVIDIA cache:', exc, file=sys.stderr)
        sys.exit(1)
