# Terraform Infrastructure - LiscenceOptimizer

Modern, best-practices Terraform structure for deploying Azure Container Apps across multiple environments.

## 📁 Directory Structure

```
terraform/
├── environments/          # Environment-specific configurations
│   ├── test/             # Test environment
│   │   ├── providers.tf  # Terraform & provider setup
│   │   ├── data.tf       # Data source lookups
│   │   ├── main.tf       # Environment configuration
│   │   ├── variables.tf  # Variable declarations
│   │   ├── outputs.tf    # Output values
│   │   └── terraform.tfvars  # Test values
│   ├── staging/          # Staging environment
│   │   └── ...           # Same structure as test
│   └── prod/             # Production environment
│       └── ...           # Same structure as test
│
└── modules/              # Reusable infrastructure modules
    └── container_app/    # Container App module
        ├── main.tf       # Module resources
        ├── variables.tf  # Module inputs
        ├── outputs.tf    # Module outputs
        └── README.md     # Module documentation
```

## 🌍 Architecture Principles

This structure follows **industry best practices**:

### 1. **Environment Isolation**
- ✅ Separate directories per environment (test/staging/prod)
- ✅ Independent state files for each environment
- ✅ No risk of cross-environment contamination
- ✅ Environment-specific configurations

### 2. **Code Reusability**
- ✅ Shared modules for common infrastructure
- ✅ DRY principle - define once, use everywhere
- ✅ Easier testing and validation
- ✅ Consistent deployments across environments

### 3. **Clear Structure**
- ✅ Self-documenting directory layout
- ✅ Standard file naming (providers.tf, data.tf, main.tf)
- ✅ Obvious what's deployed where
- ✅ Easy onboarding for new team members

### 4. **Safe Upgrades**
- ✅ Test provider/module upgrades in lower environments first
- ✅ Gradual rollout: test → staging → prod
- ✅ Version control per environment
- ✅ Rollback capabilities

### 5. **State Isolation**
- ✅ Each environment has its own state file
- ✅ Production state isolated from non-prod
- ✅ Reduced blast radius
- ✅ Compliance-friendly

## 🚀 Quick Start

### Prerequisites

1. **Existing Azure Infrastructure**:
   - Resource Group (shared across environments)
   - Container Apps Environment

2. **Tools**:
   - [Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli)
   - [Terraform](https://www.terraform.io/downloads.html) >= 1.0

3. **Permissions**: Contributor access to Resource Group

### Configuration

Update the `terraform.tfvars` file in each environment directory:

**test/terraform.tfvars**:
```hcl
resource_group_name            = "shared-infrastructure-rg"
container_app_environment_name = "shared-container-env"
container_image                = "myregistry.azurecr.io/my-app:test"
min_replicas                   = 1
max_replicas                   = 2
```

**staging/terraform.tfvars**:
```hcl
resource_group_name            = "shared-infrastructure-rg"
container_app_environment_name = "shared-container-env"
container_image                = "myregistry.azurecr.io/my-app:staging"
min_replicas                   = 1
max_replicas                   = 5
```

**prod/terraform.tfvars**:
```hcl
resource_group_name            = "shared-infrastructure-rg"
container_app_environment_name = "shared-container-env"
container_image                = "myregistry.azurecr.io/my-app:latest"
min_replicas                   = 2
max_replicas                   = 10
```

### Deployment

#### Using CLI Tool (Recommended)

The CLI tool accepts infrastructure parameters directly, eliminating the need to hardcode them in `.tfvars` files:

```bash
# Login to Azure
az login

# Deploy to test with CLI parameters
liscence-optimizer-cli iac --env test \
  --resource-group "my-shared-rg" \
  --container-env "my-container-env"

# Short form with aliases
liscence-optimizer-cli iac --env staging -rg "my-shared-rg" -ce "my-container-env"

# Deploy to production
liscence-optimizer-cli iac --env prod \
  -rg "prod-shared-rg" \
  -ce "prod-container-env"

# Preview changes without applying
liscence-optimizer-cli iac --env prod \
  -rg "prod-shared-rg" \
  -ce "prod-container-env" \
  --last-step plan

# CI/CD - Auto-approve with parameters
liscence-optimizer-cli iac --env prod \
  -rg "prod-shared-rg" \
  -ce "prod-container-env" \
  --auto-approve
```

**Available CLI Parameters:**
- `--resource-group` / `-rg`: Name of existing Azure Resource Group
- `--container-env` / `-ce`: Name of existing Container Apps Environment
- `--env` / `-e`: Target environment (test/staging/prod)
- `--last-step` / `-l`: Stop at specific step (init/validate/plan/apply)
- `--auto-approve`: Skip confirmation prompts
- `--var-file`: Use custom .tfvars file
- `--dry-run`: Preview commands without execution
- `--destroy`: Destroy infrastructure

**Note:** CLI parameters take precedence over values in `.tfvars` files.
```

#### Manual Terraform Commands

```bash
# Initialize environment
cd terraform/environments/test
terraform init

# Plan deployment
terraform plan

# Apply changes
terraform apply

# Destroy resources
terraform destroy
```

## 🎯 Common Workflows

### Promoting Changes Across Environments

```bash
# 1. Deploy and test in test environment
liscence-optimizer-cli iac --env test
# ... validate the deployment ...

# 2. Deploy to staging
liscence-optimizer-cli iac --env staging
# ... run integration tests ...

# 3. Deploy to production
liscence-optimizer-cli iac --env prod --auto-approve
```

### Testing Module Changes

```bash
# Test module changes in test environment first
cd terraform/environments/test
terraform plan
terraform apply

# If successful, roll out to other environments
cd ../staging
terraform apply

cd ../prod
terraform apply
```

### Upgrading Provider Versions

```bash
# Update providers.tf in test environment
cd terraform/environments/test
# Edit providers.tf to update version

terraform init -upgrade
terraform plan
terraform apply

# After validation, update staging and prod
```

## 🔒 State Management

### Local State (Default)

Each environment stores state locally in `terraform.tfstate`.

**⚠️ Not recommended for teams or production!**

### Remote State (Recommended)

Configure Azure Storage backend in `providers.tf`:

```hcl
terraform {
  backend "azurerm" {
    resource_group_name  = "terraform-state-rg"
    storage_account_name = "yourtfstate"
    container_name       = "tfstate"
    key                  = "liscence-optimizer-test.tfstate"
  }
}
```

Initialize with backend:
```bash
terraform init -backend-config="key=liscence-optimizer-test.tfstate"
```

## 📦 Modules

### Container App Module

Located in `modules/container_app/`, this module creates an Azure Container App.

**Usage**:
```hcl
module "container_app" {
  source = "../../modules/container_app"

  container_app_name           = "my-app-test"
  resource_group_name          = "my-rg"
  container_app_environment_id = "/subscriptions/.../managedEnvironments/env"
  environment                  = "test"
  container_image              = "registry.io/image:tag"
  
  min_replicas = 1
  max_replicas = 3
}
```

See [modules/container_app/README.md](modules/container_app/README.md) for full documentation.

## 🔧 Customization

### Adding a New Environment

```bash
# 1. Copy existing environment
cp -r environments/test environments/uat

# 2. Update terraform.tfvars
# Edit environments/uat/terraform.tfvars

# 3. Update CLI to include new environment
# Edit cli/commands/iac.py - add "uat" to valid_environments

# 4. Deploy
liscence-optimizer-cli iac --env uat
```

### Adding New Resources

1. **Add to module** (if reusable):
   ```bash
   # Edit modules/container_app/main.tf
   resource "azurerm_container_app_custom_domain" "main" {
     # ...
   }
   ```

2. **Add to environment** (if environment-specific):
   ```bash
   # Edit environments/prod/main.tf
   resource "azurerm_monitor_diagnostic_setting" "prod_monitoring" {
     # ...
   }
   ```

### Environment-Specific Resources

Production might need additional resources like monitoring:

**environments/prod/main.tf**:
```hcl
# Container app from module
module "container_app" {
  source = "../../modules/container_app"
  # ...
}

# Production-only monitoring
resource "azurerm_monitor_diagnostic_setting" "prod" {
  name                       = "liscence-optimizer-prod-diagnostics"
  target_resource_id         = module.container_app.id
  log_analytics_workspace_id = var.log_analytics_workspace_id
  
  # ... metrics and logs ...
}
```

## 🛡️ Best Practices

### 1. State Files
- ✅ Use remote state for production
- ✅ Enable state locking (Azure Storage supports this)
- ✅ Never commit state files to Git

### 2. Secrets
- ✅ Use Azure Key Vault for secrets
- ✅ Never commit `.tfvars` files with sensitive data
- ✅ Use environment variables or CI/CD secrets

### 3. Version Control
- ✅ Tag releases: `git tag v1.0.0-prod`
- ✅ Use pull requests for changes
- ✅ Review plans before applying

### 4. CI/CD
- ✅ Run `terraform plan` on pull requests
- ✅ Require approval for production applies
- ✅ Use `--auto-approve` only in automated pipelines

### 5. Testing
- ✅ Always deploy to test first
- ✅ Run validation and tests
- ✅ Promote to staging, then prod

## 📊 Outputs

After deployment, view outputs:

```bash
cd terraform/environments/prod
terraform output

# Example output:
container_app_name = "my-agent-prod"
container_app_url  = "https://my-agent-prod.azurecontainerapps.io"
environment        = "prod"
```

## 🔍 Troubleshooting

### Error: Environment directory not found
```bash
# Ensure you're in the project root
cd /path/to/project

# Verify structure
ls terraform/environments/
```

### Error: Resource Group not found
```bash
# Verify resource group exists
az group show --name shared-infrastructure-rg

# Update terraform.tfvars with correct name
```

### Error: State lock
```bash
# If state is locked (interrupted apply)
cd terraform/environments/test
terraform force-unlock <LOCK_ID>
```

## 📚 Additional Resources

- [Terraform Best Practices](https://www.terraform.io/docs/cloud/guides/recommended-practices/index.html)
- [Azure Container Apps Terraform Provider](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/container_app)
- [Module Documentation](modules/container_app/README.md)

## 🤝 Contributing

When making infrastructure changes:

1. Create a feature branch
2. Make changes in test environment
3. Test thoroughly
4. Update documentation
5. Create pull request
6. After approval, promote to staging/prod

---

**Structure based on industry best practices from:**
- HashiCorp's Terraform recommendations
- Google Cloud's Terraform best practices
- Microsoft's Azure Terraform patterns
- Community standards from DevOps leaders