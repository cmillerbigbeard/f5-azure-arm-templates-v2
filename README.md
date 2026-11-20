# BIG-IP HA pair on Azure: 2 NICs, no public IPs, BIG-IPs with outbound access

Deploys a two-unit BIG-IP high-availability pair with Cloud Failover Extension into an **existing** Azure virtual network. Each unit has two network interfaces (management and internal) and **no public IP address**; there is no bastion, load balancer, example application or virtual server. BYOL licensing.

**This branch assumes the BIG-IPs can reach the internet** through a route you provide (for example an Azure NAT gateway or a firewall), because at first boot they download their automation packages and activate their licence. **If your BIG-IPs have no route to the internet, use the offline branch instead: [azure-2nic-internal-offline](https://github.com/cmillerbigbeard/f5-azure-arm-templates-v2/tree/azure-2nic-internal-offline).**

**Full instructions: [deployment guide](examples/failover/README-2nic-internal.md).** It covers prerequisites, every template parameter, the portal button and the Azure CLI steps, how to check that the pair formed, and troubleshooting.

## The steps

1. **Provide outbound access from the management subnet** (not only the internal one) to `raw.githubusercontent.com`, `cdn.f5.com`, `f5-cft.s3.amazonaws.com` and `activate.f5.com` on port 443 ([guide section 4](examples/failover/README-2nic-internal.md#4-network-and-outbound-access)). At first boot the only route a unit has is the management one.
2. **Deploy the template** with the button below or the Azure CLI. Five values are required: `uniqueString`, `sshKey`, `restrictedSrcAddressMgmt`, `bigIpMgmtSubnetId` and `bigIpInternalSubnetId`. Also set the two licence keys, the admin password (or a Key Vault secret) and, because the default image needs a matching Declarative Onboarding version, read the note on BIG-IP versions below.
3. **Check that the pair formed** ([guide section 8](examples/failover/README-2nic-internal.md#8-checking-that-the-pair-formed)). A successful deployment does not prove it.

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fcmillerbigbeard%2Ff5-azure-arm-templates-v2%2Fno-public-ip-2nic-internal%2Fexamples%2Ffailover%2Fazuredeploy-existing-network-2nic-internal.json)

The button opens the Azure portal's custom deployment form for this template. Read the guide first.

**Cannot create roles in your subscription?** Guide section 14 covers deploying with a managed identity that someone else created beforehand.

## BIG-IP versions: read this before choosing an image

- **BIG-IP 17.5.1.11 works with the Declarative Onboarding (DO) version this branch installs by default (1.44.0).** Set `bigIpImage` to `f5-networks:f5-big-ip-byol:f5-big-all-2slot-byol:17.5.111000`.
- **Update (being verified):** the BYOL configuration files on this branch now give the BIG-IP's management software more memory (`provision.extramb` 3000 instead of 1000). With that change, BIG-IP 21.1 with the default DO 1.44.0 on the default 32 GB size passed in 2 of 2 test runs (x3, x4); the committed files themselves have not yet been deployed, and that check is in progress. Before this change:
- **BIG-IP 21.1 on the template's default size (`Standard_D8s_v5`, 32 GB) failed to onboard with the default Declarative Onboarding (DO) 1.44.0 in all 5 of the author's runs.** It worked in 3 of 3 runs with DO 1.49.0 on that size, and in 3 of 3 runs with DO 1.44.0 on a 64 GB size (`Standard_D16s_v5`). So for 21.1, **either use a 64 GB size** (set `bigIpInstanceType` to `Standard_D16s_v5`) **or install DO 1.49.0.** The template's default `bigIpImage` is `21.1.004000`; to avoid the problem altogether, use a 17.5 image, which works with the default DO 1.44.0 on the default size. DO 1.49.0 is not on GitHub or the public F5 download site, so **this branch does not install it by default**: download it from F5's downloads site (an F5 login is needed), host it where the BIG-IP's management subnet can fetch it, and use the two ready-made configuration files [instance 01](examples/failover/bigip-configurations/runtime-init-conf-2nic-byol-instance01-do149.yaml) and [instance 02](examples/failover/bigip-configurations/runtime-init-conf-2nic-byol-instance02-do149.yaml) (host them too, with `<INTERNAL-HOST>` replaced), giving their URLs to `bigIpRuntimeInitConfig01` and `bigIpRuntimeInitConfig02` ([guide section 5.1](examples/failover/README-2nic-internal.md#51-using-big-ip-211-install-declarative-onboarding-1490)). The cause was not established; the failures were the BIG-IP's own management services timing out while very little host memory was available (guide section 11).

## What has and has not been tested

This was built and tested by one person in a lab, not by F5. Treat it as a reference, and run your own tests.

- **Tested:** standard deployments with outbound access (a NAT gateway) on BIG-IP 17.5.1.11, by the Azure CLI: both units onboarded, licensed and formed a pair (both devices listed, `In Sync`, one `ACTIVE` and one `STANDBY`), and Cloud Failover Extension moved an Azure address between the units on a forced failover (no traffic was sent to it).
- **Tested on this branch's current template (BIG-IP 21.1.0.4, NAT on both subnets):** DO 1.49.0 on `Standard_D8s_v5` formed a pair in 3 of 3 runs; DO 1.44.0 on `Standard_D16s_v5` formed a pair in 3 of 3 runs; DO 1.44.0 on `Standard_D8s_v5` failed in 5 of 5 runs. A standard deployment on 17.5.1.11 was tested on an earlier version of the template.
- **Not verified:** clicking the Deploy to Azure button and completing the portal form, client traffic through a virtual server during a failover, VM sizes other than `Standard_D8s_v5` and `Standard_D16s_v5`, other regions, whether more host memory on a 32 GB VM (`provision.extramb`) avoids the failure, and availability zones.
- **No outbound access on the management subnet stops the first boot.** The guide's section 4 lists what was tried.

The guide's sections 11 and 12 list every result and every failure in detail.

## Where this comes from

This is a personal fork derived from the `failover` solution in [F5Networks/f5-azure-arm-templates-v2](https://github.com/F5Networks/f5-azure-arm-templates-v2), reduced to two NICs, with the public IP addresses, bastion, load balancer and example application removed, and with the storage accounts created as `StorageV2`. It is not an F5 product and F5 does not support it. F5's original templates, including the 3-NIC and autoscale solutions, are in F5's repository and are not part of this branch. The guide's section "What differs from F5's template" lists every change.

---

### Copyright

Copyright 2014-2023 F5 Networks Inc.

### License

#### Apache V2.0

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this file except in compliance with the License. You may obtain a copy of the
License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations
under the License.

#### Contributor License Agreement

Individuals or business entities who contribute to this project must have
completed and submitted the F5 Contributor License Agreement.