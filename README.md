# UCloudAmp public site (first slice)

This repository contains the first public release slice for **Universal Cloud Amplifications LLC. (UCloudAmp)**.

## Company profile

- **Legal name:** Universal Cloud Amplifications LLC.
- **Brand:** UCloudAmp
- **Founder:** Chad Austerberry, Founder & Systems Architect
- **Location:** Hamburg, Pennsylvania, United States
- **Positioning:** Founder-led systems engineering focused on governed AI execution, traceable automation, and operator control.

## Repository purpose

A framework-free static website build pipeline:

`master.md` → validated Python transformation (`gcce-transform.py`) → `dist/`

`master.md` is the sole source for metadata, navigation, and site copy.

## Project maturity

- This is a bounded first public slice.
- ExecutionOS and the Governed Execution Gateway are described as ongoing engineering work with implemented/tested/specified/planned distinctions.
- Deployment is intentionally disabled in this slice.

## Local build and verification

```bash
python3 -m pip install -r requirements.txt
python3 gcce-transform.py --validate-only
python3 -m unittest discover -s tests -p 'test_*.py'
python3 gcce-transform.py --source master.md --dist dist
```

Repeat-build determinism check:

```bash
python3 gcce-transform.py --source master.md --dist /tmp/ucloudamp-dist-a
python3 gcce-transform.py --source master.md --dist /tmp/ucloudamp-dist-b
diff -u /tmp/ucloudamp-dist-a/manifest-sha256.txt /tmp/ucloudamp-dist-b/manifest-sha256.txt
```

## Deployment status

- Domain reference: `ucloudamp.com`
- No claim is made that the website is currently live.
- Azure deployment prerequisites and blockers are documented in `docs/deployment.md`.
