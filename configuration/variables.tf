# =============================================================================
# Configuration Root – Variables
# All top-level variables passed into the infrastructure_shared/root module.
# Environment-specific values live in terraform.tfvars / backend-<env>.hcl.
# Sensitive values (API keys, secrets) must be supplied as CI/CD secrets and
# never committed to source control.
# =============================================================================

# ── Core identity ────────────────────────────────────────────────────────────

variable "subscription_id" {
  description = "Azure Subscription ID."
  type        = string
}

variable "tenant_id" {
  description = "Azure AD Tenant ID. Defaults to the authenticated tenant when empty."
  type        = string
  default     = ""
}

variable "env_name" {
  description = "Deployment environment. Allowed: sandbox | dev | test | staging | qa | prod."
  type        = string
  validation {
    condition     = contains(["sandbox", "dev", "test", "staging", "qa", "prod"], var.env_name)
    error_message = "Invalid environment. Choose from: sandbox, dev, test, staging, qa, prod."
  }
}

variable "product_name" {
  description = "Short product identifier used in resource names (≤ 8 chars, lower-case, no hyphens)."
  type        = string
  validation {
    condition     = length(var.product_name) <= 8
    error_message = "product_name must be 8 characters or fewer."
  }
}

# ── IAM ──────────────────────────────────────────────────────────────────────

variable "entraid_application_client_id" {
  description = "Application (client) ID of the Agentic Foundation App Registration."
  type        = string
  default     = ""
}

variable "app_registration_object_id" {
  description = "Object ID of the Agentic Foundation App Registration."
  type        = string
  default     = ""
}

variable "resource_group_name" {
  description = "Name of the pre-existing Azure Resource Group (provisioned outside Terraform)."
  type        = string
}

# ── APIM / OpenAI Gateway ─────────────────────────────────────────────────────

variable "azure_apim_base_url" {
  description = "Azure APIM Gateway base URL for OpenAI access."
  type        = string
  default     = "http://placeholder.azure-api.net"
}

variable "azure_apim_sub_key" {
  description = "Azure APIM subscription key. Supply via GH Secret – never commit."
  type        = string
  sensitive   = true
  default     = "placeholder-key"
}

variable "azure_apim_openai_deployment_name" {
  description = "OpenAI deployment name configured in APIM."
  type        = string
  default     = "gpt-4o"
}

variable "azure_apim_openai_api_version" {
  description = "OpenAI API version used with the APIM gateway."
  type        = string
  default     = "2024-02-15-preview"
}

# ── Resource-naming prefixes ──────────────────────────────────────────────────

variable "storage_account_name_prefix" {
  default     = "staf"
  description = "Storage account name prefix (alphanumeric)."
}

variable "acr_name_prefix" {
  default     = "acr"
  description = "Azure Container Registry name prefix."
}

variable "storage_account_prefix" {
  default     = "staf"
  description = "Secondary storage account prefix."
}

variable "file_share_prefix" {
  default     = "share"
  description = "File share name prefix."
}

variable "cosmosdbaccount_name_prefix" {
  default     = "cosmos"
  description = "Cosmos DB account name prefix."
}

variable "keyvault_name_prefix" {
  default     = "kv"
  description = "Key Vault name prefix (Key Vault names max 24 chars total)."
}

variable "log_analytics_workspace_name_prefix" {
  default     = "log"
  description = "Log Analytics workspace name prefix."
}

variable "application_insights_name_prefix" {
  default     = "appi"
  description = "Application Insights name prefix."
}

variable "app_service_plan_name_prefix" {
  default     = "asp"
  description = "App Service Plan name prefix."
}

variable "web_app_name_prefix" {
  default     = "app"
  description = "Linux Web App name prefix."
}

variable "vnet_name_prefix" {
  default     = "vnet"
  description = "Virtual network name prefix."
}

variable "subnet_name_prefix" {
  default     = "snet"
  description = "Subnet name prefix."
}

variable "nsg_name_prefix" {
  default     = "nsg"
  description = "Network Security Group name prefix."
}

variable "private_dns_zone_link_prefix" {
  default     = "dnslink"
  description = "Private DNS zone VNet link name prefix."
}

variable "private_endpoint_name_prefix" {
  default     = "pe"
  description = "Private endpoint name prefix."
}

variable "container_app_environment_name_prefix" {
  default     = "cae"
  description = "Container App Environment name prefix."
}

variable "container_app_name_prefix" {
  default     = "ca"
  description = "Container App name prefix."
}

variable "aifoundry_name_prefix" {
  default     = "aif"
  description = "AI Foundry resource name prefix."
}

variable "aifoundry_custom_subdomain" {
  default     = ""
  description = "Custom subdomain for AI Foundry (leave empty to auto-generate)."
}

# ── Monitoring ────────────────────────────────────────────────────────────────

variable "reservation_capacity_in_gb_per_day" {
  type        = number
  description = "Log Analytics daily capacity reservation in GB. Set null to disable."
  default     = null
}

# ── Agents ────────────────────────────────────────────────────────────────────

variable "container_app_agent_names" {
  type        = list(string)
  description = "List of agent short names. One Container App is deployed per entry."
  default     = ["agent1"]
  # Example: ["accr", "deferls", "reposts"]
}

# ── MCPs ──────────────────────────────────────────────────────────────────────

variable "container_app_mcp_configs" {
  description = <<-EOT
    Map of MCP name → configuration. One Container App is deployed per entry.
    Keys become part of the resource name (ca-<name>-<suffix>).
    extra_env_vars are merged on top of the standard set.
    Example:
      {
        "emailmcp" = { listening_port = 8000, extra_env_vars = { LOG_LEVEL = "DEBUG" } }
        "spmcp"    = { listening_port = 8000, extra_env_vars = {} }
      }
  EOT
  type = map(object({
    listening_port = number
    extra_env_vars = map(string)
  }))
  default = {}
}

# ── UI ────────────────────────────────────────────────────────────────────────

variable "container_app_ui_app_name" {
  default     = "uiapp"
  description = "Name suffix for the UI Container App."
}

variable "container_app_ui_listening_port" {
  default     = 3000
  description = "Port the UI container app listens on."
}

# ── Ports ──────────────────────────────────────────────────────────────────────

variable "container_app_agent_listening_port" {
  default     = 8000
  description = "Port every agent Container App listens on."
}

# ── Agent runtime config ───────────────────────────────────────────────────────

variable "agent_app_authentication_enabled" {
  type    = bool
  default = true
}

variable "agent_app_authentication_require_auth" {
  type    = bool
  default = true
}

variable "agent_debugpy_enable" {
  type    = bool
  default = false
}

variable "agent_debugpy_wait" {
  type    = bool
  default = false
}

# ── Observability ──────────────────────────────────────────────────────────────

variable "observability_enable_tracing" {
  type    = bool
  default = false
}

variable "observability_enable_metrics" {
  type    = bool
  default = false
}

variable "observability_enable_logging" {
  type    = bool
  default = false
}

# ── Scheduler ─────────────────────────────────────────────────────────────────

variable "scheduler_enabled" {
  type    = bool
  default = false
}

variable "scheduler_cpu" {
  type    = number
  default = 0.5
}

variable "scheduler_memory" {
  type    = string
  default = "1Gi"
}

variable "scheduler_replica_timeout_seconds" {
  type    = number
  default = 300
}

variable "scheduler_replica_retry_limit" {
  type    = number
  default = 1
}

variable "scheduler_agent_path" {
  type    = string
  default = "/"
}

variable "scheduler_agent_timeout" {
  type    = number
  default = 1
}

variable "scheduler_configs" {
  description = <<-EOT
    List of scheduler configs. Each entry creates one Container App Job.
    agent_name must match an entry in container_app_agent_names.
    cron expressions use UTC timezone.
    Example:
      [
        { agent_name = "accr", schedule_id = "monthly", cron = "0 6 1 * *",  description = "Monthly accruals run" },
        { agent_name = "accr", schedule_id = "midmonth", cron = "0 6 15 * *", description = "Mid-month accruals run" },
      ]
  EOT
  type = list(object({
    agent_name   = string
    schedule_id  = string
    cron         = string
    description  = string
  }))
  default = []
}

# ── Network security ───────────────────────────────────────────────────────────

variable "allowed_ip_ranges" {
  description = "IP ranges allowed to access network-restricted resources (emergency/debug access)."
  type        = list(string)
  default     = []
}

variable "enable_network_restrictions" {
  description = "Toggle network restrictions on ACR, Storage, and CosmosDB. Requires OIDC auth."
  type        = bool
  default     = false
}

# ── Tags ───────────────────────────────────────────────────────────────────────

variable "additional_tags" {
  description = "Extra tags merged with the default tag set (can override data-classification)."
  type        = map(string)
  default     = {}
}

# ── Key Vault ─────────────────────────────────────────────────────────────────

variable "developer_object_id" {
  description = "Entra ID Object ID of a developer for local testing Key Vault access. Leave null to skip."
  type        = string
  default     = null
}
