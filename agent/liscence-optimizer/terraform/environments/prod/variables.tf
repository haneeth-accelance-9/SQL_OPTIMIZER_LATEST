# Production Environment Variables

variable "resource_group_name" {
  description = "Name of the existing resource group"
  type        = string
}

variable "container_app_environment_name" {
  description = "Name of the existing Container Apps Environment"
  type        = string
}

variable "container_app_name" {
  description = "Base name of the container app (will be suffixed with environment)"
  type        = string
  default     = "liscence-optimizer"
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
  description = "CPU cores to allocate"
  type        = number
  default     = 1.0
}

variable "memory" {
  description = "Memory to allocate (in Gi)"
  type        = string
  default     = "2Gi"
}

variable "min_replicas" {
  description = "Minimum number of replicas"
  type        = number
  default     = 2
}

variable "max_replicas" {
  description = "Maximum number of replicas"
  type        = number
  default     = 10
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
  description = "Additional environment variables"
  type = list(object({
    name  = string
    value = string
  }))
  default = []
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default = {
    Application = "LiscenceOptimizer"
  }
}