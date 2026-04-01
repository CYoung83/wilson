# WILSON DEV ENVIRONMENT RUNBOOK
## iMac 27" (2017) — Fedora Silverblue
### Target: Dev starting line for Wilson v0.0.1

---

## PHASE 1: NETWORK & OS BASELINE

- [ ] Confirm Silverblue is current: `rpm-ostree status` then `rpm-ostree upgrade` if needed, reboot
- [ ] Set hostname: `sudo hostnamectl set-hostname wilson-dev`
- [ ] Assign static IP via Wi-Fi (NetworkManager):
  ```
  nmcli connection show                          # find your Wi-Fi connection name
  nmcli connection modify "<Wi-Fi SSID>" \
    ipv4.addresses 10.27.27.___/24 \
    ipv4.gateway 10.27.27.1 \
    ipv4.dns 10.27.27.22 \
    ipv4.method manual
  nmcli connection down "<Wi-Fi SSID>" && nmcli connection up "<Wi-Fi SSID>"
  ```
- [ ] Pick an IP outside your DHCP range (.50-.200) and not in your existing static assignments
- [ ] Verify connectivity: `ping 10.27.27.1` (pfSense) then `ping 10.27.27.4` (TrueNAS)
- [ ] Add DNS entry in pihole for `wilson-dev` pointing to the IP you chose
- [ ] Verify Ollama access from iMac: `curl http://10.27.27.201:11434/api/tags` (or wherever Ollama is bound on AI rig — confirm IP)

---

## PHASE 2: NFS MOUNTS TO TRUENAS

- [ ] Create a Wilson dataset on TrueNAS (or a folder within an existing dataset)
  - Suggested path on TrueNAS: `/mnt/tank/wilson` (adjust to your pool name)
  - NFS share permissions: read/write from wilson-dev IP, read-only from other hosts
- [ ] On the iMac, install NFS client (layered package on Silverblue):
  ```
  rpm-ostree install nfs-utils
  systemctl reboot
  ```
- [ ] Create mount point: `sudo mkdir -p /mnt/wilson-data`
- [ ] Test mount: `sudo mount -t nfs 10.27.27.4:/mnt/tank/wilson /mnt/wilson-data`
- [ ] Verify read/write: `touch /mnt/wilson-data/test && rm /mnt/wilson-data/test`
- [ ] Make persistent — add to `/etc/fstab`:
  ```
  10.27.27.4:/mnt/tank/wilson  /mnt/wilson-data  nfs  defaults,noauto,x-systemd.automount,x-systemd.idle-timeout=300  0  0
  ```
  (noauto + automount = mounts on access, doesn't block boot if NAS is down)
- [ ] Reboot and verify auto-mount works: `ls /mnt/wilson-data`

---

## PHASE 3: TOOLBOX CONTAINER

- [ ] Create the Wilson toolbox:
  ```
  toolbox create wilson-dev
  toolbox enter wilson-dev
  ```
- [ ] Inside the toolbox, update packages:
  ```
  sudo dnf update -y
  ```
- [ ] Install core development dependencies:
  ```
  sudo dnf install -y \
    python3 \
    python3-pip \
    python3-devel \
    git \
    gcc \
    gcc-c++ \
    make \
    jq \
    curl \
    wget \
    vim \
    tmux
  ```
- [ ] Verify Python version: `python3 --version` (should be 3.12+)
- [ ] Verify git: `git --version`

---

## PHASE 4: PYTHON ENVIRONMENT

- [ ] Inside the toolbox, create a project directory:
  ```
  mkdir -p ~/wilson && cd ~/wilson
  ```
- [ ] Initialize git repo:
  ```
  git init
  echo "venv/" > .gitignore
  echo "__pycache__/" >> .gitignore
  echo "*.pyc" >> .gitignore
  echo "data/" >> .gitignore
  ```
- [ ] Create Python virtual environment:
  ```
  python3 -m venv venv
  source venv/bin/activate
  ```
- [ ] Upgrade pip:
  ```
  pip install --upgrade pip
  ```
- [ ] Install Wilson core dependencies:
  ```
  pip install \
    eyecite \
    requests \
    pandas \
    jupyter \
    python-dotenv
  ```
- [ ] Verify eyecite works:
  ```python
  python3 -c "
  from eyecite import get_citations
  text = 'Foo v. Bar, 1 U.S. 2, 3-4 (1999)'
  cites = get_citations(text)
  print(f'Found {len(cites)} citation(s)')
  for c in cites:
      print(c)
  "
  ```
  Should return 1 citation with volume, reporter, page parsed out.
- [ ] Create requirements.txt: `pip freeze > requirements.txt`

---

## PHASE 5: DATASET ACQUISITION

All bulk data goes to `/mnt/wilson-data` (TrueNAS via NFS).
Working copies of active datasets go to `~/wilson/data/` (local disk).

- [ ] Create directory structure:
  ```
  mkdir -p /mnt/wilson-data/{courtlistener,cap,charlotin,wayback,working}
  mkdir -p ~/wilson/data
  ```

### 5a. Charlotin Database (you already have the CSV)
- [ ] Copy CSV to both locations:
  ```
  cp /path/to/Charlotin-hallucination_cases.csv /mnt/wilson-data/charlotin/
  cp /path/to/Charlotin-hallucination_cases.csv ~/wilson/data/
  ```
- [ ] Verify parse:
  ```python
  python3 -c "
  import pandas as pd
  df = pd.read_csv('data/Charlotin-hallucination_cases.csv')
  print(f'Rows: {len(df)}')
  print(f'Columns: {list(df.columns)}')
  print(f'Date range: {df[\"Date\"].min()} to {df[\"Date\"].max()}')
  "
  ```

### 5b. CourtListener API Token
- [ ] Register at courtlistener.com (free account)
- [ ] Get API token from: https://www.courtlistener.com/help/api/rest/
- [ ] Store token securely:
  ```
  echo "COURTLISTENER_TOKEN=your_token_here" > ~/wilson/.env
  chmod 600 ~/wilson/.env
  ```
- [ ] Test API access:
  ```
  source ~/wilson/.env
  curl -s -H "Authorization: Token $COURTLISTENER_TOKEN" \
    "https://www.courtlistener.com/api/rest/v3/clusters/?q=roe+v+wade" | jq '.count'
  ```

### 5c. CourtListener Bulk Data
- [ ] Review available bulk files at: https://www.courtlistener.com/api/bulk-data/
- [ ] Download courts table first (small, needed for everything else):
  ```
  cd /mnt/wilson-data/courtlistener
  wget https://www.courtlistener.com/api/bulk-data/courts/all.csv.gz
  gunzip all.csv.gz && mv all.csv courts.csv
  ```
- [ ] Download citations map (this is the core verification data):
  ```
  wget https://www.courtlistener.com/api/bulk-data/citations/all.csv.gz
  gunzip all.csv.gz && mv all.csv citations.csv
  ```
- [ ] Download opinion clusters (case metadata — larger file, may take time):
  ```
  wget https://www.courtlistener.com/api/bulk-data/clusters/all.csv.gz
  ```
  NOTE: The opinions bulk file (full text) is very large. Download it to NFS, not local.

### 5d. Harvard CAP via Hugging Face
- [ ] Install Hugging Face CLI:
  ```
  pip install huggingface_hub
  ```
- [ ] Download CAP dataset:
  ```
  cd /mnt/wilson-data/cap
  huggingface-cli download free-law/Caselaw_Access_Project --repo-type dataset --local-dir .
  ```
  NOTE: This is a large dataset. Let it run; it goes to NFS storage.
- [ ] Verify download completed and explore structure:
  ```
  ls -lh /mnt/wilson-data/cap/
  ```

### 5e. PACER Account (for later targeted retrieval)
- [ ] Register at pacer.uscourts.gov (free to register; $0.10/page to retrieve)
- [ ] Save credentials securely in .env file
- [ ] Do NOT bulk download anything from PACER yet — use RECAP/CourtListener first

---

## PHASE 6: FIRST SMOKE TEST

This confirms the entire pipeline works end to end before you write any Wilson code.

- [ ] Activate environment: `cd ~/wilson && source venv/bin/activate`
- [ ] Create `smoke_test.py`:
  ```python
  """
  Wilson v0.0.1 Smoke Test
  
  Takes one known-fabricated citation from the Charlotin database,
  extracts it with eyecite, and checks it against CourtListener API.
  """
  import os
  from dotenv import load_dotenv
  import requests
  from eyecite import get_citations
  
  load_dotenv()
  CL_TOKEN = os.getenv("COURTLISTENER_TOKEN")
  CL_HEADERS = {"Authorization": f"Token {CL_TOKEN}"}
  
  # Known fabricated citation from Mata v. Avianca (Charlotin row 1252)
  # "Varghese v. China Southern Airlines Co., Ltd., 925 F.3d 1339"
  test_text = "Varghese v. China Southern Airlines Co., Ltd., 925 F.3d 1339 (11th Cir. 2019)"
  
  # Step 1: Extract citation with eyecite
  citations = get_citations(test_text)
  print(f"[EXTRACT] Found {len(citations)} citation(s)")
  for c in citations:
      print(f"  Volume: {c.groups.get('volume', 'N/A')}")
      print(f"  Reporter: {c.groups.get('reporter', 'N/A')}")
      print(f"  Page: {c.groups.get('page', 'N/A')}")
  
  # Step 2: Check against CourtListener citation lookup
  if citations:
      c = citations[0]
      vol = c.groups.get('volume')
      reporter = c.groups.get('reporter')
      page = c.groups.get('page')
      
      lookup_url = (
          f"https://www.courtlistener.com/api/rest/v3/citation-lookup/"
          f"?reporter={reporter}&volume={vol}&page={page}"
      )
      print(f"\n[VERIFY] Checking: {vol} {reporter} {page}")
      
      resp = requests.get(lookup_url, headers=CL_HEADERS)
      results = resp.json()
      
      if resp.status_code == 200 and results.get('count', 0) > 0:
          print(f"  STATUS: FOUND — Citation exists in CourtListener")
          print(f"  Matches: {results['count']}")
      else:
          print(f"  STATUS: NOT FOUND — Citation does not exist in CourtListener")
          print(f"  (This is expected for a known fabrication)")
  
  print("\n[DONE] Smoke test complete.")
  ```
- [ ] Run it: `python3 smoke_test.py`
- [ ] Expected result: eyecite extracts the citation, CourtListener returns NOT FOUND
- [ ] If both steps work, Wilson's proof-of-concept pipeline is functional

---

## PHASE 7: GIT REMOTE & BACKUP

- [ ] Create GitHub repo: `wilson` (or `wilson-ai`) — public from day one (open source commitment)
- [ ] Add remote:
  ```
  cd ~/wilson
  git remote add origin git@github.com:<your-username>/wilson.git
  ```
- [ ] Create initial commit:
  ```
  git add .gitignore requirements.txt smoke_test.py
  git commit -m "Wilson v0.0.1: initial environment and smoke test"
  git push -u origin main
  ```
- [ ] Do NOT commit .env, data files, or API tokens
- [ ] Verify .gitignore excludes: `venv/`, `data/`, `.env`, `__pycache__/`

---

## AIR GAP PROCEDURE (when needed)

- [ ] Ensure all working datasets are copied to local disk (`~/wilson/data/`)
- [ ] Verify toolbox functions without network: `toolbox enter wilson-dev`
- [ ] Turn off Wi-Fi (System Settings > Wi-Fi > Off, or `nmcli radio wifi off`)
- [ ] Confirm no connectivity: `ping 10.27.27.1` should fail
- [ ] NFS mount will be unavailable — all work must use local copies
- [ ] Ollama will be unavailable — Wilson core (citation extraction + database lookup against local data) should still function
- [ ] To reconnect: `nmcli radio wifi on`

---

## REFERENCE: KEY PATHS

| Item | Path |
|------|------|
| Wilson project root | `~/wilson/` |
| Python venv | `~/wilson/venv/` |
| Local working data | `~/wilson/data/` |
| NFS bulk storage | `/mnt/wilson-data/` |
| API credentials | `~/wilson/.env` |
| Toolbox name | `wilson-dev` |
| iMac hostname | `wilson-dev` |

## REFERENCE: KEY URLS

| Source | URL |
|--------|-----|
| CourtListener API docs | https://www.courtlistener.com/help/api/rest/ |
| CourtListener bulk data | https://www.courtlistener.com/api/bulk-data/ |
| Harvard CAP | https://case.law |
| CAP on Hugging Face | https://huggingface.co/datasets/free-law/Caselaw_Access_Project |
| eyecite GitHub | https://github.com/freelawproject/eyecite |
| eyecite tutorial | https://github.com/freelawproject/eyecite/blob/main/TUTORIAL.ipynb |
| Charlotin database | https://www.damiencharlotin.com/ai-evidence/ |
| PACER | https://pacer.uscourts.gov |
| Wayback Machine CDX API | https://web.archive.org/cdx/search/cdx |

---

## CLASSIFICATION-FORWARD DESIGN NOTES

These don't matter today but are baked in for later portability:

- No cloud dependencies in the core pipeline. eyecite runs local. CourtListener data can be local after bulk download. Verification logic is pure Python.
- Air gap capability is built in from day one. The only network-dependent component is initial data acquisition and Ollama LLM calls. Core Wilson functions (extract, parse, verify against local DB) work offline.
- No proprietary dependencies. Every component is open source with permissive licensing (eyecite is BSD, CourtListener data is CC BY-ND, CAP is CC0).
- All API tokens are stored in .env, never committed. If this environment ever moves to a classified network, the .env pattern translates to whatever credential management system is in place.
- The toolbox container is reproducible. `requirements.txt` plus this runbook gets you from bare Silverblue to working dev environment on any hardware.
