# Backend configuration for the prod environment.
# Used with: terraform init -backend-config="backend-prod.hcl"

resource_group_name  = "REPLACE_WITH_TF_BACKEND_RG"
storage_account_name = "REPLACE_WITH_TF_BACKEND_SA"
container_name       = "tfstate"
key                  = "prod.terraform.tfstate"
