# Test Environment Configuration

# Existing Infrastructure
# Note: These can be provided via CLI:
#   --resource-group "my-rg" --container-env "my-env"
# Or uncomment and set here:
# resource_group_name             = "shared-infrastructure-rg"
# container_app_environment_name  = "shared-container-env"

# Container Configuration
container_app_name = "liscence-optimizer"
container_image    = "your-registry.azurecr.io/liscence-optimizer:test"
port               = "8000"

# Scaling - Conservative for test
min_replicas = 1
max_replicas = 2

# Resource Limits - Lower for test
cpu    = 0.25
memory = "0.5Gi"

# Tags
tags = {
  Environment = "Test"
  Application = "LiscenceOptimizer"
  CostCenter  = "Engineering"
}