# BIG-IP HA pair on Azure: 2 NICs (management + internal), no public IP addresses

This template deploys a two-unit BIG-IP high-availability (HA) pair with Cloud Failover Extension (CFE) into an **existing** Azure virtual network. Each unit has two network interfaces, **management** and **internal**, and the deployment creates **no public IP addresses of any kind**: none on the BIG-IPs, and no bastion host, load balancer, example application or virtual server.

It is derived from F5's `failover` solution template (`azuredeploy-existing-network.json`). The section "What differs from F5's template" lists every change.

**Status of this guide.** Everything marked *Verified* was run by the author on 2026-11-18 and 2026-11-19 with the Azure CLI and the BIG-IP REST API. Everything marked *Not verified* was not run. Please read those parts before you rely on the template.

---

## 1. Contents

1. [Quick start](#2-quick-start)
2. [Prerequisites](#3-prerequisites)
3. [Network and outbound access](#4-network-and-outbound-access)
4. [Licensing](#5-licensing)
5. [Template parameters (complete reference)](#6-template-parameters-complete-reference)
6. [Deploying](#7-deploying)
7. [Checking that the pair formed](#8-checking-that-the-pair-formed)
8. [Redeploying and cleaning up](#9-redeploying-and-cleaning-up)
9. [What differs from F5's template](#10-what-differs-from-f5s-template)
10. [What was and was not verified](#11-what-was-and-was-not-verified)
11. [Troubleshooting](#12-troubleshooting)

## 2. Quick start

1. Make sure you have the things in section 3, especially **outbound access from the internal subnet**.
2. Gather the five required values: `uniqueString`, `sshKey`, `restrictedSrcAddressMgmt`, `bigIpMgmtSubnetId`, `bigIpInternalSubnetId`.
3. Deploy with the portal button or the CLI (section 7).
4. Confirm the pair formed (section 8). A successful deployment alone does not prove it.

**Deploy to Azure button** (opens the portal's custom deployment page with this template loaded):

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fcmillerbigbeard%2Ff5-azure-arm-templates-v2%2Fno-public-ip-2nic-internal%2Fexamples%2Ffailover%2Fazuredeploy-existing-network-2nic-internal.json)

*Not verified:* the author built this link and checked that the template and every file it loads resolve, but did **not** click it or complete the portal form. All deployments described here used the Azure CLI with the same template URL.

## 3. Prerequisites

| You need | Detail |
|---|---|
| An existing virtual network | With **two different subnets**: one for management and one for the internal (data) network. |
| Outbound access from the internal subnet | Because the units have no public IP, you must provide the route out. See section 4. **This is the requirement most likely to stop a deployment.** |
| BIG-IP BYOL registration keys | One per unit, two in total. See section 5. |
| An SSH public key | For the `azureuser` account on both VMs. |
| Permission to create resources, roles and role assignments | The template creates a custom role, a role assignment, a managed identity, a Key Vault, three storage accounts and the VMs. |
| A way to reach the units' private management addresses | A jump host, VPN or ExpressRoute. The template creates none. |
| A **new resource group** for each deployment | See section 9: two deployments cannot share a resource group. |

Required Azure resource providers (they were already registered in the author's subscription): `Microsoft.Compute`, `Microsoft.Network`, `Microsoft.Storage`, `Microsoft.KeyVault`, `Microsoft.ManagedIdentity`, `Microsoft.Authorization`.

## 4. Network and outbound access

**Why outbound access matters.** The BIG-IP's default route leaves through the **internal** NIC. At first boot each unit downloads its automation packages and, for BYOL, activates its licence. CFE calls Azure APIs when it needs to move an address. A unit that cannot reach the internet cannot onboard.

**What to provide:** a route to the internet from the **internal subnet**, for example an Azure NAT gateway attached to that subnet, or a firewall or proxy route.

**What the author tested** (all with 17.5.1.11, BYOL):

| Test | Result |
|---|---|
| NAT gateway on both subnets | *Verified.* Both units onboarded, licensed and paired. |
| NAT gateway on the internal subnet only (management subnet had Azure's default outbound access, no NAT) | *Verified.* Both units onboarded, licensed and paired (deployment `twonic6`). |
| Both subnets with default outbound access **switched off** and no NAT | See section 11. The result is recorded there. |
| Firewall or proxy route instead of NAT | *Not verified.* |

**About the NAT gateway's public IP.** An Azure NAT gateway uses a public IP address of its own. That address belongs to your network, not to the BIG-IPs. If your requirement is that nothing in the VNet has a public IP, use a firewall or proxy route instead (not verified).

**Azure's "default outbound access".** Subnets that have no NAT gateway or other explicit outbound method still get Azure's default outbound access (a shared, Microsoft-managed public IP) unless the subnet's `defaultOutboundAccess` is set to `false`. Microsoft has announced that this default is being retired for new subnets, so do not rely on it.

## 5. Licensing

This template uses **BYOL** licensing. `bigIpImage` is a BYOL image URN (the default is `f5-networks:f5-big-ip-byol:f5-big-all-2slot-byol:21.1.004000`), and you supply one registration key per unit in `bigIpLicenseKey01` and `bigIpLicenseKey02`. Both keys are required.

Accept the image's marketplace terms once per subscription if you have not already:

```
az vm image terms accept --publisher f5-networks --offer f5-big-ip-byol --plan f5-big-all-2slot-byol
```

To list the BYOL image versions available in your region:

```
az vm image list --publisher f5-networks --offer f5-big-ip-byol --sku f5-big-all-2slot-byol --all --query "[].version" -o tsv
```

**BIG-IP version.** See section 11 for the BIG-IP versions that were and were not tested with this template. The version of the BIG-IP automation packages (Declarative Onboarding, AS3 and Cloud Failover Extension) installed at first boot is set in the template's runtime-init configuration files in `examples/failover/bigip-configurations/`, and is independent of the image you choose.

**BYOL keys are bound to a unit.** Deleting a VM does not release its key. Before you delete BYOL units, revoke the licence on each (`tmsh revoke sys license`), or the key stays bound to the deleted unit and cannot be reused.

## 6. Template parameters (complete reference)

The template file is `examples/failover/azuredeploy-existing-network-2nic-internal.json`. It has 28 parameters. Five are required.

### 6.1 Required (no default)

| Parameter | Type | What to enter |
|---|---|---|
| `uniqueString` | string | A short prefix used to name the resources. Some names must be globally unique, so choose something distinctive. **Use a new value for every deployment** (section 9). Lower case letters and digits work best. |
| `sshKey` | string | Your SSH **public** key (for example the contents of `id_rsa.pub`), for the `azureuser` account. |
| `restrictedSrcAddressMgmt` | string | The network allowed to reach the units' management ports (SSH 22 and HTTPS 443), in CIDR notation, for example `10.20.0.0/16`. Enter a private range such as your jump host's network. `*` allows any source; do not use that. |
| `bigIpMgmtSubnetId` | string | Full Azure resource ID of the management subnet. |
| `bigIpInternalSubnetId` | string | Full Azure resource ID of the internal (data) subnet. |

Get a subnet's resource ID:

```
az network vnet subnet show -g <vnet-resource-group> --vnet-name <vnet> -n <subnet> --query id -o tsv
```

### 6.2 Addresses (defaults almost certainly need changing)

| Parameter | Default | Notes |
|---|---|---|
| `bigIpInternalSelfIp01` | `10.0.1.11` | Unit 1's address on the internal subnet. **Must be inside `bigIpInternalSubnetId`.** Unit 2 forms the cluster by contacting this address, so it is the one value both units depend on. |
| `bigIpInternalSelfIp02` | `10.0.1.12` | Unit 2's address on the internal subnet. Must be inside the same subnet. |
| `bigIpMgmtAddress01` | `10.0.0.11` | Unit 1's management address. Must be inside `bigIpMgmtSubnetId`. |
| `bigIpMgmtAddress02` | `10.0.0.12` | Unit 2's management address. Must be inside the same subnet. |

Azure reserves the first four and the last address of every subnet, so do not use `.0` to `.3` or the broadcast address.

### 6.3 Image, size, licence and credentials

| Parameter | Default | Notes |
|---|---|---|
| `bigIpImage` | `f5-networks:f5-big-ip-byol:f5-big-all-2slot-byol:21.1.004000` | `publisher:offer:sku:version` of the BYOL marketplace image, or the resource ID of a custom image. See section 11 for which versions were tested. |
| `bigIpInstanceType` | `Standard_D8s_v5` | 8 vCPUs per unit. Choose a size your image and licence support. |
| `bigIpLicenseKey01`, `bigIpLicenseKey02` | empty | BYOL registration keys, one per unit. **Required.** |
| `bigIpPasswordSecretValue` | empty (secure string) | The `admin` password. Required if `bigIpPasswordSecretId` is empty. The template stores it in a Key Vault it creates. |
| `bigIpPasswordSecretId` | empty | Alternative to the previous one: the full URL of an existing Key Vault secret holding the password. |
| `bigIpHostname01`, `bigIpHostname02` | `failover01.local`, `failover02.local` | Hostnames, fewer than 63 characters. The pair identifies its peer through them, so keep them different. |

### 6.4 Failover (CFE)

| Parameter | Default | Notes |
|---|---|---|
| `cfeTag` | `bigip_high_availability_solution` | Value of the `f5_cloud_failover_label` tag. CFE finds the network interfaces and addresses it may move by this tag, so keep it consistent with any other resources you tag for failover. |
| `cfeStorageAccountName` | empty | Name for the CFE state storage account. If empty, the template uses `<uniqueString>stcfe`. Storage account names must be 3 to 24 lower-case letters and digits and globally unique. |

### 6.5 Placement, tags and telemetry

| Parameter | Default | Notes |
|---|---|---|
| `useAvailabilityZones` | `false` | Places the two units in different availability zones if the region supports them. *Not verified.* |
| `tagValues` | `application`, `cost`, `environment`, `group`, `owner` with placeholder values | Resource tags. Replace the placeholder values with yours. |
| `allowUsageAnalytics` | `true` | Sends anonymous usage statistics to F5. Set `false` to turn this off. |
| `bigIpUserAssignManagedIdentity` | empty | Resource ID of an existing user-assigned managed identity for the VMs. If empty, the template creates one, with a custom role and role assignment. |

### 6.6 Advanced: where the template loads its files from (usually leave alone)

| Parameter | Default | Notes |
|---|---|---|
| `templateBaseUrl` | `https://raw.githubusercontent.com/cmillerbigbeard/f5-azure-arm-templates-v2/` | Where the linked modules are fetched from. |
| `artifactLocation` | `no-public-ip-2nic-internal/examples/` | Path under the base URL. **Both defaults point at this branch of the fork**, so the template and the files it loads match. Do not change them to F5's download site: its copies still create general-purpose v1 storage and use the old interface names. |
| `bigIpRuntimeInitPackageUrl` | F5 download site, runtime-init v2.0.3 | The BIG-IP runtime-init package. |
| `bigIpRuntimeInitConfig01`, `02` | empty | Optional replacement BIG-IP onboarding configuration (a URL or an escaped JSON string). If empty, the template picks the BYOL 2-NIC configuration from this branch. |

### 6.7 Outputs

`bigIpInstance01VmId`, `bigIpInstance02VmId`, `bigIpInstance01ManagementPrivateIp`, `bigIpInstance02ManagementPrivateIp`, `bigIpInstance01ManagementPrivateUrl`, `bigIpInstance02ManagementPrivateUrl`, `bigIpSecretId`. There are no public addresses to output.

## 7. Deploying

### 7.1 Option A: the Deploy to Azure button (portal)

1. Select the button in section 2 and sign in.
2. Choose the **subscription** and a **new resource group** (section 9), and a region.
3. Fill in the five required parameters, then the addresses, image, licence keys and password from section 6.
4. Select **Review + create**, then **Create**.

### 7.2 Option B: Azure CLI

1. Sign in and choose the subscription:

   ```
   az login
   az account set --subscription "<subscription name or id>"
   ```

2. Create a new resource group:

   ```
   az group create -n <new-resource-group> -l <region>
   ```

3. Write `params.json` (a minimal BYOL example; replace every value in angle brackets):

   ```json
   {
     "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
     "contentVersion": "1.0.0.0",
     "parameters": {
       "uniqueString": { "value": "myhapair1" },
       "sshKey": { "value": "ssh-rsa AAAA... you@example" },
       "restrictedSrcAddressMgmt": { "value": "10.20.0.0/16" },
       "bigIpMgmtSubnetId": { "value": "/subscriptions/<id>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<mgmt>" },
       "bigIpInternalSubnetId": { "value": "/subscriptions/<id>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<internal>" },
       "bigIpInternalSelfIp01": { "value": "10.20.1.11" },
       "bigIpInternalSelfIp02": { "value": "10.20.1.12" },
       "bigIpMgmtAddress01": { "value": "10.20.0.11" },
       "bigIpMgmtAddress02": { "value": "10.20.0.12" },
       "bigIpImage": { "value": "f5-networks:f5-big-ip-byol:f5-big-all-2slot-byol:21.1.004000" },
       "bigIpLicenseKey01": { "value": "<registration key 1>" },
       "bigIpLicenseKey02": { "value": "<registration key 2>" },
       "bigIpPasswordSecretValue": { "value": "<admin password>" }
     }
   }
   ```

4. Validate (creates nothing):

   ```
   az deployment group validate -g <new-resource-group> --template-uri "https://raw.githubusercontent.com/cmillerbigbeard/f5-azure-arm-templates-v2/no-public-ip-2nic-internal/examples/failover/azuredeploy-existing-network-2nic-internal.json" --parameters @params.json
   ```

5. Deploy:

   ```
   az deployment group create -g <new-resource-group> -n <deployment-name> --template-uri "https://raw.githubusercontent.com/cmillerbigbeard/f5-azure-arm-templates-v2/no-public-ip-2nic-internal/examples/failover/azuredeploy-existing-network-2nic-internal.json" --parameters @params.json
   ```

   Deployment takes about 15 to 20 minutes.

**Validation does not catch every error.** During development of this template, two faults passed `validate` and failed only during deployment. Always read the result of the deployment.

**Windows and Git Bash.** Git Bash rewrites any argument that starts with `/subscriptions/...` into `C:/Program Files/Git/subscriptions/...`, which Azure rejects as an invalid resource ID. Use PowerShell, or set `MSYS_NO_PATHCONV=1`, or keep the IDs in the parameters file.

## 8. Checking that the pair formed

A successful deployment does not prove the units clustered. From a host that can reach the management addresses (the units have no public IPs), query each unit's REST API at `https://<management-ip>/mgmt/...` as `admin`:

| Check | Expected |
|---|---|
| `GET /mgmt/tm/sys/version` | the BIG-IP version of the image you deployed |
| `GET /mgmt/tm/sys/license` | a registration key present on both units |
| `GET /mgmt/tm/cm/device` | **both** devices listed (`failover01.local`, `failover02.local`) on **each** unit |
| `GET /mgmt/tm/cm/sync-status` | `In Sync` |
| `GET /mgmt/tm/cm/failover-status` | one unit `ACTIVE`, the other `STANDBY` |
| `GET /mgmt/tm/net/self` | `internal-self` on VLAN `/Common/internal` (there is no `external-self`) |
| `GET /mgmt/shared/cloud-failover/declare` | a Cloud_Failover declaration |

If a unit lists only itself, the pair did not form. Check that the units can reach each other on the internal subnet and that `bigIpInternalSelfIp01` is unit 1's real address.

**Verifying address failover.** The template creates no virtual address, so a forced failover (`tmsh run sys failover standby` on the active unit) only swaps the active unit. To see CFE move an address, add a secondary private IP to the active unit's internal NIC in Azure and create a matching virtual address in `traffic-group-1` on the BIG-IP, then force a failover and look at which NIC holds the IP.

## 9. Redeploying and cleaning up

These came from real failures and apply to anyone who deploys this template more than once.

1. **One deployment per resource group.** The template's role assignment is named from the resource group alone (`guid(resourceGroup().id, 'roleId')`, in F5's shared `modules/access/access.json`). A second deployment into the same resource group, with a different `uniqueString`, creates a new identity and fails with `RoleAssignmentUpdateNotPermitted` ("Tenant ID, application ID, principal ID, and scope are not allowed to be updated"). Use a **new resource group** for every deployment. The subnets can stay in another resource group, because you pass their full IDs. If you must reuse a group, delete the old role assignment first.
2. **A new `uniqueString` every time.** The Key Vault the template creates has purge protection, so deleting a resource group leaves the vault soft-deleted for 90 days and its name unusable (`ConflictError: A vault with the same name already exists in deleted state`). Never reuse a `uniqueString` after deleting a deployment, unless you recover the vault.
3. **Revoke BYOL licences before you delete** (section 5).
4. To delete a deployment, delete its resource group. Resources outside it (your VNet) are not affected.

## 10. What differs from F5's template

- **Two NICs only.** NIC 1 is management and NIC 2 is the data network, called **internal** everywhere: parameter names, the VLAN `internal`, the self IP `internal-self` and the runtime parameter `SELF_IP_INTERNAL`. There is no 3-NIC mode, and `numNics` is removed.
- **No public IPs, no bastion, no load balancer, no example application, no virtual server, no NAT gateway.** The parameters `provisionPublicIpMgmt`, `provisionServicePublicIp`, `restrictedSrcAddressApp` and `bigIpExternalVip01` are removed.
- **No virtual address is created.** Add your own virtual servers (for example with AS3) in the floating traffic group.
- **The peer address is derived** from `bigIpInternalSelfIp01`. F5's template has a separate `bigIpPeerAddr` that can disagree with it and silently stop the pair forming.
- **The internal NIC has a network security group with one rule** (the management source, TCP 443). Azure's default rules allow traffic inside the virtual network, which the pair uses to synchronise. Add your own rules for your applications.
- **Storage accounts are created as `StorageV2`** (general-purpose v2). Templates loaded from F5's default download site still create the retired general-purpose v1 type, which Azure no longer lets you create.
- The template's modules and BIG-IP configuration files load from **this branch**.
- The shared F5 modules are **not modified**.

## 11. What was and was not verified

**Verified** (Azure CLI, BIG-IP 17.5.1.11, BYOL with evaluation keys, one region, no availability zones):

- Validation and deployment succeed from the branch URL, on three separate deployments.
- No public IP is attached to any BIG-IP NIC. The only public IP in the test resource groups was the NAT gateway's. No bastion, load balancer or application VM was created.
- On two deployments, both units reported 17.5.1.11, licensed, listing both devices, `In Sync`, one `ACTIVE` and one `STANDBY`, with the internal NIC named `internal`.
- All storage accounts created were `StorageV2`.
- Outbound access through a NAT gateway on the internal subnet is sufficient, with or without NAT on the management subnet.
- CFE moves an address on failover: with a secondary IP on the active unit's internal NIC and a matching virtual address in `traffic-group-1`, a forced failover moved the IP to the other unit's internal NIC, and back on the next failover. Azure reported the move about 70 seconds after the failover was requested, but that figure is limited by how often it was checked and is not a measured outage. **No traffic was sent to the address.**

**Not verified:**

- Clicking the Deploy to Azure button and completing the portal form.
- Any BIG-IP version other than 17.5.1.11, including 21.x.
- Other VM sizes, other regions, availability zones.
- A firewall or proxy route instead of a NAT gateway.
- Client traffic through a virtual server during a failover, and the length of any outage.
- Upgrading or redeploying over an existing deployment.

## 12. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `RoleAssignmentUpdateNotPermitted` | A second deployment in the same resource group (section 9). |
| `ConflictError ... already exists in deleted state` | A reused `uniqueString` (section 9). |
| `Property id 'C:/Program Files/Git/subscriptions/...' is invalid` | Git Bash rewrote a subnet ID (section 7.2). |
| `InvalidTemplate ... property 'nsg1Id' doesn't exist` or `Property id '' ... networkSecurityGroup.id is invalid` | You are using an older copy of this template. Use the current one on this branch. |
| `SecurityRuleParametersMissing` | The same: an older copy of this template. |
| Deployment succeeds but a unit lists only itself | The pair did not form (section 8). Check `bigIpInternalSelfIp01` and connectivity between the units. |
| Units never finish onboarding | No outbound access from the internal subnet (section 4). |
| `MissingSubscriptionRegistration` or similar | A required resource provider is not registered (section 3). |
| A licence key will not activate on a new unit | The key is still bound to a deleted unit. Revoke the licence before deleting units (section 5). |
