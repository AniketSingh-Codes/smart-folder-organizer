#!/usr/bin/env bash
# ==============================================================================
# Smart Folder Organizer - Installation Script for Fedora Workstation (GNOME)
# ==============================================================================

set -e

APP_ID="com.aniket.SmartFolderOrganizer"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
APP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"
META_DIR="${HOME}/.local/share/metainfo"
OPT_VENV="${HOME}/.local/share/smart-folder-organizer/venv"

# Color outputs
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
CYAN="\033[1;36m"
RED="\033[1;31m"
RESET="\033[0m"

echo -e "${CYAN}============================================================${RESET}"
echo -e "${CYAN}  Smart Folder Organizer — Installer (Fedora / GNOME)${RESET}"
echo -e "${CYAN}============================================================${RESET}"

# Handle uninstallation
if [[ "$1" == "--uninstall" ]]; then
    echo -e "${YELLOW}[*] Uninstalling Smart Folder Organizer...${RESET}"
    rm -f "${BIN_DIR}/smart-folder-organizer"
    rm -f "${APP_DIR}/${APP_ID}.desktop"
    rm -f "${ICON_DIR}/${APP_ID}.svg"
    rm -f "${ICON_DIR}/${APP_ID}-symbolic.svg"
    rm -f "${META_DIR}/${APP_ID}.metainfo.xml"
    rm -rf "${OPT_VENV}"
    
    update-desktop-database "${APP_DIR}" 2>/dev/null || true
    gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" 2>/dev/null || true
    echo -e "${GREEN}[✓] Successfully uninstalled.${RESET}"
    exit 0
fi

# 1. Check & Prompt DNF System Dependencies
echo -e "\n${YELLOW}[1/4] Checking required system packages (dnf)...${RESET}"
REQUIRED_PKGS=("python3-gobject" "gtk4" "libadwaita")
MISSING_PKGS=()

for pkg in "${REQUIRED_PKGS[@]}"; do
    if ! rpm -q "$pkg" &>/dev/null; then
        MISSING_PKGS+=("$pkg")
    fi
done

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    echo -e "Missing packages: ${RED}${MISSING_PKGS[*]}${RESET}"
    echo -e "Installing with sudo dnf..."
    sudo dnf install -y "${MISSING_PKGS[@]}"
else
    echo -e "${GREEN}[✓] System dependencies satisfied:${RESET} ${REQUIRED_PKGS[*]}"
fi

# 2. Setup Optional Python Dependencies in Venv (pypdf, python-docx)
echo -e "\n${YELLOW}[2/4] Setting up optional Python libraries for PDF & Word content inspection...${RESET}"
mkdir -p "$(dirname "${OPT_VENV}")"

if [ ! -d "${OPT_VENV}" ]; then
    echo -e "Creating isolated venv with system site-packages for PyGObject..."
    python3 -m venv --system-site-packages "${OPT_VENV}"
fi

echo -e "Installing/updating pypdf and python-docx..."
"${OPT_VENV}/bin/pip" install --retries 0 --timeout 2 --upgrade --quiet pip setuptools 2>/dev/null || true
"${OPT_VENV}/bin/pip" install --retries 0 --timeout 2 --quiet pypdf python-docx 2>/dev/null || {
    echo -e "${YELLOW}[!] Note: Network unavailable; skipped optional pip packages. Plain text & Markdown inspection will still function.${RESET}"
}

# 3. Install Executable Launcher
echo -e "\n${YELLOW}[3/4] Creating launcher script in ${BIN_DIR}...${RESET}"
mkdir -p "${BIN_DIR}"

cat << EOF > "${BIN_DIR}/smart-folder-organizer"
#!/usr/bin/env bash
export PYTHONPATH="${SCRIPT_DIR}:\${PYTHONPATH}"
if [ -x "${OPT_VENV}/bin/python3" ]; then
    exec "${OPT_VENV}/bin/python3" -m smart_folder_organizer "\$@"
else
    exec python3 -m smart_folder_organizer "\$@"
fi
EOF

chmod +x "${BIN_DIR}/smart-folder-organizer"

# 4. Install Desktop Entry, Icons, and AppStream Metadata
echo -e "\n${YELLOW}[4/4] Installing GNOME integration files...${RESET}"
mkdir -p "${APP_DIR}" "${ICON_DIR}" "${META_DIR}"

cp -f "${SCRIPT_DIR}/data/${APP_ID}.desktop" "${APP_DIR}/"
cp -f "${SCRIPT_DIR}/data/icons/hicolor/scalable/apps/${APP_ID}.svg" "${ICON_DIR}/"
cp -f "${SCRIPT_DIR}/data/icons/hicolor/scalable/apps/${APP_ID}-symbolic.svg" "${ICON_DIR}/"
cp -f "${SCRIPT_DIR}/data/${APP_ID}.metainfo.xml" "${META_DIR}/"

# Update desktop and icon caches
update-desktop-database "${APP_DIR}" 2>/dev/null || true
gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" 2>/dev/null || true

echo -e "\n${GREEN}============================================================${RESET}"
echo -e "${GREEN}  [✓] Smart Folder Organizer Installed Successfully!${RESET}"
echo -e "${GREEN}============================================================${RESET}"
echo -e "You can now launch the app:"
echo -e "  • From the GNOME App Grid / Dock (search: 'Smart Folder Organizer')"
echo -e "  • From the command line: ${CYAN}smart-folder-organizer${RESET}"
echo -e "  • In headless CLI mode : ${CYAN}smart-folder-organizer --cli --dry-run ~/Downloads${RESET}"
