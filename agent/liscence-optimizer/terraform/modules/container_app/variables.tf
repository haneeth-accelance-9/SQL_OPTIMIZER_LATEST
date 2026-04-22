# Container App Module Variables

variable "container_app_name" {
  description = "Name of the container app"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "container_app_environment_id" {
  description = "ID of the Container Apps Environment"
  type        = string
}

variable "environment" {
  description = "Environment name (test, staging, prod)"
  type        = string
}

variable "container_name" {
  description = "Name of the container within the app"
  type        = string
  default     = "main"
}

variable "container_image" {
  description = "Container image to deploy"
  type        = string
}

variable "cpu" {
  description = "CPU cores to allocate to the container"
  type        = number
  default     = 0.5
}

variable "memory" {
  description = "Memory to allocate to the container (in Gi)"
  type        = string
  default     = "1Gi"
}

variable "min_replicas" {
  description = "Minimum number of replicas"
  type        = number
  default     = 1
}

variable "max_replicas" {
  description = "Maximum number of replicas"
  type        = number
  default     = 3
}

variable "port" {
  description = "Port the container listens on"
  type        = string
  default     = "8000"
}

variable "external_ingress_enabled" {
  description = "Whether to enable external ingress"
  type        = bool
  default     = true
}

variable "additional_env_vars" {
  description = "Additional environment variables for the container"
  type = list(object({
    name  = string
    value = string
  }))
  default = []
}

variable "tags" {
  description = "Tags to apply to the resources"
  type        = map(string)
  default     = {}
}
