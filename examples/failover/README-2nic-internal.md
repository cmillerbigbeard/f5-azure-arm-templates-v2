# BIG-IP HA pair on Azure: 2 NICs (management + internal), no public IP addresses

Deploys a two-unit BIG-IP high-availability pair with Cloud Failover Extension (CFE) into an **existing** Azure virtual network, using two network interfaces per unit (management and internal) and **no public IP addresses of any kind**: none on the BIG-IPs, no bastion host, no load balancer, no example application, no virtual server.

This template is derived from F5's `failover` solution template. Read "What differs from F5's template" before relying on it.

## Deploy to Azure

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fcmillerbigbeard%2Ff5-azure-arm-templates-v2%2Fno-public-ip-2nic-internal%2Fexamples%2Ffailover%2Fazuredeploy-existing-network-2nic-internal.json)

The button opens the Azure portal's custom deployment page with this template loaded. Sign in, then follow **Option A** below.

## Before you start: what you must already have

1. **An existing virtual network with two subnets**: one for management and one for the internal (data) network. They must be different subnets.
2. **Outbound internet access from the internal subnet** (this is the part most likely to catch you out). Because the BIG-IPs have no public IPs, you must provide the route out yourself: an Azure NAT gateway attached to the internal subnet, or a firewall or proxy route. See **Outbound access (NAT)** below.
3. **A BIG-IP licence**: either BYOL registration keys (one per unit), or PAYG with the marketplace image terms accepted on your subscription. See **Licensing**.
4. An **SSH public key**, and permission to create resources in the target resource group.
5. A way to reach the BIG-IPs' private management addresses (a jump host, VPN, ExpressRoute or similar). The template deliberately creates none.

### Outbound access (NAT)

The BIG-IP's default route leaves through the **internal** NIC. At first boot each unit downloads its automation packages and, for BYOL, activates its licence, and Cloud Failover Extension calls Azure APIs afterwards. Without outbound access from the internal subnet the units cannot onboard.

- Attach a NAT gateway (or an equivalent route) to the **internal subnet**.
- The management subnet does not need to reach the internet for onboarding. The tested network below attached the NAT gateway to both subnets, so I did not test a management subnet without it.
- A NAT gateway has a public IP address of its own. That address belongs to your network, not to the BIG-IPs. If "no public IPs" for you includes the NAT gateway, use a firewall or proxy route instead. I did not test that.
- I did not test what happens with no outbound route. I expect onboarding to fail.

### Licensing

- **BYOL:** set `bigIpImage` to a BYOL image URN, and supply `bigIpLicenseKey01` and `bigIpLicenseKey02`. Tested with `f5-networks:f5-big-ip-byol:f5-big-all-2slot-byol:17.5.111000`. The units activate the licence at boot, so each key must be unused. Before deleting BYOL units, revoke the licence (`tmsh revoke sys license`) or the key stays bound to the deleted unit.
- **PAYG:** leave the licence keys empty and keep a PAYG image. The runtime-init configuration for PAYG exists in this branch, **but I did not deploy it**. You must also accept the marketplace terms for the plan once per subscription (`az vm image terms accept`).

## Parameters

Only these have no default and must be supplied:

| Parameter | What to enter |
|---|---|
| `uniqueString` | A short prefix used to name resources. Some names must be globally unique, so choose something distinctive. |
| `sshKey` | Your SSH **public** key, for the `azureuser` account. |
| `restrictedSrcAddressMgmt` | The network allowed to reach management (22 and 443), in CIDR notation. Use your jump host's or management network's private range. |
| `bigIpMgmtSubnetId` | Full Azure resource ID of the management subnet. |
| `bigIpInternalSubnetId` | Full Azure resource ID of the internal subnet. |

Everything else has a default. You will almost certainly want to change these:

| Parameter | Default | Note |
|---|---|---|
| `bigIpInternalSelfIp01` / `02` | `10.0.1.11` / `.12` | **Must be inside the internal subnet.** The second unit clusters to the first using `bigIpInternalSelfIp01`, so there is only one value to get right. |
| `bigIpMgmtAddress01` / `02` | `10.0.0.11` / `.12` | Must be inside the management subnet. |
| `bigIpImage` | PAYG image | Set a BYOL image for BYOL. |
| `bigIpInstanceType` | `Standard_D8s_v4` | 8 vCPUs per unit. |
| `bigIpLicenseKey01` / `02` | empty | BYOL only. |
| `bigIpPasswordSecretValue` | empty | Admin password. If empty, supply `bigIpPasswordSecretId` for an existing Key Vault secret. Do not use a password you care about in a shared parameters file. |

To get a subnet's resource ID:

```
az network vnet subnet show -g <resource-group> --vnet-name <vnet> -n <subnet> --query id -o tsv
```

## Option A: the Deploy to Azure button (portal)

1. Select the **Deploy to Azure** button above and sign in.
2. Choose the **subscription** and **resource group** (an existing one containing, or in the same region as, your network).
3. Fill in the five required parameters and any defaults you need to change (especially the self IPs and the image).
4. Review and create.

I built and checked the button's link, and the deployment it loads, but I could not click through the portal form myself. Everything in this guide was run with the Azure CLI against the same template URL.

## Option B: manual (Azure CLI)

Use the template from this branch directly.

1. Log in and select the subscription:

   ```
   az login
   az account set --subscription "<subscription name or id>"
   ```

2. Write a parameters file, `params.json`. A minimal BYOL example:

   ```json
   {
     "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
     "contentVersion": "1.0.0.0",
     "parameters": {
       "uniqueString": { "value": "myhapair" },
       "sshKey": { "value": "ssh-rsa AAAA... you@example" },
       "restrictedSrcAddressMgmt": { "value": "10.20.0.0/16" },
       "bigIpMgmtSubnetId": { "value": "/subscriptions/<id>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<mgmt>" },
       "bigIpInternalSubnetId": { "value": "/subscriptions/<id>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<internal>" },
       "bigIpInternalSelfIp01": { "value": "10.20.1.11" },
       "bigIpInternalSelfIp02": { "value": "10.20.1.12" },
       "bigIpMgmtAddress01": { "value": "10.20.0.11" },
       "bigIpMgmtAddress02": { "value": "10.20.0.12" },
       "bigIpImage": { "value": "f5-networks:f5-big-ip-byol:f5-big-all-2slot-byol:17.5.111000" },
       "bigIpLicenseKey01": { "value": "<registration key 1>" },
       "bigIpLicenseKey02": { "value": "<registration key 2>" },
       "bigIpPasswordSecretValue": { "value": "<admin password>" }
     }
   }
   ```

3. Validate, which creates nothing:

   ```
   az deployment group validate -g <resource-group> --template-uri "https://raw.githubusercontent.com/cmillerbigbeard/f5-azure-arm-templates-v2/no-public-ip-2nic-internal/examples/failover/azuredeploy-existing-network-2nic-internal.json" --parameters @params.json
   ```

4. Deploy:

   ```
   az deployment group create -g <resource-group> -n <deployment-name> --template-uri "https://raw.githubusercontent.com/cmillerbigbeard/f5-azure-arm-templates-v2/no-public-ip-2nic-internal/examples/failover/azuredeploy-existing-network-2nic-internal.json" --parameters @params.json
   ```

Validation does **not** catch every error. Two real faults in this template's development passed validation and failed only during deployment, so run the deployment and read its result.

**Windows and Git Bash:** Git Bash rewrites any argument that begins with `/subscriptions/...` into `C:/Program Files/Git/subscriptions/...`, which Azure then rejects as an invalid resource ID. Run the commands from PowerShell, or set `MSYS_NO_PATHCONV=1`, or put the IDs in the parameters file.

## Check that it worked

A successful deployment does not by itself prove the pair formed. Check from a host that can reach the management addresses (the BIG-IPs have no public IPs). For each unit, query its REST API (`https://<management-ip>/mgmt/...`, user `admin`) and confirm:

| Check | Expected |
|---|---|
| `GET /mgmt/tm/sys/version` | 17.5.1.x |
| licence | present on both units |
| `GET /mgmt/tm/cm/device` | **both** devices listed (`failover01.local` and `failover02.local`) on **each** unit |
| `GET /mgmt/tm/cm/sync-status` | `In Sync` |
| `GET /mgmt/tm/cm/failover-status` | one unit `ACTIVE`, the other `STANDBY` |
| `GET /mgmt/tm/net/self` | `internal-self` on VLAN `/Common/internal` (there is no `external-self`) |

If a unit lists only itself, the pair did not form. Check that both units can reach each other on the internal subnet and that `bigIpInternalSelfIp01` is the first unit's real address.

## What differs from F5's template

- **Two NICs only.** NIC 1 is management, NIC 2 is the data network, named **internal** everywhere (parameters, VLAN `internal`, self IP `internal-self`, runtime parameter `SELF_IP_INTERNAL`). There is no 3-NIC mode.
- **No public IPs, no bastion, no load balancer, no example application, no virtual server, no NAT gateway.**
- **No virtual address is created.** Add your own virtual servers (for example with AS3) in the floating traffic group.
- **The peer address is derived** from `bigIpInternalSelfIp01`. F5's template has a separate `bigIpPeerAddr` that can disagree with it and silently stop the pair forming.
- **The data NIC gets a network security group with one rule** (the management source, TCP 443). Azure's default rules allow traffic inside the virtual network, which is what the pair uses to sync. Add your own rules for your applications.
- **Storage accounts are created as `StorageV2`** (general-purpose v2). Templates fetched from F5's default download site still create the retired general-purpose v1 type.
- The template's modules and BIG-IP configuration files are fetched from **this branch** (`templateBaseUrl` and `artifactLocation` default to it).

## What was and was not verified

Verified, on one deployment into the network described below (2026-11-18), using the Azure CLI:

- Validation passes and the deployment succeeds from the branch URL.
- No public IP is attached to any BIG-IP NIC, and none exists in the resource group except the NAT gateway's. No bastion, load balancer or application VM was created.
- Both units reported 17.5.1.11, licensed (BYOL), see each other, are `In Sync`, one `ACTIVE` and one `STANDBY`, with the data NIC named `internal`.
- All three storage accounts were `StorageV2`.

**Not verified:**

- Clicking the button and completing the portal form. The manual path was run with the CLI, not the portal's custom-template page.
- PAYG deployments, other VM sizes or regions, availability zones, and a second deployment (the pair has formed on one run, and in other tests of F5's 3-NIC template, but one run is not a guarantee).
- That CFE moves addresses on failover. With no virtual address on the box it has nothing to move, so a forced failover here only swaps the active unit.
- Management access without a jump host, and a NAT-less or firewall-only outbound route.

The tested network: a virtual network `10.20.0.0/16` with a management subnet `10.20.0.0/24` and an internal subnet `10.20.1.0/24`, both attached to one NAT gateway, plus a small jump VM with no public IP in the management subnet, used to query the BIG-IPs.

## Known issues in this template

- The unused 3-NIC and "with-app" runtime-init files in `bigip-configurations` are left from the source template and are not used by this one.
- The DAG module still uses `external*` parameter names internally. They are not inputs to this template and do not appear on the BIG-IP.
