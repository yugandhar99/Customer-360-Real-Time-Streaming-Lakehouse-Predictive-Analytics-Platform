terraform {
  required_version = ">= 1.5.0"

  # State stays on the operator machine until a remote backend is chosen.
  # Do not commit terraform.tfstate. It is ignored by git.

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}
