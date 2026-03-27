# GitHub Copilot Terraform Instructions

> These instructions are for GitHub Copilot and Copilot Chat when generating Terraform configurations in this repository.

---

## General Guidelines

1. **Whenever possible, use approved Terraform modules** from Bayer internal repositories (see "Preferred Modules").
2. **Always use the latest released version** of the module.

   * **Before referencing a module, always check the latest released version by running:**

     ```bash
     git ls-remote --tags <repo-url>
     ```
   * **Use the latest tag in the `ref` parameter of the module source (e.g., `ref=v1.2.3`).**
   * **Never use `latest` or omit the version.**
   * **If no tags are available, use the latest commit hash from the main branch.**
   * **Document the version used in the code or comments for traceability.**
   * **Review the module's CHANGELOG or release notes before upgrading to a new version to avoid breaking changes.**
3. **Avoid creating Azure resources manually (`azurerm_*`)** if a corresponding module is available.
4. **Provider configuration must always be stored in a separate file named `terraform.tf`** at the root of the project.

   * Never include `provider` or `backend` blocks inside modules.
5. **After generating or modifying Terraform code**, always:

   * Run `[ "$(basename $(pwd))" != "configuration" ] && cd configuration` to ensure you are in the correct directory (requires a Unix-like shell, such as Bash).
     For Windows PowerShell, use the equivalent command:
     ```powershell
     if ((Get-Item -Path ".").Name -ne "configuration") { Set-Location -Path "configuration" }
     ```
   * Run `terraform init --backend=false` to install providers and modules.
   * Run `terraform fmt` to fix formatting for all `.tf` files.
   * Run `terraform validate` to detect errors.
   * Run `pre-commit run -a` to ensure compliance with repo checks.
   * Apply fixes for any validation or formatting issues found.
6. **Store all Terraform configuration files inside the `configuration/` directory.**

   * This folder is used by GitHub Actions for deployment.
> **Note:** All main infrastructure configurations (e.g., main.tf, `variables.tf`, `terraform.tfvars`) must be placed directly in the root of the configuration directory. Subdirectories should only be used for submodules or examples, and their usage must be referenced from the root.

7. **Do not change the contents of the `configuration/examples/` folder.**

   * It contains official usage examples of SCA modules.
   * **If a bug is found in the `configuration/examples/` folder or in one of the Bayer approved modules, help the user compose an error report message and ask them to post this message to the SCA Team channel:**
     https://teams.microsoft.com/l/channel/19%3A2e31c3ac228343f9962c9400b7594d0a%40thread.skype/SCA%20-%20SMART%20Cloud%20Automation?groupId=daa8392e-7099-4414-8a18-262100c24624&tenantId=fcb2b37b-5da0-466b-9b83-0014b67a7c78
8. **Validate all generated or modified Terraform code before asking the user for further actions.**

Copilot must ensure that the proposed code is syntactically correct and passes Terraform validation (terraform validate) before suggesting next steps or asking for user input.
If the code is invalid, Copilot must fix the issues automatically or notify the user about the errors with clear explanations.

Example:

```plaintext
❗ Validation failed: The generated Terraform code contains errors.
- Error: Missing required argument `location` in resource `azurerm_resource_group`.
- Suggested fix: Add the `location` argument with a valid Azure region (e.g., `location = "East US"`).
```
After fixing the issues, revalidate the code before proceeding.

9. **Do not ask the user for further actions until the code is valid.**

Copilot must confirm that the code passes terraform validate and is properly formatted (terraform fmt) before prompting the user for additional steps.

> Note: You do not need to run `terraform plan` or `terraform apply` locally. Infrastructure is deployed via GitHub Actions workflows.
> Copilot's responsibility is to generate a valid, properly structured, and validated configuration.
> For more context, Copilot can refer to the repository README and GitHub Actions workflows to understand deployment flow.

10. **Handle restricted access to module repositories gracefully.**

If Copilot cannot access a module repository URL (e.g., due to internal repository restrictions):
* Check the .terraform/modules directory for the downloaded module.
* If the directory is not available - run `terraform init --backend=false` and try again.
* Extract relevant information (e.g., input variables, outputs, examples) from the module files in .terraform/modules.
* Use this information to generate or validate the Terraform configuration.

11. **Use the Conventional Commit format for all commit messages.**

    * Copilot must ensure that all commit messages follow the **Conventional Commit** specification.
    * The format is as follows:

      ```plaintext
      <type>[optional scope]: <description>

      [optional body]

      [optional footer(s)]
      ```

    * Common types include:
      - `feat`: A new feature
      - `fix`: A bug fix
      - `docs`: Documentation changes
      - `style`: Code style changes (formatting, no functional changes)
      - `refactor`: Code refactoring (no new features or bug fixes)
      - `test`: Adding or updating tests
      - `chore`: Maintenance tasks (e.g., updating dependencies)

    * Example commit messages:
      - `feat(vnet): add support for multiple subnets`
      - `fix(vm): resolve issue with incorrect VM size`
      - `docs: update README with usage examples`

    * If Copilot generates a commit message, it must adhere to this format.
    * Before running the command `git add .`, Copilot must ensure it is in the **root directory of the repository**. If not, it should navigate to the root directory using:

      ```bash
      cd $(git rev-parse --show-toplevel)
      ```

---

## Preferred Modules

When generating infrastructure code, prioritize using the following approved modules created by the SCA Team:

| Purpose                | Module                                                                                                              | Description                                                            |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Virtual Machine (VM)   | [`bayer-int/smart-azure-vm-terraform`](https://github.com/bayer-int/smart-azure-vm-terraform)                       | Deploys Linux/Windows VMs with Tanium and CrowdStrike installed        |
| API Management         | [`bayer-int/smart-azure-api-gateway-terraform`](https://github.com/bayer-int/smart-azure-api-gateway-terraform)     | Deploys Azure API Management with API documentation support            |
| Virtual Network (VNet) | [`bayer-int/smart-azure-vnet-terraform`](https://github.com/bayer-int/smart-azure-vnet-terraform)                   | Creates virtual networks and one or more subnets                       |
| Backup Service         | [`bayer-int/smart-azure-backup-terraform`](https://github.com/bayer-int/smart-azure-backup-terraform)               | Deploys Recovery Services Vault with policy-based VM backup enrollment |
| Microsoft SQL Server   | [`bayer-int/smart-azure-mssql-db-terraform`](https://github.com/bayer-int/smart-azure-mssql-db-terraform)           | Deploys and manages MSSQL databases in Azure                           |
| PostgreSQL Server      | [`bayer-int/smart-azure-postgresql-db-terraform`](https://github.com/bayer-int/smart-azure-postgresql-db-terraform) | Deploys PostgreSQL Flexible Server                                     |
| MySQL Server           | [`bayer-int/smart-azure-mysql-db-terraform`](https://github.com/bayer-int/smart-azure-mysql-db-terraform)           | Deploys MySQL Flexible Server                                          |
| Key Vault              | [`bayer-int/smart-azure-key-vault-terraform`](https://github.com/bayer-int/smart-azure-key-vault-terraform)         | Creates and manages Azure Key Vault                                    |

---

## Project Structure

* All Terraform configurations should follow a modular structure.
* Store the main infrastructure in `main.tf`.
* Use `variables.tf` for input definitions.
* Use `terraform.tfvars` for variable values (see note below for sensitive values).
* Keep the provider block in `terraform.tf`.

Example `terraform.tf`:

```hcl
provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
}
```

---

## Handling Sensitive Variables

* **Never store secrets, passwords, or sensitive data in `terraform.tfvars`, `variables.tf`, or version-controlled files.**
* Use **environment variables** instead. Terraform will automatically use variables prefixed with `TF_VAR_`.

Example:

```bash
export TF_VAR_db_password="your-secret-password"
```

Then run validation steps normally. The deployment workflow will handle applying the configuration using these values.

* For shared or long-term secrets, consider using Azure Key Vault and referencing secrets via data sources or automation scripts.

* **If a configuration includes a sensitive variable**, Copilot must:

  * Add the corresponding environment variable reference to `terraform plan` and `terraform apply` steps in all GitHub Actions workflows.
  * Display a message to the user: `❗ Please remember to add this sensitive value to your repository environment secrets.`

---

## Avoid the Following

* Do not create Azure resources manually if a Bayer-approved module exists.
* Do not hardcode module versions without checking Git tags.
* Do not include `provider` or `backend` blocks inside individual modules.
* Avoid using deprecated Azure resources.

---

## Example: Using a Module

```hcl
resource "random_id" "id" {
  byte_length = 2
}

resource "azurerm_resource_group" "rg" {
  location = var.location
  name     = "test-vnet-rg"
}

module "vnet" {
  source             = "git::https://github.com/bayer-int/smart-azure-vnet-terraform?ref=v1.1.0"
  enable_telemetry   = true
  stage              = "dev"
  name               = "test-vnet-${random_id.id.hex}"
  address_space      = ["192.168.0.0/24"]
  location           = azurerm_resource_group.rg.location
  enable_nat_gateway = true
  subnets = {
    "subnet1" = {
      name             = "subnet1"
      address_prefixes = ["192.168.0.0/28"]
    }
    "subnet2" = {
      name             = "subnet2"
      address_prefixes = ["192.168.0.16/28"]
    }
  }
  resource_group_name = azurerm_resource_group.rg.name
  tags = {
    environment = "dev"
  }
}
```
