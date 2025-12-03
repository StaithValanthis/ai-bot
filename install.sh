#!/usr/bin/env bash
#
# One-shot installer for Bybit AI Trading Bot v2.1+
#
# This script sets up the complete environment for the trading bot:
# - Installs system dependencies
# - Creates Python virtual environment
# - Installs Python packages
# - Prompts for configuration (API keys, profile, etc.)
# - Writes .env file
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
    
    read -sp "$(echo -e "${BLUE}$prompt${NC}: ")" response
    echo ""
    echo "$response"
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
if [[ -z "$BYBIT_API_SECRET" ]]; then
    log_error "API secret is required!"
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
        
        # Write merged .env
        {
            echo "# Bybit AI Trading Bot v2.1+ - Environment Configuration"
            echo "# Generated by install.sh on $(date)"
            echo ""
            echo "# Bybit API Credentials"
            echo "BYBIT_API_KEY=$BYBIT_API_KEY"
            echo "BYBIT_API_SECRET=$BYBIT_API_SECRET"
            echo "BYBIT_TESTNET=$BYBIT_TESTNET"
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
        # Write new .env file
        cat > "$ENV_FILE" <<EOF
# Bybit AI Trading Bot v2.1+ - Environment Configuration
# Generated by install.sh on $(date)

# Bybit API Credentials
BYBIT_API_KEY=$BYBIT_API_KEY
BYBIT_API_SECRET=$BYBIT_API_SECRET
BYBIT_TESTNET=$BYBIT_TESTNET

# Default Trading Profile
# Options: profile_conservative, profile_moderate, profile_aggressive
DEFAULT_PROFILE=$DEFAULT_PROFILE

# Discord Alerts (Optional)
$(if [[ -n "$DISCORD_WEBHOOK" ]]; then echo "DISCORD_WEBHOOK_URL=$DISCORD_WEBHOOK"; else echo "# DISCORD_WEBHOOK_URL="; fi)

# Additional Configuration
# You can add more environment variables here as needed
EOF
    fi
    
    # Set restrictive permissions
    chmod 600 "$ENV_FILE" 2>/dev/null || log_warn "Could not set .env permissions (may need manual chmod 600)"
    log_success ".env file written to $ENV_FILE"
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

if prompt_yes_no "Do you want to fetch historical data now?" "N"; then
    log_info "Fetching historical data..."
    SYMBOL=$(prompt_input "Enter symbol (e.g., BTCUSDT)" "BTCUSDT")
    YEARS=$(prompt_input "Enter years of history" "2")
    
    log_info "Running data fetch..."
    source "$VENV_PATH/bin/activate"
    python scripts/fetch_and_check_data.py \
        --symbol "$SYMBOL" \
        --years "$YEARS" \
        --timeframe 60 || log_warn "Data fetch completed with warnings (check logs)"
fi

if prompt_yes_no "Do you want to train an initial model now?" "N"; then
    log_info "Training initial model..."
    SYMBOL=$(prompt_input "Enter symbol (e.g., BTCUSDT)" "BTCUSDT")
    
    log_info "Running model training..."
    source "$VENV_PATH/bin/activate"
    python train_model.py --symbol "$SYMBOL" || log_warn "Model training completed with warnings (check logs)"
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

# Check requirements
if python3 -c "import pandas, numpy, xgboost, pybit" 2>/dev/null; then
    log_success "Core Python packages installed"
else
    log_warn "Some Python packages may be missing (check manually)"
fi

# Syntax check on key files
log_info "Running syntax checks..."
if [[ -d "$VENV_PATH" ]]; then
    source "$VENV_PATH/bin/activate"
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
log_info "Next Steps:"
echo ""
echo "1. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "2. Fetch historical data (if not done already):"
echo "   python scripts/fetch_and_check_data.py --symbol BTCUSDT --years 2"
echo ""
echo "3. Train an initial model:"
echo "   python train_model.py --symbol BTCUSDT"
echo ""
echo "4. Run a testnet campaign (HIGHLY RECOMMENDED):"
echo "   python scripts/run_testnet_campaign.py --profile $DEFAULT_PROFILE --duration-days 14"
echo ""
echo "5. Monitor status:"
echo "   python scripts/show_status.py"
echo ""
echo "6. Review documentation:"
echo "   - docs/FIRST_DEPLOYMENT_BUNDLE.md"
echo "   - docs/TESTNET_CAMPAIGN_GUIDE.md"
echo "   - docs/OPERATIONS_RUNBOOK.md"
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
echo ""
if [[ -d "$SYSTEMD_DIR" ]]; then
    log_info "Systemd services:"
    echo "  - Service files: $SYSTEMD_DIR/"
    echo "  - Follow instructions above to enable them"
    echo ""
fi
log_success "Happy trading! (But remember: no guarantees, start small, test first)"
echo ""

