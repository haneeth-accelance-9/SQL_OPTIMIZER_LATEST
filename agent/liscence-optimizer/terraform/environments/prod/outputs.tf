# Production Environment Outputs

output "container_app_id" {
  description = "The ID of the Container App"
  value       = module.container_app.id
}

output "container_app_name" {
  description = "The name of the Container App"
  value       = module.container_app.name
}

output "container_app_fqdn" {
  description = "The FQDN of the Container App"
  value       = module.container_app.fqdn
}

output "container_app_url" {
  description = "The URL of the Container App"
  value       = module.container_app.url
}

output "environment" {
  description = "The deployment environment"
  value       = "prod"
}
