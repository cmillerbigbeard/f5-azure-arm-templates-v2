# BIG-IP HA pair on Azure: 2 NICs (management + internal), no public IP addresses

This template deploys a two-unit BIG-IP high-availability (HA) pair with Cloud Failover Extension (CFE) into an **existing** Azure virtual network. Each unit has two network interfaces, **management** and **internal**, and the deployment creates **no public IP addresses of any kind**: none on the BIG-IPs, and no bastion host, load balancer, example application or virtual server.

It is derived from the `failover` solution template (`azuredeploy-existing-network.json`) in [F5's repository](https://github.com/F5Networks/f5-azure-arm-templates-v2), which is not included here. The section "What differs from F5's template" lists every change.

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
12. [Deploying with no internet access at all (offline variant)](#13-deploying-with-no-internet-access-at-all-offline-variant)
13. [Deploying with a pre-created managed identity](#14-deploying-with-a-pre-created-managed-identity-no-permission-to-create-roles)

## 2. Quick start

1. Make sure you have the things in section 3, especially **outbound access from the management subnet** (section 4). If you cannot allow any, see section 13.
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
| Outbound access from the **management** subnet (and the internal subnet) | Because the units have no public IP, you must provide the route out. See section 4. **This is the requirement most likely to stop a deployment.** If you cannot, see section 13. |
| BIG-IP BYOL registration keys | One per unit, two in total. See section 5. |
| An SSH public key | For the `azureuser` account on both VMs. |
| Permission to create resources, roles and role assignments | The template creates a custom role, a role assignment, a managed identity, a Key Vault, three storage accounts and the VMs. If you cannot create roles, see section 14. |
| A way to reach the units' private management addresses | A jump host, VPN or ExpressRoute. The template creates none. |
| A **new resource group** for each deployment | See section 9: two deployments cannot share a resource group. |

Required Azure resource providers (they were already registered in the author's subscription): `Microsoft.Compute`, `Microsoft.Network`, `Microsoft.Storage`, `Microsoft.KeyVault`, `Microsoft.ManagedIdentity`, `Microsoft.Authorization`.

## 4. Network and outbound access

**Why outbound access matters.** At first boot each unit downloads its onboarding configuration and automation packages and, for BYOL, activates its licence. CFE calls Azure when it moves an address. A unit with no route to the internet cannot complete the standard deployment.

**Which subnet needs the route: the management subnet.** At first boot a unit has only its management interface. The internal interface does not exist at the operating-system level until Declarative Onboarding creates it, which happens *after* the first downloads. The unit's only default route at that point is the **management** one, so **the first-boot downloads leave through the management subnet.** After onboarding, the data-plane default route points at the internal subnet and ordinary traffic leaves that way, but this does not help the first boot.

**What to provide (standard deployment):** a route to the internet from the **management subnet**, for example an Azure NAT gateway attached to it, or a firewall or proxy route that allows the hosts below. A route from the internal subnet is also needed for CFE and for traffic your applications send.

**Hosts the units contact (port 443).**

| Host | Used for | Basis |
|---|---|---|
| `raw.githubusercontent.com` | the onboarding configuration file (default; avoidable, see below) | Observed in the first-boot log |
| `cdn.f5.com` | the runtime-init installer and the DO, AS3 and CFE packages | Observed in the first-boot log |
| `f5-cft.s3.amazonaws.com` | the key that verifies the runtime-init package | Observed in the first-boot log |
| `activate.f5.com` | BYOL licence activation | Observed to answer from a unit (HTTP 301); not seen in a log |
| `management.azure.com`, `login.microsoftonline.com` | CFE moving addresses at failover | Required by CFE per F5's documentation; not observed in a log |

This list comes from logs and spot checks on one deployment, not from a packet capture, so treat it as a minimum and confirm it with your firewall logs.

**What the author tested** (BIG-IP 17.5.1.11, BYOL):

| Test | Result |
|---|---|
| NAT gateway on both subnets | *Verified.* Both units onboarded, licensed and paired. |
| NAT gateway on the **internal** subnet only, management subnet **with** Azure's default outbound access | Worked, but this result is **misleading**: the management subnet still had a route out through Azure's default outbound access, which is what the first boot used. |
| Management subnet with default outbound access **switched off** and no NAT (internal subnet with NAT) | *Verified failure.* Unit 01 retried the first download (`raw.githubusercontent.com`) for 16 minutes without success. |
| No outbound route on either subnet, standard template | *Verified failure.* The download of `cdn.f5.com` timed out, the runtime-init package was never installed and the onboarding script exited with status 127. No licence was activated. |
| No internet on either subnet, using the offline variant (section 13) | *Verified.* The pair formed. |
| Firewall or proxy route instead of NAT | *Not verified.* |

**Do not rely on Azure's "default outbound access".** Subnets with no NAT gateway or other explicit outbound method still get a shared, Microsoft-managed public IP unless the subnet's `defaultOutboundAccess` is `false`. Microsoft is retiring this default for new subnets.

**About the NAT gateway's public IP.** An Azure NAT gateway uses a public IP of its own. That address belongs to your network, not to the BIG-IPs. If nothing in your network may have a public IP, use a firewall or proxy route instead (not verified).

**Moving the default route to the internal NIC from first boot is not possible** with this template. It would require changing the first-boot script in `modules/bigip-standalone/bigip.json`, which this solution deliberately does not modify.

**If you cannot open any route to the internet,** see section 13.

## 5. Licensing

This template uses **BYOL** licensing. `bigIpImage` is a BYOL image URN, and you supply one registration key per unit in `bigIpLicenseKey01` and `bigIpLicenseKey02`. Both keys are required.

**Default image and size.** The template's default is `f5-networks:f5-big-ip-byol:f5-big-all-2slot-byol:21.1.004000` on `Standard_D8s_v5` (32 GB), chosen to match what one customer uses. BIG-IP 21.1 on that size needs more host (control-plane) memory than F5's module sets by default, so **this repository's copy of the first-boot script sets `provision.extramb` to 3000 instead of F5's 1000**. With that, 21.1 with the default Declarative Onboarding (DO) 1.44.0 passed in 4 of 4 runs on `Standard_D8s_v5`, and the 3000 setting was confirmed on all 8 units. With the original 1000 it failed in 5 of 5 runs. The trade-off is that about 2 GB moves from the traffic engine's reserved memory to the host, and the effect on traffic handling was **not tested** (the template creates no virtual server). If you want to avoid that trade-off, other options that worked in the author's tests are a 64 GB size (`Standard_D16s_v5`) or DO 1.49.0 (section 5.1). BIG-IP 17.5.1.11 also works with DO 1.44.0 on `Standard_D8s_v5`: set `bigIpImage` to `f5-networks:f5-big-ip-byol:f5-big-all-2slot-byol:17.5.111000` if you want that combination. Section 11 has the full results.

Accept the image's marketplace terms once per subscription if you have not already:

```
az vm image terms accept --publisher f5-networks --offer f5-big-ip-byol --plan f5-big-all-2slot-byol
```

To list the BYOL image versions available in your region:

```
az vm image list --publisher f5-networks --offer f5-big-ip-byol --sku f5-big-all-2slot-byol --all --query "[].version" -o tsv
```

**Automation package versions.** The versions of Declarative Onboarding, AS3 and Cloud Failover Extension installed at first boot are set in the runtime-init files in `examples/failover/bigip-configurations/` (DO 1.44.0, AS3 3.51.0, CFE 2.1.2, each with a SHA-256 hash) and are independent of the image you choose. **Those files pin DO 1.44.0, which does not work on BIG-IP 21.1.** For 21.1, follow section 5.1 (online) or the offline route in section 13: DO 1.49.0 is not on GitHub or the public F5 download site, so you host it yourself.

### 5.1 Using BIG-IP 21.1: install Declarative Onboarding 1.49.0

BIG-IP 21.1 needs Declarative Onboarding (DO) **1.49.0**. The configuration files this template loads by default install DO 1.44.0, and DO 1.49.0 is not on GitHub or cdn.f5.com, so you download it and host it yourself. In the author's test this procedure produced a working pair on BIG-IP 21.1.0.4 (both devices in `failoverGroup`, `In Sync`, one `ACTIVE` and one `STANDBY`, both licensed), with the BIG-IPs reaching the internet through NAT for AS3, Cloud Failover Extension and the licence, and DO 1.49.0 coming from a file hosted in an Azure Storage account.

1. **Download** `f5-declarative-onboarding-1.49.0-14.noarch.rpm` (2,384,335 bytes) from F5's downloads site (https://downloads.f5.com, Declarative Onboarding, version 1.49; an F5 login is needed). Check its SHA-256 is `7297eb9a79db6e8def279c9f6df40f148fe6f0d600bdd59e706dcad55d28f0aa`. That is the hash of the copy the author used; F5 does not publish one that the author could compare it against. The BIG-IP rejects a file that does not match the hash in the configuration.
2. **Host the file** at an address the BIG-IP's **management subnet** can fetch with no credentials, over HTTP or HTTPS. A UNC or file-share path will not work, because the BIG-IP uses `curl`. An Azure Storage container is one option (the author's test used one with anonymous read access); an internal web server also works.
3. **Make your own copies of the two configuration files** from `examples/failover/bigip-configurations/`: `runtime-init-conf-2nic-byol-instance01-do149.yaml` and `runtime-init-conf-2nic-byol-instance02-do149.yaml`. They are the standard BYOL files with only the Declarative Onboarding entry changed. In each, replace `<INTERNAL-HOST>` in the `extensionUrl` line with the address where you put the RPM. **Host both edited files** the same way as the RPM.
4. **Set the template parameters** `bigIpRuntimeInitConfig01` and `bigIpRuntimeInitConfig02` to the URLs of those two files, and leave the rest as for any online deployment.

What the author did not test: a deployment in which these files were hosted on an internal web server rather than an Azure Storage account, and a 21.1 deployment with the standard (unedited) files and DO 1.44.0 repeated, so the failure described in section 11 has not been reproduced a second time.

**BYOL keys are bound to a unit.** Deleting a VM does not release its key. Before you delete BYOL units, revoke the licence on each (`tmsh revoke sys license`), or the key stays bound to the deleted unit and cannot be reused.

**Licensing needs to reach F5.** Activation contacts `activate.f5.com` from the unit. A unit that cannot reach it stays unlicensed and the standard onboarding fails. If you cannot allow that, license the units by hand (section 13).

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
| `cfeStorageAccountName` | empty | Name for the CFE state storage account. If empty, the template uses `<uniqueString>stcfe`. Storage account names must be **3 to 24 characters, lower-case letters and digits only (no capitals, no hyphens)** and globally unique. **The template does not check this**, and Azure rejects a bad name only at deployment (`AccountNameInvalid`). Example of a name that is rejected: `EUSF51PRD-failover-sa`; use `eusf51prdfailoversa`. |

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
- **F5's linked modules:** `modules/access/access.json` and `modules/dag/dag.json` are F5's own files, unchanged. `modules/bigip-standalone/bigip.json` (the BIG-IP virtual machine module) has two changes: (1) an optional parameter, `bigIpRuntimeInitKeyUrl`, inserted into the runtime-init installer command so that the installer's signature key can be taken from an internal address (section 13); when it is empty the installer command is identical to F5's; and (2) its first-boot script sets `provision.extramb` to 3000 instead of F5's 1000 (section 5). The rest of the first-boot script is F5's.

## 11. What was and was not verified

**Verified** (Azure CLI, BYOL with evaluation keys, one region, no availability zones; most results on BIG-IP 17.5.1.11, and the 21.1.0.4 results are stated as such):

- Validation and deployment succeed from the branch URL, on several separate deployments.
- No public IP is attached to any BIG-IP NIC. The only public IP in the test resource groups was the NAT gateway's. No bastion, load balancer or application VM was created.
- On the standard deployments, both units reported 17.5.1.11, licensed, listing both devices, `In Sync`, one `ACTIVE` and one `STANDBY`, with the internal NIC named `internal`.
- All storage accounts created were `StorageV2`.
- **A pre-created managed identity works.** With `bigIpUserAssignManagedIdentity` and `bigIpPasswordSecretId` supplied (section 14), the deployment had no access-module step, so it did not create the custom role, role assignment or Key Vault (seen in the deployment's step list), and the pair formed. The test account was an owner, so this shows the template skips those steps; it does not prove that a restricted account is sufficient.
- CFE moves an address on failover: with a secondary IP on the active unit's internal NIC and a matching virtual address in `traffic-group-1`, a forced failover moved the IP to the other unit's internal NIC, and back on the next failover. Azure reported the move about 70 seconds after the failover was requested, but that figure is limited by how often it was checked and is not a measured outage. **No traffic was sent to the address.**
- **A standard (online) deployment on BIG-IP 21.1.0.4 formed a pair** with DO 1.49.0 (section 5.1): the template created its own role, identity and Key Vault, the units downloaded AS3 and CFE through a NAT gateway and DO 1.49.0 from a hosted file, and both were licensed, `In Sync`, one `ACTIVE` and one `STANDBY`. One runtime-init telemetry message on unit 02, "Digital asset id ... is already registered", did not affect onboarding.
- **The offline variant (section 13) formed a pair with no internet access on either subnet,** on 17.5.1.11 with DO 1.44.0, AS3 3.51.0 and CFE 2.1.2, **and on 21.1.0.4 with DO 1.49.0**, AS3 3.51.0 and CFE 2.1.2: both devices listed, `In Sync`, one `ACTIVE` and one `STANDBY`.

**Verified failures:**

- **BIG-IP 21.1.0.4 (image `21.1.004000`) with DO 1.44.0, AS3 3.51.0 and CFE 2.1.2 failed on `Standard_D8s_v5` (32 GB) in 5 of 5 runs, and passed on `Standard_D16s_v5` (64 GB) in 3 of 3 runs.** The failures were REST calls to the BIG-IP's own management services failing or timing out: a Declarative Onboarding task ending in `ECONNRESET` then `rollback failed` (3 runs), a Cloud Failover declaration timing out with `AsyncContext timeout` (2 runs), and once each an AS3 availability check returning 404 and a Cloud Failover declaration returning 400. On a failed 32 GB unit the host had about 44 to 48 MB of memory available, against about 815 to 833 MB on a passing 64 GB unit. Both had the same provisioning (LTM nominal), the same `provision.extramb` (1000) and the same restjavad heap, and the kernel killed no process on either. The BIG-IP reserved about 86% of RAM for TMM on both sizes, which leaves the management software about 5.3 GB on 32 GB and about 9.4 GB on 64 GB. Low memory is consistent with the failures but is not proven to be their cause: DO 1.49.0 passed on 32 GB with similarly low available memory. The same image worked with DO 1.49.0 on 32 GB (3 of 3 runs, one of them the offline route), so use 1.49.0 on 21.1 (section 5.1) or a 64 GB size. **What fixed it:** raising `provision.extramb` from 1000 to 3000. Each 1000 MB moves 500 two-megabyte pages (1 GB) from the traffic engine to the host. Set from the BYOL configuration files' pre-onboard step, 3000 passed in most runs, but that step can run while the BIG-IP is still provisioning and then be refused (`Cannot set db variable` and `mcpd: A previous provisioning operation is in progress`), and its failure is ignored by `|| exit 0`; in one run that left a unit at 1000 and it failed as the 1000 runs did. Setting the value in the module's first-boot script, which runs before the BIG-IP's configuration service starts, avoided that: 4 of 4 runs passed, with 3000 confirmed on all 8 units, 657 to 962 MB available, and no pre-onboard command involved. 2000 MB failed in the one run tried. A larger restjavad heap (2000 or 2400 MB, against 1384 MB) made no difference in 5 runs. The cause of the original failures was not established beyond this correlation, and p2, one run at 3000 that failed, was not examined for the timing problem.
- No outbound route on the management subnet stops the first boot (section 4).

**Not verified:**

- Clicking the Deploy to Azure button and completing the portal form.
- BIG-IP versions other than 17.5.1.11 and 21.1.0.4; other VM sizes between 32 GB and 64 GB, other 32 GB sizes, other regions; DO 1.47.0 (the newest public version) on 21.1; and the effect of the `provision.extramb` 3000 setting on traffic handling, since it moves about 2 GB from the traffic engine's reserved memory to the host.
- Other VM sizes, other regions, availability zones.
- A firewall or proxy route instead of a NAT gateway.
- Client traffic through a virtual server during a failover, and the length of any outage.
- CFE moving an address when the units cannot reach Azure (it cannot; section 13).
- Upgrading or redeploying over an existing deployment.

## 12. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `RoleAssignmentUpdateNotPermitted` | A second deployment in the same resource group (section 9). |
| `ConflictError ... already exists in deleted state` | A reused `uniqueString` (section 9). |
| `AuthorizationFailed ... roleDefinitions/write` or `roleAssignments/write` | The account deploying cannot create roles. Use a pre-created managed identity (section 14). |
| `AccountNameInvalid ... is not a valid storage account name` | `cfeStorageAccountName` has capital letters, hyphens or is over 24 characters (section 6.4). |
| `Property id 'C:/Program Files/Git/subscriptions/...' is invalid` | Git Bash rewrote a subnet ID (section 7.2). |
| `InvalidTemplate ... property 'nsg1Id' doesn't exist` or `Property id '' ... networkSecurityGroup.id is invalid` | You are using an older copy of this template. Use the current one on this branch. |
| `SecurityRuleParametersMissing` | The same: an older copy of this template. |
| Deployment succeeds but a unit lists only itself | The pair did not form (section 8). Check `bigIpInternalSelfIp01` and connectivity between the units. |
| `onboarder` extension fails with `exit status=127` and `Connection timed out` to `cdn.f5.com` | No outbound route from the **management** subnet (section 4). |
| `onboarder` extension fails with `exit status=1` and `ENOENT: no such file or directory, open '/config/cloud/runtime-init.conf'` (often followed by `Provided config file is not valid YAML`) | The BIG-IP could not download its onboarding configuration file, so `/config/cloud/runtime-init.conf` was never created. The first-boot script downloads it with a silent `curl`, retries 30 times, and then carries on, so the real error is not in the deployment message. The runtime-init package itself installed, so the unit can reach `cdn.f5.com`; the usual cause is that it cannot reach `raw.githubusercontent.com` (the default source of the configuration files), because of a firewall rule, DNS, a proxy, or TLS inspection that treats the BIG-IP differently from your other machines. Test from the unit (SSH to its management address, type `bash`): `curl -v <the configuration file address> 2>&1 \| head -5`, and read `/var/log/cloud/startup-script.log`. If `bigIpRuntimeInitConfig01` or `02` was filled in, check it is the full address of one file. To avoid the dependency, host the two configuration files inside your network and enter their addresses in those two parameters (section 13). |
| The extension fails with a Declarative Onboarding error `rollback failed` / `ECONNRESET`, or a Cloud Failover `AsyncContext timeout` | Seen on BIG-IP 21.1 with DO 1.44.0 on a 32 GB VM size (section 11). Use DO 1.49.0 (section 5.1), or a 64 GB size such as `Standard_D16s_v5`, or a 17.5 image. |
| `MissingSubscriptionRegistration` or similar | A required resource provider is not registered (section 3). |
| A licence key will not activate on a new unit | The key is still bound to a deleted unit. Revoke the licence before deleting units (section 5). |

## 13. Deploying with no internet access at all (offline variant)

**Use this only if you cannot allow the hosts in section 4.** It uses the **same template** as the rest of this guide, with extra parameters, an install-only configuration file and two scripts (in `examples/failover/offline/`). The author verified it once, on BIG-IP 17.5.1.11, with the units having no route to the internet on either subnet. It needs more manual steps than the standard deployment and has limits, listed below.

### 13.1 What changes

The standard template downloads files from the internet at first boot and licenses the units online. The offline variant instead:

1. **Takes every first-boot download from a location inside your network** that the management subnet can reach over HTTPS.
2. **Installs the automation packages only**, and applies no declaration. The units come up unlicensed.
3. **Is finished by two scripts** that license each unit by hand and then apply the declarations.

### 13.2 Files to host internally

Place these where the BIG-IP's management subnet can fetch them over **HTTP(S)**. The unit uses `curl`, so a **UNC or file-share path will not work**. An internal web server, a Nexus or Artifactory repository, or an Azure Storage account reachable only from that subnet (a service or private endpoint) all work. Use a certificate the BIG-IP trusts.

| File | Download from | SHA-256 |
|---|---|---|
| runtime-init installer `f5-bigip-runtime-init-2.0.3-1.gz.run` | https://cdn.f5.com/product/cloudsolutions/f5-bigip-runtime-init/v2.0.3/dist/f5-bigip-runtime-init-2.0.3-1.gz.run | `e38fabfee268d6b965a7c801ead7a5708e5766e349cfa6a19dd3add52018549a` |
| Declarative Onboarding `f5-declarative-onboarding-1.44.0-5.noarch.rpm` | https://github.com/F5Networks/f5-declarative-onboarding/releases/download/v1.44.0/f5-declarative-onboarding-1.44.0-5.noarch.rpm | `3b05d9bcafbcf0b5b625ff81d6bab5ad26ed90c0dd202ded51756af3598a97ec` |
| Declarative Onboarding `f5-declarative-onboarding-1.49.0-14.noarch.rpm` | F5's downloads site (software.downloads.f5.com, DO 1.49, requires an F5 login). **Use this one for BIG-IP 21.1.** It is not on GitHub or cdn.f5.com. | `7297eb9a79db6e8def279c9f6df40f148fe6f0d600bdd59e706dcad55d28f0aa` (the hash of the file as the author downloaded it) |
| AS3 `f5-appsvcs-3.51.0-5.noarch.rpm` | https://github.com/F5Networks/f5-appsvcs-extension/releases/download/v3.51.0/f5-appsvcs-3.51.0-5.noarch.rpm | `e151a9ccd0fd60c359f31839dc3a70bfcf2b46b9fedb8e1c37e67255ee482c0f` |
| Cloud Failover `f5-cloud-failover-2.1.2-2.noarch.rpm` | https://github.com/F5Networks/f5-cloud-failover-extension/releases/download/v2.1.2/f5-cloud-failover-2.1.2-2.noarch.rpm | `476d38a4d32d6474ae5435b5d448b318e638db4655edf049944f854504310839` |
| signing key `gpg.key` | https://f5-cft.s3.amazonaws.com/f5-bigip-runtime-init/gpg.key | `5e329086089056079b32f6828b2e2c6fde5dcae8bef62b1f06308af1ede7072b` |
| install-only configuration `runtime-init-installonly.yaml` | `examples/failover/bigip-configurations/runtime-init-conf-2nic-installonly.yaml` in this repository, with the three `extensionUrl` lines edited to your internal addresses (replace `<INTERNAL-HOST>`) | n/a |

The three RPM hashes are the values pinned in the template's configuration files, and the author's downloads matched them. The GitHub download links were assembled from GitHub's standard release layout; check each one before you rely on it.

### 13.3 Template parameters for the offline variant

Set these in addition to the usual ones (section 6), using your internal addresses:

| Parameter | Value |
|---|---|
| `templateBaseUrl` and `artifactLocation` | Where the template's linked modules load from. Azure itself fetches these when you deploy (this is separate from the BIG-IPs), so they must be reachable from Azure: the defaults (this branch on GitHub) work, or point them at a copy you host. The author's test used the GitHub branch. |
| `bigIpRuntimeInitPackageUrl` | the internal address of `f5-bigip-runtime-init-2.0.3-1.gz.run` |
| `bigIpRuntimeInitConfig01`, `bigIpRuntimeInitConfig02` | the internal address of the install-only configuration (the same file for both units) |
| `bigIpRuntimeInitKeyUrl` | `--key https://<internal host>/gpg.key --skip-toolchain-metadata-sync` |

**Key Vault.** Each unit reads the admin password from Key Vault at onboarding, using a Key Vault address it cannot reach over the internet in this setup. The vault must be reachable from the management subnet through a **service endpoint or private endpoint**. The author's test used a vault created beforehand (section 14), with a Key Vault service endpoint on the management subnet. A vault the template creates itself was not tested in the offline variant.

### 13.4 Finishing the deployment (stage 2)

After the deployment succeeds, the two units are installed and **unlicensed**. Run the two scripts from a machine that can reach both management addresses **over SSH** and holds the private key matching `sshKey`. A machine with no internet access is fine for these steps.

**Step 1: license each unit** with `stage2-license.py`. For each unit:

```
python3 stage2-license.py --host <management IP> --regkey <registration key> --ssh-key <private key file> --password-file <file holding the admin password> --manual
```

The script logs in with the SSH key, **sets the admin password** (a unit that has not run Declarative Onboarding has no usable admin password), reads the unit's dossier and prints it. On any computer **with internet access**, open https://activate.f5.com/license/dossier.jsp, paste the dossier, and copy the licence text it returns. Paste that text into the script, followed by a line containing only `END`. The script installs it and waits until the unit reports licensed. The BIG-IP itself never contacts F5. F5's activation page asks you to agree to the **F5 Platform Terms of Use** before it returns the licence; you read and accept them in the browser as you paste the dossier. (`--auto` does the web step itself when the machine running the script has internet access, but only if you also pass `--accept-terms`, which means **you** are agreeing to those terms. Without it the script stops and tells you to accept them yourself. The author's 17.5 test used `--manual`; the 21.1 test used `--auto`'s exchange with the terms accepted on the account holder's instruction.)

**Step 2: apply the declarations** with `stage2-apply.py`, after **both** units are licensed:

```
python3 stage2-apply.py --yaml-dir examples/failover/bigip-configurations --password-file <password file> --ssh-key <private key file> --mgmt1 <unit 1 management IP> --mgmt2 <unit 2 management IP> --self1 <unit 1 internal IP> --self2 <unit 2 internal IP> --mgmt-gw <management subnet gateway> --internal-gw <internal subnet gateway>
```

It removes the `License` class from the declarations (the units are already licensed), applies unit 1's declaration, then unit 2's (which joins the cluster), and sends each Cloud Failover declaration. It needs Python 3 and PyYAML. It reaches each unit by SSH and calls the unit's REST API on the unit's own loopback address, because a remote REST login as `admin` returned `401` on units set up this way even with the correct password; the author did not find the cause.

Then check the pair as in section 8, **using SSH to the unit** if REST login from your host fails.

### 13.5 Limits of the offline variant

- **Cloud Failover cannot move addresses.** CFE needs to reach Azure's management endpoint (`management.azure.com`). With no route out it stores its declaration and retries a refused connection. The pair forms and synchronises, but **a failover will not move any Azure address**. If you later open a route from the internal subnet to those two hosts, this may start working; the author did not test that.
- **The units log errors** for the IP reputation service (`api.bcti.brightcloud.com`). They are harmless.
- **It was verified twice:** on 17.5.1.11 with DO 1.44.0, and on 21.1.0.4 with DO 1.49.0 (both with AS3 3.51.0 and CFE 2.1.2). Other package versions have not been tried.
- **It is not a released template.** It has been run once, by its author, in a lab.
- **The standard deployment (sections 2 to 12) was last run before the offline parameter and scripts were added to this branch.** The new parameter defaults to empty and should not change the standard behaviour, but that has not been re-tested on this branch.

## 14. Deploying with a pre-created managed identity (no permission to create roles)

By default the template creates a custom role, a role assignment, a user-assigned managed identity and a Key Vault. That needs permission to **write role definitions and role assignments** (`Microsoft.Authorization/roleDefinitions/write` and `Microsoft.Authorization/roleAssignments/write`). If your account lacks them, the deployment fails with `AuthorizationFailed`, as seen from a customer deployment.

The alternative is for someone with those permissions to create four things **before** the deployment, then give the template the identity and the secret.

### 14.1 What to create beforehand

1. **A custom role** with the permissions below, assignable at the resource group that will hold the deployment (and the group that holds the identity, if different).
2. **A user-assigned managed identity.**
3. **A role assignment** giving that identity the custom role **at the resource group where the BIG-IPs will be deployed**. CFE uses it to read and change network interfaces and route tables there.
4. **A Key Vault** holding the BIG-IP `admin` password as a secret, with an **access policy** for the identity allowing `get` and `list` on secrets. The vault must be reachable from the BIG-IPs.

The custom role's permissions are exactly those the template's own access module defines:

- **Actions (29):** `*/read`, `Microsoft.Authorization/*/read`, `Microsoft.Compute/locations/*/read`, `Microsoft.Compute/virtualMachineScaleSets/*/read`, `Microsoft.Compute/virtualMachineScaleSets/networkInterfaces/read`, `Microsoft.Compute/virtualMachines/*/read`, `Microsoft.Compute/virtualMachines/extensions/*`, `Microsoft.HybridCompute/machines/extensions/write`, `Microsoft.Insights/Register/Action`, `Microsoft.Insights/alertRules/*`, `Microsoft.Insights/diagnosticSettings/*`, `Microsoft.Network/*/join/action`, `Microsoft.Network/networkInterfaces/read`, `Microsoft.Network/networkInterfaces/write`, `Microsoft.Network/publicIPAddresses/read`, `Microsoft.Network/publicIPAddresses/write`, `Microsoft.Network/routeTables/*/read`, `Microsoft.Network/routeTables/*/write`, `Microsoft.OperationalInsights/*`, `Microsoft.OperationsManagement/*`, `Microsoft.Resources/deployments/*`, `Microsoft.Resources/subscriptions/read`, `Microsoft.Resources/subscriptions/resourceGroups/deployments/*`, `Microsoft.Resources/subscriptions/resourceGroups/read`, `Microsoft.Storage/storageAccounts/blobServices/containers/read`, `Microsoft.Storage/storageAccounts/blobServices/containers/write`, `Microsoft.Storage/storageAccounts/listKeys/action`, `Microsoft.Storage/storageAccounts/read`, `Microsoft.Support/*`
- **Data actions (4):** `Microsoft.Insights/Metrics/Write`, `Microsoft.Insights/Telemetry/Write`, `Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read`, `Microsoft.Storage/storageAccounts/blobServices/containers/blobs/write`

### 14.2 Template parameters

| Parameter | Value |
|---|---|
| `bigIpUserAssignManagedIdentity` | the managed identity's full resource ID |
| `bigIpPasswordSecretId` | the secret's URL, for example `https://<vault name>.vault.azure.net/secrets/<secret name>` (the secret **ID**, not its value) |
| `bigIpPasswordSecretValue` | leave empty |

With these set, the template creates **no custom role, no role assignment and no Key Vault** (verified; section 11). It also does not read the password itself: each BIG-IP fetches it from the vault.

**What the secret is for.** The secret holds the password for the BIG-IP `admin` account. At onboarding each unit reads it from the vault and sets `admin` to that value. You enter the secret's address in `bigIpPasswordSecretId`, or the password itself in `bigIpPasswordSecretValue` (in which case the template creates a vault and stores it). Supply one of them, not both.

**The deploying account still needs** permission to create the other resources (virtual machines, network interfaces, storage accounts, network security groups, tags) in the target resource group.

