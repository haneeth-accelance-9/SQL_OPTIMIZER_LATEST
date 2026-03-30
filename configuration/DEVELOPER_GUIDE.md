# Developer Guide – af-agentcell-template

This guide explains how to provision and work with the template infrastructure from a developer laptop, and how to run it in a fully network-isolated production configuration via GitHub Actions CI/CD.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [First-time setup](#2-first-time-setup)
3. [Configure your deployment](#3-configure-your-deployment)
4. [Deploy – local development mode](#4-deploy--local-development-mode)
5. [Deploy – GitHub Actions CI/CD](#5-deploy--github-actions-cicd)
6. [Deploy – network-hardened mode (production)](#6-deploy--network-hardened-mode-production)
7. [Post-apply steps (network-hardened only)](#7-post-apply-steps-network-hardened-only)
8. [Accessing the UI](#8-accessing-the-ui)
9. [Accessing the infrastructure as a developer](#9-accessing-the-infrastructure-as-a-developer)
10. [Switching between modes](#10-switching-between-modes)
11. [Network architecture summary](#11-network-architecture-summary)
12. [Known limitations / TODOs](#12-known-limitations--todos)

---

## 1. Prerequisites

| Tool | Minimum version | Install |
|---|---|---|
| Terraform | 1.5.7 | https://developer.hashicorp.com/terraform/install |
| Azure CLI | 2.57 | https://learn.microsoft.com/cli/azure/install-azure-cli |
| Git | any | https://git-scm.com |

Azure permissions required for your user/service principal:

- **Contributor** on the target Resource Group
- **User Access Administrator** on the Resource Group (for role assignments to managed identities)

---

## 2. First-time setup

```bash
# Clone your agentcell repository
git clone <repo-url>
cd <your-agentcell-repo>

# Authenticate to Azure
az login
az account set --subscription "<your-subscription-id>"
```

**Backend initialisation – option A: local `.hcl` file (recommended for laptop use)**

Edit `configuration/backend-dev.hcl` (copy from `environments/prod/backend-prod.hcl`) with your backend Storage Account details, then run:

```bash
cd configuration
terraform init -backend-config="backend-dev.hcl"
```

**Backend initialisation – option B: inline flags (used by GitHub Actions)**

```bash
cd configuration
terraform init \
  -backend-config="resource_group_name=<tf-backend-rg>" \
  -backend-config="storage_account_name=<tf-backend-sa>" \
  -backend-config="container_name=<container>" \
  -backend-config="key=<project>-<env>.terraform.tfstate" \
  -backend-config="use_azuread_auth=true" \
  -upgrade -reconfigure
```

> The GitHub Actions workflow automatically fills these values from repository variables/secrets (`AZURE_TF_RG_NAME`, `AZURE_TF_BACKEND_NAME`, `AZURE_TF_BACKEND_CONTAINER_NAME`, `PROJECT_NAME`). See [section 5](#5-deploy--github-actions-cicd) for details.

---

## 3. Configure your deployment

`configuration/terraform.tfvars` contains non-sensitive defaults. Fields commented with `TODO` must be filled in before the first apply. Sensitive and environment-specific values are **not** stored in this file — they are supplied at plan/apply time via CLI `-var` flags or `TF_VAR_*` environment variables (see below).

```hcl
# ── Project identity ──────────────────────────────────────────────────────────
# TODO: Set your product name (≤ 8 chars, lower-case, no hyphens)
# product_name = "myapp"        # supplied via CLI: -var="product_name=..."

# TODO: Set your environment (sandbox | dev | test | staging | qa | prod)
# env_name = "dev"              # supplied via CLI: -var="env_name=..."

# ── Resource Group ─────────────────────────────────────────────────────────────
# TODO: Replace with the name of the Resource Group provisioned for this cell
# resource_group_name = "MY_AgentCell_RG"   # supplied via TF_VAR_resource_group_name

# ── Entra ID ───────────────────────────────────────────────────────────────────
# TODO: Replace with your Agentic Foundation App Registration values
# entraid_application_client_id = "<app-client-id>"
# app_registration_object_id    = "<app-object-id>"

# ── APIM / OpenAI Gateway ──────────────────────────────────────────────────────
# TODO: Replace with your APIM gateway URL and deployment name
# azure_apim_base_url               = "https://<apim-name>.azure-api.net"
#   → in CI/CD: supplied via TF_VAR_azure_apim_base_url (GitHub variable AZURE_APIM_BASE_URL)
# azure_apim_openai_deployment_name = "gpt-4o"
# azure_apim_openai_api_version     = "2024-02-15-preview"
# azure_apim_sub_key is supplied via TF_VAR_azure_apim_sub_key (GitHub secret AZURE_APIM_SUB_KEY)

# ── Agents ─────────────────────────────────────────────────────────────────────
container_app_agent_names = ["agent1"]

# ── MCPs ───────────────────────────────────────────────────────────────────────
container_app_mcp_configs = {}

# ── UI ─────────────────────────────────────────────────────────────────────────
container_app_ui_app_name       = "uiapp"
container_app_ui_listening_port = 3000

# ── Network: local dev mode (open) — see section 6 to harden ─────────────────
enable_network_restrictions = false
allowed_ip_ranges           = []
```

### Sensitive values

The following variables must **never** be committed to source control. Supply them as:

| Variable | Local laptop | GitHub Actions |
|---|---|---|
| `azure_apim_sub_key` | `export TF_VAR_azure_apim_sub_key="<key>"` | Secret `AZURE_APIM_SUB_KEY` → `TF_VAR_azure_apim_sub_key` |
| `subscription_id` | `export TF_VAR_subscription_id="<id>"` | Variable/secret `AZURE_SUBSCRIPTION_ID` → `TF_VAR_subscription_id` |
| `resource_group_name` | `export TF_VAR_resource_group_name="<rg>"` | Variable/secret `AZURE_TF_RG_NAME` → `TF_VAR_resource_group_name` |

Other variables passed via `TF_VAR_*` in CI/CD:

| GitHub variable/secret | Terraform variable |
|---|---|
| `vars.AZURE_APIM_BASE_URL` | `TF_VAR_azure_apim_base_url` |
| `vars.AZURE_APIM_OPENAI_DEPLOYMENT_NAME` | `TF_VAR_azure_apim_openai_deployment_name` |
| `vars.AZURE_APIM_OPENAI_API_VERSION` | `TF_VAR_azure_apim_openai_api_version` |
| `vars.PROJECT_NAME` | `-var="product_name=..."` (CLI flag) |

---

## 4. Deploy – local development mode

In this mode (`enable_network_restrictions = false`) all PaaS services allow public network access. You can run `terraform apply` directly from your laptop.

```bash
cd configuration

# Set sensitive values as environment variables
export TF_VAR_azure_apim_sub_key="<key>"
export TF_VAR_subscription_id="<subscription-id>"
export TF_VAR_resource_group_name="<resource-group-name>"

terraform plan \
  -var="product_name=myapp" \
  -var="env_name=dev" \
  -var-file="terraform.tfvars"

terraform apply \
  -var="product_name=myapp" \
  -var="env_name=dev" \
  -var-file="terraform.tfvars"
```

**What gets deployed:**

- Virtual Network with subnets (Container Apps, Private Endpoints, Bastion)
- Container App Environment (VNet-integrated)
- Azure Container Registry + private endpoint
- Cosmos DB + private endpoint
- Key Vault + private endpoint
- Storage Account (blob + file share) + private endpoints
- Agent, MCP, UI, and Scheduler Container Apps
- Azure Front Door Premium + WAF
- Azure Bastion (Standard, with tunneling)
- NSGs on every subnet
- Application Insights + Log Analytics

**Outputs you need after apply:**

```bash
terraform output frontdoor_endpoint_hostname   # → public UI URL
terraform output containerapp_agent_urls       # → internal agent FQDNs
terraform output bastion_host_name             # → for developer access
```

---

## 5. Deploy – GitHub Actions CI/CD

The repository ships with a reusable workflow (`deploy-infrastructure-FID.yml`) that deploys infrastructure via GitHub Actions using **OIDC (Federated Identity)** — no long-lived credentials are stored.

### 5a. Required GitHub repository configuration

Configure the following in **Settings → Secrets and variables → Actions** of your agentcell repository:

**Variables (`vars.*`)**

| Variable | Description |
|---|---|
| `AZURE_CLIENT_ID` | Client ID of the Azure App Registration used for OIDC |
| `AZURE_TENANT_ID` | Azure AD Tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Target Azure Subscription ID |
| `AZURE_TF_RG_NAME` | Resource Group containing the Terraform backend Storage Account (also used as the deployment resource group) |
| `AZURE_TF_BACKEND_NAME` | Storage Account name for Terraform remote state |
| `AZURE_TF_BACKEND_CONTAINER_NAME` | Blob container name for Terraform state files |
| `PROJECT_NAME` | Your project/product name (≤ 8 chars, lowercase) – maps to `product_name` Terraform variable |
| `AZURE_APIM_BASE_URL` | APIM gateway URL |
| `AZURE_APIM_OPENAI_DEPLOYMENT_NAME` | OpenAI deployment name in APIM |
| `AZURE_APIM_OPENAI_API_VERSION` | OpenAI API version |

**Secrets (`secrets.*`)**

| Secret | Description |
|---|---|
| `AZURE_APIM_SUB_KEY` | APIM subscription key (sensitive) |
| `GH_PAT_MODULES` | GitHub PAT with `read:packages` / `contents:read` for private Terraform modules |
| `GH_PAT_RUNNER` | (Optional) GitHub PAT for the runner — used by the `github_pat` Terraform variable |

> Variables and secrets can be set at repository level (shared across environments) or overridden at **environment** level for per-environment isolation.

### 5b. Required GitHub environments

Create these environments in **Settings → Environments**:

| Environment | Purpose |
|---|---|
| `dev` / `test` / `qa` / `prod` | Target deployment environments; set environment-specific variables here to override repository-level ones |
| `hitl-approvals` | Human-in-the-loop gate — add required reviewers so that `apply` and `destroy` jobs pause for approval |

### 5c. Backend initialisation in CI/CD

The workflow initialises Terraform using inline `-backend-config` flags sourced from GitHub variables:

```bash
terraform init \
  -backend-config="resource_group_name=${{ env.AZURE_TF_RG_NAME }}" \
  -backend-config="storage_account_name=${{ env.AZURE_TF_BACKEND_NAME }}" \
  -backend-config="container_name=${{ env.AZURE_TF_BACKEND_CONTAINER_NAME }}" \
  -backend-config="key=${{ vars.PROJECT_NAME }}-${{ env.ENV_NAME }}.terraform.tfstate" \
  -backend-config="use_azuread_auth=true" \
  -upgrade -reconfigure
```

State keys follow the pattern `<PROJECT_NAME>-<environment>.terraform.tfstate` (e.g. `myapp-dev.terraform.tfstate`), one per environment.

### 5d. How Terraform variables are supplied in CI/CD

Sensitive and environment-specific Terraform variables are passed via `TF_VAR_*` environment variables in the workflow — they are **not** stored in `terraform.tfvars`:

```yaml
env:
  TF_VAR_subscription_id:                    ${{ env.AZURE_SUBSCRIPTION_ID }}
  TF_VAR_resource_group_name:                ${{ env.AZURE_TF_RG_NAME }}
  TF_VAR_azure_apim_base_url:                ${{ vars.AZURE_APIM_BASE_URL }}
  TF_VAR_azure_apim_sub_key:                 ${{ secrets.AZURE_APIM_SUB_KEY }}
  TF_VAR_azure_apim_openai_deployment_name:  ${{ vars.AZURE_APIM_OPENAI_DEPLOYMENT_NAME }}
  TF_VAR_azure_apim_openai_api_version:      ${{ vars.AZURE_APIM_OPENAI_API_VERSION }}
```

`product_name` and `env_name` are passed as CLI `-var` flags:

```bash
terraform plan \
  -var="product_name=${{ vars.PROJECT_NAME }}" \
  -var="env_name=${{ env.ENV_NAME }}" \
  -var-file="terraform.tfvars"
```

### 5e. Trigger the workflow

The workflow supports both manual dispatch and programmatic invocation:

- **Manual:** Go to **Actions → Deploy Infrastructure → Run workflow**, select the target environment and action (`plan` / `apply` / `destroy`).
- **Automated:** Call the workflow from another workflow using `workflow_call`.

`apply` and `destroy` actions require approval in the `hitl-approvals` environment before proceeding.

---

## 6. Deploy – network-hardened mode (production)

Set `enable_network_restrictions = true` in your `terraform.tfvars` (or pass it via `TF_VAR_enable_network_restrictions`). Also set:

```hcl
enable_network_restrictions = true

# Add your corporate egress IP(s) so the CI runner / Key Vault break-glass access works.
# Find your public IP: curl https://api.ipify.org
allowed_ip_ranges = ["203.0.113.10/32"]   # replace with your actual egress IP

# WAF mode: Detection during onboarding, Prevention for production
frontdoor_waf_mode = "Prevention"

# Bastion subnet — must not overlap with 10.10.0.0/23, 10.10.2.0/24, 10.10.3.0/24
bastion_subnet_cidr = "10.10.4.0/26"
```

**Effect of `enable_network_restrictions = true`:**

| Service | Change |
|---|---|
| Key Vault | Network ACL: Deny all public; allow containerapp subnet + `allowed_ip_ranges` |
| Cosmos DB | `public_network_access = Disabled`; all access via private endpoint only |
| Storage | Network rules: Deny all; allow containerapp subnet + `allowed_ip_ranges` |
| ACR | `public_network_access_enabled = false`; all pulls via private endpoint |

All services remain reachable from Container Apps because the Private Endpoints are always deployed regardless of this flag.

```bash
terraform plan
terraform apply
```

---

## 7. Post-apply steps (network-hardened only)

These are one-time steps required **after the first `terraform apply`** with Front Door.

### 7a. Approve the Front Door Private Link connection

Front Door Premium connects to the Container App Environment via a managed Private Link. This connection starts in **Pending** state and must be approved:

```bash
# Find the pending connection name
az network private-endpoint-connection list \
  --resource-group <your-rg> \
  --name <your-cae-name> \
  --type Microsoft.App/managedEnvironments \
  --query "[?properties.privateLinkServiceConnectionState.status=='Pending'].name" \
  --output tsv

# Approve it
az network private-endpoint-connection approve \
  --resource-group <your-rg> \
  --name <pending-connection-name> \
  --resource-name <your-cae-name> \
  --type Microsoft.App/managedEnvironments \
  --description "Approved"
```

The CAE name is available from: `terraform output container_app_environment_name`

### 7b. Update the Entra ID App Registration redirect URIs

Get the Front Door hostname:

```bash
terraform output frontdoor_endpoint_hostname
# → ep-ui-<suffix>.z01.azurefd.net
```

In the [Azure Portal → Entra ID → App Registrations → your app → Authentication](https://portal.azure.com), add these redirect URIs:

```
https://ep-ui-<suffix>.z01.azurefd.net
https://ep-ui-<suffix>.z01.azurefd.net/api/auth/callback   # if using NextAuth
```

### 7c. Update NEXT_PUBLIC_AZURE_REDIRECT_URI

In `configuration/infrastructure_shared/root/containerapp_ui_app.tf`, replace the internal CAE FQDN with the Front Door hostname:

```hcl
NEXT_PUBLIC_AZURE_REDIRECT_URI = "https://ep-ui-<suffix>.z01.azurefd.net"
```

Then run `terraform apply` again to push the updated env var to the UI Container App.

---

## 8. Accessing the UI

| Mode | URL | Notes |
|---|---|---|
| Local dev | `terraform output containerapp_ui_app_url` | Direct Container App URL, publicly accessible |
| Network-hardened | `terraform output frontdoor_endpoint_hostname` | Front Door URL; direct Container App URL is internal-only |

The UI authenticates users via Entra ID (MSAL). Users must be present in your Azure AD tenant.

---

## 9. Accessing the infrastructure as a developer

In network-hardened mode, PaaS services reject direct connections from outside the VNet. Use **Azure Bastion** to tunnel into the VNet from your laptop — no VPN or jump-box VM required.

### Check Bastion details

```bash
terraform output bastion_host_name   # → bastion-<suffix>
```

### SSH into a VM in the VNet

```bash
az network bastion ssh \
  --name bastion-<suffix> \
  --resource-group <your-rg> \
  --target-resource-id <vm-resource-id> \
  --auth-type AAD
```

### Native client tunnel (for tools like `mongosh`, `redis-cli`, custom ports)

```bash
# Open a local tunnel on port 2222 → VM port 22
az network bastion tunnel \
  --name bastion-<suffix> \
  --resource-group <your-rg> \
  --target-resource-id <vm-resource-id> \
  --resource-port 22 \
  --port 2222

# In a separate terminal:
ssh user@localhost -p 2222
```

### Temporary break-glass access to Key Vault / Cosmos DB from your laptop

Add your current public IP to `allowed_ip_ranges` and re-apply:

```hcl
# terraform.tfvars
allowed_ip_ranges = ["<your-public-ip>/32"]
```

```bash
# Find your current public IP
curl https://api.ipify.org

terraform apply
```

Remove the IP when you're done.

---

## 10. Switching between modes

```bash
# Switch from local dev → hardened (before merging to main / deploying to prod)
# In terraform.tfvars:
enable_network_restrictions = true
allowed_ip_ranges           = ["<ci-runner-ip>/32"]

terraform apply
# Then complete steps 7a–7c above.

# Switch back to local dev (for troubleshooting)
enable_network_restrictions = false
terraform apply
```

No resources are destroyed on toggle — only network rules on Key Vault, Cosmos DB, Storage, and ACR are updated.

---

## 11. Network architecture summary

```
Internet
  │
  ▼
Azure Front Door Premium (WAF: OWASP DefaultRuleSet + BotProtection)
  │  Private Link (managed by Front Door Premium)
  ▼
┌─────────────────────────────── Virtual Network 10.10.0.0/16 ────────────────────────┐
│                                                                                      │
│  Container App Subnet 10.10.0.0/23          Private Endpoint Subnet 10.10.3.0/24   │
│  ┌──────────────────────────────┐            ┌────────────────────────────────────┐  │
│  │  Container App Environment   │◄──────────►│  PE: ACR                           │  │
│  │  ┌──────────┐  ┌──────────┐  │            │  PE: Cosmos DB                     │  │
│  │  │  UI App  │  │  Agent   │  │            │  PE: Key Vault                     │  │
│  │  │(internal)│  │(internal)│  │            │  PE: Storage (blob + file)         │  │
│  │  └──────────┘  └──────────┘  │            └────────────────────────────────────┘  │
│  │  ┌──────────┐                │                                                    │
│  │  │   MCP    │                │  Outbound internet egress (port 443 only):         │
│  │  │(internal)│                │  • AzureActiveDirectory  (OIDC token exchange)     │
│  │  └──────────┘                │  • APIM public endpoint  (Azure OpenAI gateway)    │
│  └──────────────────────────────┘                                                    │
│                                                                                      │
│  AzureBastionSubnet 10.10.4.0/26                                                    │
│  ┌────────────────────────────┐                                                      │
│  │  Azure Bastion (Standard)  │◄── Developer browser / az CLI (HTTPS on port 443)   │
│  └────────────────────────────┘                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**No Container App has a public FQDN** (`external_enabled = false` on all ingress blocks). The only public surfaces are:
- Front Door endpoint (UI access, protected by WAF)
- Bastion public IP (developer access, HTTPS/443 only)

---

## 12. Known limitations / TODOs

| # | Item | Location | Impact |
|---|---|---|---|
| 1 | **CAE internal mode not enabled** | [containerapp_environment.tf](infrastructure_shared/root/containerapp_environment.tf#L21) | The CAE still has an Azure-managed public IP (not routable to any app). Requires `internal_load_balancer_enabled` to be added to the upstream `containerapp_environment` module. See the `TODO` block in that file for the exact changes needed. |
| 2 | **APIM egress is public** | [network_nsg.tf](infrastructure_shared/root/network_nsg.tf) rule `Allow-APIM-OpenAI` | Agents reach Azure OpenAI via the public APIM gateway. Tighten by scoping the destination to the APIM public IP, or eliminate by moving APIM to a private endpoint / VNet-injected deployment. |
| 3 | **Front Door Private Link requires manual approval** | Post-apply step 7a | Cannot be automated via the current Terraform provider without an `azapi_update_resource` workaround. |
| 4 | **WAF starts in Detection mode** | `frontdoor_waf_mode = "Detection"` | Switch to `"Prevention"` once you have confirmed no false positives in your workload. |
