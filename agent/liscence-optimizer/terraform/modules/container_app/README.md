# Container App Module

This module creates an Azure Container App in an existing Container Apps Environment.

## Features

- ✅ Configurable auto-scaling (min/max replicas)
- ✅ HTTP ingress with external access
- ✅ Environment variables support
- ✅ Resource limits (CPU/Memory)
- ✅ Tagging support

## Usage

```hcl
module "container_app" {
  source = "../../modules/container_app"

  container_app_name           = "my-app-test"
  resource_group_name          = "shared-rg"
  container_app_environment_id = "/subscriptions/.../managedEnvironments/env"
  environment                  = "test"
  
  container_image = "myregistry.azurecr.io/my-app:latest"
  port            = "8000"
  
  min_replicas = 1
  max_replicas = 3
  
  cpu    = 0.5
  memory = "1Gi"

  tags = {
    Environment = "Test"
    Application = "MyApp"
  }
}
```

## Required Inputs

| Name | Description | Type |
|------|-------------|------|
| container_app_name | Name of the container app | string |
| resource_group_name | Name of the resource group | string |
| container_app_environment_id | ID of Container Apps Environment | string |
| environment | Environment name (test/staging/prod) | string |
| container_image | Container image to deploy | string |

## Optional Inputs

| Name | Description | Type | Default |
|------|-------------|------|---------|
| container_name | Name of container within app | string | "main" |
| cpu | CPU cores to allocate | number | 0.5 |
| memory | Memory to allocate (Gi) | string | "1Gi" |
| min_replicas | Minimum replicas | number | 1 |
| max_replicas | Maximum replicas | number | 3 |
| port | Container port | string | "8000" |
| external_ingress_enabled | Enable external ingress | bool | true |
| additional_env_vars | Additional environment variables | list(object) | [] |
| tags | Resource tags | map(string) | {} |

## Outputs

| Name | Description |
|------|-------------|
| id | Container App resource ID |
| name | Container App name |
| fqdn | Fully qualified domain name |
| url | HTTPS URL of the app |
| latest_revision_name | Latest revision name |
