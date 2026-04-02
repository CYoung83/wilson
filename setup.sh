#!/usr/bin/env bash
# ==============================================================================
# Wilson Setup Script
# ==============================================================================
# Sets up Wilson on any Unix system (Linux, macOS).
# Run once after cloning the repo:
#
#   git clone https://github.com/CYoung83/wilson.git
#   cd wilson
#   chmod +x setup.sh
#   ./setup.sh
#
# Idempotent — safe to run multiple times.
# ==============================================================================

set -e

WILSON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$WILSON_DIR/venv"
ENV_FILE="$WILSON_DIR/.env"
ENV_EXAMPLE="$WILSON_DIR/.env.example"
DATA_DIR="$WILSON_DIR/data"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "============================================================"
echo " Wilson — AI Reasoning Auditor"
echo " Setup Script"
echo "============================================================"
echo ""

# ------------------------------------------------------------------------------
# Step 1: Check Python version
# ------------------------------------------------------------------------------
echo -e "${BLUE}[1/7] Checking Python version...${NC}"

if ! command -v python3 &>/dev/null; then
    echo -e "${RED}ERROR: python3 not found. Install Python 3.12+ and try again.${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 12 ]); then
    echo -e "${RED}ERROR: Python 3.12+ required. Found Python $PYTHON_VERSION.${NC}"
    exit 1
fi

echo -e "${GREEN}  Python $PYTHON_VERSION — OK${NC}"

# ------------------------------------------------------------------------------
# Step 2: Create virtual environment
# ------------------------------------------------------------------------------
echo ""
echo -e "${BLUE}[2/7] Setting up virtual environment...${NC}"

if [ -d "$VENV_DIR" ]; then
    echo -e "${GREEN}  Virtual environment already exists — skipping${NC}"
else
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}  Created venv at $VENV_DIR${NC}"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# ------------------------------------------------------------------------------
# Step 3: Install dependencies
# ------------------------------------------------------------------------------
echo ""
echo -e "${BLUE}[3/7] Installing dependencies...${NC}"

pip install --quiet --upgrade pip
pip install --quiet -r "$WILSON_DIR/requirements.txt"
echo -e "${GREEN}  Dependencies installed${NC}"

# ------------------------------------------------------------------------------
# Step 4: Configure .env
# ------------------------------------------------------------------------------
echo ""
echo -e "${BLUE}[4/7] Configuring environment...${NC}"

if [ -f "$ENV_FILE" ]; then
    echo -e "${GREEN}  .env already exists — skipping${NC}"
else
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo -e "${YELLOW}  Created .env from .env.example${NC}"
fi

# Check for CourtListener token
CL_TOKEN=$(grep "^COURTLISTENER_TOKEN=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'")

if [ -z "$CL_TOKEN" ] || [ "$CL_TOKEN" = "your_courtlistener_token_here" ]; then
    echo ""
    echo -e "${YELLOW}  CourtListener API token required for Wilson to function.${NC}"
    echo -e "  Get yours free at: ${BLUE}https://www.courtlistener.com/sign-in/${NC}"
    echo ""
    read -rp "  Enter your CourtListener API token (or press Enter to skip): " CL_TOKEN_INPUT

    if [ -n "$CL_TOKEN_INPUT" ]; then
        # Replace the placeholder in .env
        sed -i "s|COURTLISTENER_TOKEN=.*|COURTLISTENER_TOKEN=$CL_TOKEN_INPUT|" "$ENV_FILE"
        echo -e "${GREEN}  Token saved to .env${NC}"
    else
        echo -e "${YELLOW}  Skipped — add COURTLISTENER_TOKEN to .env before running Wilson${NC}"
    fi
else
    echo -e "${GREEN}  CourtListener token found${NC}"
fi

# ------------------------------------------------------------------------------
# Step 5: Bulk citation data (optional)
# ------------------------------------------------------------------------------
echo ""
echo -e "${BLUE}[5/7] Bulk citation data (optional)...${NC}"
echo ""
echo "  Wilson can verify citations offline against 18 million federal case"
echo "  records. This requires a ~1.9GB CSV file (~121MB compressed download)."
echo ""

# Check if already configured
EXISTING_CSV=$(grep "^CITATIONS_CSV=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'")

if [ -n "$EXISTING_CSV" ] && [ "$EXISTING_CSV" != "/path/to/citations-2026-03-31.csv" ] && [ -f "$EXISTING_CSV" ]; then
    echo -e "${GREEN}  Bulk CSV already configured at $EXISTING_CSV${NC}"
else
    read -rp "  Download bulk citation data? ~1.9GB uncompressed (y/N): " DOWNLOAD_CSV

    if [[ "$DOWNLOAD_CSV" =~ ^[Yy]$ ]]; then
        echo ""

        # Determine data directory
        echo "  Where should Wilson store bulk data?"
        echo "  Default: $DATA_DIR"
        read -rp "  Data directory (press Enter for default): " CUSTOM_DATA_DIR

        if [ -n "$CUSTOM_DATA_DIR" ]; then
            DATA_DIR="$CUSTOM_DATA_DIR"
        fi

        mkdir -p "$DATA_DIR"
        echo -e "  Downloading to $DATA_DIR..."

        # Get the latest bulk data URL
        BULK_URL="https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/citations-2026-03-31.csv.bz2"
        COMPRESSED="$DATA_DIR/citations-2026-03-31.csv.bz2"
        FINAL_CSV="$DATA_DIR/citations-2026-03-31.csv"

        if [ -f "$FINAL_CSV" ]; then
            echo -e "${GREEN}  CSV already exists at $FINAL_CSV — skipping download${NC}"
        else
            echo "  Downloading... (this may take a few minutes)"
            if command -v wget &>/dev/null; then
                wget -q --show-progress -O "$COMPRESSED" "$BULK_URL"
            elif command -v curl &>/dev/null; then
                curl -L --progress-bar -o "$COMPRESSED" "$BULK_URL"
            else
                echo -e "${RED}  ERROR: wget or curl required for download${NC}"
                exit 1
            fi

            echo "  Decompressing..."
            bunzip2 "$COMPRESSED"
            echo -e "${GREEN}  Downloaded and decompressed to $FINAL_CSV${NC}"
        fi

        # Update .env with CSV path
        if grep -q "^CITATIONS_CSV=" "$ENV_FILE"; then
            sed -i "s|CITATIONS_CSV=.*|CITATIONS_CSV=$FINAL_CSV|" "$ENV_FILE"
        else
            echo "CITATIONS_CSV=$FINAL_CSV" >> "$ENV_FILE"
        fi

        echo -e "${GREEN}  CITATIONS_CSV updated in .env${NC}"
    else
        echo -e "${YELLOW}  Skipped — Wilson will use API-only verification${NC}"
        echo "  You can download bulk data later and set CITATIONS_CSV in .env"
    fi
fi

# ------------------------------------------------------------------------------
# Step 6: Check Ollama (optional — Phase 3 coherence checking)
# ------------------------------------------------------------------------------
echo ""
echo -e "${BLUE}[6/7] Checking Ollama (Phase 3 coherence checking)...${NC}"

OLLAMA_HOST=$(grep "^OLLAMA_HOST=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'")
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
OLLAMA_MODEL=$(grep "^OLLAMA_MODEL=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'")
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3}"

if curl -s --connect-timeout 3 "$OLLAMA_HOST/api/tags" &>/dev/null; then
    echo -e "${GREEN}  Ollama reachable at $OLLAMA_HOST${NC}"

    # Check if configured model is available
    MODELS=$(curl -s "$OLLAMA_HOST/api/tags" | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = [m['name'] for m in data.get('models', [])]
print('\n'.join(models))
" 2>/dev/null)

    if echo "$MODELS" | grep -q "$OLLAMA_MODEL"; then
        echo -e "${GREEN}  Model $OLLAMA_MODEL loaded — Phase 3 ENABLED${NC}"
    else
        echo -e "${YELLOW}  Model $OLLAMA_MODEL not found${NC}"
        echo "  Available models:"
        echo "$MODELS" | sed 's/^/    /'
        echo ""
        echo "  To enable Phase 3, run: ollama pull $OLLAMA_MODEL"
        echo "  Or set OLLAMA_MODEL in .env to an available model"
    fi
else
    echo -e "${YELLOW}  Ollama not reachable at $OLLAMA_HOST${NC}"
    echo "  Phase 3 coherence checking will be skipped"
    echo "  Install Ollama at https://ollama.com to enable"
    echo "  Configure OLLAMA_HOST in .env if running on another machine"
fi

# ------------------------------------------------------------------------------
# Step 7: Run tests
# ------------------------------------------------------------------------------
echo ""
echo -e "${BLUE}[7/7] Running Wilson test suite...${NC}"
echo ""

cd "$WILSON_DIR"

TESTS_PASSED=0
TESTS_FAILED=0

# Test 1: smoke test
echo "  Running smoke_test.py (Phases 1 + 2)..."
if python3 smoke_test.py; then
    echo -e "${GREEN}  smoke_test.py — PASSED${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}  smoke_test.py — FAILED${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

echo ""

# Test 2: Mata v. Avianca proof of concept
echo "  Running test_mata_avianca.py (proof of concept)..."
if python3 test_mata_avianca.py; then
    echo -e "${GREEN}  test_mata_avianca.py — PASSED${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}  test_mata_avianca.py — FAILED${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

echo ""

# Test 3: Coherence check (optional)
echo "  Running coherence_check.py (Phase 3)..."
if python3 coherence_check.py; then
    echo -e "${GREEN}  coherence_check.py — PASSED${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${YELLOW}  coherence_check.py — SKIPPED or FAILED (Ollama required)${NC}"
fi

# ------------------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------------------
echo ""
echo "============================================================"
echo " Wilson Setup Complete"
echo "============================================================"
echo ""
echo -e "  Tests passed:  ${GREEN}$TESTS_PASSED${NC}"
if [ "$TESTS_FAILED" -gt 0 ]; then
    echo -e "  Tests failed:  ${RED}$TESTS_FAILED${NC}"
fi
echo ""
echo "  To run Wilson:"
echo "    source venv/bin/activate"
echo "    python3 smoke_test.py"
echo "    python3 test_mata_avianca.py"
echo "    python3 coherence_check.py"
echo ""
echo "  Configuration: .env"
echo "  Documentation: README.md"
echo "  API notes:     API_ACCESS_NOTES.md"
echo ""
echo -e "${GREEN}  Wilson is ready.${NC}"
echo ""
