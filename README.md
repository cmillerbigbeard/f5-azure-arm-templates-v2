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
- **BIG-IP 21.1 on the template's default size (`Standard_D8s_v5`, 32 GB) works with the default Declarative Onboarding (DO) 1.44.0, because this branch gives the BIG-IP's management software more memory.** The first-boot script in `modules/bigip-standalone/bigip.json` sets `provision.extramb` to 3000 (F5's value is 1000), which moves about 2 GB from the traffic engine's reserved memory to the host. Without that, BIG-IP 21.1 on this size failed to onboard in all 5 of the author's runs; with it, 4 of 4 runs from the same published files passed, and every one of their 8 units showed the 3000 setting applied and 657 to 962 MB of memory available (against 44 to 48 MB at 1000). Nothing needs to be downloaded or changed by you. **What this does not cover:** the effect of giving the traffic engine 2 GB less memory has not been measured (this template creates no virtual server, so no traffic was tested), and the author's runs were on one image (`21.1.004000`) in one region. If you run production traffic, check the BIG-IP's memory use under load. For a 64 GB size, or for DO 1.49.0, see [guide section 5](examples/failover/README-2nic-internal.md#5-licensing).

## What has and has not been tested

This was built and tested by one person in a lab, not by F5. Treat it as a reference, and run your own tests.

- **Tested:** standard deployments with outbound access (a NAT gateway) on BIG-IP 17.5.1.11, by the Azure CLI: both units onboarded, licensed and formed a pair (both devices listed, `In Sync`, one `ACTIVE` and one `STANDBY`), and Cloud Failover Extension moved an Azure address between the units on a forced failover (no traffic was sent to it).
- **Tested on this branch's current template (BIG-IP 21.1.0.4, NAT on both subnets):** DO 1.49.0 on `Standard_D8s_v5` formed a pair in 3 of 3 runs; DO 1.44.0 on `Standard_D16s_v5` formed a pair in 3 of 3 runs; DO 1.44.0 on `Standard_D8s_v5` failed in 5 of 5 runs with F5's original `provision.extramb` of 1000 and passed in 4 of 4 runs with the 3000 this branch sets. A standard deployment on 17.5.1.11 was tested on an earlier version of the template.
- **Not verified:** clicking the Deploy to Azure button and completing the portal form, client traffic through a virtual server during a failover, the effect of the 3000 setting on traffic handling (about 2 GB less reserved for the traffic engine), VM sizes other than `Standard_D8s_v5` and `Standard_D16s_v5`, other regions, and availability zones.
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