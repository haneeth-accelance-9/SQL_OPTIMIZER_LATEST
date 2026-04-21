# Staging Environment Configuration

# Existing Infrastructure
# Note: These can be provided via CLI:
#   --resource-group "my-rg" --container-env "my-env"
# Or uncomment and set here:
# resource_group_name             = "shared-infrastructure-rg"
# container_app_environment_name  = "shared-container-env"

# Container Configuration
container_app_name = "liscence-optimizer"
container_image    = "your-registry.azurecr.io/liscence-optimizer:staging"
port               = "8000"

# Scaling - Moderate for staging
min_replicas = 1
max_replicas = 5

# Resource Limits - Standard for staging
cpu    = 0.5
memory = "1Gi"

# Tags
tags = {
  Environment = "Staging"
  Application = "LiscenceOptimizer"
  CostCenter  = "Engineering"
}