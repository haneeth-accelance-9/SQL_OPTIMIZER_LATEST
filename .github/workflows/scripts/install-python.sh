#!/bin/bash

set -ex

echo "Updating package lists..."
apt update

echo "Installing Python and pip..."
chown -R $(whoami) /github/home
apt install -y python${PYTHON_VERSION} python3-pip

echo "Python and pip installed successfully"
