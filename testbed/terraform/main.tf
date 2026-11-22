# PQC topology testbed on Hetzner Cloud.
#
# Creates ONLY its own resources, all named "${var.name_prefix}-*" and labelled
# testbed=pqc-topology: one private network, two firewalls, one SSH key and six
# servers. It never reads or modifies other servers in the project. For full
# isolation from other workloads, use a dedicated Hetzner Cloud project and a
# token scoped to it.

terraform {
  required_version = ">= 1.5"
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.49"
    }
  }
}

provider "hcloud" {
  # Leave null to read HCLOUD_TOKEN from the environment.
  token = var.hcloud_token
}

locals {
  labels = { testbed = "pqc-topology" }
  estate = {
    gw   = "10.42.1.10"
    lb   = "10.42.1.11"
    appa = "10.42.1.12"
    data = "10.42.1.13"
    appb = "10.42.1.14"
  }
  client_private_ip = "10.42.1.30" # probe vantage point; client traffic uses gw's public IP
  hosts_block       = join("\n", [for name, ip in local.estate : "${ip} ${name}"])
}

# Either create a testbed SSH key, or reuse one already registered in the
# project (Hetzner may refuse to register the same public key twice).
resource "hcloud_ssh_key" "admin" {
  count      = var.existing_ssh_key_name == null ? 1 : 0
  name       = "${var.name_prefix}-admin"
  public_key = file(pathexpand(var.ssh_public_key_path))
  labels     = local.labels
}

data "hcloud_ssh_key" "existing" {
  count = var.existing_ssh_key_name == null ? 0 : 1
  name  = var.existing_ssh_key_name
}

locals {
  ssh_key_id = var.existing_ssh_key_name == null ? hcloud_ssh_key.admin[0].id : data.hcloud_ssh_key.existing[0].id
}

resource "hcloud_network" "estate" {
  name     = "${var.name_prefix}-estate"
  ip_range = "10.42.0.0/16"
  labels   = local.labels
}

resource "hcloud_network_subnet" "estate" {
  network_id   = hcloud_network.estate.id
  type         = "cloud"
  network_zone = var.network_zone
  ip_range     = "10.42.1.0/24"
}

resource "hcloud_firewall" "admin_ssh" {
  name   = "${var.name_prefix}-admin-ssh"
  labels = local.labels
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = var.admin_cidrs
  }
}

# Public HTTPS on the gateway, reachable only from the client server.
resource "hcloud_firewall" "gw_https" {
  name   = "${var.name_prefix}-gw-https"
  labels = local.labels
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["${hcloud_server.client.ipv4_address}/32"]
  }
}

resource "hcloud_server" "client" {
  name         = "${var.name_prefix}-client"
  server_type  = var.server_type
  image        = var.image
  location     = var.location
  ssh_keys     = [local.ssh_key_id]
  firewall_ids = [hcloud_firewall.admin_ssh.id]
  labels       = merge(local.labels, { role = "client" })
  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    hosts_block = "" # client resolves gw to its PUBLIC address via the compose file
  })
  network {
    network_id = hcloud_network.estate.id
    ip         = local.client_private_ip
  }
  # IPv4 only: each primary IP counts against the project limit, and the testbed does not use IPv6.
  public_net {
    ipv4_enabled = true
    ipv6_enabled = false
  }
  depends_on = [hcloud_network_subnet.estate]
}

resource "hcloud_server" "estate" {
  for_each    = local.estate
  name        = "${var.name_prefix}-${each.key}"
  server_type = var.server_type
  image       = var.image
  location    = var.location
  ssh_keys    = [local.ssh_key_id]
  firewall_ids = each.key == "gw" ? [hcloud_firewall.admin_ssh.id, hcloud_firewall.gw_https.id] : [
    hcloud_firewall.admin_ssh.id
  ]
  labels    = merge(local.labels, { role = each.key })
  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", { hosts_block = local.hosts_block })
  network {
    network_id = hcloud_network.estate.id
    ip         = each.value
  }
  public_net {
    ipv4_enabled = true
    ipv6_enabled = false
  }
  depends_on = [hcloud_network_subnet.estate]
}
