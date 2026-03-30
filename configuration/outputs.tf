output "resource_group_name" {
  value       = module.agentcell_stack.resource_group_name
  description = "Name of the resource group."
}

output "acr_login_server" {
  value       = module.agentcell_stack.acr_login_server
  description = "ACR login server URL."
}

output "container_app_agent_urls" {
  value       = module.agentcell_stack.containerapp_agent_urls
  description = "Map of agent name → Container App URL."
}

output "container_app_mcp_urls" {
  value       = module.agentcell_stack.containerapp_mcp_urls
  description = "Map of MCP name → Container App URL."
}

output "container_app_ui_url" {
  value       = module.agentcell_stack.containerapp_ui_app_url
  description = "UI Container App URL."
}

output "cosmosdbaccount_endpoint" {
  value       = module.agentcell_stack.cosmosdbaccount_endpoint
  description = "Cosmos DB endpoint."
}

output "container_app_identity_client_id" {
  value       = module.agentcell_stack.container_app_identity_client_id
  description = "Client ID of the shared managed identity used by all Container Apps."
}
