output "hosts" {
  description = "Public and private addresses per role."
  value = merge(
    { for k, s in hcloud_server.estate : k => { public = s.ipv4_address, private = local.estate[k] } },
    { client = { public = hcloud_server.client.ipv4_address, private = local.client_private_ip } }
  )
}
