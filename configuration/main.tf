terraform {
  required_version = ">=1.5.7"

  # Backend config provided via -backend-config flag at runtime:
  #   terraform init -backend-config="backend-<env>.hcl"
  backend "azurerm" {}
  # backend "local" {} # For testing only. Use azurerm backend in production.
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

# =============================================================================
# Root Stack Module
# Calls the shared infrastructure root module which provisions all Azure
# resources (VNet, ACR, Container Apps, CosmosDB, etc.)
# =============================================================================
module "agentcell_stack" {
  source = "git::https://github.com/bayer-int/agentic_ai_template_azure_infrastructure.git//terraform/root?ref=v1.0.2"

  # ── Identity ──────────────────────────────────────────────────────────────
  product_name    = var.product_name
  env_name        = var.env_name
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id

  # ── IAM ───────────────────────────────────────────────────────────────────
  entraid_application_client_id = var.entraid_application_client_id
  app_registration_object_id    = var.app_registration_object_id

  # ── Resource Group (provisioned externally) ────────────────────────────────
  resource_group_name = var.resource_group_name

  # ── APIM / OpenAI Gateway ─────────────────────────────────────────────────
  azure_apim_base_url               = var.azure_apim_base_url
  azure_apim_sub_key                = var.azure_apim_sub_key
  azure_apim_openai_deployment_name = var.azure_apim_openai_deployment_name
  azure_apim_openai_api_version     = var.azure_apim_openai_api_version

  # ── Resource-naming prefixes ───────────────────────────────────────────────
  storage_account_name_prefix             = var.storage_account_name_prefix
  acr_name_prefix                         = var.acr_name_prefix
  storage_account_prefix                  = var.storage_account_prefix
  file_share_prefix                       = var.file_share_prefix
  cosmosdbaccount_name_prefix             = var.cosmosdbaccount_name_prefix
  keyvault_name_prefix                    = var.keyvault_name_prefix
  log_analytics_workspace_name_prefix     = var.log_analytics_workspace_name_prefix
  application_insights_name_prefix        = var.application_insights_name_prefix
  app_service_plan_name_prefix            = var.app_service_plan_name_prefix
  web_app_name_prefix                     = var.web_app_name_prefix
  vnet_name_prefix                        = var.vnet_name_prefix
  subnet_name_prefix                      = var.subnet_name_prefix
  nsg_name_prefix                         = var.nsg_name_prefix
  private_dns_zone_link_prefix            = var.private_dns_zone_link_prefix
  private_endpoint_name_prefix            = var.private_endpoint_name_prefix
  container_app_environment_name_prefix   = var.container_app_environment_name_prefix
  container_app_name_prefix               = var.container_app_name_prefix

  # ── Monitoring ─────────────────────────────────────────────────────────────
  reservation_capacity_in_gb_per_day = var.reservation_capacity_in_gb_per_day

  # ── Agents ─────────────────────────────────────────────────────────────────
  # List of short agent identifiers — one Container App is created per entry.
  # Example: ["agentA", "agentB"]  →  ca-agentA-<suffix>, ca-agentB-<suffix>
  container_app_agent_names = var.container_app_agent_names

  # ── MCPs ───────────────────────────────────────────────────────────────────
  # Map of MCP name → config.  One Container App is created per entry.
  # Example:
  #   container_app_mcp_configs = {
  #     "emailmcp" = { listening_port = 8000, extra_env_vars = {} }
  #     "spmcp"    = { listening_port = 8000, extra_env_vars = {} }
  #   }
  container_app_mcp_configs = var.container_app_mcp_configs

  # ── UI ─────────────────────────────────────────────────────────────────────
  container_app_ui_app_name       = var.container_app_ui_app_name
  container_app_ui_listening_port = var.container_app_ui_listening_port

  # ── Ports ──────────────────────────────────────────────────────────────────
  container_app_agent_listening_port = var.container_app_agent_listening_port

  # ── Agent runtime config ───────────────────────────────────────────────────
  agent_app_authentication_enabled      = var.agent_app_authentication_enabled
  agent_app_authentication_require_auth = var.agent_app_authentication_require_auth
  agent_debugpy_enable                  = var.agent_debugpy_enable
  agent_debugpy_wait                    = var.agent_debugpy_wait

  # ── Observability ──────────────────────────────────────────────────────────
  observability_enable_tracing  = var.observability_enable_tracing
  observability_enable_metrics  = var.observability_enable_metrics
  observability_enable_logging  = var.observability_enable_logging

  # ── Scheduler ──────────────────────────────────────────────────────────────
  scheduler_enabled                 = var.scheduler_enabled
  scheduler_cpu                     = var.scheduler_cpu
  scheduler_memory                  = var.scheduler_memory
  scheduler_replica_timeout_seconds = var.scheduler_replica_timeout_seconds
  scheduler_replica_retry_limit     = var.scheduler_replica_retry_limit
  scheduler_agent_path              = var.scheduler_agent_path
  scheduler_agent_timeout           = var.scheduler_agent_timeout
  # Map of agent_name → list of { schedule_id, cron, description }
  # Leave empty {} to disable all schedulers.
  scheduler_configs = var.scheduler_configs

  # ── Network security ────────────────────────────────────────────────────────
  allowed_ip_ranges           = var.allowed_ip_ranges
  enable_network_restrictions = var.enable_network_restrictions

  # ── Key Vault ───────────────────────────────────────────────────────────────
  developer_object_id = var.developer_object_id

  # ── Tags ───────────────────────────────────────────────────────────────────
  additional_tags = var.additional_tags
}
