#!/bin/bash

set -ex

echo "Updating package lists..."
apt update

apt install -y wget gpg lsb-release

echo "Adding the GPG key for the HashiCorp repository..."
wget -O - https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg

echo "Adding the HashiCorp repository to the sources list..."
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" |  tee /etc/apt/sources.list.d/hashicorp.list

echo "Updating package lists and installing Terraform..."
apt update && apt install -y terraform=${TERRAFORM_VERSION}-1

echo "Terraform installed successfully"
terraform --version
