# =============================================================================
# terraform.tfvars – non-sensitive defaults
# Override per-environment values using tfvars files passed at CLI:
#   terraform apply -var-file="envs/<env>.tfvars"
# Sensitive values (API keys, passwords) must be supplied via CI/CD secrets.
# =============================================================================

# ── Project identity ──────────────────────────────────────────────────────────
# TODO: Set your product name (≤ 8 chars, lower-case, no hyphens)
product_name = "licagree"

# TODO: Set your environment (sandbox | dev | test | staging | qa | prod)
# env_name = "dev"

# ── Resource Group ─────────────────────────────────────────────────────────────
# TODO: Replace with the name of the Resource Group provisioned for this cell
resource_group_name = "rg-ac-license-agreement-171817-sandbox"

# ── Entra ID ───────────────────────────────────────────────────────────────────
# TODO: Replace with your Agentic Foundation App Registration values
entraid_application_client_id = "73a96b5d-083f-4b82-a3e8-47807e98ef5e"
app_registration_object_id    = "4561ce80-6451-45c7-a410-0fc379f07e73"

# ── APIM / OpenAI Gateway ──────────────────────────────────────────────────────
# TODO: Replace with your APIM gateway URL and deployment name
azure_apim_base_url               = "https://<your-apim-name>.azure-api.net"
azure_apim_openai_deployment_name = "gpt-4o"                                                                                                                   
azure_apim_openai_api_version     = "2024-02-15-preview"
# azure_apim_sub_key is supplied via GH Secret AZURE_APIM_SUB_KEY

# ── Agents ─────────────────────────────────────────────────────────────────────
# One Container App is created per entry. Use short lowercase identifiers.
container_app_agent_names = ["licopt"]
# Example for multiple agents: ["accr", "deferls", "reposts"]

# ── MCPs ───────────────────────────────────────────────────────────────────────
# Add/remove MCPs here. Each entry creates one Container App.
container_app_mcp_configs = {
  # "emailmcp" = { listening_port = 8000, extra_env_vars = {} }
  # "spmcp"    = { listening_port = 8000, extra_env_vars = {} }
}

# ── UI ─────────────────────────────────────────────────────────────────────────
container_app_ui_app_name = "webapp"                                                                                
container_app_ui_listening_port = 8000

# ── Ports ──────────────────────────────────────────────────────────────────────
container_app_agent_listening_port = 8000

# ── Agent runtime ──────────────────────────────────────────────────────────────
agent_app_authentication_enabled      = false
agent_app_authentication_require_auth = false
agent_debugpy_enable                  = false
agent_debugpy_wait                    = false

# ── Observability ──────────────────────────────────────────────────────────────
observability_enable_tracing  = false
observability_enable_metrics  = false
observability_enable_logging  = false

# ── Scheduler ──────────────────────────────────────────────────────────────────
scheduler_enabled                 = false
scheduler_cpu                     = 0.5
scheduler_memory                  = "1Gi"
scheduler_replica_timeout_seconds = 300
scheduler_replica_retry_limit     = 1
scheduler_agent_path              = "/"
scheduler_agent_timeout           = 1

# Define scheduler configs here when scheduler_enabled = true.
# agent_name must match an entry in container_app_agent_names.
scheduler_configs = [
  # { agent_name = "agent1", schedule_id = "monthly", cron = "0 6 1 * *", description = "Monthly run" },
]

# ── Network security ───────────────────────────────────────────────────────────
enable_network_restrictions = true
allowed_ip_ranges           = []

# ── Tags ───────────────────────────────────────────────────────────────────────
additional_tags = {
  # team    = "my-team"
  # project = "my-project"
}
