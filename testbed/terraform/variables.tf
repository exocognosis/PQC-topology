variable "hcloud_token" {
  description = "Hetzner Cloud API token. Leave unset to use the HCLOUD_TOKEN environment variable."
  type        = string
  default     = null
  sensitive   = true
}

variable "admin_cidrs" {
  description = "CIDRs allowed to SSH to the testbed servers, e.g. [\"203.0.113.7/32\"]."
  type        = list(string)
  validation {
    condition     = length(var.admin_cidrs) > 0 && !contains(var.admin_cidrs, "0.0.0.0/0")
    error_message = "Set admin_cidrs to your own address(es); 0.0.0.0/0 is not allowed."
  }
}

variable "ssh_public_key_path" {
  description = "Public key installed on the servers."
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "name_prefix" {
  description = "Prefix for every resource name. Change it to run two testbeds side by side."
  type        = string
  default     = "pqc-topo"
}

variable "server_type" {
  description = "x86 server type (legacy client image is x86/arm, but keep x86 for parity). Check `hcloud server-type list`."
  type        = string
  default     = "cx23"
}

variable "image" {
  type    = string
  default = "ubuntu-24.04"
}

variable "location" {
  type    = string
  default = "fsn1"
}

variable "network_zone" {
  type    = string
  default = "eu-central"
}

variable "existing_ssh_key_name" {
  description = "Name of an SSH key already registered in the Hetzner project to reuse. Leave null to create a testbed key."
  type        = string
  default     = null
}
