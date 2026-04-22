# Container App Module
# This module creates an Azure Container App in an existing environment

resource "azurerm_container_app" "main" {
  name                         = var.container_app_name
  container_app_environment_id = var.container_app_environment_id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"
  tags                         = var.tags

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name   = var.container_name
      image  = var.container_image
      cpu    = var.cpu
      memory = var.memory

      env {
        name  = "PORT"
        value = var.port
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      dynamic "env" {
        for_each = var.additional_env_vars
        content {
          name  = env.value.name
          value = env.value.value
        }
      }
    }
  }

  ingress {
    external_enabled = var.external_ingress_enabled
    target_port      = var.port
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}
