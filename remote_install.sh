#!/bin/bash
check_and_install() {
    local package=$1
    echo "Checking for $package..."
    if ! command -v "$package" >/dev/null 2>&1; then
        read -p "$package is required but not installed. Would you like to install it? [Y/n] " response
        response=${response:-Y}
        if [[ "$response" =~ ^[Yy]$ ]]; then
            sudo apt-get update && sudo apt-get install -y "$package"
        else
            echo "Cannot proceed without $package. Exiting."
            exit 1
        fi
    fi
}

check_and_install git
if ! command -v python3 >/dev/null 2>&1; then
    read -p "Python3 and related packages are required but not installed. Would you like to install them? [Y/n] " response
    response=${response:-Y}
    if [[ "$response" =~ ^[Yy]$ ]]; then
        sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
    else
        echo "Cannot proceed without Python3. Exiting."
        exit 1
    fi
fi

# Create and move to temporary directory
TEMP_DIR=$(mktemp -d)
cd "$TEMP_DIR" || exit 1

# Clone the repository
git clone https://github.com/nilock/dictate.git .

# Make the installation script executable
chmod +x installation.sh

# Run the installation script with sudo
sudo ./installation.sh

# Clean up
cd - || exit 1
rm -rf "$TEMP_DIR"
