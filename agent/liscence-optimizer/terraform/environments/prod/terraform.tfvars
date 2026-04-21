# Production Environment Configuration

# Existing Infrastructure
# Note: These can be provided via CLI:
#   --resource-group "my-rg" --container-env "my-env"
# Or uncomment and set here:
# resource_group_name             = "shared-infrastructure-rg"
# container_app_environment_name  = "shared-container-env"

# Container Configuration
container_app_name = "liscence-optimizer"
container_image    = "your-registry.azurecr.io/liscence-optimizer:latest"
port               = "8000"

# Scaling - High capacity for production
min_replicas = 2
max_replicas = 10

# Resource Limits - Maximum for production
cpu    = 1.0
memory = "2Gi"

# Tags
tags = {
  Environment = "Production"
  Application = "LiscenceOptimizer"
  CostCenter  = "Engineering"
  Critical    = "true"
}