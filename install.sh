#!/usr/bin/env bash
#
# One-shot installer for Bybit AI Trading Bot v2.1+
#
# This script sets up the complete environment for the trading bot:
# - Installs system dependencies
# - Creates Python virtual environment
# - Installs Python packages
# - Prompts for configuration (API keys, profile, universe mode, etc.)
# - Writes .env file
# - Updates config.yaml with universe settings
# - Optionally sets up systemd services
#
# Usage: bash install.sh
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory (repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

prompt_yes_no() {
    local prompt="$1"
    local default="${2:-Y}"
    local response
    
    if [[ "$default" == "Y" ]]; then
        read -p "$(echo -e "${BLUE}$prompt${NC} [Y/n]: ")" response
        response="${response:-Y}"
    else
        read -p "$(echo -e "${BLUE}$prompt${NC} [y/N]: ")" response
        response="${response:-N}"
    fi
    
    [[ "$response" =~ ^[Yy]$ ]]
}

prompt_input() {
    local prompt="$1"
    local default="${2:-}"
    local response
    
    if [[ -n "$default" ]]; then
        read -p "$(echo -e "${BLUE}$prompt${NC} [default: $default]: ")" response
        echo "${response:-$default}"
    else
        read -p "$(echo -e "${BLUE}$prompt${NC}: ")" response
        echo "$response"
    fi
}

prompt_secret() {
    local prompt="$1"
    local response
    
    # Print prompt to stderr (so it's visible even when output is captured)
    # Use printf for better compatibility than echo -ne
    printf "${BLUE}%s${NC}: " "$prompt" >&2
    
    # Use read -s for silent input (no echo of typed characters)
    # The -r flag prevents backslash interpretation
    # Read from /dev/tty to ensure we read from terminal, not stdin
    read -rs response < /dev/tty 2>/dev/null || read -rs response
    
    # Print newline to stderr after input (so it's visible)
    echo "" >&2
    
    # Output the response to stdout for capture
    echo "$response"
}

# Load .env file and export variables
load_env_file() {
    local env_file="$1"
    if [[ -f "$env_file" ]]; then
        # Read .env file and export variables (handles comments and empty lines)
        while IFS= read -r line || [[ -n "$line" ]]; do
            # Skip comments and empty lines
            [[ "$line" =~ ^[[:space:]]*# ]] && continue
            [[ -z "${line// }" ]] && continue
            
            # Export variable if it's in KEY=VALUE format
            if [[ "$line" =~ ^[[:space:]]*([^=]+)=(.*)$ ]]; then
                local key="${BASH_REMATCH[1]// /}"
                local value="${BASH_REMATCH[2]}"
                # Remove quotes if present (handles both single and double quotes)
                value="${value#\"}"
                value="${value%\"}"
                value="${value#\'}"
                value="${value%\'}"
                # Remove leading/trailing whitespace from key
                key="${key#"${key%%[![:space:]]*}"}"
                key="${key%"${key##*[![:space:]]}"}"
                # Remove leading/trailing whitespace from value
                value="${value#"${value%%[![:space:]]*}"}"
                value="${value%"${value##*[![:space:]]}"}"
                # Export the variable (using printf %q for safe handling, but simpler: just export)
                # For most cases, direct export works fine
                export "${key}"="${value}"
            fi
        done < "$env_file"
    fi
}

# Trap for cleanup on interrupt
cleanup() {
    log_warn "Installation interrupted. Partial changes may remain."
    exit 1
}
trap cleanup INT TERM

# Banner
echo ""
echo "=========================================="
echo "  Bybit AI Trading Bot v2.1+ Installer"
echo "=========================================="
echo ""
log_info "This script will set up your trading bot environment."
log_warn "Make sure you have your Bybit API keys ready."
echo ""

# (A) Pre-flight checks
log_info "Step 1: Pre-flight checks..."

# Check OS
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    log_warn "This script is designed for Linux (Ubuntu/Debian)."
    log_warn "Other operating systems may require manual setup."
    if ! prompt_yes_no "Continue anyway?" "N"; then
        exit 1
    fi
fi

# Check if Debian/Ubuntu
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    if [[ "$ID" != "debian" && "$ID" != "ubuntu" ]]; then
        log_warn "Detected OS: $ID (not Debian/Ubuntu)"
        log_warn "Some package installation steps may fail."
    fi
fi

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    log_info "Python 3 not found. Installing..."
    if prompt_yes_no "Install Python 3 and required system packages? (requires sudo)" "Y"; then
        sudo apt-get update
        sudo apt-get install -y python3 python3-venv python3-pip build-essential git
    else
        log_error "Python 3 is required. Please install manually and rerun this script."
        exit 1
    fi
else
    PYTHON_VERSION=$(python3 --version)
    log_success "Found $PYTHON_VERSION"
fi

# Check for git
if ! command -v git &> /dev/null; then
    log_info "Git not found. Installing..."
    if prompt_yes_no "Install git? (requires sudo)" "Y"; then
        sudo apt-get install -y git
    else
        log_warn "Git is recommended but not required. Continuing..."
    fi
fi

# Check for build tools (needed for some Python packages)
if ! command -v gcc &> /dev/null; then
    log_info "Build tools not found. Some Python packages may fail to install."
    if prompt_yes_no "Install build-essential? (requires sudo)" "Y"; then
        sudo apt-get install -y build-essential
    fi
fi

# Create required directories
log_info "Creating required directories..."
mkdir -p logs
mkdir -p data/raw/bybit
mkdir -p models
mkdir -p models/archive
log_success "Directories created"

# (B) Virtual environment setup
log_info ""
log_info "Step 2: Setting up Python virtual environment..."

VENV_PATH="$SCRIPT_DIR/venv"

if [[ -d "$VENV_PATH" ]]; then
    log_warn "Virtual environment already exists at $VENV_PATH"
    if prompt_yes_no "Reuse existing virtual environment?" "Y"; then
        log_info "Reusing existing virtual environment"
        log_info "Clearing Python bytecode cache to avoid stale imports..."
        # Clear __pycache__ directories in the project
        find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        find "$SCRIPT_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
        find "$SCRIPT_DIR" -type f -name "*.pyo" -delete 2>/dev/null || true
        log_success "Python cache cleared"
    else
        if prompt_yes_no "Delete and recreate virtual environment?" "N"; then
            log_info "Removing existing virtual environment..."
            rm -rf "$VENV_PATH"
            python3 -m venv "$VENV_PATH"
            log_success "Virtual environment recreated"
        else
            log_info "Keeping existing virtual environment"
        fi
    fi
else
    log_info "Creating new virtual environment..."
    python3 -m venv "$VENV_PATH"
    log_success "Virtual environment created"
fi

# Activate venv and upgrade pip
log_info "Activating virtual environment and upgrading pip..."
source "$VENV_PATH/bin/activate"
pip install --upgrade pip --quiet
log_success "Pip upgraded"

# Install Python dependencies
log_info "Installing Python dependencies (this may take a few minutes)..."
if [[ -f requirements.txt ]]; then
    pip install -r requirements.txt
    log_success "Python dependencies installed"
else
    log_error "requirements.txt not found!"
    exit 1
fi

# Clear Python import cache after installation (important if venv was reused)
log_info "Clearing Python import cache..."
find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$SCRIPT_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$SCRIPT_DIR" -type f -name "*.pyo" -delete 2>/dev/null || true
log_success "Import cache cleared"

# (C) Interactive secret/config prompts
log_info ""
log_info "Step 3: Configuration"
log_info "Please provide the following information:"
echo ""

# Bybit API credentials
log_info "Bybit API Configuration:"
BYBIT_API_KEY=$(prompt_input "Enter Bybit API Key" "")
if [[ -z "$BYBIT_API_KEY" ]]; then
    log_error "API key is required!"
    exit 1
fi

BYBIT_API_SECRET=$(prompt_secret "Enter Bybit API Secret")
# Trim only leading/trailing whitespace (preserve internal spaces/special chars)
BYBIT_API_SECRET="${BYBIT_API_SECRET#"${BYBIT_API_SECRET%%[![:space:]]*}"}"
BYBIT_API_SECRET="${BYBIT_API_SECRET%"${BYBIT_API_SECRET##*[![:space:]]}"}"

if [[ -z "$BYBIT_API_SECRET" ]]; then
    log_error "API secret is required!"
    log_error "   The secret input appears to be empty. Please ensure you type it correctly."
    exit 1
fi

# Debug: Verify secret was captured (show length only, not value)
if [[ ${#BYBIT_API_SECRET} -gt 0 ]]; then
    log_info "✓ API secret captured (length: ${#BYBIT_API_SECRET} characters)"
else
    log_error "❌ API secret appears to be empty after capture!"
    exit 1
fi

# Testnet vs Live
log_info ""
if prompt_yes_no "Use Bybit testnet? (HIGHLY RECOMMENDED for initial testing)" "Y"; then
    BYBIT_TESTNET="true"
    log_info "Testnet mode enabled (recommended)"
else
    BYBIT_TESTNET="false"
    log_warn "LIVE trading mode selected. Proceed with caution!"
    if ! prompt_yes_no "Are you sure you want to use LIVE trading?" "N"; then
        BYBIT_TESTNET="true"
        log_info "Switched to testnet mode"
    fi
fi

# Default profile
log_info ""
log_info "Select default trading profile:"
echo "  [1] profile_conservative (Recommended for first deployment)"
echo "  [2] profile_moderate (After validation)"
echo "  [3] profile_aggressive (EXPERIMENTAL - Use with extreme caution)"
echo ""
PROFILE_CHOICE=$(prompt_input "Enter profile number [1-3]" "1")

case "$PROFILE_CHOICE" in
    1)
        DEFAULT_PROFILE="profile_conservative"
        log_info "Selected: Conservative profile"
        ;;
    2)
        DEFAULT_PROFILE="profile_moderate"
        log_info "Selected: Moderate profile"
        ;;
    3)
        DEFAULT_PROFILE="profile_aggressive"
        log_warn "Selected: Aggressive profile (EXPERIMENTAL)"
        ;;
    *)
        DEFAULT_PROFILE="profile_conservative"
        log_warn "Invalid choice, defaulting to conservative"
        ;;
esac

# Model training mode selection
log_info ""
log_info "Model Training Mode:"
echo "  [1] single_symbol (Train on one symbol, shared model - Recommended for first deployment)"
echo "  [2] multi_symbol (Train on multiple symbols with symbol encoding - More robust)"
echo ""
TRAINING_MODE_CHOICE=$(prompt_input "Enter training mode [1-2]" "1")

case "$TRAINING_MODE_CHOICE" in
    1)
        MODEL_TRAINING_MODE="single_symbol"
        log_info "Selected: Single-symbol training mode"
        ;;
    2)
        MODEL_TRAINING_MODE="multi_symbol"
        log_info "Selected: Multi-symbol training mode"
        ;;
    *)
        MODEL_TRAINING_MODE="single_symbol"
        log_warn "Invalid choice, defaulting to single_symbol"
        ;;
esac

# Symbol encoding (if multi_symbol)
MODEL_SYMBOL_ENCODING="one_hot"
MULTI_SYMBOL_SYMBOLS=""
if [[ "$MODEL_TRAINING_MODE" == "multi_symbol" ]]; then
    log_info ""
    log_info "Symbol Encoding Method:"
    echo "  [1] one_hot (Safer, more interpretable - Recommended)"
    echo "  [2] index (Compact, less interpretable)"
    echo ""
    ENCODING_CHOICE=$(prompt_input "Enter encoding method [1-2]" "1")
    
    case "$ENCODING_CHOICE" in
        1)
            MODEL_SYMBOL_ENCODING="one_hot"
            log_info "Selected: One-hot encoding"
            ;;
        2)
            MODEL_SYMBOL_ENCODING="index"
            log_info "Selected: Index encoding"
            ;;
        *)
            MODEL_SYMBOL_ENCODING="one_hot"
            log_warn "Invalid choice, defaulting to one_hot"
            ;;
    esac
    
    log_info ""
    log_info "Multi-Symbol Training Configuration:"
    echo "  [1] Use auto universe (discover symbols dynamically during training)"
    echo "  [2] Specify core symbols manually (comma-separated, e.g., BTCUSDT,ETHUSDT,SOLUSDT)"
    echo ""
    MULTI_SYMBOL_CHOICE=$(prompt_input "Enter choice [1-2]" "1")
    
    case "$MULTI_SYMBOL_CHOICE" in
        1)
            MULTI_SYMBOL_SYMBOLS=""  # Empty = use universe
            log_info "Selected: Use auto universe for training"
            ;;
        2)
            MULTI_SYMBOL_SYMBOLS=$(prompt_input "Enter core symbols (comma-separated)" "BTCUSDT,ETHUSDT,SOLUSDT,DOGEUSDT,LINKUSDT")
            log_info "Selected: Manual symbol list: $MULTI_SYMBOL_SYMBOLS"
            ;;
        *)
            MULTI_SYMBOL_SYMBOLS=""
            log_warn "Invalid choice, defaulting to auto universe"
            ;;
    esac
fi

# Universe mode selection
log_info ""
log_info "Universe Discovery Mode:"
echo "  [1] fixed (Recommended for first deployment - uses explicit symbol list)"
echo "  [2] auto (Dynamic discovery from Bybit - requires API access)"
echo ""
UNIVERSE_CHOICE=$(prompt_input "Enter universe mode [1-2]" "1")

case "$UNIVERSE_CHOICE" in
    1)
        UNIVERSE_MODE="fixed"
        log_info "Selected: Fixed mode (will use symbols from config.yaml)"
        ;;
    2)
        UNIVERSE_MODE="auto"
        log_info "Selected: Auto mode (will discover symbols dynamically)"
        log_warn "Auto mode requires API access and makes additional API calls"
        ;;
    *)
        UNIVERSE_MODE="fixed"
        log_warn "Invalid choice, defaulting to fixed mode"
        ;;
esac

# Universe settings (if auto mode)
UNIVERSE_MIN_VOLUME=""
UNIVERSE_MAX_SYMBOLS=""
if [[ "$UNIVERSE_MODE" == "auto" ]]; then
    log_info ""
    log_info "Universe Filtering Settings (for auto mode):"
    UNIVERSE_MIN_VOLUME=$(prompt_input "Minimum 24h USD volume (e.g., 50000000 for \$50M)" "50000000")
    UNIVERSE_MAX_SYMBOLS=$(prompt_input "Maximum symbols to include (e.g., 10 for testing, 30 for production)" "10")
    
    # Calculate volume in millions for display (handle empty/unset safely)
    if [[ -n "${UNIVERSE_MIN_VOLUME:-}" ]] && [[ "$UNIVERSE_MIN_VOLUME" =~ ^[0-9]+$ ]]; then
        VOLUME_MILLIONS=$((UNIVERSE_MIN_VOLUME / 1000000))
        log_info "Universe will filter symbols with >= \$${VOLUME_MILLIONS}M volume, max $UNIVERSE_MAX_SYMBOLS symbols"
    else
        log_info "Universe will filter symbols with >= \$${UNIVERSE_MIN_VOLUME:-50000000} volume, max $UNIVERSE_MAX_SYMBOLS symbols"
    fi
fi

# Discord webhook
log_info ""
DISCORD_WEBHOOK=$(prompt_input "Enter Discord webhook URL for alerts (leave blank to skip)" "")
if [[ -n "$DISCORD_WEBHOOK" ]]; then
    log_info "Discord webhook configured"
else
    log_info "Discord alerts disabled"
fi

# (D) Writing environment/config files
log_info ""
log_info "Step 4: Writing configuration files..."

ENV_FILE="$SCRIPT_DIR/.env"
ENV_BACKUP=""
ENV_CHOICE=""

# Handle existing .env file
if [[ -f "$ENV_FILE" ]]; then
    log_warn ".env file already exists"
    echo "  [1] Append/merge new values (update duplicates)"
    echo "  [2] Backup existing and create new"
    echo "  [3] Keep existing unchanged (skip writing .env)"
    echo ""
    ENV_CHOICE=$(prompt_input "Choose option [1-3]" "1")
    
    case "$ENV_CHOICE" in
        1)
            log_info "Merging with existing .env..."
            # Backup first
            ENV_BACKUP="${ENV_FILE}.backup_$(date +%Y%m%d_%H%M%S)"
            cp "$ENV_FILE" "$ENV_BACKUP"
            log_info "Backup created: $ENV_BACKUP"
            ;;
        2)
            ENV_BACKUP="${ENV_FILE}.backup_$(date +%Y%m%d_%H%M%S)"
            mv "$ENV_FILE" "$ENV_BACKUP"
            log_info "Existing .env backed up to: $ENV_BACKUP"
            ;;
        3)
            log_info "Keeping existing .env unchanged"
            ENV_FILE=""  # Skip writing
            ;;
    esac
fi

# Write .env file
if [[ -n "$ENV_FILE" ]]; then
    log_info "Writing .env file..."
    
    # If merging, read existing values first
    if [[ -n "$ENV_BACKUP" ]] && [[ -f "$ENV_BACKUP" ]] && [[ "$ENV_CHOICE" == "1" ]]; then
        # Read existing .env and preserve non-conflicting variables
        declare -A existing_vars
        while IFS='=' read -r key value || [[ -n "$key" ]]; do
            # Skip comments and empty lines
            [[ "$key" =~ ^#.*$ ]] && continue
            [[ -z "$key" ]] && continue
            # Remove leading/trailing whitespace
            key=$(echo "$key" | xargs)
            value=$(echo "$value" | xargs)
            existing_vars["$key"]="$value"
        done < "$ENV_BACKUP"
        
        # Verify variables are set before writing
        if [[ -z "${BYBIT_API_SECRET:-}" ]]; then
            log_error "❌ BYBIT_API_SECRET variable is empty before writing .env file!"
            log_error "   This suggests the secret was not captured correctly during input."
            log_error "   Please re-run the installer and ensure you type the secret correctly."
            exit 1
        fi
        
        # Write merged .env
        {
            echo "# Bybit AI Trading Bot v2.1+ - Environment Configuration"
            echo "# Generated by install.sh on $(date)"
            echo ""
            echo "# Bybit API Credentials"
            printf "BYBIT_API_KEY=%s\n" "$BYBIT_API_KEY"
            printf "BYBIT_API_SECRET=%s\n" "$BYBIT_API_SECRET"
            printf "BYBIT_TESTNET=%s\n" "$BYBIT_TESTNET"
            echo ""
            echo "# Default Trading Profile"
            echo "# Options: profile_conservative, profile_moderate, profile_aggressive"
            echo "DEFAULT_PROFILE=$DEFAULT_PROFILE"
            echo ""
            echo "# Discord Alerts (Optional)"
            if [[ -n "$DISCORD_WEBHOOK" ]]; then
                echo "DISCORD_WEBHOOK_URL=$DISCORD_WEBHOOK"
            else
                echo "# DISCORD_WEBHOOK_URL="
            fi
            echo ""
            echo "# Additional Configuration (preserved from existing .env)"
            for key in "${!existing_vars[@]}"; do
                # Skip keys we just wrote
                if [[ "$key" != "BYBIT_API_KEY" && "$key" != "BYBIT_API_SECRET" && \
                      "$key" != "BYBIT_TESTNET" && "$key" != "DEFAULT_PROFILE" && \
                      "$key" != "DISCORD_WEBHOOK_URL" ]]; then
                    echo "$key=${existing_vars[$key]}"
                fi
            done
        } > "$ENV_FILE"
    else
        # Verify variables are set before writing
        if [[ -z "${BYBIT_API_SECRET:-}" ]]; then
            log_error "❌ BYBIT_API_SECRET variable is empty before writing .env file!"
            log_error "   Variable length: ${#BYBIT_API_SECRET}"
            log_error "   This suggests the secret was not captured correctly during input."
            log_error "   Please re-run the installer and ensure you type the secret correctly."
            exit 1
        fi
        
        # Write new .env file
        # Use printf to safely write values (handles special characters)
        {
            echo "# Bybit AI Trading Bot v2.1+ - Environment Configuration"
            echo "# Generated by install.sh on $(date)"
            echo ""
            echo "# Bybit API Credentials"
            printf "BYBIT_API_KEY=%s\n" "$BYBIT_API_KEY"
            printf "BYBIT_API_SECRET=%s\n" "$BYBIT_API_SECRET"
            printf "BYBIT_TESTNET=%s\n" "$BYBIT_TESTNET"
            echo ""
            echo "# Default Trading Profile"
            echo "# Options: profile_conservative, profile_moderate, profile_aggressive"
            printf "DEFAULT_PROFILE=%s\n" "$DEFAULT_PROFILE"
            echo ""
            echo "# Discord Alerts (Optional)"
            if [[ -n "$DISCORD_WEBHOOK" ]]; then
                printf "DISCORD_WEBHOOK_URL=%s\n" "$DISCORD_WEBHOOK"
            else
                echo "# DISCORD_WEBHOOK_URL="
            fi
            echo ""
            echo "# Additional Configuration"
            echo "# You can add more environment variables here as needed"
        } > "$ENV_FILE"
    fi
    
    # Set restrictive permissions
    chmod 600 "$ENV_FILE" 2>/dev/null || log_warn "Could not set .env permissions (may need manual chmod 600)"
    
    # Verify .env file was written correctly
    if [[ -f "$ENV_FILE" ]]; then
        if grep -q "^BYBIT_API_KEY=" "$ENV_FILE" && grep -q "^BYBIT_API_SECRET=" "$ENV_FILE"; then
            API_KEY_LINE=$(grep "^BYBIT_API_KEY=" "$ENV_FILE" | head -1 | cut -d'=' -f2- | xargs)
            API_SECRET_LINE=$(grep "^BYBIT_API_SECRET=" "$ENV_FILE" | head -1 | cut -d'=' -f2- | xargs)
            if [[ -z "$API_KEY_LINE" ]]; then
                log_warn "⚠️  BYBIT_API_KEY appears empty in .env file"
            fi
            if [[ -z "$API_SECRET_LINE" ]]; then
                log_error "❌ BYBIT_API_SECRET is EMPTY in .env file!"
                log_error "   Variable value before write: ${BYBIT_API_SECRET:+SET (length: ${#BYBIT_API_SECRET})}${BYBIT_API_SECRET:-EMPTY}"
                log_error "   Variable value after write check: ${API_SECRET_LINE:+SET}${API_SECRET_LINE:-EMPTY}"
                log_error "   This will cause API authentication to fail."
                log_error "   Please check the .env file: cat $ENV_FILE | grep BYBIT_API_SECRET"
                log_error "   You may need to manually edit the .env file and add your API secret."
                log_error "   Or re-run the installer and ensure you type the secret correctly."
            else
                log_success ".env file written to $ENV_FILE (API keys verified)"
            fi
        else
            log_warn "⚠️  Could not verify API keys in .env file"
        fi
    else
        log_error "❌ .env file was not created!"
    fi
fi

# Update config.yaml with universe settings
CONFIG_FILE="$SCRIPT_DIR/config/config.yaml"
if [[ -f "$CONFIG_FILE" ]]; then
    log_info "Updating config.yaml with universe settings..."
    
    # Backup config.yaml
    CONFIG_BACKUP="${CONFIG_FILE}.backup_$(date +%Y%m%d_%H%M%S)"
    cp "$CONFIG_FILE" "$CONFIG_BACKUP"
    log_info "Config backup created: $CONFIG_BACKUP"
    
    # Use Python to update YAML (more reliable than sed for YAML)
    if [[ -d "$VENV_PATH" ]]; then
        source "$VENV_PATH/bin/activate"
        cd "$SCRIPT_DIR"
        export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
        
        python3 <<PYTHON_SCRIPT
import yaml
import sys

config_path = "$CONFIG_FILE"
universe_mode = "$UNIVERSE_MODE"
min_volume = "$UNIVERSE_MIN_VOLUME"
max_symbols = "$UNIVERSE_MAX_SYMBOLS"
training_mode = "$MODEL_TRAINING_MODE"
symbol_encoding = "$MODEL_SYMBOL_ENCODING"
multi_symbol_symbols = "$MULTI_SYMBOL_SYMBOLS"

try:
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Ensure exchange section exists
    if 'exchange' not in config:
        config['exchange'] = {}
    
    # Update universe settings
    config['exchange']['universe_mode'] = universe_mode
    
    if universe_mode == 'auto':
        if min_volume:
            config['exchange']['min_usd_volume_24h'] = int(min_volume)
        if max_symbols:
            config['exchange']['max_symbols'] = int(max_symbols)
    
    # Ensure model section exists
    if 'model' not in config:
        config['model'] = {}
    
    # Update model training settings
    config['model']['training_mode'] = training_mode
    config['model']['symbol_encoding'] = symbol_encoding
    
    if training_mode == 'multi_symbol' and multi_symbol_symbols:
        # Parse comma-separated symbols into list
        symbols_list = [s.strip() for s in multi_symbol_symbols.split(',') if s.strip()]
        config['model']['multi_symbol_symbols'] = symbols_list
    elif training_mode == 'multi_symbol':
        # Empty list means use universe
        config['model']['multi_symbol_symbols'] = []
    
    # Set new symbol onboarding defaults
    config['model']['auto_train_new_symbols'] = True
    config['model']['block_untrained_symbols'] = True
    config['model']['target_history_days'] = 730  # Target: up to 2 years
    config['model']['min_history_days_to_train'] = 90  # Minimum: 3 months
    config['model']['min_history_coverage_pct'] = 0.95
    config['model']['block_short_history_symbols'] = True
    
    # Write back
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    print(f"Updated config.yaml:")
    print(f"  universe_mode={universe_mode}")
    if universe_mode == 'auto':
        print(f"  min_usd_volume_24h={min_volume}")
        print(f"  max_symbols={max_symbols}")
    print(f"  model.training_mode={training_mode}")
    print(f"  model.symbol_encoding={symbol_encoding}")
    if training_mode == 'multi_symbol' and multi_symbol_symbols:
        print(f"  model.multi_symbol_symbols={multi_symbol_symbols}")
except Exception as e:
    print(f"Warning: Could not update config.yaml: {e}", file=sys.stderr)
    sys.exit(1)
PYTHON_SCRIPT
        
        if [[ $? -eq 0 ]]; then
            log_success "config.yaml updated with universe settings"
        else
            log_warn "Could not update config.yaml (you may need to set universe_mode manually)"
        fi
        
        deactivate 2>/dev/null || true
    else
        log_warn "Virtual environment not found, cannot update config.yaml automatically"
        log_info "Please manually set universe_mode=$UNIVERSE_MODE in config/config.yaml"
    fi
else
    log_warn "config.yaml not found, skipping universe settings update"
fi

# (E) Optional systemd/cron integration
log_info ""
if prompt_yes_no "Set up systemd services for live trading and scheduled retraining?" "N"; then
    log_info "Step 5: Setting up systemd services..."
    
    SYSTEMD_DIR="$SCRIPT_DIR/systemd"
    mkdir -p "$SYSTEMD_DIR"
    
    # Get absolute paths
    ABS_SCRIPT_DIR="$(cd "$SCRIPT_DIR" && pwd)"
    ABS_VENV="$ABS_SCRIPT_DIR/venv"
    ABS_ENV_FILE="$ABS_SCRIPT_DIR/.env"
    
    # Get current user (fallback if $USER not set)
    # Use parameter expansion with default, then verify
    if [[ -n "${USER:-}" ]]; then
        CURRENT_USER="$USER"
    else
        CURRENT_USER=$(whoami 2>/dev/null || echo "root")
    fi
    
    # Ensure CURRENT_USER is set (handle edge cases)
    if [[ -z "${CURRENT_USER:-}" ]]; then
        CURRENT_USER="root"
        log_warn "Could not determine current user, defaulting to 'root'"
    fi
    
    # Generate live bot service
    cat > "$SYSTEMD_DIR/bybit-bot-live.service" <<EOF
[Unit]
Description=Bybit AI Trading Bot (Live Trading)
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$ABS_SCRIPT_DIR
Environment="PATH=$ABS_VENV/bin"
ExecStart=$ABS_VENV/bin/python $ABS_SCRIPT_DIR/live_bot.py --config config/config.yaml
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
    
    # Generate retrain service
    cat > "$SYSTEMD_DIR/bybit-bot-retrain.service" <<EOF
[Unit]
Description=Bybit AI Trading Bot (Scheduled Retraining)
After=network.target

[Service]
Type=oneshot
User=$CURRENT_USER
WorkingDirectory=$ABS_SCRIPT_DIR
Environment="PATH=$ABS_VENV/bin"
ExecStart=$ABS_VENV/bin/python $ABS_SCRIPT_DIR/scripts/scheduled_retrain.py
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    
    # Generate retrain timer
    cat > "$SYSTEMD_DIR/bybit-bot-retrain.timer" <<EOF
[Unit]
Description=Bybit AI Trading Bot Retraining Timer
Requires=bybit-bot-retrain.service

[Timer]
# Run weekly on Sunday at 3:00 AM
OnCalendar=Sun *-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
    
    log_success "Systemd service files created in $SYSTEMD_DIR"
    echo ""
    log_info "To enable these services, run the following commands as root:"
    echo ""
    echo "  # Copy service files"
    echo "  sudo cp $SYSTEMD_DIR/bybit-bot-live.service /etc/systemd/system/"
    echo "  sudo cp $SYSTEMD_DIR/bybit-bot-retrain.service /etc/systemd/system/"
    echo "  sudo cp $SYSTEMD_DIR/bybit-bot-retrain.timer /etc/systemd/system/"
    echo ""
    echo "  # Reload systemd"
    echo "  sudo systemctl daemon-reload"
    echo ""
    echo "  # Enable and start services (DO NOT START LIVE BOT YET!)"
    echo "  # sudo systemctl enable bybit-bot-retrain.timer"
    echo "  # sudo systemctl start bybit-bot-retrain.timer"
    echo ""
    echo "  # For live bot (ONLY after testnet validation):"
    echo "  # sudo systemctl enable bybit-bot-live.service"
    echo "  # sudo systemctl start bybit-bot-live.service"
    echo ""
    log_warn "DO NOT start the live bot service until you have:"
    log_warn "  1. Completed testnet validation (2+ weeks)"
    log_warn "  2. Reviewed and adjusted configuration"
    log_warn "  3. Verified all safety controls are active"
    echo ""
    
    # Cron alternative
    log_info "Alternative: Cron setup (if you prefer cron over systemd):"
    echo ""
    echo "  # Add to crontab (crontab -e):"
    echo "  # Weekly retraining on Sunday at 3:00 AM"
    echo "  0 3 * * 0 cd $ABS_SCRIPT_DIR && $ABS_VENV/bin/python scripts/scheduled_retrain.py >> logs/retrain_cron.log 2>&1"
    echo ""
else
    log_info "Skipping systemd setup"
fi

# (F) Optional initial steps
log_info ""
log_info "Step 6: Optional initial setup steps"

# Check if data already exists before prompting
DATA_EXISTS=false
SKIP_DATA_FETCH=false  # Initialize to avoid unbound variable error
if [[ -d "$SCRIPT_DIR/data/raw/bybit" ]] || [[ -d "$SCRIPT_DIR/data/historical" ]]; then
    # Check for any parquet files
    if find "$SCRIPT_DIR/data" -name "*.parquet" -type f 2>/dev/null | grep -q .; then
        DATA_EXISTS=true
        log_info "Found existing data files in data/ directory"
    fi
fi

if [[ "$DATA_EXISTS" == "true" ]]; then
    if prompt_yes_no "Historical data files already exist. Re-download anyway?" "N"; then
        log_info "Re-downloading historical data..."
        SKIP_DATA_FETCH=false  # User wants to re-download
    else
        log_info "Skipping data download (using existing data)"
        SKIP_DATA_FETCH=true  # User wants to skip
    fi
else
    SKIP_DATA_FETCH=false  # No data exists, can proceed
fi

if [[ "$SKIP_DATA_FETCH" != "true" ]] && prompt_yes_no "Do you want to fetch historical data now?" "N"; then
    log_info "Fetching historical data..."
    
    # If auto universe mode, let user choose symbols or use discovered ones
    if [[ "$UNIVERSE_MODE" == "auto" ]]; then
        log_info "Auto universe mode detected. You can:"
        echo "  [1] Fetch data for specific symbol(s)"
        echo "  [2] Test universe discovery first (recommended)"
        echo ""
        FETCH_CHOICE=$(prompt_input "Choose option [1-2]" "2")
        
        if [[ "$FETCH_CHOICE" == "2" ]]; then
            log_info "Testing universe discovery..."
            if [[ -d "$VENV_PATH" ]]; then
                source "$VENV_PATH/bin/activate"
                cd "$SCRIPT_DIR"
                # Load .env file to export API keys for the test
                load_env_file "$SCRIPT_DIR/.env"
                export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
                # Debug: Show what's in environment
                if [[ -n "${BYBIT_API_SECRET:-}" ]]; then
                    log_info "✓ BYBIT_API_SECRET is set in environment (length: ${#BYBIT_API_SECRET})"
                else
                    log_warn "⚠️  BYBIT_API_SECRET is NOT set in environment"
                fi
                python3 scripts/test_universe.py || log_warn "Universe test completed with warnings"
                deactivate 2>/dev/null || true
                
                # After successful test, offer to fetch data for discovered symbols
                if prompt_yes_no "Fetch data for discovered symbols?" "Y"; then
                    log_info "Discovering symbols and fetching data..."
                    source "$VENV_PATH/bin/activate"
                    cd "$SCRIPT_DIR"
                    load_env_file "$SCRIPT_DIR/.env"
                    export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
                    
                    # Discover symbols
                    DISCOVERED_SYMBOLS=$(python3 <<PYTHON_SCRIPT
import sys
import json
from src.config.config_loader import load_config
from src.exchange.universe import UniverseManager

try:
    config = load_config()
    universe_manager = UniverseManager(config)
    symbols = universe_manager.get_symbols(force_refresh=True)
    print(json.dumps(symbols))
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
PYTHON_SCRIPT
)
                    
                    if [[ $? -eq 0 ]] && [[ -n "$DISCOVERED_SYMBOLS" ]]; then
                        SYMBOLS_TO_FETCH=($(echo "$DISCOVERED_SYMBOLS" | python3 -c "import sys, json; symbols = json.load(sys.stdin); print(' '.join(symbols))"))
                        YEARS=$(prompt_input "Enter years of history" "2")
                        
                        log_info "Fetching data for ${#SYMBOLS_TO_FETCH[@]} symbols: ${SYMBOLS_TO_FETCH[*]}"
                        for SYMBOL in "${SYMBOLS_TO_FETCH[@]}"; do
                            log_info "Fetching data for $SYMBOL..."
                            python3 scripts/fetch_and_check_data.py \
                                --symbol "$SYMBOL" \
                                --years "$YEARS" \
                                --timeframe 60 || log_warn "Data fetch for $SYMBOL completed with warnings"
                        done
                    else
                        log_warn "Could not discover symbols. You can fetch data manually later."
                    fi
                    deactivate 2>/dev/null || true
                fi
            fi
        else
            SYMBOL=$(prompt_input "Enter symbol (e.g., BTCUSDT)" "BTCUSDT")
            YEARS=$(prompt_input "Enter years of history" "2")
            
            log_info "Running data fetch..."
            if [[ -d "$VENV_PATH" ]]; then
                source "$VENV_PATH/bin/activate"
                cd "$SCRIPT_DIR"
                # Load .env file to export API keys
                load_env_file "$SCRIPT_DIR/.env"
                export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
                python3 scripts/fetch_and_check_data.py \
                    --symbol "$SYMBOL" \
                    --years "$YEARS" \
                    --timeframe 60 || log_warn "Data fetch completed with warnings (check logs)"
                deactivate 2>/dev/null || true
            else
                log_error "Virtual environment not found, cannot fetch data"
            fi
        fi
    else
        # Fixed mode - prompt for symbol
        SYMBOL=$(prompt_input "Enter symbol (e.g., BTCUSDT)" "BTCUSDT")
        YEARS=$(prompt_input "Enter years of history" "2")
        
        log_info "Running data fetch..."
        if [[ -d "$VENV_PATH" ]]; then
            source "$VENV_PATH/bin/activate"
            cd "$SCRIPT_DIR"
            # Load .env file to export API keys
            load_env_file "$SCRIPT_DIR/.env"
            export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
            python3 scripts/fetch_and_check_data.py \
                --symbol "$SYMBOL" \
                --years "$YEARS" \
                --timeframe 60 || log_warn "Data fetch completed with warnings (check logs)"
            deactivate 2>/dev/null || true
        else
            log_error "Virtual environment not found, cannot fetch data"
        fi
    fi
fi

if prompt_yes_no "Do you want to train an initial model now?" "N"; then
    log_info "Training initial model (mode: $MODEL_TRAINING_MODE)..."
    
    # Determine symbols based on training mode
    if [[ "$MODEL_TRAINING_MODE" == "multi_symbol" ]]; then
        # Multi-symbol: symbols already configured in config.yaml
        SYMBOLS_TO_TRAIN=()  # Not used for multi-symbol
    else
        # Single-symbol: need to select one symbol
        if [[ "$UNIVERSE_MODE" == "auto" ]]; then
            log_info "Auto universe mode: Discovering symbols for training..."
            if [[ -d "$VENV_PATH" ]]; then
                source "$VENV_PATH/bin/activate"
                cd "$SCRIPT_DIR"
                load_env_file "$SCRIPT_DIR/.env"
                export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
                
                # Discover symbols using UniverseManager
                DISCOVERED_SYMBOLS=$(python3 <<PYTHON_SCRIPT
import sys
import json
from src.config.config_loader import load_config
from src.exchange.universe import UniverseManager

try:
    config = load_config()
    universe_manager = UniverseManager(config)
    symbols = universe_manager.get_symbols(force_refresh=True)
    print(json.dumps(symbols))
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
PYTHON_SCRIPT
)
                
                if [[ $? -ne 0 ]] || [[ -z "$DISCOVERED_SYMBOLS" ]]; then
                    log_error "Failed to discover symbols. Falling back to manual input."
                    SYMBOL=$(prompt_input "Enter symbol (e.g., BTCUSDT)" "BTCUSDT")
                    SYMBOLS_TO_TRAIN=("$SYMBOL")
                else
                    # Parse JSON array of symbols
                    DISCOVERED_ARRAY=($(echo "$DISCOVERED_SYMBOLS" | python3 -c "import sys, json; symbols = json.load(sys.stdin); print(' '.join(symbols))"))
                    log_info "Discovered ${#DISCOVERED_ARRAY[@]} symbols: ${DISCOVERED_ARRAY[*]}"
                    SYMBOL=$(prompt_input "Enter symbol to train (e.g., BTCUSDT)" "${DISCOVERED_ARRAY[0]}")
                    SYMBOLS_TO_TRAIN=("$SYMBOL")
                fi
                
                deactivate 2>/dev/null || true
            else
                log_error "Virtual environment not found, cannot discover symbols"
                SYMBOL=$(prompt_input "Enter symbol (e.g., BTCUSDT)" "BTCUSDT")
                SYMBOLS_TO_TRAIN=("$SYMBOL")
            fi
        else
            # Fixed mode - prompt for symbol
            SYMBOL=$(prompt_input "Enter symbol (e.g., BTCUSDT)" "BTCUSDT")
            SYMBOLS_TO_TRAIN=("$SYMBOL")
        fi
    fi
    
    # Train model based on training mode
    log_info "Running model training (mode: $MODEL_TRAINING_MODE)..."
    if [[ -d "$VENV_PATH" ]]; then
        source "$VENV_PATH/bin/activate"
        cd "$SCRIPT_DIR"
        load_env_file "$SCRIPT_DIR/.env"
        export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
        
        if [[ "$MODEL_TRAINING_MODE" == "multi_symbol" ]]; then
            # Multi-symbol training - train_model.py reads config
            if [[ -n "$MULTI_SYMBOL_SYMBOLS" ]]; then
                log_info "Training multi-symbol model on: $MULTI_SYMBOL_SYMBOLS"
            else
                log_info "Training multi-symbol model using auto universe discovery..."
            fi
            python3 train_model.py --days 730 || log_warn "Model training completed with warnings (check logs)"
        else
            # Single-symbol training
            for SYMBOL in "${SYMBOLS_TO_TRAIN[@]}"; do
                if [[ -n "$SYMBOL" ]]; then
                    log_info "Training single-symbol model for $SYMBOL..."
                    python3 train_model.py --symbol "$SYMBOL" --days 730 || log_warn "Model training for $SYMBOL completed with warnings (check logs)"
                fi
            done
        fi
        
        deactivate 2>/dev/null || true
    else
        log_error "Virtual environment not found, cannot train model"
    fi
fi

# Self-test section
log_info ""
log_info "Step 7: Verification"

# Check Python version
PYTHON_VER=$(python3 --version 2>&1)
log_success "Python: $PYTHON_VER"

# Check venv
if [[ -d "$VENV_PATH" ]]; then
    log_success "Virtual environment: $VENV_PATH"
else
    log_error "Virtual environment not found!"
fi

# Check .env
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    ENV_KEYS=$(grep -E "^[A-Z_]+=" "$SCRIPT_DIR/.env" | cut -d= -f1 | tr '\n' ', ' | sed 's/,$//')
    log_success ".env file exists with keys: $ENV_KEYS"
else
    log_warn ".env file not found (may have been skipped)"
fi

# Check requirements (activate venv first)
if [[ -d "$VENV_PATH" ]]; then
    source "$VENV_PATH/bin/activate"
    cd "$SCRIPT_DIR"
    export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
    if python -c "import pandas, numpy, xgboost, pybit, yaml" 2>/dev/null; then
        log_success "Core Python packages installed"
    else
        log_warn "Some Python packages may be missing (check manually)"
    fi
    
    # Test universe module if auto mode
    if [[ "$UNIVERSE_MODE" == "auto" ]]; then
        if python -c "from src.exchange.universe import UniverseManager" 2>/dev/null; then
            log_success "Universe module importable"
        else
            log_warn "Universe module may have issues (check manually)"
        fi
    fi
    
    deactivate 2>/dev/null || true
else
    log_warn "Cannot check packages (venv not found)"
fi

# Syntax check on key files
log_info "Running syntax checks..."
if [[ -d "$VENV_PATH" ]]; then
    source "$VENV_PATH/bin/activate"
    cd "$SCRIPT_DIR"
    export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
    if python -m py_compile src/config/config_loader.py live_bot.py train_model.py 2>/dev/null; then
        log_success "Python syntax check passed"
    else
        log_warn "Syntax check found issues (review manually)"
    fi
    deactivate 2>/dev/null || true
else
    log_warn "Cannot run syntax check (venv not found)"
fi

# Final summary
echo ""
echo "=========================================="
log_success "Installation Complete!"
echo "=========================================="
echo ""

# Prompt to start bot now
log_info ""
if prompt_yes_no "Do you want to start the bot now on TESTNET with the conservative profile?" "N"; then
    log_info "Starting bot..."
    
    if [[ -d "$VENV_PATH" ]]; then
        source "$VENV_PATH/bin/activate"
        cd "$SCRIPT_DIR"
        load_env_file "$SCRIPT_DIR/.env"
        export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
        
        log_info "Starting live_bot.py in foreground (press Ctrl+C to stop)..."
        log_warn "This will run in the current terminal. For background operation, use systemd or screen/tmux."
        echo ""
        
        # Run bot (will run until interrupted)
        python3 live_bot.py || log_warn "Bot exited with warnings (check logs)"
        
        deactivate 2>/dev/null || true
    else
        log_error "Virtual environment not found, cannot start bot"
    fi
else
    log_info "Bot not started. Use the instructions below to start it manually."
fi

echo ""
log_info "Next Steps:"
echo ""
echo "1. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "2. Check model coverage (if using universe mode):"
echo "   python scripts/check_model_coverage.py"
echo ""
echo "3. Start the bot manually:"
echo ""
echo "   Option A - Direct run (foreground):"
echo "   source venv/bin/activate"
echo "   python live_bot.py"
echo ""
echo "   Option B - Using systemd (background, if configured):"
echo "   sudo systemctl start bybit-bot-live.service"
echo "   sudo systemctl enable bybit-bot-live.service  # Enable on boot"
echo "   sudo journalctl -u bybit-bot-live.service -f   # Monitor logs"
echo ""
echo "   Option C - Using screen/tmux (background):"
echo "   screen -S trading_bot"
echo "   source venv/bin/activate"
echo "   python live_bot.py"
echo "   # Press Ctrl+A then D to detach"
echo ""
echo "4. Monitor status:"
echo "   python scripts/show_status.py"
echo ""
echo "5. Check model coverage:"
echo "   python scripts/check_model_coverage.py"
echo ""
echo "6. Review documentation:"
echo "   - docs/FIRST_DEPLOYMENT_BUNDLE.md"
echo "   - docs/TESTNET_CAMPAIGN_GUIDE.md"
echo "   - docs/OPERATIONS_RUNBOOK.md"
echo "   - docs/NEW_SYMBOL_ONBOARDING.md"
echo "   - docs/UNIVERSE_MANAGEMENT.md (if using auto mode)"
echo ""
log_warn "IMPORTANT REMINDERS:"
echo "  - Always start on testnet first!"
echo "  - Run testnet campaign for 2-4 weeks minimum"
echo "  - Review testnet results before considering live trading"
echo "  - Start with minimal capital if going live"
echo "  - Monitor closely, especially in the first week"
echo ""
log_info "Configuration files:"
echo "  - .env: $SCRIPT_DIR/.env"
echo "  - config.yaml: $SCRIPT_DIR/config/config.yaml"
if [[ "$UNIVERSE_MODE" == "auto" ]]; then
    echo "  - Universe mode: auto (discovering symbols dynamically)"
    echo "  - Universe cache: $SCRIPT_DIR/data/universe_cache.json"
else
    echo "  - Universe mode: fixed (using symbols from config.yaml)"
fi
echo ""
if [[ -d "$SYSTEMD_DIR" ]]; then
    log_info "Systemd services:"
    echo "  - Service files: $SYSTEMD_DIR/"
    echo "  - Follow instructions above to enable them"
    echo ""
fi
log_success "Happy trading! (But remember: no guarantees, start small, test first)"
echo ""

