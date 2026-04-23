# Test Environment Configuration

module "container_app" {
  source = "../../modules/container_app"

  # App Configuration
  container_app_name           = "${var.container_app_name}-test"
  resource_group_name          = data.azurerm_resource_group.main.name
  container_app_environment_id = data.azurerm_container_app_environment.main.id
  environment                  = "test"

  # Container Configuration
  container_name  = var.container_name
  container_image = var.container_image
  port            = var.port

  # Scaling Configuration
  min_replicas = var.min_replicas
  max_replicas = var.max_replicas

  # Resource Limits
  cpu    = var.cpu
  memory = var.memory

  # Ingress Configuration
  external_ingress_enabled = var.external_ingress_enabled

  # Additional Environment Variables
  additional_env_vars = var.additional_env_vars

  # Tags
  tags = merge(
    var.tags,
    {
      Environment = "Test"
      ManagedBy   = "Terraform"
    }
  )
}
