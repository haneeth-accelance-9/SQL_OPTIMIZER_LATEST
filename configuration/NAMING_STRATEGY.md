# Azure Resource Naming Strategy

## Overview

This document defines a simplified naming strategy for Azure resources with **strict upfront rules** to eliminate the need for multiple name variants.

## Core Naming Rules

All names must follow these rules from the start:

| Component | Max Length | Rule | Examples |
|-----------|------------|------|----------|
| **Product Name** | 8 characters | Short, descriptive abbreviation | `repos`, `accr`, `admin`, `deferrals` |
| **Environment** | 7 characters | Standard full names only | `dev`, `test`, `staging`, `prod` |
| **Location** | No limit | Azure short codes | `gwc`, `eus`, `wus`, `scus`, `eastus`, `westeurope` |

## Single Naming Pattern

One suffix pattern is used: `{product}-{env}-{location}`

**Example**: `repos-staging-gwc`

### Naming Formats

**With Hyphens** (for most resources):
```
{resource_type_prefix}-{product}-{env}-{location}
Example: rg-repos-staging-gwc
```

**Without Hyphens** (such as storage accounts, container registries):
```
{prefix}{product}{env}{location}
Example: streposstaginggwc
```

## Standard Product Names

All products must use 8 characters or less:

| Full Name | Product Name | Length |
|-----------|--------------|--------|
| Repostings | `repos` | 5 |
| Accruals | `accr` | 4 |
| Administration | `admin` | 5 |
| Deferrals | `defer` | 5 |
| Reconciliation | `recon` | 5 |
| Scheduler | `sched` | 5 |

## Standard Environments

Only these environment names are allowed:

| Environment | Name | Length |
|-------------|------|--------|
| Development | `dev` | 3 |
| Test | `test` | 4 |
| Staging | `staging` | 7 |
| Production | `prod` | 4 |

## Example Resource Names

For **product**: `repos`, **env**: `staging`, **location**: `gwc`

| Resource Type | Prefix | Pattern | Full Name | Length | Limit |
|---------------|--------|---------|-----------|--------|-------|
| Resource Group | `rg` | with hyphens | `rg-repos-staging-gwc` | 21 | 90 ✓ |
| Container App | `ca` | with hyphens | `ca-agent-repos-staging-gwc` | 27 | 32 ✓ |
| Key Vault | `kv` | with hyphens | `kv-repos-staging-gwc` | 21 | 24 ✓ |
| Storage Account | `st` | no hyphens | `streposstaginggwc` | 18 | 24 ✓ |
| Cosmos DB | `cosmos` | with hyphens | `cosmos-repos-staging-gwc` | 25 | 44 ✓ |
| VNet | `vnet` | with hyphens | `vnet-repos-staging-gwc` | 23 | 64 ✓ |
| App Insights | `appi` | with hyphens | `appi-repos-staging-gwc` | 23 | 255 ✓ |
| Log Analytics | `log` | with hyphens | `log-repos-staging-gwc` | 22 | 63 ✓ |

Microsoft maintains a list of Azure product abbreviations for naming resources:
https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-abbreviations

## Configuration Files

### Infrastructure Shared (`infrastructure_shared/root/variables.tf`)

```hclProduct name (max 8 characters: repos, accr, admin, etc.)"
  type        = string
  
  validation {
    condition     = length(var.product_name) <= 8
    error_message = "Product name must be 8 characters or less."
  }
}

variable "env_name" {
  description = "Environment name (must be: dev, test, staging, or prod)"
  type        = string
  
  validation {
    condition     = contains(["dev", "test", "staging", "prod"], var.env_name)
    error_message = "Environment must be one of: dev, test, staging, prod."
  }
}
```

### Environment Configuration (`repostings_infra/terraform/environments/staging/repos.staging.tfvars`)

```hcl
product_name = "repos"
env_name     = "staging"
location     = "canadacentral"
```

## Adding New Products/Environments

### Adding a New Product

1. Choose an 8-character (or less) abbreviation:
   ```hcl
   product_name = "defer"  # for "deferrals"
   ```

2. Create environment-specific tfvars:
   ```
   defer.dev.tfvars
   defer.test.tfvars
   defer.staging.tfvars
   defer.prod.tfvars
   ```

### Adding a New Environment

Only the four standard environments are supported:
- `dev` - Development
- `test` - Testing
- `staging` - Staging  
- `prod` - Production

No other environment names are allowed.

## Terraform Implementation

### Suffix Variables (`infrastructure_shared/root/main.tf`)

```hcl
locals {
  # Single suffix with hyphens
  resource_suffix = "${var.product_name}-${var.env_name}-${var.location_short}"
  
  # Suffix without hyphens (for storage accounts)
  resource_suffix_compact = "${var.product_name}${var.env_name}${var.location_short}"
}
```

### Usage in Resource Naming

```hcl
# Most resources (with hyphens)
resource "azurerm_resource_group" "main" {
  name     = "rg-${local.resource_suffix}"
  location = var.location
}

resource "azurerm_key_vault" "main" {
  name                = "kv-${local.resource_suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
}

# Storage accounts (without hyphens)
resource "azurerm_storage_account" "main" {
  name                     = "st${local.resource_suffix_compact}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}
```

## Benefits

1. **Simple**: Only one product name, one environment name
2. **Validated**: Terraform enforces length limits upfront
3. **Consistent**: Same pattern for all resources (just +/- hyphens)
4. **No Confusion**: No "full vs short" decisions to make
5. **Self-Documenting**: Names are descriptive but constrained
6. **Future-Proof**: Works for all Azure resource types

## Name Length Validation

Example with `product (8) + env (7) + location (3) = 18 chars` (using 3-char location code):

| Resource Type | Prefix Length | Suffix Length | Total | Limit | Safe? |
|---------------|---------------|---------------|-------|-------|-------|
| Key Vault | 3 (`kv-`) | 18 | 21 | 24 | ✓ (3 chars margin) |
| Storage Account | 2 (`st`) | 18 | 20 | 24 | ✓ (4 chars margin) |
| Container App | 9 (`ca-agent-`) | 18 | 27 | 32 | ✓ (5 chars margin) |
| Cosmos DB | 7 (`cosmos-`) | 18 | 25 | 44 | ✓ (19 chars margin) |

**Note**: Longer location codes reduce the safety margin. For example, `eastus` (6 chars) gives a suffix of 21 chars, resulting in `kv-repos-staging-eastus` (24 chars, at the limit).

**All Azure resources fit comfortably within limits!**
