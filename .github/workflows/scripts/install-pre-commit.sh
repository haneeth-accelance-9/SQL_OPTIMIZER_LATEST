#!/bin/bash

set -ex

echo "Updating package lists..."
apt update

apt install -y wget unzip

echo "Installing pre-commit and checkov..."
pip install pre-commit==${PRE_COMMIT_VERSION} checkov==${CHECKOV_VERSION} --break-system-packages

echo "Installing terraform-docs..."

download_with_retries() {
  local version=$1
  local output=$2
  local max_retries=5
  local retry_delay=5

  set +e

  for attempt in $(seq 1 $max_retries); do
    echo "Download terraform-docs v$version..."
    wget -O "$output" "https://terraform-docs.io/dl/v${version}/terraform-docs-v${version}-linux-amd64.tar.gz"
    if [ $? -eq 0 ]; then
      echo "Download succeeded!"
      return 0
    fi
    echo "Download failed. Retrying in $retry_delay seconds..."
    sleep $retry_delay
  done

  echo "Error: Failed to download $url after $max_retries attempts."
  return 1
}

download_with_retries "$TERRAFORM_DOCS_VERSION" terraform-docs.tgz
if [ $? -ne 0 ]; then
  echo "Error: Failed to download terraform-docs."
  exit 1
fi

if [ ! -s terraform-docs.tgz ]; then
  echo "Error: terraform-docs.tgz is empty or not downloaded."
  exit 1
fi

echo "Extracting terraform-docs..."
tar -xzf terraform-docs.tgz
if [ $? -ne 0 ]; then
  echo "Error: Failed to extract terraform-docs.tgz."
  exit 1
fi
rm terraform-docs.tgz
chmod +x terraform-docs
mv terraform-docs /usr/bin/

echo "Installing tflint..."
echo "Downloading TFLint $TFLINT_VERSION"
wget -O tflint.zip "https://github.com/terraform-linters/tflint/releases/download/v${TFLINT_VERSION}/tflint_linux_amd64.zip"
if [ $? -ne 0 ]; then
  echo "Error: Failed to download TFLint."
  exit 1
fi
if [ ! -s tflint.zip ]; then
  echo "Error: tflint.zip is empty or not downloaded."
  exit 1
fi
echo "Downloaded successfully"
unzip tflint.zip
if [ $? -ne 0 ]; then
  echo "Error: Failed to extract tflint.zip."
  exit 1
fi
rm tflint.zip
chmod +x tflint
mv tflint /usr/bin/

echo "Installation completed successfully."
checkov --version
terraform-docs --version
pre-commit --version
tflint --version
