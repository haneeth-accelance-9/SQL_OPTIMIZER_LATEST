# Test Environment - LiscenceOptimizer

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }

  # Backend configuration for remote state
  # Configure via CLI: --state-storage <account> --state-container <container> --state-rg <rg>
  # Or via backend-config during init:
  #   terraform init -backend-config="resource_group_name=..." \
  #                  -backend-config="storage_account_name=..." \
  #                  -backend-config="container_name=..." \
  #                  -backend-config="key=liscence-optimizer-test.tfstate"
  backend "azurerm" {}
}

provider "azurerm" {
  features {}
}