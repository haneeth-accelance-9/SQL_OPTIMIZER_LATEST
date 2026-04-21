# Container App Module Outputs

output "id" {
  description = "The ID of the Container App"
  value       = azurerm_container_app.main.id
}

output "name" {
  description = "The name of the Container App"
  value       = azurerm_container_app.main.name
}

output "fqdn" {
  description = "The FQDN of the Container App"
  value       = azurerm_container_app.main.latest_revision_fqdn
}

output "url" {
  description = "The URL of the Container App"
  value       = "https://${azurerm_container_app.main.latest_revision_fqdn}"
}

output "latest_revision_name" {
  description = "The name of the latest revision"
  value       = azurerm_container_app.main.latest_revision_name
}
